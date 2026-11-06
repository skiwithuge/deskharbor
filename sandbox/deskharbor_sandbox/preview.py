"""Guest loopback gateway; host SSH requests select the guest port."""
import os
import socket
import socketserver
import struct
from deskharbor_sandbox.proxy import tunnel


class Gateway(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.settimeout(10)
            data = b''
            while len(data) < 2:
                part = self.request.recv(2 - len(data))
                if not part:
                    return
                data += part
            port = struct.unpack('!H', data)[0]
            if port < 1024:
                return
            with socket.create_connection(('127.0.0.1', port), timeout=10) as service:
                tunnel(self.request, service)
        except OSError:
            pass


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


if __name__ == '__main__':
    path = '/run/deskharbor-preview/gateway.sock'
    if os.path.lexists(path):
        os.unlink(path)
    with Server(path, Gateway) as server:
        os.chmod(path, 0o600)
        server.serve_forever()
