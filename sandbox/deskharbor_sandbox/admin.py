"""Root-only registration; never exposed through the SSH request protocol."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

CONFIG = Path('/etc/deskharbor-sandbox/host.json')


def main():
    if os.getuid() != 0:
        raise SystemExit('Run host administration with sudo.')
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    register = sub.add_parser('register')
    register.add_argument('id')
    register.add_argument('host_path')
    register.add_argument('--workstation-path', required=True)
    register.add_argument('--hide', action='append', default=[])
    register.add_argument('--allow-gpu', action='store_true')
    remove = sub.add_parser('unregister')
    remove.add_argument('id')
    image = sub.add_parser('image')
    image.add_argument('tag')
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    if args.action == 'register':
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.id):
            parser.error('Use a simple project ID: letters, digits, dash or underscore.')
        root = Path(args.host_path).resolve(strict=True)
        if not root.is_dir() or root.stat().st_uid != config['uid']:
            parser.error('Project must be a directory owned by the configured host user.')
        import pwd
        home = Path(pwd.getpwuid(config['uid']).pw_dir)
        if root == home or root in home.parents or ',' in str(root):
            parser.error('Do not register home, its parents, or paths containing commas.')
        workstation = Path(args.workstation_path)
        if not workstation.is_absolute() or '..' in workstation.parts:
            parser.error('Workstation path must be absolute and normalized.')
        for hidden in args.hide:
            path = Path(hidden)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                parser.error('--hide requires a relative project path.')
        config['projects'][args.id] = {'host_path': str(root),
                                      'workstation_path': str(workstation),
                                      'hidden_paths': args.hide, 'allow_gpu': args.allow_gpu}
    elif args.action == 'unregister':
        config['projects'].pop(args.id, None)
    else:
        if args.tag.startswith('-'):
            parser.error('Invalid image tag.')
        result = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.tag],
                                text=True, capture_output=True, check=True)
        config['image'] = result.stdout.strip()
    fd, name = tempfile.mkstemp(dir=CONFIG.parent, prefix='.host-')
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(config, output, indent=2)
            output.write('\n')
        os.chmod(name, 0o644)
        os.replace(name, CONFIG)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print('Host sandbox policy updated.')


if __name__ == '__main__':
    main()
