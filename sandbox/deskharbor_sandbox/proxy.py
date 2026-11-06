"""A bounded Unix-socket forward proxy with DNS-pinned public destinations."""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler
import ipaddress
import os
import selectors
import socket
import socketserver
import threading
from urllib.parse import urlsplit

V4_DENY = tuple(ipaddress.ip_network(p) for p in (
    '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
    '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24',
    '192.168.0.0/16', '198.18.0.0/15', '198.51.100.0/24', '203.0.113.0/24',
    '224.0.0.0/4', '240.0.0.0/4'))
V6_DENY = tuple(ipaddress.ip_network(p) for p in (
    '::/128', '::1/128', 'fc00::/7', 'fe80::/10', 'ff00::/8',
    '2001:db8::/32', '2002::/16', '2001::/32', '64:ff9b::/96', '64:ff9b:1::/48'))


def public_address(value, blocked=()):
    ip = ipaddress.ip_address(value)
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    denied = V4_DENY if ip.version == 4 else V6_DENY
    return ip.is_global and not any(ip in n for n in denied) and str(ip) not in blocked


def connect_public(host, port, blocked):
    if not 1 <= port <= 65535:
        raise ValueError('Invalid destination port')
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses or any(not public_address(a[4][0], blocked) for a in addresses):
        raise PermissionError('Private, special-use or host destination denied')
    # Connect directly to an already validated numeric address. No second DNS
    # lookup, redirects, proxy chaining or environment-dependent connection API.
    last_error = None
    for family, socktype, proto, _, address in addresses:
        sock = socket.socket(family, socktype, proto)
        sock.settimeout(30)
        try:
            sock.connect(address)
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
    raise last_error or OSError('No destination address')


def tunnel(left, right):
    with selectors.DefaultSelector() as selector:
        left.setblocking(False)
        right.setblocking(False)
        selector.register(left, selectors.EVENT_READ, right)
        selector.register(right, selectors.EVENT_READ, left)
        while True:
            events = selector.select(300)
            if not events:
                return
            for key, _ in events:
                data = key.fileobj.recv(65536)
                if not data:
                    return
                target = key.data
                target.setblocking(True)
                target.settimeout(30)
                target.sendall(data)
                target.setblocking(False)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def setup(self):
        self.request.settimeout(30)
        super().setup()
        # CONNECT bytes following headers must remain on the socket for tunnel.
        self.rfile = self.connection.makefile('rb', buffering=0)

    def log_message(self, *_):
        pass  # URLs and proxy headers may contain credentials.

    def target(self, authority):
        parsed = urlsplit('//' + authority)
        if not parsed.hostname or parsed.username or parsed.password or parsed.path:
            raise ValueError('Invalid CONNECT target')
        return parsed.hostname, parsed.port or 443

    def do_CONNECT(self):
        try:
            host, port = self.target(self.path)
            upstream = connect_public(host, port, self.server.blocked)
        except (OSError, ValueError):
            self.send_error(403, 'Destination denied or unavailable')
            return
        try:
            self.send_response(200, 'Connection established')
            self.end_headers()
            self.wfile.flush()
            tunnel(self.connection, upstream)
        except OSError:
            pass
        finally:
            upstream.close()
            self.close_connection = True

    def forward(self):
        upstream = None
        try:
            target = urlsplit(self.path)
            if target.scheme != 'http' or not target.hostname or target.username or target.password:
                raise ValueError('An absolute HTTP URL is required')
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('Chunked request bodies are unsupported')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 16 * 1024 * 1024:
                raise ValueError('Request body too large')
            body = self.rfile.read(length) if length else None
            if body is not None and len(body) != length:
                raise ValueError('Incomplete request body')
            upstream = connect_public(target.hostname, target.port or 80, self.server.blocked)
            connection = http.client.HTTPConnection(target.hostname, target.port or 80, timeout=30)
            connection.sock = upstream
            ignored = {'connection', 'proxy-connection', 'proxy-authorization',
                       'keep-alive', 'transfer-encoding', 'upgrade', 'te', 'trailer'}
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ignored}
            headers['Host'] = target.netloc
            headers['Connection'] = 'close'
            path = target.path or '/'
            if target.query:
                path += '?' + target.query
            connection.request(self.command, path, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in ignored:
                    self.send_header(key, value)
            self.send_header('Connection', 'close')
            self.end_headers()
            if self.command != 'HEAD':
                while data := response.read(65536):
                    self.wfile.write(data)
        except (OSError, ValueError, http.client.HTTPException):
            self.send_error(403, 'Destination denied or request unsupported')
        finally:
            if upstream:
                upstream.close()
            self.close_connection = True

    do_GET = do_POST = do_HEAD = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = forward


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, path, blocked):
        self.blocked = set(blocked)
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(path, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('socket')
    parser.add_argument('--block', action='append', default=[])
    args = parser.parse_args()
    with Server(args.socket, args.block) as server:
        os.chmod(args.socket, 0o600)
        server.serve_forever()


if __name__ == '__main__':
    main()
