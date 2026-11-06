#!/usr/bin/env python3
"""Authenticated browser playback of the container's virtual PulseAudio sink."""
import argparse
import base64
import binascii
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading

ITERATIONS = 200_000


def prepare_auth(password_path, output_path, username):
    password = Path(password_path).read_text().rstrip('\n')
    if not password or not username or ':' in username:
        raise ValueError('Audio requires a username and nonempty VNC password')
    salt = secrets.token_bytes(16)
    record = {'username': username, 'salt': salt.hex(),
              'digest': hashlib.pbkdf2_hmac('sha256', password.encode(), salt, ITERATIONS).hex()}
    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(record, stream)


def authorized(header, record):
    try:
        scheme, value = header.split(' ', 1)
        if scheme.lower() != 'basic':
            return False
        username, password = base64.b64decode(value, validate=True).decode().split(':', 1)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(record['salt']), ITERATIONS)
        return (hmac.compare_digest(username.encode(), record['username'].encode())
                and hmac.compare_digest(digest, bytes.fromhex(record['digest'])))
    except (ValueError, UnicodeError, binascii.Error):
        return False


def encoder_command(source, pcm=False):
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-f', 'pulse', '-fragment_size', '4096', '-i', source,
            '-ac', '2', '-ar', '48000']
    if pcm:
        return command + ['-c:a', 'pcm_s16le', '-flush_packets', '1', '-f', 's16le', 'pipe:1']
    return command + ['-c:a', 'libmp3lame', '-b:a', '128k', '-flush_packets', '1',
                      '-write_xing', '0', '-f', 'mp3', 'pipe:1']


class AudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, record, page, source):
        super().__init__(address, AudioHandler)
        self.record, self.page, self.source = record, page, source
        self.listeners = threading.BoundedSemaphore(2)
        self.requests = threading.BoundedSemaphore(16)

    def process_request(self, request, client_address):
        if not self.requests.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.requests.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.requests.release()


class AudioHandler(BaseHTTPRequestHandler):
    server_version = 'DeskHarborAudio'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, fmt, *args):
        # Never log Authorization, passwords or arbitrary URL query strings.
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy',
                         "default-src 'none'; script-src 'self'; style-src 'self'; "
                         "media-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        super().end_headers()

    def reply(self, status, content=b'', content_type='text/plain; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(content)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        # Do not let other sites embed the workstation's audio with cached credentials.
        if self.headers.get('Sec-Fetch-Site', '') not in ('', 'none', 'same-origin'):
            self.reply(403, b'Open the audio page directly.')
            return
        if not authorized(self.headers.get('Authorization', ''), self.server.record):
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="DeskHarbor workstation audio", charset="UTF-8"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        route = self.path.split('?', 1)[0]
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/audio.js': ('audio.js', 'text/javascript; charset=utf-8'),
                  '/audio.css': ('audio.css', 'text/css; charset=utf-8')}
        if route in assets:
            filename, mime = assets[route]
            self.reply(200, (self.server.page / filename).read_bytes(), mime)
        elif route == '/health':
            try:
                result = subprocess.run(['pactl', 'list', 'short', 'sources'],
                                        capture_output=True, timeout=3)
                ready = result.returncode == 0 and any(
                    line.split()[1:2] == [self.server.source.encode()]
                    for line in result.stdout.splitlines())
            except (OSError, subprocess.TimeoutExpired):
                ready = False
            self.reply(200 if ready else 503, b'Audio ready\n' if ready else b'Audio unavailable\n')
        elif route in ('/stream.mp3', '/stream.pcm'):
            pcm = route.endswith('.pcm')
            if self.command == 'HEAD':
                self.reply(200, content_type='application/octet-stream' if pcm else 'audio/mpeg')
            else:
                self.stream_audio(pcm)
        else:
            self.reply(404, b'Not found')

    def stream_audio(self, pcm=False):
        if not self.server.listeners.acquire(blocking=False):
            self.reply(503, b'Too many listeners. Stop audio on the previous client and retry.')
            return
        encoder = None
        try:
            encoder = subprocess.Popen(encoder_command(self.server.source, pcm), stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL)
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream' if pcm else 'audio/mpeg')
            self.send_header('Accept-Ranges', 'none')
            self.send_header('Connection', 'close')
            self.end_headers()
            while True:
                chunk = encoder.stdout.read1(2048)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionError, TimeoutError):
            pass
        finally:
            if encoder is not None:
                encoder.terminate()
                try:
                    encoder.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    encoder.kill()
                    encoder.wait()
                encoder.stdout.close()
            self.server.listeners.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-auth', nargs=3, metavar=('PASSWORD_FILE', 'OUTPUT', 'USERNAME'))
    parser.add_argument('--auth-file')
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=6081)
    parser.add_argument('--source', default='workstation.monitor')
    parser.add_argument('--page-dir', type=Path, default=Path('/etc/workstation/audio'))
    args = parser.parse_args()
    if args.prepare_auth:
        prepare_auth(*args.prepare_auth)
        return
    if not args.auth_file:
        parser.error('--auth-file is required')
    record = json.loads(Path(args.auth_file).read_text())
    with AudioServer((args.bind, args.port), record, args.page_dir, args.source) as server:
        server.serve_forever()


if __name__ == '__main__':
    main()
