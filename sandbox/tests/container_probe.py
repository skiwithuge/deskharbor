"""Disposable image/proxy integration. No real project or credentials mounted."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

parser = argparse.ArgumentParser()
parser.add_argument('--gpu', action='store_true')
parser.add_argument('--image', default='deskharbor-agent-sandbox:prototype')
args = parser.parse_args()
base = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='deskharbor-container-probe-') as temporary:
    stage = Path(temporary)
    project, home, proxy = stage / 'project', stage / 'home', stage / 'proxy'
    preview = stage / 'preview'
    for directory in (project, home, proxy, preview):
        directory.mkdir()
    (stage / 'outside-canary').write_text('synthetic-outside-secret')
    server = subprocess.Popen([sys.executable, '-m', 'deskharbor_sandbox.proxy', str(proxy / 'proxy.sock')],
                              env={**os.environ, 'PYTHONPATH': str(base)})
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError('Proxy exited')
            if (proxy / 'proxy.sock').exists():
                break
            time.sleep(.05)
        else:
            raise RuntimeError('Proxy startup timeout')
        command = ['docker', 'run', '--rm', '--init', '--network', 'none', '--runtime', 'runc',
                   '--user', f'{os.getuid()}:{os.getgid()}', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', '--read-only',
                   '--pids-limit', '128', '--memory', '1g', '--cpus', '2',
                   '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=256m',
                   '--tmpfs', '/run:rw,nosuid,nodev,size=16m',
                   '--mount', f'type=bind,src={project},dst=/project',
                   '--mount', f'type=bind,src={home},dst=/home/sandbox',
                   '--mount', f'type=bind,src={proxy},dst=/run/deskharbor-proxy,readonly',
                   '--mount', f'type=bind,src={preview},dst=/run/deskharbor-preview',
                   '--env', 'NVIDIA_VISIBLE_DEVICES=void', args.image, 'shell', '-c']
        if args.gpu:
            pos = command.index('--runtime')
            del command[pos:pos + 2]
            command[command.index('NVIDIA_VISIBLE_DEVICES=void')] = 'NVIDIA_VISIBLE_DEVICES=all'
            command[1:1] = []
            command[command.index(args.image):command.index(args.image)] = ['--gpus', 'all']
        script = r'''
set -eu
python3 - <<'PY'
import os, socket, urllib.request
from pathlib import Path
assert os.getuid() != 0
status = Path('/proc/self/status').read_text()
assert 'CapEff:\t0000000000000000' in status
assert 'NoNewPrivs:\t1' in status
assert not Path('/var/run/docker.sock').exists()
if os.environ.get('NVIDIA_VISIBLE_DEVICES') == 'void':
    assert not list(Path('/dev').glob('nvidia*'))
try:
    Path('/etc/deskharbor-test-write').write_text('bad')
    raise AssertionError('Root filesystem writable')
except OSError:
    pass
for address in ('192.0.2.10', '1.1.1.1'):
    try:
        socket.create_connection((address, 443), timeout=1)
        raise AssertionError('Direct network permitted')
    except OSError:
        pass
for url in ('http://127.0.0.1:22/', 'http://192.0.2.10/', 'http://169.254.169.254/'):
    try:
        # Force use of proxy, including local destinations excluded by NO_PROXY.
        connection = socket.create_connection(('127.0.0.1', 18080))
        connection.sendall(('GET ' + url + ' HTTP/1.1\r\nHost: test\r\n\r\n').encode())
        response = connection.recv(1024)
        connection.close()
        assert b'403' in response.split(b'\r\n')[0], response
    except OSError as exc:
        raise AssertionError('Proxy did not respond to private request') from exc
with urllib.request.urlopen('https://example.com', timeout=30) as response:
    assert response.status == 200
Path('/project/live-output').write_text('container-write')
Path('/home/sandbox/persistence-canary').write_text('private-home')
# Exercise the guest preview service over its pinned Unix socket.
import subprocess, struct, time
http = subprocess.Popen(['python3', '-m', 'http.server', '3099', '--bind', '127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(.3)
    with socket.socket(socket.AF_UNIX) as preview:
        preview.connect('/run/deskharbor-preview/gateway.sock')
        preview.sendall(struct.pack('!H', 3099) + b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
        assert b'200 OK' in preview.recv(4096)
finally:
    http.terminate()
    http.wait()
print('Non-root, zero caps, read-only OS, direct network denied; public HTTPS, preview gateway and private-network blocks passed.')
PY
git init -q /project
git -C /project -c user.name=Probe -c user.email=probe@example.invalid add live-output
git -C /project -c user.name=Probe -c user.email=probe@example.invalid commit -qm probe
codex --version
agy --version
'''
        if args.gpu:
            script += r"""
nvidia-smi
cat > /tmp/probe.cu <<'CUDA'
#include <cuda_runtime.h>
#include <cstdio>
__global__ void probe(int *value) { *value = 42; }
int main() {
    int *device = nullptr, result = 0;
    if (cudaMalloc(&device, sizeof(int)) != cudaSuccess) return 1;
    probe<<<1,1>>>(device);
    if (cudaDeviceSynchronize() != cudaSuccess) return 2;
    if (cudaMemcpy(&result, device, sizeof(int), cudaMemcpyDeviceToHost) != cudaSuccess) return 3;
    cudaFree(device);
    if (result != 42) return 4;
    std::puts("CUDA kernel execution passed.");
    return 0;
}
CUDA
nvcc -arch=sm_86 /tmp/probe.cu -o /tmp/cuda-probe
/tmp/cuda-probe
"""
        result = subprocess.run(command + [script], text=True, capture_output=True, timeout=90)
        print(result.stdout)
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode)
        assert (project / 'live-output').read_text() == 'container-write'
        assert (project / '.git').is_dir()
        assert (home / 'persistence-canary').read_text() == 'private-home'
        again = subprocess.run(command + ['test "$(cat "$HOME/persistence-canary")" = private-home'],
                               capture_output=True, text=True, timeout=30)
        assert again.returncode == 0, again.stderr
        print('Live file/Git writes and per-project home persistence passed.')
    finally:
        server.terminate()
        server.wait(5)
