"""Forced-SSH host helper. Inputs select registered projects, never Docker flags."""
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time

CONFIG = Path('/etc/deskharbor-sandbox/host.json')
AGENTS = {'codex', 'agy', 'shell'}


def decode_request(command):
    match = re.fullmatch(r'deskharbor-sandbox-v1 ([A-Za-z0-9_-]{1,24000}={0,2})', command)
    if not match:
        raise ValueError('Only deskharbor-sandbox-v1 requests are accepted')
    raw = base64.b64decode(match[1], altchars=b'-_', validate=True)
    request = json.loads(raw)
    keys = {'version', 'action', 'project', 'agent', 'args', 'gpu', 'port'}
    if not isinstance(request, dict) or set(request) - keys:
        raise ValueError('Unknown request fields')
    if request.get('version') != 1 or request.get('action') not in ('run', 'reset', 'list', 'preview'):
        raise ValueError('Unsupported request')
    if request['action'] != 'list':
        if not isinstance(request.get('project'), str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', request['project']):
            raise ValueError('Invalid project ID')
    if request['action'] == 'run':
        if not isinstance(request.get('agent'), str) or request['agent'] not in AGENTS or type(request.get('gpu')) is not bool:
            raise ValueError('Invalid agent or GPU mode')
        args = request.get('args')
        if (not isinstance(args, list) or len(args) > 128
                or any(not isinstance(a, str) or '\x00' in a or len(a) > 8192 for a in args)):
            raise ValueError('Invalid agent arguments')
    if request['action'] == 'preview':
        if type(request.get('port')) is not int or not 1024 <= request['port'] <= 65535:
            raise ValueError('Invalid guest preview port')
    return request


def load_config(path=CONFIG):
    st = path.stat()
    if st.st_uid != 0 or st.st_mode & 0o022 or path.is_symlink():
        raise ValueError('Host config must be root-owned, not writable by group/others, and not a symlink')
    config = json.loads(path.read_text())
    if config.get('version') != 1 or config.get('uid') != os.getuid() or config.get('gid') != os.getgid():
        raise ValueError('Host config does not match this user')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', config.get('image', '')):
        raise ValueError('Host config must pin an image ID')
    return config


def checked_project(project):
    root = Path(project['host_path'])
    resolved = root.resolve(strict=True)
    if root != resolved or not root.is_dir() or root == Path.home() or root in Path.home().parents:
        raise ValueError('Project must be a canonical directory, not home or its parent')
    if ',' in str(root) or '\n' in str(root):
        raise ValueError('Project path cannot contain commas or newlines')
    git = root / '.git'
    if git.is_symlink() or (git.exists() and not git.is_dir()):
        raise ValueError('External Git worktrees are unsupported; use a standalone clone')
    return root


def env_for_helpers():
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(Path.home()),
            'LANG': 'C.UTF-8', 'PYTHONPATH': str(Path(__file__).resolve().parent.parent)}


def spawn(module, args):
    return subprocess.Popen([sys.executable, '-m', module, *args],
                            env=env_for_helpers(), start_new_session=True)


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def wait_ready(process, predicate, name):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'{name} exited before becoming ready')
        if predicate():
            return
        time.sleep(0.05)
    raise RuntimeError(f'{name} did not become ready')


def host_addresses(extra=()):
    addresses = set(extra)
    result = subprocess.run(['ip', '-j', 'address'], capture_output=True, text=True, check=True)
    for interface in json.loads(result.stdout):
        for item in interface.get('addr_info', []):
            addresses.add(item['local'])
    return sorted(addresses)


def docker_command(config, root, home, view, proxy, name, request, preview=None):
    # Arguments are built from root-owned policy and trusted paths. Workload
    # arguments follow the fixed image/entrypoint and cannot become Docker flags.
    command = ['docker', 'run', '--rm', '--init', '--name', name,
               '--hostname', 'deskharbor-sandbox', '--network', 'none',
               '--user', f"{config['uid']}:{config['gid']}", '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--read-only',
               '--pids-limit', '512', '--memory', '8g', '--cpus', '4',
               '--ulimit', 'nofile=4096:4096', '--shm-size', '256m',
               '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=1g',
               '--tmpfs', '/run:rw,nosuid,nodev,size=32m',
               '--mount', f'type=bind,src={view},dst=/project',
               '--mount', f'type=bind,src={home},dst=/home/sandbox',
               '--mount', f'type=bind,src={proxy},dst=/run/deskharbor-proxy,readonly',
               '--workdir', '/project']
    if preview is not None:
        command += ['--mount', f'type=bind,src={preview},dst=/run/deskharbor-preview']
    if request['gpu']:
        command += ['--gpus', 'all', '--env', 'NVIDIA_VISIBLE_DEVICES=all',
                    '--env', 'NVIDIA_DRIVER_CAPABILITIES=compute,utility']
    else:
        command += ['--runtime', 'runc', '--env', 'NVIDIA_VISIBLE_DEVICES=void']
    command += ['-i']
    if sys.stdin.isatty() and sys.stdout.isatty():
        command += ['-t']
    command += [config['image'], request['agent'], *request['args']]
    return command


def run(config, request):
    if request['action'] == 'list':
        print(json.dumps({'projects': {key: {'workstation_path': p['workstation_path'],
                                         'allow_gpu': p.get('allow_gpu', False)}
                                      for key, p in config['projects'].items()}}))
        return 0
    project = config['projects'].get(request['project'])
    if not project:
        raise ValueError('Project is not registered on the host')
    root = checked_project(project)
    if request.get('gpu') and not project.get('allow_gpu', False):
        raise ValueError('GPU mode is not enabled for this registered project')
    state = Path(config['state_dir']).resolve()
    if ',' in str(state) or state == root or root in state.parents or state in root.parents:
        raise ValueError('Sandbox state and project must be disjoint')
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state.stat().st_uid != os.getuid() or state.stat().st_mode & 0o077:
        raise ValueError('Sandbox state must be owned by this user with mode 0700')
    identity = hashlib.sha256(str(root).encode()).hexdigest()[:24]
    active = state / 'active'
    active.mkdir(mode=0o700, exist_ok=True)
    marker = active / (identity + '.json')
    if request['action'] == 'preview':
        from deskharbor_sandbox.stdio import relay
        data = json.loads(marker.read_text())
        stage = Path(data['stage'])
        if stage.parent != state / 'runs':
            raise ValueError('Invalid active session')
        sockpath = stage / 'preview/gateway.sock'
        # Pin the socket inode first. Never connect by a guest-mutable pathname:
        # a symlink swap could otherwise redirect the helper to a host socket.
        fd = os.open(sockpath, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if not stat.S_ISSOCK(os.fstat(fd).st_mode):
                raise ValueError('Preview gateway is not a socket')
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as service:
                service.settimeout(30)
                service.connect(f'/proc/self/fd/{fd}')
                service.sendall(struct.pack('!H', request['port']))
                relay(service)
        finally:
            os.close(fd)
        return 0
    home = state / 'homes' / identity
    home.parent.mkdir(mode=0o700, exist_ok=True)
    lockdir = state / 'locks'
    lockdir.mkdir(mode=0o700, exist_ok=True)
    with open(lockdir / identity, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('This project already has a running sandbox session')
        if request['action'] == 'reset':
            if home.is_symlink():
                raise ValueError('Home path is a symlink')
            if home.exists():
                shutil.rmtree(home)
            print('Sandbox home reset; project files are unchanged.')
            return 0
        home.mkdir(mode=0o700, exist_ok=True)
        if home.is_symlink():
            raise ValueError('Home path is a symlink')
        rundir = state / 'runs'
        rundir.mkdir(mode=0o700, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=identity + '-', dir=rundir))
        view, proxy, preview = stage / 'project', stage / 'proxy', stage / 'preview'
        view.mkdir()
        proxy.mkdir()
        preview.mkdir()
        name = 'deskharbor-sandbox-' + identity
        children = []
        try:
            fsargs = [str(root), str(view), '--allow-other']
            for hidden in project.get('hidden_paths', []):
                fsargs += ['--hide', hidden]
            filesystem = spawn('deskharbor_sandbox.projectfs', fsargs)
            children.append(filesystem)
            wait_ready(filesystem, lambda: os.path.ismount(view), 'Filtered project filesystem')
            proxyargs = [str(proxy / 'proxy.sock')]
            for address in host_addresses(config.get('blocked_ips', [])):
                proxyargs += ['--block', address]
            network = spawn('deskharbor_sandbox.proxy', proxyargs)
            children.append(network)
            wait_ready(network, lambda: (proxy / 'proxy.sock').exists(), 'Public network proxy')
            marker.write_text(json.dumps({'stage': str(stage)}))
            print(f"DeskHarbor sandbox: {request['project']} / {request['agent']} / "
                  f"{'GPU' if request['gpu'] else 'CPU'}; live project, private home, filtered network.",
                  file=sys.stderr)
            return subprocess.call(docker_command(config, root, home, view, proxy, name, request, preview),
                                   env=env_for_helpers())
        finally:
            marker.unlink(missing_ok=True)
            # Remove workload before unmounting; stale/FUSE failure never causes
            # a retry with the unfiltered original project or host networking.
            subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, env=env_for_helpers())
            if os.path.ismount(view):
                subprocess.run(['fusermount3', '-u', str(view)], capture_output=True)
            for child in reversed(children):
                stop(child)
            if os.path.ismount(view):
                subprocess.run(['fusermount3', '-uz', str(view)], capture_output=True)
            if not os.path.ismount(view):
                shutil.rmtree(stage)


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        request = decode_request(os.environ.get('SSH_ORIGINAL_COMMAND', ''))
        config = load_config()
        os.umask(0o077)
        sys.exit(run(config, request))
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(f'deskharbor-sandbox: {exc}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == '__main__':
    main()
