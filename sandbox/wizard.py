#!/usr/bin/env python3
"""Host setup manager. Policy lives in the root-owned helper, never in this UI."""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
CONFIG = Path('/etc/deskharbor-sandbox/host.json')
ADMIN = '/usr/local/sbin/deskharbor-sandbox-admin'
PYTHON = '/opt/deskharbor-sandbox/venv/bin/python'


def run(command):
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or f'{command[0]} exited with {result.returncode}')
    return result.stdout.strip()


def policy():
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {'projects': {}}


def saved_settings():
    file = BASE / '.setup.env'
    if not file.exists():
        return {}
    # Data only: never source saved values as shell code.
    return dict(line.split('=', 1) for line in file.read_text().splitlines()
                if '=' in line and not line.startswith('#'))


def detect_container(candidate='', explicit=False):
    if candidate:
        try:
            info = json.loads(run(['docker', 'inspect', '--format',
                                  '{"running":{{json .State.Running}},"name":{{json .Name}}}', candidate]))
            if info['running']:
                return info['name'].lstrip('/')
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
        if explicit:
            raise ValueError(f'Container {candidate} is missing or stopped. Edit the container setting.')
    command = ['docker', 'compose', '--project-directory', str(BASE.parent)]
    manifest = BASE.parent / '.deskharbor/compose.json'
    if manifest.exists():
        command += ['-f', str(manifest)]
    identifier = run(command + ['ps', '-q', 'workstation'])
    if not identifier or '\n' in identifier:
        raise ValueError('Start the workstation first, then retry detection.')
    return detect_container(identifier, explicit=True)


def detect_host():
    try:
        parts = run(['ip', '-4', 'route', 'get', '1.1.1.1']).split()
        return parts[parts.index('src') + 1]
    except (ValueError, IndexError):
        return ''


def mapped_path(container, project):
    root = Path(project).resolve(strict=True)
    mounts = json.loads(run(['docker', 'inspect', '--format', '{{json .Mounts}}', container]))
    choices = []
    for mount in mounts:
        if mount.get('Type') != 'bind':
            continue
        source = Path(mount['Source']).resolve()
        try:
            relative = root.relative_to(source)
        except ValueError:
            continue
        choices.append((len(source.parts), str(Path(mount['Destination']) / relative)))
    if not choices:
        raise ValueError('This folder is not bind-mounted into the workstation. Choose a folder under its project mount.')
    return max(choices)[1]


def project_id(path):
    name = re.sub(r'[^A-Za-z0-9_-]', '-', Path(path).name)[:48] or 'project'
    return name + '-' + hashlib.sha256(path.encode()).hexdigest()[:8]


@dataclass
class Settings:
    host: str = ''
    container: str = ''
    project: str = ''
    id: str = ''
    gpu: bool = False
    hidden: list = field(default_factory=list)
    mapped: str = ''
    editing: bool = False

    def load_project(self, name, item):
        self.id = name
        self.project = item['host_path']
        self.mapped = item['workstation_path']
        self.gpu = item.get('allow_gpu', False)
        self.hidden = list(item.get('hidden_paths', []))
        self.editing = True

    def validate(self, needs_project=True):
        if not re.fullmatch(r'[A-Za-z0-9.:-]+', self.host) or self.host.startswith('-'):
            raise ValueError('Enter the host address reachable from your workstation, for example 192.0.2.10.')
        self.container = detect_container(self.container, explicit=True)
        if not needs_project:
            return
        root = Path(self.project).expanduser().resolve(strict=True)
        if not root.is_dir() or root.stat().st_uid != os.getuid():
            raise ValueError('Choose a project directory owned by your host user.')
        if root == Path.home() or root in Path.home().parents or any(c in str(root) for c in ',\n'):
            raise ValueError('Choose one project, not your home or a parent directory.')
        git = root / '.git'
        if git.is_symlink() or (git.exists() and not git.is_dir()):
            raise ValueError('External Git worktrees are unsupported; choose a standalone clone.')
        self.project = str(root)
        self.mapped = mapped_path(self.container, self.project)
        if not self.id:
            self.id = project_id(self.project)
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', self.id):
            raise ValueError('Project ID must contain 1–64 letters, digits, dashes or underscores.')
        for name, item in policy().get('projects', {}).items():
            if item['host_path'] == self.project and name != self.id:
                raise ValueError(f'This folder is already registered as {name}. Select that project from the menu to edit it.')
        for hidden in self.hidden:
            path = Path(hidden)
            if path.is_absolute() or '..' in path.parts or not path.parts or '\n' in hidden:
                raise ValueError('Additional exclusions must be relative project paths without .. or newlines.')

    def registration(self):
        command = ['sudo', ADMIN, 'register', self.id, self.project,
                   '--workstation-path', self.mapped]
        if self.gpu:
            command.append('--allow-gpu')
        for hidden in self.hidden:
            command.extend(['--hide', hidden])
        return command

    def remember(self):
        values = {'HOST_ADDRESS': self.host, 'WORKSTATION_CONTAINER': self.container,
                  'HOST_PROJECT': self.project, 'WORKSTATION_PROJECT': self.mapped, 'PROJECT_ID': self.id}
        temporary = BASE / '.setup.env.tmp'
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as output:
            for key, value in values.items():
                output.write(f'{key}={value}\n')
        temporary.replace(BASE / '.setup.env')


class UI:
    def box(self, title, kind, text, *extra):
        if not shutil.which('whiptail'):
            raise ValueError('Install the TUI dependency on the host: sudo apt-get install whiptail')
        if os.environ.get('TERM', '') in ('', 'dumb'):
            raise ValueError('Use a terminal that supports cursor positioning (for example Tilix). TERM is missing or set to dumb.')
        size = shutil.get_terminal_size((90, 28))
        if size.columns < 60 or size.lines < 20:
            raise ValueError('Enlarge the terminal to at least 60 columns and 20 rows.')
        height, width = min(24, size.lines - 2), min(100, size.columns - 2)
        with os.fdopen(os.open('/dev/tty', os.O_RDWR), 'rb', buffering=0) as terminal:
            # A dedicated output FD keeps UI drawing separate from selected data.
            read_fd, write_fd = os.pipe()
            try:
                command = ['whiptail', '--backtitle', 'DeskHarbor workstation · Sandbox manager',
                           '--title', title, '--output-fd', str(write_fd), kind, text,
                           str(height), str(width)]
                if kind in ('--menu', '--checklist'):
                    command.append(str(max(3, min(10, height - 12))))
                if kind == '--msgbox':
                    command.append('--scrolltext')
                command.extend(extra)
                result = subprocess.run(command, stdin=terminal, stdout=terminal, stderr=terminal,
                                        pass_fds=(write_fd,))
                os.close(write_fd)
                write_fd = -1
                with os.fdopen(read_fd) as output:
                    value = output.read().strip()
                read_fd = -1
                if result.returncode in (1, 255):
                    return None
                if result.returncode != 0:
                    raise ValueError(f'whiptail exited with {result.returncode}')
                return value
            finally:
                if read_fd >= 0:
                    os.close(read_fd)
                if write_fd >= 0:
                    os.close(write_fd)

    def menu(self, title, text, items):
        return self.box(title, '--menu', text, *(value for pair in items for value in pair))

    def input(self, title, text, value=''):
        return self.box(title, '--inputbox', text, value)

    def message(self, title, text):
        self.box(title, '--msgbox', text)

    def gpu(self, current):
        result = self.box('GPU permission', '--checklist',
                          'Space toggles GPU access. Launches still default to CPU.',
                          'GPU', 'Allow optional NVIDIA/CUDA launches', 'ON' if current else 'OFF')
        return current if result is None else 'GPU' in shlex.split(result)


def edit_exclusions(ui, settings):
    while True:
        items = [('add', 'Add a relative secret path')]
        items += [(str(index), 'Remove: ' + path) for index, path in enumerate(settings.hidden)]
        choice = ui.menu('Additional secret exclusions', 'Standard secret filename filters always apply.', items)
        if choice is None:
            return
        if choice == 'add':
            value = ui.input('Hide a path', 'Relative to this project, e.g. config/private.json')
            if value and value not in settings.hidden:
                settings.hidden.append(value)
        else:
            settings.hidden.pop(int(choice))


def settings_screen(ui, settings, operation):
    project_operation = operation in ('setup', 'project')
    while True:
        text = {'setup': 'Install host helper, register this live project and verify.',
                'project': 'Save project settings. No image rebuild or host reinstallation.',
                'update': 'Rebuild image and refresh helper/client. Preserve projects, GPU permissions, tools and logins.'}[operation]
        text += '\nSelect a setting to edit. Escape returns to the menu.'
        if project_operation and settings.project and settings.container:
            try:
                settings.mapped = mapped_path(settings.container, settings.project)
            except (ValueError, OSError):
                settings.mapped = ''
            text += '\nContainer path: ' + (settings.mapped or '(not mapped yet)')
        if project_operation:
            text += '\nAgents can edit this project and its Git history.'
        items = [('host', 'Host address: ' + (settings.host or '(not detected)')),
                 ('container', 'Workstation: ' + (settings.container or '(not detected)'))]
        if project_operation:
            items += [('project', 'Folder: ' + (settings.project or '(choose folder)')),
                      ('id', 'Project ID: ' + (settings.id or '(automatic)')),
                      ('gpu', 'GPU access: ' + ('enabled' if settings.gpu else 'disabled')),
                      ('hidden', f'Extra secret exclusions: {len(settings.hidden)}')]
        items += [('apply', {'setup': 'Install and register', 'project': 'Save project', 'update': 'Update image and helper'}[operation])]
        choice = ui.menu('Review settings', text, items)
        if choice is None:
            return False
        if choice == 'apply':
            try:
                settings.validate(project_operation)
                if operation != 'setup' and not CONFIG.exists():
                    raise ValueError('Host helper is not installed yet. Choose First setup.')
                return True
            except (ValueError, OSError) as error:
                ui.message('Check settings', str(error))
                continue
        if choice == 'gpu':
            settings.gpu = ui.gpu(settings.gpu)
        elif choice == 'hidden':
            edit_exclusions(ui, settings)
        elif choice == 'id' and settings.editing:
            ui.message('Registered project', 'The existing ID is retained so this folder is not registered twice.')
        else:
            prompts = {'host': 'Host address reachable from VNC', 'container': 'Running workstation container name',
                       'project': 'Absolute project folder on the host', 'id': 'Letters, digits, dash or underscore'}
            value = ui.input('Edit ' + choice, prompts[choice], getattr(settings, choice))
            if value is not None:
                setattr(settings, choice, value)
                if choice == 'project':
                    settings.mapped = ''
                    if not settings.editing:
                        settings.id = ''


def operation_steps(settings, operation, rebuild=False):
    steps = []
    if operation == 'update' or (operation == 'setup' and (rebuild or not image_available())):
        steps.append(('Build sandbox image', [str(BASE / 'build.sh')]))
    if operation in ('setup', 'update'):
        steps.append(('Install host helper and workstation client',
                      ['sudo', str(BASE / 'setup-host.sh'), settings.host, settings.container]))
    if operation in ('setup', 'project'):
        steps.append(('Save project registration', settings.registration()))
    if operation in ('setup', 'update'):
        steps.append(('Check broker, filtered files and network',
                      [PYTHON, str(BASE / 'tests/end_to_end.py'), '--image', 'deskharbor-agent-sandbox:local']))
    return steps


def image_available():
    return subprocess.run(['docker', 'image', 'inspect', 'deskharbor-agent-sandbox:local'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def execute_steps(ui, steps, execute=subprocess.call):
    for index, (label, command) in enumerate(steps):
        while True:
            print(f'\n[{index + 1}/{len(steps)}] {label}', flush=True)
            try:
                result = execute(command)
                reason = f'Exit code: {result}'
            except OSError as error:
                result, reason = 1, str(error)
            if result == 0:
                break
            choice = ui.menu('Step failed', f'{label}\n{reason}\nThe command output remains in terminal scrollback. Inputs are retained.',
                             [('retry', 'Retry this step'), ('edit', 'Edit settings'), ('exit', 'Return to menu')])
            if choice == 'retry':
                continue
            return 'edit' if choice == 'edit' else 'exit'
    return 'done'


def choose_project(ui, settings, gpu_default=False, supplied_project='', hidden_default=(), id_default=''):
    registered = policy().get('projects', {})
    items = [('__add__', 'Add a project')]
    items += [('p:' + name, item['host_path']) for name, item in registered.items()]
    choice = ui.menu('Projects', 'Choose a registered project to edit, or add one.', items)
    if choice is None:
        return False
    if choice == '__add__':
        value = ui.input('Add project', 'Project folder on the host', supplied_project or settings.project)
        if value is None:
            return False
        root = str(Path(value).expanduser().resolve()) if value else ''
        existing = [(name, item) for name, item in registered.items() if item['host_path'] == root]
        if len(existing) == 1:
            settings.load_project(*existing[0])
        else:
            settings.project, settings.id, settings.mapped = root, id_default, ''
            settings.hidden, settings.gpu, settings.editing = list(hidden_default), gpu_default, False
    else:
        settings.load_project(choice[2:], registered[choice[2:]])
    return True


def status(ui):
    lines = [f'Host helper: {"installed" if CONFIG.exists() else "not installed"}',
             f'Sandbox image: {"available" if image_available() else "missing"}']
    try:
        lines.append('Running workstation: ' + detect_container())
    except ValueError as error:
        lines.append(str(error))
    for name, item in policy().get('projects', {}).items():
        lines.append(f'{name}: {item["host_path"]} (GPU {"on" if item.get("allow_gpu") else "off"})')
    ui.message('Current status', '\n'.join(lines))
    choice = ui.menu('Status', 'Choose a check or return to the menu.', [('check', 'Run disposable integration check'), ('back', 'Back')])
    if choice == 'check':
        if not CONFIG.exists():
            ui.message('First setup needed', 'Install the host helper before running the integration check.')
        else:
            result = execute_steps(ui, [('Disposable integration check', [PYTHON, str(BASE / 'tests/end_to_end.py'), '--image', 'deskharbor-agent-sandbox:local'])])
            if result == 'done':
                ui.message('Check passed', 'Broker, filtered project access, networking and cleanup passed.')


def main():
    parser = argparse.ArgumentParser(prog='setup-wizard.sh', description='DeskHarbor sandbox TUI manager (run on the host).')
    parser.add_argument('project', nargs='?', default='')
    parser.add_argument('--host')
    parser.add_argument('--container')
    parser.add_argument('--project-id')
    parser.add_argument('--hide', action='append', default=[])
    parser.add_argument('--gpu', action='store_true', help='Preselect GPU access for a new project')
    parser.add_argument('--no-gpu', action='store_true', help='Explicitly disable GPU for the initial project')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild image during first setup')
    parser.add_argument('--yes', action='store_true', help='Compatibility alias; review still happens in the TUI')
    args = parser.parse_args()
    if Path('/.dockerenv').exists():
        parser.error('Run this manager on the HOST, outside Docker.')
    if os.getuid() == 0:
        parser.error('Run as your normal host user; individual install steps ask for sudo.')
    if not sys.stdin.isatty():
        parser.error('Open an interactive host terminal to use the TUI.')
    if args.gpu and args.no_gpu:
        parser.error('Choose --gpu or --no-gpu, not both.')
    ui = UI()
    saved = saved_settings()
    settings = Settings(host=args.host or saved.get('HOST_ADDRESS') or detect_host(),
                        container=args.container or saved.get('WORKSTATION_CONTAINER', ''),
                        project=args.project or saved.get('HOST_PROJECT', ''), id=args.project_id or '',
                        gpu=args.gpu, hidden=list(args.hide))
    try:
        settings.container = detect_container(settings.container, explicit=bool(args.container))
    except ValueError:
        # Leave the value visible and editable instead of exiting before the UI.
        pass
    if settings.project:
        root = str(Path(settings.project).expanduser().resolve())
        for name, item in policy().get('projects', {}).items():
            if item['host_path'] == root:
                settings.load_project(name, item)
                settings.hidden = list(dict.fromkeys(settings.hidden + args.hide))
                if args.gpu:
                    settings.gpu = True
                if args.no_gpu:
                    settings.gpu = False
                break
    while True:
        choice = ui.menu('Sandbox manager', 'Choose only the operation you need. Escape exits.',
                         [('setup', 'First setup'), ('project', 'Add / edit project'),
                          ('update', 'Update image and helper'), ('status', 'Status / check'), ('exit', 'Exit')])
        if choice in (None, 'exit'):
            return
        try:
            if choice == 'status':
                status(ui)
                continue
            if choice == 'project' and not choose_project(ui, settings, args.gpu, args.project, args.hide, args.project_id or ''):
                continue
            while settings_screen(ui, settings, choice):
                result = execute_steps(ui, operation_steps(settings, choice, args.rebuild))
                if result == 'edit':
                    continue
                if result == 'done':
                    settings.remember()
                    text = 'Operation complete. Existing tools and logins were preserved.'
                    if choice in ('setup', 'project'):
                        text += f'\n\nIn a VNC terminal:\ncd {shlex.quote(settings.mapped)}\n~/.local/bin/deskharbor-sandbox codex\n\nFor first login: deskharbor-sandbox shell, then codex login --device-auth. Log into agy separately.'
                    ui.message('Complete', text)
                break
        except (ValueError, OSError) as error:
            ui.message('Cannot continue', str(error))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        print(f'deskharbor sandbox manager: {error}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
