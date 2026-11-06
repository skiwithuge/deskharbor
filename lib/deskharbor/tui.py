"""Small host TUI: one review screen, explicit apply, no installer question chain."""
import copy
import curses
import getpass
from pathlib import Path
import subprocess
from . import actions, config


class UI:
    def menu(self, title, items, text='', selected=None):
        def draw(screen):
            try: curses.curs_set(0)
            except curses.error: pass
            screen.keypad(True)
            cursor = next((i for i, item in enumerate(items) if item[0] == selected), 0)
            while True:
                screen.erase()
                height, width = screen.getmaxyx()
                def line(row, value, reverse=False):
                    if 0 <= row < height - 1:
                        screen.addnstr(row, 1, str(value), max(0, width - 3), curses.A_REVERSE if reverse else 0)
                line(0, title, True)
                if height < 20 or width < 64:
                    line(2, 'Enlarge to at least 64 columns × 20 rows. Q exits.')
                else:
                    for row, value in enumerate(text.splitlines()[:3], 2): line(row, value)
                    visible = height - 9
                    offset = max(0, cursor - visible + 1)
                    for index in range(offset, min(len(items), offset + visible)):
                        line(6 + index - offset, items[index][1], index == cursor)
                    line(height - 2, '↑/↓ navigate · Enter/Space choose · Esc/Q back')
                screen.refresh()
                key = screen.getch()
                if key in (27, ord('q'), ord('Q')): return None
                if height < 20 or width < 64: continue
                if key in (curses.KEY_UP, ord('k')): cursor = (cursor - 1) % len(items)
                elif key in (curses.KEY_DOWN, ord('j')): cursor = (cursor + 1) % len(items)
                elif key in (10, 13, 32, curses.KEY_ENTER): return items[cursor][0]
        return curses.wrapper(draw)

    def message(self, title, text):
        self.menu(title, [('back', 'Back')], text)

    def input(self, title, default=''):
        print('\n' + title)
        answer = input(f'[{default}]: ').strip()
        return answer or default

    def secret(self, title):
        print('\n' + title)
        value = getpass.getpass('Password: ')
        if getpass.getpass('Repeat: ') != value: raise ValueError('Passwords do not match')
        return value


def credentials(ui, root, c, pending):
    while True:
        choice = ui.menu('Credentials', [('vnc', 'Set VNC / audio password'),
                        ('key', 'SSH: choose a public key (recommended)'),
                        ('password', 'SSH: use a password'), ('back', 'Back')],
                        'Credentials are private local files and never shown in the plan.')
        if choice in (None, 'back'): return
        if choice == 'vnc':
            pending['secrets/vnc_password'] = config.validate_password('vnc_password', ui.secret('VNC / audio: 6–8 ASCII characters'))
        elif choice == 'key':
            keys = sorted((Path.home() / '.ssh').glob('*.pub'))
            filename = ui.input('OpenSSH public-key path', str(keys[0]) if keys else '')
            pending['authorized_keys'] = config.public_key_text(filename)
            c['ssh_auth'] = 'key'
        else:
            pending['secrets/ssh_password'] = config.validate_password('ssh_password', ui.secret('SSH: at least 12 characters'))
            c['ssh_auth'] = 'password'


def settings(ui, root, original, initial_pending=None):
    c = copy.deepcopy(original)
    pending = dict(initial_pending or {})
    while True:
        active = ', '.join(key for key, value in c['features'].items() if value)
        choice = ui.menu('DeskHarbor — configuration', [
            ('features', 'Features: ' + active), ('network', 'Network: ' + c['bind']),
            ('projects', 'Project folder: ' + c['projects']), ('credentials', 'Credentials: VNC password / SSH key'),
            ('ports', 'Service and development ports'), ('mounts', 'Advanced: shared host settings'),
            ('display', 'Display fallback and sizing'), ('save', 'Save configuration'), ('back', 'Cancel / back')],
            'Changes are staged here. Save preserves data; Start / apply changes the running container.')
        if choice in (None, 'back'): return None
        try:
            if choice == 'features':
                while True:
                    options = [(key, ('[x] ' if c['features'][key] else '[ ] ') +
                                {'browser': 'Browser desktop', 'vnc': 'Native VNC / Remmina', 'ssh': 'SSH access', 'audio': 'Desktop audio', 'gpu': 'NVIDIA / CUDA'}[key]) for key in config.FEATURES]
                    toggle = ui.menu('Features — Space toggles', options + [('back', 'Done')])
                    if toggle in (None, 'back'): break
                    c['features'][toggle] = not c['features'][toggle]
                    if toggle in ('browser', 'vnc') and not (c['features']['browser'] or c['features']['vnc']):
                        c['features']['audio'] = False
                    if toggle == 'audio' and c['features']['audio']:
                        c['features']['browser'] = True
            elif choice == 'network':
                bind = ui.menu('Network', [('local', 'Local only (recommended initially)'), ('lan', 'LAN / VPN clients'), ('custom', 'Specific host IPv4 address')],
                               'LAN mode binds selected ports on all host interfaces. No router rules are changed.')
                if bind == 'local': c['bind'] = '127.0.0.1'
                elif bind == 'lan': c['bind'] = '0.0.0.0'
                elif bind == 'custom': c['bind'] = ui.input('Host bind IPv4', c['bind'])
            elif choice == 'projects':
                c['projects'] = ui.input('Host project folder', c['projects'])
            elif choice == 'credentials': credentials(ui, root, c, pending)
            elif choice == 'ports':
                port_choice = ui.menu('Ports', [(key, key + ': ' + str(c['ports'][key])) for key in config.PORTS] +
                                     [('extra', 'Development port ranges'), ('back', 'Back')])
                if port_choice in config.PORTS:
                    c['ports'][port_choice] = int(ui.input('Host port', str(c['ports'][port_choice])))
                elif port_choice == 'extra':
                    value = ui.input('Mappings host:container, comma separated; use "none" to clear',
                                     ','.join(item['host'] + ':' + item['container'] for item in c['extra_ports']) or 'none')
                    if value == 'none':
                        c['extra_ports'] = []
                    else:
                        pairs = [item.strip().split(':') for item in value.split(',')]
                        if any(len(pair) != 2 or not all(pair) for pair in pairs):
                            raise ValueError('Use host:container pairs, such as 3000-3010:3000-3010')
                        c['extra_ports'] = [{'host': host, 'container': target} for host, target in pairs]
            elif choice == 'mounts':
                options = [(name, ('[x] ' if any(item['target'].endswith('/' + name) for item in c['mounts']) else '[ ] ') + name) for name in config.SHARED_SETTINGS]
                name = ui.menu('Shared settings — advanced', options + [('back', 'Back')],
                               'Mounts share host credentials/settings read-write. Disabled by default.\nDisabling a mount never deletes its source directory.')
                if name in config.SHARED_SETTINGS:
                    target = '/home/' + c['username'] + '/' + name
                    found = [item for item in c['mounts'] if item['target'] == target]
                    if found: c['mounts'] = [item for item in c['mounts'] if item['target'] != target]
                    else:
                        path = Path(ui.input('Host settings directory', str(Path.home() / name))).expanduser().absolute()
                        if not path.is_dir(): raise ValueError('That directory does not exist')
                        c['mounts'].append({'source': str(path), 'target': target})
            elif choice == 'display':
                mode = ui.menu('Resolution mode', [('auto', 'Automatic: follow the active client'), ('fixed', 'Fixed resolution')])
                if mode:
                    c['display']['mode'] = mode
                    value = ui.input('Startup/fixed resolution WIDTHxHEIGHT', f"{c['display']['width']}x{c['display']['height']}")
                    width, height = value.lower().split('x')
                    c['display'].update(width=int(width), height=int(height))
            elif choice == 'save':
                c = config.validate(c)
                for filename, value in pending.items():
                    config.private_write(Path(root) / '.deskharbor' / filename, value)
                return config.save(root, c)
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            ui.message('Check configuration', str(error))


def execute(ui, operation):
    while True:
        try:
            operation()
            return
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            print('\n' + str(error))
            choice = ui.menu('Operation failed', [('retry', 'Retry'), ('back', 'Back to menu')],
                             'Configuration and private data were preserved.\nCommand output remains in terminal scrollback.')
            if choice != 'retry': return


def setup(ui, root):
    c = config.defaults()
    c['uid'], c['gid'] = __import__('os').getuid(), __import__('os').getgid()
    c['projects'] = ui.input('Folder to access inside the workstation', c['projects'])
    pending = {'secrets/vnc_password': config.validate_password('vnc_password', ui.secret('Choose VNC / audio password: 6–8 ASCII characters'))}
    keys = sorted((Path.home() / '.ssh').glob('*.pub'))
    filename = ui.input('SSH public-key path (type "password" to use a password)', str(keys[0]) if keys else 'password')
    if filename == 'password':
        pending['secrets/ssh_password'] = config.validate_password('ssh_password', ui.secret('Choose a separate SSH password: at least 12 characters'))
        c['ssh_auth'] = 'password'
    else: pending['authorized_keys'] = config.public_key_text(filename)
    return settings(ui, root, c, pending)


def main(root):
    ui = UI()
    while True:
        exists = (root / '.deskharbor/config.json').is_file()
        imported = exists and config.load(root)['adopted'] and not (root / '.deskharbor/applied.json').exists()
        choice = ui.menu('DeskHarbor — your workstation, wherever you dock', [
            ('setup' if not exists else 'configure', 'First setup' if not exists else 'Configuration'),
            ('up', 'Start / apply configuration'), ('status', 'Status and connection addresses'),
            ('apps', 'Install / update applications'), ('shell', 'Open workstation terminal'),
            ('stop', 'Stop workstation'), ('doctor', 'Check prerequisites'), ('logs', 'Service logs'),
            ('update', 'Update DeskHarbor source'), ('sandbox', 'Advanced: agent sandbox (experimental)'),
            ('import', 'Advanced: import an existing workstation'), ('exit', 'Exit')],
            ('Imported installation: Apply may replace its running container.\n' if imported else '') +
            'Local settings and secrets stay outside Git.\nStopping/disabling features does not remove persistent data.')
        if choice in (None, 'exit'): return
        def operation():
            if choice == 'setup': setup(ui, root)
            elif choice == 'import':
                source = ui.input('Existing workstation repository path')
                config.legacy(root, source)
                ui.message('Imported for review', 'No containers were changed. Review Configuration and volumes before applying.')
            elif choice == 'configure': settings(ui, root, config.load(root))
            elif choice == 'update': actions.update(root)
            else:
                c = config.load(root)
                if choice == 'up':
                    print('\n' + actions.plan(c))
                    if ui.menu('Apply configuration', [('apply', 'Apply — build/start/recreate if needed'), ('back', 'Back')],
                               'Save open work first. Existing named volumes are retained.') != 'apply': return
                actions.perform(root, choice, c)
                if choice in ('status', 'doctor', 'up'): input('\nPress Enter to return to the menu.')
        execute(ui, operation)
