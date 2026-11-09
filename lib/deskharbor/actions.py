"""Host actions. Commands are argv lists, never shell strings."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from . import config


def run(command, **kwargs):
    return subprocess.run([str(item) for item in command], check=True, **kwargs)


def host_required():
    if Path('/.dockerenv').exists():
        raise ValueError('Run workstation management on the Docker HOST, not inside the workstation')
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'amd64'):
        raise ValueError('DeskHarbor v1 supports Linux x86-64 hosts')
    if os.getuid() == 0:
        raise ValueError('Run as your normal Docker-enabled user; sandbox setup requests sudo separately')
    if not shutil.which('docker'):
        raise ValueError('Docker is missing. Install Docker Engine and the Compose plugin first')


def command(root, c, *args):
    path = config.render(root, c)
    return ['docker', 'compose', '--project-directory', str(root), '--project-name', c['project_name'], '-f', str(path), *args]


def prerequisites(root, c):
    host_required()
    run(['docker', 'compose', 'version'], stdout=subprocess.DEVNULL)
    run(['docker', 'info'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if c['features']['gpu']:
        if not shutil.which('nvidia-smi'):
            raise ValueError('NVIDIA requested, but nvidia-smi is missing on the host')
        run(['nvidia-smi', '-L'], stdout=subprocess.DEVNULL)
        runtimes = subprocess.check_output(['docker', 'info', '--format', '{{json .Runtimes}}'], text=True)
        if 'nvidia' not in runtimes.lower():
            raise ValueError('NVIDIA Container Toolkit runtime not detected; configure it before GPU startup')
    private = Path(root) / '.deskharbor'
    if c['features']['browser'] or c['features']['vnc']:
        if not (private / 'secrets/vnc_password').is_file():
            raise ValueError('Set the VNC password in Configuration → Credentials')
    if c['features']['ssh']:
        name = 'authorized_keys' if c['ssh_auth'] == 'key' else 'secrets/ssh_password'
        if not (private / name).is_file():
            raise ValueError('Set SSH credentials in Configuration → Credentials')
    if c['adopted']:
        for volume in c['volumes'].values():
            try:
                run(['docker', 'volume', 'inspect', volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                raise ValueError('Original volume is missing: ' + volume + '. Refusing an empty replacement') from None
        if not Path(c['projects']).is_dir():
            raise ValueError('Original project folder is unavailable on this host')
    for mount in c['mounts']:
        if not Path(mount['source']).is_dir():
            raise ValueError('Shared settings folder is missing: ' + mount['source'])


def plan(c):
    enabled = ', '.join(key for key, value in c['features'].items() if value)
    lines = ['Workstation user: ' + c['username'], 'Enabled: ' + enabled, 'Network bind: ' + c['bind'],
             'Projects: ' + c['projects'], 'SSH authentication: ' + c['ssh_auth'],
             'Persistent volumes: ' + ', '.join(c['volumes'].values()),
             'Shared settings mounts: ' + str(len(c['mounts'])),
             'Apply builds if needed and may recreate the container. Save open desktop work first.',
             'Disabling features preserves home, applications and volume data.']
    if c['adopted']:
        lines += ['Imported installation: existing volumes are required; the original Compose project is reused.',
                  'Do not start both old and new definitions. Start only one management checkout.']
    return '\n'.join(lines)


def perform(root, action, c):
    host_required()
    if action in ('up', 'build', 'doctor'):
        prerequisites(root, c)
    if action == 'up':
        if not c['adopted']:
            Path(c['projects']).mkdir(parents=True, exist_ok=True)
        run(command(root, c, 'up', '-d', '--build', '--wait', '--wait-timeout', '180'))
        config.private_write(Path(root) / '.deskharbor/applied.json', json.dumps(c, indent=2))
    elif action == 'build':
        run(command(root, c, 'build'))
    elif action == 'stop':
        run(command(root, c, 'stop'))
    elif action == 'status':
        run(command(root, c, 'ps', '--all'))
        print(addresses(c))
    elif action == 'logs':
        run(command(root, c, 'logs', '--tail', '100', '-f'))
    elif action in ('shell', 'apps'):
        program = 'bash' if action == 'shell' else 'workstation-apps'
        run(command(root, c, 'exec', '--user', c['username'], '-e', 'HOME=/home/' + c['username'], 'workstation', 'bash', '-lc', 'exec ' + program))
    elif action == 'sandbox':
        if not shutil.which('whiptail'):
            raise ValueError('The optional sandbox manager requires whiptail on the host')
        env = dict(os.environ, WORKSTATION_IMAGE=c['image'], WORKSTATION_USER=c['username'], WORKSTATION_UID=str(c['uid']), WORKSTATION_GID=str(c['gid']))
        run([Path(root) / 'sandbox/setup-wizard.sh', '--container', c['project_name'] + '-workstation-1'], env=env)
    elif action == 'doctor':
        run(command(root, c, 'config', '--quiet'))
        print('Host prerequisites, credentials, mounts and Compose configuration passed.')
    else:
        raise ValueError('Unsupported action: ' + action)


def addresses(c):
    host = '127.0.0.1' if c['bind'] == '127.0.0.1' else '<docker-host-ip>'
    lines = []
    for key in config.PORTS:
        if not c['features'][key]: continue
        port = c['ports'][key]
        address = f'http://{host}:{port}/' if key in ('browser', 'audio') else f'{host}:{port}'
        lines.append(key + ': ' + address)
    return '\n'.join(lines)


def update(root):
    host_required()
    dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True)
    if dirty.strip():
        raise ValueError('Commit/stash source changes before updating; private ignored settings can stay')
    run(['git', '-C', root, 'pull', '--ff-only'])
    print('Source updated. Choose Start / apply when ready to rebuild. Running services were not restarted.')
