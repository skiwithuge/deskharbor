#!/usr/bin/env python3
"""Image entrypoint: start the constrained proxy relay, then the selected CLI."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

AGENTS = {
    'codex': ['codex', '--sandbox', 'danger-full-access', '--ask-for-approval', 'on-request'],
    'agy': ['agy', '--sandbox=false'],
    'shell': ['bash', '--noprofile', '--norc'],
}

if os.getuid() == 0 or len(sys.argv) < 2 or sys.argv[1] not in AGENTS:
    raise SystemExit('Run as the non-root sandbox user; choose codex, agy or shell.')
if not Path('/run/deskharbor-proxy/proxy.sock').is_socket():
    raise SystemExit('Host-controlled proxy socket is missing; refusing to start.')

home = Path('/home/sandbox')
for relative in ('.local/bin', '.local/npm', '.cache', '.config', '.codex', '.gemini'):
    (home / relative).mkdir(parents=True, exist_ok=True)

env = os.environ.copy()
env.update(HOME=str(home), CODEX_HOME=str(home / '.codex'),
           BASH_ENV='', ENV='', DISPLAY='', XDG_RUNTIME_DIR='/tmp/runtime-sandbox',
           PYTHONPATH='/opt/deskharbor-sandbox',
           HTTP_PROXY='http://127.0.0.1:18080', HTTPS_PROXY='http://127.0.0.1:18080',
           http_proxy='http://127.0.0.1:18080', https_proxy='http://127.0.0.1:18080',
           ALL_PROXY='http://127.0.0.1:18080', all_proxy='http://127.0.0.1:18080',
           NO_PROXY='localhost,127.0.0.1,::1', no_proxy='localhost,127.0.0.1,::1',
           NODE_USE_ENV_PROXY='1', npm_config_prefix=str(home / '.local/npm'),
           PIP_CACHE_DIR=str(home / '.cache/pip'), UV_LINK_MODE='copy',
           PATH=f'{home}/.local/bin:{home}/.local/npm/bin:/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin')
os.makedirs(env['XDG_RUNTIME_DIR'], mode=0o700, exist_ok=True)
relay = subprocess.Popen([sys.executable, '-m', 'deskharbor_sandbox.relay'], env=env)
if not Path('/run/deskharbor-preview').is_dir():
    raise SystemExit('Preview gateway directory is missing.')
preview = subprocess.Popen([sys.executable, '-m', 'deskharbor_sandbox.preview'], env=env)
for _ in range(100):
    if relay.poll() is not None or preview.poll() is not None:
        raise SystemExit('Proxy relay failed; refusing to start.')
    try:
        with socket.create_connection(('127.0.0.1', 18080), timeout=.1):
            if Path('/run/deskharbor-preview/gateway.sock').is_socket():
                break
            time.sleep(.05)
    except OSError:
        time.sleep(.05)
else:
    raise SystemExit('Proxy relay did not become ready.')
os.chdir('/project')
os.execvpe(AGENTS[sys.argv[1]][0], AGENTS[sys.argv[1]] + sys.argv[2:], env)
