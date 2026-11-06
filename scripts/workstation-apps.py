"""Small dependency-free installer/update menu for the workstation terminal."""
import argparse
import curses
import os
from pathlib import Path
import re
import subprocess
import sys

HOME_DIR = Path.home()
SCRIPTS = Path(__file__).resolve().parent
BREW = Path('/home/linuxbrew/.linuxbrew/bin/brew')
TOOLS = [
    ('sublime', 'Sublime Text', 'Install/update the official stable apt package'),
    ('brew', 'Homebrew', 'Updates Brew and all installed formulae'),
    ('dev-tools', 'Development runtimes (nvm, Node, pyenv)', 'Refresh Node/Python installs; manager revisions stay pinned'),
    ('codex-app', 'Codex desktop (ChatGPT)', 'Official Linux desktop package'),
    ('antigravity', 'Antigravity desktop', 'Requires a local archive or an HTTPS archive URL'),
    ('codex-cli', 'Codex CLI', 'Official npm package'),
    ('antigravity-cli', 'Antigravity CLI (agy)', 'Official Google CLI installer'),
]


def installed(tool):
    locations = {
        'sublime': [Path('/usr/bin/subl')],
        'brew': [BREW],
        'dev-tools': [HOME_DIR / '.nvm/nvm.sh', HOME_DIR / '.pyenv/bin/pyenv'],
        'codex-app': [Path('/usr/lib/chatgpt/ChatGPT')],
        'antigravity': [HOME_DIR / '.local/share/workstation/antigravity/current/executable-path'],
        'codex-cli': [HOME_DIR / '.local/npm/bin/codex'],
        'antigravity-cli': [HOME_DIR / '.local/bin/agy'],
    }
    return all(path.is_file() for path in locations[tool])


def select(screen):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    screen.keypad(True)
    mode, cursor, chosen = 'install', 0, set()
    status = {tool: installed(tool) for tool, _, _ in TOOLS}
    while True:
        screen.erase()
        height, width = screen.getmaxyx()

        def line(row, value, highlighted=False):
            if row < height - 1:
                screen.addnstr(row, 0, value, max(0, width - 1), curses.A_REVERSE if highlighted else 0)

        if height < 18 or width < 60:
            line(0, 'Enlarge terminal to at least 60 columns x 18 rows; Q exits.')
        else:
            line(0, 'DeskHarbor - applications', True)
            line(2, f'Mode: {mode.upper()}    [Tab switches; I install; U update]')
            line(3, 'Install skips existing tools. Update applies to installed tools.')
            for index, (tool, name, _) in enumerate(TOOLS):
                mark = 'x' if tool in chosen else ' '
                state = 'installed' if status[tool] else 'missing'
                line(5 + index, f' [{mark}] {name}  ({state})', index == cursor)
            line(6 + len(TOOLS), TOOLS[cursor][2])
            line(8 + len(TOOLS), 'Up/Down: move  Space: select  Enter: run selected  Q: exit')
        screen.refresh()
        key = screen.getch()
        if key in (ord('q'), ord('Q'), 27):
            return None
        if height < 18 or width < 60:
            continue
        if key in (curses.KEY_UP, ord('k')):
            cursor = (cursor - 1) % len(TOOLS)
        elif key in (curses.KEY_DOWN, ord('j')):
            cursor = (cursor + 1) % len(TOOLS)
        elif key in (9, ord('i'), ord('u')):
            mode = ('update' if mode == 'install' else 'install') if key == 9 else ('install' if key == ord('i') else 'update')
            chosen.clear()
        elif key == ord(' '):
            tool = TOOLS[cursor][0]
            if status[tool] == (mode == 'update'):
                chosen.symmetric_difference_update({tool})
            else:
                curses.beep()
        elif key in (10, 13, curses.KEY_ENTER) and chosen:
            return mode, [tool for tool, _, _ in TOOLS if tool in chosen]


def plan(mode, tools, archive='', node='22', python=''):
    if not re.fullmatch(r'[A-Za-z0-9.+_-]+', node):
        raise ValueError('Invalid Node version')
    if python and not re.fullmatch(r'[A-Za-z0-9.+_-]+', python):
        raise ValueError('Invalid Python version')
    if 'antigravity' in tools:
        if not archive:
            raise ValueError('Antigravity desktop requires an archive')
        if not archive.startswith('https://'):
            archive = str(Path(archive).expanduser())
            if not Path(archive).is_file():
                raise ValueError('Antigravity archive file does not exist')
    result = []
    for tool in tools:
        if tool == 'brew' and mode == 'update':
            commands = [[str(BREW), 'update'], [str(BREW), 'upgrade']]
        elif tool == 'dev-tools':
            commands = [[str(SCRIPTS / 'install-dev-tools.sh'), node, python]]
        else:
            commands = [[str(SCRIPTS / f'{mode}-{tool}.sh')]]
            if tool == 'antigravity':
                commands[0].append(archive)
        result.append((tool, commands))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='Print installation status without opening the menu')
    args = parser.parse_args()
    if args.list:
        for tool, name, _ in TOOLS:
            print(f'{tool}: {"installed" if installed(tool) else "missing"} - {name}')
        return 0
    if os.getuid() == 0:
        parser.error('Run as the workstation user, not root')
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error('An interactive terminal is required; use ./workstation.sh apps on the host')
    while True:
        selection = curses.wrapper(select)
        if selection is None:
            return 0
        mode, tools = selection
        try:
            archive, node, python = '', '22', ''
            if 'antigravity' in tools:
                previous = HOME_DIR / '.local/share/workstation/antigravity/current/source'
                default = previous.read_text().strip() if previous.is_file() else ''
                archive = input(f'Antigravity archive path or HTTPS URL [{default}]: ').strip() or default
            if 'dev-tools' in tools:
                node = input('Node version [22]: ').strip() or '22'
                python = input('Python version (blank skips compilation): ').strip()
            actions = plan(mode, tools, archive, node, python)
        except (ValueError, OSError) as error:
            print(f'Cannot start: {error}')
            input('Press Enter to return to the menu.')
            continue
        results = []
        for tool, commands in actions:
            print(f'\n--- {mode.capitalize()}: {tool} ---', flush=True)
            success = True
            for command in commands:
                try:
                    code = subprocess.run(command).returncode
                except OSError as error:
                    print(f'Could not run installer: {error}')
                    code = 1
                if code != 0:
                    success = False
                    break
            results.append((tool, success))
        print('\nResults:')
        for tool, success in results:
            print(f'  {tool}: {"completed" if success else "FAILED - rerun to retry"}')
        print('Open a new shell to load newly installed tools. App sign-in remains interactive.')
        input('Press Enter to return to the menu (Q then exits).')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.')
        sys.exit(130)
