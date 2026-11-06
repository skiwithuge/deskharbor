"""Validated private configuration and generated Compose model (stdlib only)."""
import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

FEATURES = ('browser', 'vnc', 'ssh', 'audio', 'gpu')
PORTS = {'browser': 6080, 'vnc': 5901, 'ssh': 20222, 'audio': 6081}
TARGET_PORTS = {'browser': 6080, 'vnc': 5901, 'ssh': 22, 'audio': 6081}
SHARED_SETTINGS = ('.codex', '.gemini', '.antigravity', '.antigravity-ide')


def defaults():
    return {'version': 1, 'project_name': 'deskharbor', 'image': 'deskharbor:local',
            'hostname': 'deskharbor', 'username': 'deskharbor', 'uid': os.getuid(), 'gid': os.getgid(),
            'projects': str(Path.home() / 'DeskHarbor/projects'), 'bind': '127.0.0.1',
            'timezone': 'UTC', 'features': dict(browser=True, vnc=False, ssh=True, audio=False, gpu=False),
            'ports': dict(PORTS), 'extra_ports': [], 'mounts': [], 'ssh_auth': 'key',
            'display': {'width': 1920, 'height': 1080, 'mode': 'auto'}, 'restore_tools': True,
            'cpu_image': 'ubuntu:24.04', 'cuda_image': 'nvidia/cuda:12.9.2-devel-ubuntu24.04',
            'extra_apt_packages': '',
            'volumes': {name: 'deskharbor_' + name for name in ('home', 'ssh_host_keys', 'brew')},
            'adopted': False}


def validate(config):
    if not isinstance(config, dict):
        raise ValueError('Configuration must be a JSON object')
    required = set(defaults())
    if set(config) != required:
        raise ValueError('Configuration fields do not match version 1; compare config.example.json')
    c = copy.deepcopy(config)
    for key in ('features', 'ports', 'volumes', 'display'):
        if not isinstance(c[key], dict): raise ValueError('Invalid configuration section: ' + key)
    for key in ('extra_ports', 'mounts'):
        if not isinstance(c[key], list): raise ValueError('Invalid configuration list: ' + key)
    for key in ('project_name', 'image', 'hostname', 'username', 'projects', 'bind', 'timezone', 'ssh_auth', 'cpu_image', 'cuda_image', 'extra_apt_packages'):
        if not isinstance(c[key], str) or any(char in c[key] for char in ('\n', '\r', '\0')):
            raise ValueError('Invalid text field: ' + key)
    if set(c['ports']) != set(PORTS) or set(c['display']) != {'width', 'height', 'mode'}:
        raise ValueError('Port/display fields do not match version 1')
    if c.get('version') != 1:
        raise ValueError('Unsupported configuration version')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', c['project_name']):
        raise ValueError('Invalid Compose project name')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', c['username']):
        raise ValueError('Invalid Linux username')
    for field in ('uid', 'gid'):
        if type(c[field]) is not int or not 0 < c[field] < 2**31:
            raise ValueError('UID/GID must be positive non-root integers')
    if set(c['features']) != set(FEATURES) or any(type(v) is not bool for v in c['features'].values()):
        raise ValueError('Invalid feature settings')
    desktop = c['features']['browser'] or c['features']['vnc']
    if not (desktop or c['features']['ssh']):
        raise ValueError('Keep at least browser, VNC or SSH enabled')
    if c['features']['audio'] and not desktop:
        raise ValueError('Audio requires browser desktop or native VNC')
    if c['ssh_auth'] not in ('key', 'password'):
        raise ValueError('SSH authentication must be key or password')
    import ipaddress
    try:
        address = ipaddress.ip_address(c['bind'])
    except ValueError:
        raise ValueError('Bind address must be an IP address') from None
    if address.version != 4:
        raise ValueError('This version supports IPv4 bind addresses')
    used = set()
    for field in PORTS:
        port = c['ports'][field]
        if type(port) is not int or not 1 <= port <= 65535 or port in used:
            raise ValueError('Service ports must be distinct integers from 1 to 65535')
        used.add(port)
    for item in c['extra_ports']:
        if not isinstance(item, dict) or set(item) != {'host', 'container'}:
            raise ValueError('Extra ports require host/container ranges')
        ranges = []
        for side in ('host', 'container'):
            value = str(item[side])
            if not re.fullmatch(r'[0-9]+(?:-[0-9]+)?', value):
                raise ValueError('Invalid development port range')
            ends = list(map(int, value.split('-')))
            start, end = ends[0], ends[-1]
            if not 1 <= start <= end <= 65535 or end - start > 100:
                raise ValueError('Development ranges must contain at most 101 valid ports')
            ranges.append((start, end))
        if ranges[0][1] - ranges[0][0] != ranges[1][1] - ranges[1][0]:
            raise ValueError('Host and container ranges must have equal lengths')
        for port in range(ranges[0][0], ranges[0][1] + 1):
            if port in used:
                raise ValueError('Development ports overlap another published port')
            used.add(port)
    c['projects'] = str(Path(c['projects']).expanduser().absolute())
    if '\n' in c['projects'] or c['projects'] == '/':
        raise ValueError('Choose a project folder, not the filesystem root')
    for mount in c['mounts']:
        if (not isinstance(mount, dict) or set(mount) != {'source', 'target'}
                or not all(isinstance(value, str) for value in mount.values())
                or not Path(mount['source']).is_absolute()):
            raise ValueError('Mount source must be an absolute path')
        if not mount['target'].startswith('/home/' + c['username'] + '/') or '..' in Path(mount['target']).parts:
            raise ValueError('Additional settings mounts must be beneath the workstation home')
    if set(c['volumes']) != {'home', 'ssh_host_keys', 'brew'}:
        raise ValueError('All persistent volume names are required')
    for volume in c['volumes'].values():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', volume):
            raise ValueError('Invalid persistent volume name')
    for dimension in ('width', 'height'):
        if type(c['display'][dimension]) is not int or not 320 <= c['display'][dimension] <= 16384:
            raise ValueError('Invalid display dimensions')
    if c['display']['mode'] not in ('auto', 'fixed'):
        raise ValueError('Display mode must be auto or fixed')
    for field in ('image', 'hostname', 'timezone', 'cpu_image', 'cuda_image', 'extra_apt_packages'):
        if not isinstance(c[field], str) or any(char in c[field] for char in ('\n', '\r', '\0')):
            raise ValueError('Invalid ' + field)
    if type(c['adopted']) is not bool or type(c['restore_tools']) is not bool:
        raise ValueError('Invalid persistence flags')
    return c


def private_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(descriptor, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def save(root, config):
    c = validate(config)
    private_write(Path(root) / '.deskharbor/config.json', json.dumps(c, indent=2) + '\n')
    return c


def load(root):
    path = Path(root) / '.deskharbor/config.json'
    if not path.exists():
        raise ValueError('Run ./deskharbor setup first')
    return validate(json.loads(path.read_text()))


def validate_password(name, value):
    if '\n' in value or '\0' in value:
        raise ValueError('Passwords must occupy one line')
    if name == 'vnc_password' and not (6 <= len(value) <= 8 and value.isascii()):
        raise ValueError('VNC requires 6–8 ASCII characters (protocol limit)')
    if name == 'ssh_password' and len(value) < 12:
        raise ValueError('Use an SSH password with at least 12 characters')
    return value


def store_password(root, name, value):
    private_write(Path(root) / '.deskharbor/secrets' / name, validate_password(name, value))


def public_key_text(path):
    source = Path(path).expanduser()
    lines = [line.strip() for line in source.read_text().splitlines() if line.strip() and not line.startswith('#')]
    if not lines or any(not re.match(r'^(ssh-|ecdsa-|sk-)[A-Za-z0-9@._+-]+ [A-Za-z0-9+/]+=*(?: |$)', line) for line in lines):
        raise ValueError('Choose an OpenSSH public-key file, never a private key')
    subprocess.run(['ssh-keygen', '-lf', str(source)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return '\n'.join(lines) + '\n'


def store_public_key(root, path):
    private_write(Path(root) / '.deskharbor/authorized_keys', public_key_text(path))


def compose(root, config):
    c = validate(config)
    root = Path(root).resolve()
    private = root / '.deskharbor'
    f = c['features']; desktop = f['browser'] or f['vnc']
    switches = dict(DBUS=desktop, SSH=f['ssh'], VNC=desktop, WEB=f['browser'], PULSE=f['audio'], AUDIO=f['audio'])
    environment = {'TZ': c['timezone'], 'DISPLAY_WIDTH': str(c['display']['width']),
                   'DISPLAY_HEIGHT': str(c['display']['height']), 'DISPLAY_MODE': c['display']['mode'],
                   'RESTORE_SYSTEM_TOOLS': str(c['restore_tools']).lower(), 'SSH_AUTH_MODE': c['ssh_auth'],
                   'AUDIO_PORT': str(c['ports']['audio']),
                   'NVIDIA_VISIBLE_DEVICES': 'all' if f['gpu'] else 'void'}
    environment.update({'ENABLE_' + key: str(value).lower() for key, value in switches.items()})
    volumes = [{'type': 'volume', 'source': 'home', 'target': '/home/' + c['username']},
               {'type': 'volume', 'source': 'ssh_host_keys', 'target': '/var/lib/workstation/ssh'},
               {'type': 'volume', 'source': 'brew', 'target': '/home/linuxbrew/.linuxbrew'},
               {'type': 'bind', 'source': c['projects'], 'target': '/home/' + c['username'] + '/projects',
                'bind': {'create_host_path': False}}]
    volumes += [{'type': 'bind', **mount, 'bind': {'create_host_path': False}} for mount in c['mounts']]
    secrets = {}
    if desktop:
        secrets['vnc_password'] = {'file': str(private / 'secrets/vnc_password')}
    if f['ssh'] and c['ssh_auth'] == 'password':
        secrets['ssh_password'] = {'file': str(private / 'secrets/ssh_password')}
    if f['ssh'] and c['ssh_auth'] == 'key':
        volumes.append({'type': 'bind', 'source': str(private / 'authorized_keys'),
                        'target': '/etc/workstation/authorized_keys', 'read_only': True,
                        'bind': {'create_host_path': False}})
    service = {'build': {'context': str(root), 'args': {
                    'BASE_IMAGE': c['cuda_image'] if f['gpu'] else c['cpu_image'],
                    'USER_NAME': c['username'], 'USER_UID': str(c['uid']), 'USER_GID': str(c['gid']),
                    'EXTRA_APT_PACKAGES': c['extra_apt_packages']}},
               'image': c['image'], 'hostname': c['hostname'], 'platform': 'linux/amd64',
               'restart': 'unless-stopped', 'shm_size': '2gb', 'environment': environment,
               'ports': [f"{c['bind']}:{c['ports'][key]}:{TARGET_PORTS[key]}" for key in PORTS if f[key]],
               'volumes': volumes}
    service['ports'] += [f"{c['bind']}:{item['host']}:{item['container']}" for item in c['extra_ports']]
    if secrets:
        service['secrets'] = list(secrets)
    if f['gpu']:
        service['deploy'] = {'resources': {'reservations': {'devices': [
            {'driver': 'nvidia', 'count': 'all', 'capabilities': ['gpu']}]}}}
    result = {'name': c['project_name'], 'services': {'workstation': service},
              'volumes': {key: {'name': value, **({'external': True} if c['adopted'] else {})}
                          for key, value in c['volumes'].items()}}
    if secrets:
        result['secrets'] = secrets
    # Compose interpolates dollar signs even in JSON string values.
    def literal(value):
        if isinstance(value, str): return value.replace('$', '$$')
        if isinstance(value, list): return [literal(item) for item in value]
        if isinstance(value, dict): return {key: literal(item) for key, item in value.items()}
        return value
    return literal(result)


def render(root, config):
    path = Path(root) / '.deskharbor/compose.json'
    private_write(path, json.dumps(compose(root, config), indent=2) + '\n')
    return path


def parse_env(path):
    values = {}
    if not path.exists(): return values
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        key, separator, value = line.partition('=')
        if separator and re.fullmatch(r'[A-Z_][A-Z0-9_]*', key.strip()):
            parts = shlex.split(value, comments=True)
            values[key.strip()] = parts[0] if len(parts) == 1 else value.strip()
    return values


def legacy(root, source):
    """Import into ignored local files; never execute the old .env or start Docker."""
    source = Path(source).expanduser().resolve()
    if (Path(root) / '.deskharbor/config.json').exists():
        raise ValueError('A profile already exists; back it up before importing')
    values = parse_env(source / '.env')
    c = defaults()
    declared = re.search(r'^name:\s*([\w-]+)', (source / 'compose.yaml').read_text(), re.M)
    if not declared: raise ValueError('Cannot determine the original Compose project name')
    c['project_name'] = values.get('COMPOSE_PROJECT_NAME', declared.group(1))
    c['hostname'] = declared.group(1)
    c['image'] = 'deskharbor:personal'
    for key, env in (('username', 'USER_NAME'), ('projects', 'PROJECTS_PATH'), ('timezone', 'TZ'), ('bind', 'BIND_ADDRESS'), ('extra_apt_packages', 'EXTRA_APT_PACKAGES')):
        if env in values: c[key] = values[env]
    for key, env in (('uid', 'USER_UID'), ('gid', 'USER_GID')):
        if env in values: c[key] = int(values[env])
    for key, env in (('browser', 'WEB_PORT'), ('vnc', 'VNC_PORT'), ('ssh', 'SSH_PORT'), ('audio', 'AUDIO_PORT')):
        if env in values: c['ports'][key] = int(values[env])
    c['features'] = dict.fromkeys(FEATURES, True)
    c['ssh_auth'] = 'password'
    c['adopted'] = True
    c['volumes'] = {name: c['project_name'] + '_' + name for name in c['volumes']}
    # Sublime was part of the legacy base image, not an apt-manifest addition.
    if 'sublime-text' not in shlex.split(c['extra_apt_packages']):
        c['extra_apt_packages'] = (c['extra_apt_packages'] + ' sublime-text').strip()
    c['cuda_image'] = values.get('CUDA_IMAGE', c['cuda_image'])
    c['restore_tools'] = values.get('RESTORE_SYSTEM_TOOLS', 'true') == 'true'
    c['display'] = {'width': int(values.get('DISPLAY_WIDTH', 1920)), 'height': int(values.get('DISPLAY_HEIGHT', 1080)), 'mode': values.get('DISPLAY_MODE', 'auto')}
    for env, default in (('HUGO_PORTS', '1313-1323'), ('WEB_DEV_PORTS', '3000-3010'), ('API_PORTS', '8000-8010')):
        port = values.get(env, default)
        c['extra_ports'].append({'host': port, 'container': default})
    # Preserve the original project target as well as its new generic alias.
    original_target = '/home/' + c['username'] + '/workspace/antigravity'
    c['mounts'].append({'source': c['projects'], 'target': original_target})
    if 'compose.settings.yaml' in values.get('COMPOSE_FILE', ''):
        home = Path(values.get('HOST_SETTINGS_HOME', str(Path.home())))
        for name in SHARED_SETTINGS:
            c['mounts'].append({'source': str(home / name), 'target': '/home/' + c['username'] + '/' + name})
    c = validate(c)
    password_contents = {}
    for name in ('vnc_password', 'ssh_password'):
        path = source / 'secrets' / name
        if not path.is_file(): raise ValueError('Original secret file is missing: ' + name)
        password_contents[name] = path.read_bytes()
    for name, value in password_contents.items():
        private_write(Path(root) / '.deskharbor/secrets' / name, value.decode())
    save(root, c)
    render(root, c)
    return c
