"""Workstation-side CLI; the host helper owns project and runtime policy."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import socketserver
import threading


def connection(config, command, tty=False):
    host, user = config['host'], config['user']
    if not re.fullmatch(r'[A-Za-z0-9.:-]+', host) or host.startswith('-'):
        raise ValueError('Invalid host')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', user):
        raise ValueError('Invalid SSH user')
    port = config.get('port', 22)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid SSH port')
    return ['ssh', '-tt' if tty else '-T', '-o', 'IdentitiesOnly=yes',
            '-o', 'ClearAllForwardings=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
            '-o', 'UserKnownHostsFile=' + str(Path(config['known_hosts']).expanduser()),
            '-i', str(Path(config['identity_file']).expanduser()),
            '-p', str(port), user + '@' + host, command]


def encode(request):
    payload = base64.urlsafe_b64encode(json.dumps(request, separators=(',', ':')).encode()).decode()
    return 'deskharbor-sandbox-v1 ' + payload


def main():
    parser = argparse.ArgumentParser(description='Launch a registered project sandbox from the workstation.')
    parser.add_argument('--gpu', action='store_true')
    parser.add_argument('--reset', action='store_true', help='Delete this project sandbox home, never the project')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--publish', type=int, action='append', default=[],
                        help='Forward a guest port to workstation localhost while the agent runs')
    parser.add_argument('--forward', type=int, action='append', default=[],
                        help='Forward a guest port from an existing session until Ctrl+C')
    parser.add_argument('agent', nargs='?', choices=('codex', 'agy', 'shell'))
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    configfile = Path.home() / '.config/deskharbor-sandbox/client.json'
    try:
        config = json.loads(configfile.read_text())
        listing = {'version': 1, 'action': 'list'}
        result = subprocess.run(connection(config, encode(listing)), capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        projects = json.loads(result.stdout)['projects']
        if args.list:
            for name, project in projects.items():
                print(name + '\t' + project['workstation_path'])
            return
        cwd = Path.cwd().resolve()
        matching = [(name, p) for name, p in projects.items()
                    if cwd == Path(p['workstation_path'])]
        if len(matching) != 1:
            raise ValueError('Run from the root of one registered project. Use --list to see roots.')
        if not args.reset and not args.agent and not args.forward:
            parser.error('Choose codex, agy or shell')
        if args.reset and input('Delete this project sandbox login/tool home? Type RESET: ') != 'RESET':
            raise ValueError('Reset cancelled')
        request = {'version': 1, 'action': 'reset' if args.reset else 'run',
                   'project': matching[0][0], 'agent': args.agent,
                   'args': args.args, 'gpu': args.gpu}
        if args.forward and (args.agent or args.reset or args.publish):
            raise ValueError('--forward is a separate connection; do not combine it with an agent, reset or publish')
        if args.reset and args.publish:
            raise ValueError('Do not combine reset with publish')
        servers = []
        try:
            for port in args.publish + args.forward:
                if not 1024 <= port <= 65535:
                    raise ValueError('Forward ports must be between 1024 and 65535')
                server = preview_server(config, request['project'], port)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                servers.append(server)
                print(f'Guest port {port} forwarded to workstation http://localhost:{port}', file=sys.stderr)
            if args.forward:
                print('Keep this terminal open for the forwarding connection.', file=sys.stderr)
                threading.Event().wait()
            else:
                sys.exit(subprocess.call(connection(config, encode(request), sys.stdin.isatty())))
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(f'deskharbor-sandbox: {exc}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


def preview_server(config, project, port):
    # Each connection uses a forced-command SSH pipe, not unrestricted SSH -L.
    class Forward(socketserver.BaseRequestHandler):
        def handle(self):
            from selectors import DefaultSelector, EVENT_READ
            command = encode({'version': 1, 'action': 'preview', 'project': project, 'port': port})
            process = subprocess.Popen(connection(config, command), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE)
            try:
                with DefaultSelector() as selector:
                    selector.register(self.request, EVENT_READ)
                    selector.register(process.stdout, EVENT_READ)
                    while events := selector.select(300):
                        for key, _ in events:
                            if key.fileobj is self.request:
                                data = self.request.recv(65536)
                                if not data:
                                    process.stdin.close()
                                    selector.unregister(self.request)
                                    continue
                                process.stdin.write(data)
                                process.stdin.flush()
                            else:
                                data = os.read(process.stdout.fileno(), 65536)
                                if not data:
                                    return
                                self.request.sendall(data)
            except OSError:
                pass
            finally:
                process.terminate()
                try:
                    process.wait(5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True
        slots = threading.BoundedSemaphore(32)
        def process_request(self, request, client_address):
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except BaseException:
                self.slots.release()
                raise
        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.slots.release()
    return Server(('127.0.0.1', port), Forward)


if __name__ == '__main__':
    main()
