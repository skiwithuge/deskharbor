"""DeskHarbor command line and TUI entrypoint."""
import argparse
import curses
import json
import os
from pathlib import Path
import subprocess
import sys
from . import actions, config, tui


def main(root=None):
    root = Path(root or Path(__file__).resolve().parents[2]).resolve()
    parser = argparse.ArgumentParser(prog='deskharbor', description='Persistent Linux workstation manager. Run without a command to open the host TUI.')
    parser.add_argument('command', nargs='?', choices=['setup', 'init', 'configure', 'up', 'build', 'stop', 'status', 'logs', 'shell', 'apps', 'sandbox', 'doctor', 'plan', 'update', 'import-legacy'])
    parser.add_argument('source', nargs='?', help='Old repository path for import-legacy')
    args = parser.parse_args()
    try:
        if args.command is None:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                parser.print_help()
                return 0
            tui.main(root)
        elif args.command in ('setup', 'init', 'configure'):
            if not (sys.stdin.isatty() and sys.stdout.isatty()): raise ValueError('Setup/configuration requires an interactive host terminal')
            if args.command == 'configure': tui.settings(tui.UI(), root, config.load(root))
            else:
                if (root / '.deskharbor/config.json').exists(): raise ValueError('Already configured; use configure')
                tui.setup(tui.UI(), root)
        elif args.command == 'import-legacy':
            if not args.source: raise ValueError('Provide the existing workstation repository path')
            config.legacy(root, args.source)
            print('Private profile imported. No running containers changed. Review ./deskharbor plan before applying.')
        elif args.command == 'plan':
            c = config.load(root)
            print(actions.plan(c))
            print('\nConnection addresses:\n' + actions.addresses(c))
            config.render(root, c)
        elif args.command == 'update': actions.update(root)
        else:
            c = config.load(root)
            if args.command == 'up': print(actions.plan(c), flush=True)
            actions.perform(root, args.command, c)
        return 0
    except (ValueError, OSError, curses.error, subprocess.CalledProcessError) as error:
        print('DeskHarbor: ' + str(error), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled; persistent data was not removed.', file=sys.stderr)
        return 130
