"""Check the browser WebSocket path through authenticated RFB initialization.

Bare TCP probes count as unauthenticated attempts in TigerVNC and can blacklist
websockify's loopback address. Always finish authentication before disconnecting.
"""
import base64
import hashlib
import os
import socket
import struct
import subprocess
import sys
from pathlib import Path


def check():
    with socket.create_connection(("127.0.0.1", 6080), timeout=3) as sock:
        stream = sock.makefile("rb")

        def exact(n):
            data = stream.read(n)
            if len(data) != n:
                raise RuntimeError("connection closed")
            return data

        key = base64.b64encode(os.urandom(16))
        sock.sendall(
            b"GET /websockify HTTP/1.1\r\nHost: localhost:6080\r\n"
            b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            b"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\n"
            b"Sec-WebSocket-Key: " + key + b"\r\n\r\n"
        )
        if b" 101 " not in stream.readline(4096):
            raise RuntimeError("WebSocket upgrade failed")
        headers = {}
        for _ in range(64):
            line = stream.readline(4096)
            if line == b"\r\n":
                break
            name, value = line.split(b":", 1)
            headers[name.lower()] = value.strip()
        expected = base64.b64encode(hashlib.sha1(
            key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        ).digest())
        if headers.get(b"sec-websocket-accept") != expected:
            raise RuntimeError("invalid WebSocket upgrade")

        def send(data, opcode=2):
            mask = os.urandom(4)
            size = len(data)
            head = bytes([128 | opcode, 128 | size]) if size < 126 else (
                bytes([128 | opcode, 254]) + struct.pack(">H", size)
            )
            sock.sendall(head + mask + bytes(
                byte ^ mask[i % 4] for i, byte in enumerate(data)
            ))

        pending = bytearray()

        def read(n):
            while len(pending) < n:
                first, second = exact(2)
                size = second & 127
                if size == 126:
                    size = struct.unpack(">H", exact(2))[0]
                elif size == 127:
                    size = struct.unpack(">Q", exact(8))[0]
                if size > 1024 * 1024 or second & 128:
                    raise RuntimeError("invalid server frame")
                payload = exact(size)
                opcode = first & 15
                if opcode in (0, 2):
                    pending.extend(payload)
                elif opcode == 9:
                    send(payload, 10)
                elif opcode == 8:
                    raise RuntimeError("WebSocket closed before desktop initialization")
                else:
                    raise RuntimeError("unexpected WebSocket frame")
            result = bytes(pending[:n])
            del pending[:n]
            return result

        if read(12) != b"RFB 003.008\n":
            raise RuntimeError("VNC handshake rejected (check TigerVNC blacklist)")
        send(b"RFB 003.008\n")
        count = read(1)[0]
        if not count or 2 not in read(count):
            raise RuntimeError("VNC password authentication unavailable")
        send(b"\x02")
        challenge = read(16)
        password = Path("/run/secrets/vnc_password").read_bytes().rstrip(b"\n")[:8].ljust(8, b"\0")
        des_key = bytes(int(f"{byte:08b}"[::-1], 2) for byte in password)
        response = subprocess.check_output([
            "openssl", "enc", "-des-ecb", "-provider", "legacy", "-provider",
            "default", "-K", des_key.hex(), "-nosalt", "-nopad",
        ], input=challenge, stderr=subprocess.DEVNULL)
        send(response)
        if struct.unpack(">I", read(4))[0] != 0:
            raise RuntimeError("VNC authentication failed")
        send(b"\x01")  # Shared client: preserve existing desktop connections.
        header = read(24)
        name_size = struct.unpack(">I", header[20:])[0]
        if name_size > 1024 * 1024:
            raise RuntimeError("invalid desktop name length")
        read(name_size)
        send(struct.pack(">H", 1000), 8)


def check_direct():
    """Authenticate native-only VNC without requiring the browser proxy."""
    with socket.create_connection(("127.0.0.1", 5901), timeout=3) as sock:
        stream = sock.makefile("rb")
        def exact(size):
            value = stream.read(size)
            if len(value) != size:
                raise RuntimeError("VNC connection closed")
            return value
        if exact(12) != b"RFB 003.008\n":
            raise RuntimeError("VNC handshake rejected")
        sock.sendall(b"RFB 003.008\n")
        count = exact(1)[0]
        if not count or 2 not in exact(count):
            raise RuntimeError("VNC authentication unavailable")
        sock.sendall(b"\x02")
        challenge = exact(16)
        password = Path("/run/secrets/vnc_password").read_bytes().rstrip(b"\n")[:8].ljust(8, b"\0")
        key = bytes(int(f"{byte:08b}"[::-1], 2) for byte in password)
        response = subprocess.check_output([
            "openssl", "enc", "-des-ecb", "-provider", "legacy", "-provider", "default",
            "-K", key.hex(), "-nosalt", "-nopad"], input=challenge, stderr=subprocess.DEVNULL)
        sock.sendall(response)
        if struct.unpack(">I", exact(4))[0] != 0:
            raise RuntimeError("VNC authentication failed")
        sock.sendall(b"\x01")
        size = struct.unpack(">I", exact(24)[20:])[0]
        if size > 1024 * 1024:
            raise RuntimeError("Invalid desktop name")
        exact(size)


if __name__ == "__main__":
    try:
        check_direct() if "--direct" in sys.argv[1:] else check()
    except subprocess.CalledProcessError:
        print("Browser VNC health failed: password challenge processing failed", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # Never include subprocess commands, keys or challenge responses in logs.
        print(f"Browser VNC health failed: {error}", file=sys.stderr)
        sys.exit(1)
