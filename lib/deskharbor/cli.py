"""DeskHarbor command line and TUI entrypoint."""
import argparse
import curses
from pathlib import Path
import subprocess
import sys
from . import actions, config, tui


def build_parser():
    parser = argparse.ArgumentParser(
        prog='deskharbor',
        description='Manage a persistent Linux workstation in Docker. Run without a command to open the interactive menu.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  ./deskharbor                 Open the interactive menu
  ./deskharbor setup           Configure a new installation
  ./deskharbor doctor          Check the host and saved configuration
  ./deskharbor up              Build and start the workstation
  ./deskharbor status          Show container status and connection addresses

Run ./deskharbor COMMAND --help for details about a command.
Run management commands on the Linux Docker host, as your normal user.
""")
    commands = parser.add_subparsers(dest='command', title='commands', metavar='COMMAND')
    descriptions = {
        'setup': ('Configure a new workstation (alias: init)',
                  'Choose a project folder, credentials and features interactively. Saves a private profile; does not start Docker. Use configure for an existing profile.'),
        'configure': ('Edit features, access, folders and ports',
                      'Edit the existing profile in the interactive menu. Changes stay staged until Save. Use up afterward to apply them to the workstation.'),
        'up': ('Build if needed, then start or apply changes',
               'Build the image if needed and start the saved configuration. May recreate an existing container: save open work first. Persistent volumes are retained.'),
        'build': ('Build the image without starting the workstation',
                  'Build the image selected by the saved profile. Does not start, stop or recreate the running workstation.'),
        'stop': ('Stop the workstation and retain its data',
                 'Stop the workstation services. Keeps containers, persistent volumes, installed user tools and project files. Use up to start again.'),
        'status': ('Show container status and connection addresses',
                   'Show the Compose container status and browser, VNC, SSH or audio addresses enabled by the saved profile. Does not start the workstation.'),
        'logs': ('Follow service logs until Ctrl+C',
                 'Show the last 100 log lines and follow new output. Ctrl+C stops viewing logs; services keep running. When opened from the interactive menu, Ctrl+C returns to that menu.'),
        'shell': ('Open a terminal inside the running workstation',
                  'Open a Bash shell as the workstation user. Type exit or press Ctrl+D to leave the shell. The workstation must already be running.'),
        'apps': ('Install or update optional applications',
                 'Open the application selection menu inside the running workstation. Choose install or update and select the tools to manage. Application login remains interactive.'),
        'doctor': ('Check prerequisites and saved configuration',
                   'After setup, check Docker access, Compose, required credentials, shared folder paths and optional NVIDIA support. Validate the generated Compose definition without starting services.'),
        'plan': ('Review saved settings without starting Docker',
                 'Show enabled features, networking, project folder, persistent volumes and connection addresses. Regenerates the private Compose file; starts no containers.'),
        'update': ('Download DeskHarbor source updates only',
                   'Update this checkout with git pull --ff-only. Requires a clean source tree and Git access to the repository. Does not restart services or update installed applications; use up to apply image changes.'),
        'sandbox': ('Open the optional agent sandbox manager',
                    'Open the experimental project sandbox wizard on the host. Requires whiptail and a running workstation; provisioning may request sudo for host FUSE and SSH setup.'),
        'import-legacy': ('Import an earlier workstation profile (advanced)',
                          'Import the supported legacy workstation layout into private local files. Requires no existing DeskHarbor profile. Preserves references to existing volumes and starts no containers; this is not a general Docker importer.'),
    }
    for name, (summary, detail) in descriptions.items():
        options = {'aliases': ['init']} if name == 'setup' else {}
        child = commands.add_parser(name, help=summary, description=detail, **options)
        if name == 'import-legacy':
            child.add_argument('source', metavar='OLD_REPOSITORY', help='Path to the earlier workstation repository containing compose.yaml, .env and secrets')
    return parser


def main(root=None):
    root = Path(root or Path(__file__).resolve().parents[2]).resolve()
    parser = build_parser()
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
