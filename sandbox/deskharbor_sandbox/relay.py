"""In-container loopback TCP to a host-controlled Unix proxy socket."""
import socket
import socketserver
from deskharbor_sandbox.proxy import tunnel


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as remote:
            try:
                remote.connect('/run/deskharbor-proxy/proxy.sock')
                tunnel(self.request, remote)
            except OSError:
                pass


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    with Server(('127.0.0.1', 18080), Relay) as server:
        server.serve_forever()
