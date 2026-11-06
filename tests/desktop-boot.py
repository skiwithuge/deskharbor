#!/usr/bin/env python3
"""Boot GNOME on a private display; never restart the user's desktop."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

parser = argparse.ArgumentParser()
parser.add_argument('--session', default='deskharbor-flashback')
parser.add_argument('--config-dir', default='/etc/workstation/desktop')
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='deskharbor-desktop-boot-') as temporary:
    root = Path(temporary)
    for directory in ('home', 'runtime', 'config', 'cache', 'data'):
        (root / directory).mkdir(mode=0o700)
    env = dict(os.environ, HOME=str(root / 'home'),
               XDG_RUNTIME_DIR=str(root / 'runtime'),
               XDG_CONFIG_HOME=str(root / 'config'),
               XDG_CACHE_HOME=str(root / 'cache'),
               XDG_DATA_HOME=str(root / 'data'),
               XDG_CONFIG_DIRS=args.config_dir + ':/etc/xdg',
               XDG_CURRENT_DESKTOP='GNOME-Flashback:GNOME',
               LIBGL_ALWAYS_SOFTWARE='1')
    env.pop('DBUS_SESSION_BUS_ADDRESS', None)
    # Let the X server choose a free display. No TCP or VNC listeners.
    read_fd, write_fd = os.pipe()
    session = None
    with (root / 'x.log').open('w') as xlog, (root / 'session.log').open('w') as slog:
        server = subprocess.Popen(['Xtigervnc', '-displayfd', str(write_fd),
                                   '-rfbport', '-1', '-nolisten', 'tcp',
                                   '-SecurityTypes', 'None', '-geometry', '1024x768'],
                                  pass_fds=(write_fd,), env=env, stdout=xlog, stderr=xlog)
        os.close(write_fd)
        try:
            import select
            assert select.select([read_fd], [], [], 5)[0], 'Test X server did not start'
            display = os.read(read_fd, 32).decode().strip()
            assert display.isdigit(), 'No test display allocated'
            env['DISPLAY'] = ':' + display
            session = subprocess.Popen(['dbus-run-session', '--', 'gnome-session',
                                        '--session=' + args.session], env=env,
                                       stdout=slog, stderr=slog, start_new_session=True)
            time.sleep(12)
            text = (root / 'session.log').read_text(errors='replace')
            errors = [line for line in text.splitlines()
                      if ('gnome-session-binary' in line and 'App ' in line and 'exited with code 1' in line)
                      or 'Unrecoverable failure' in line]
            assert not errors, '\n'.join(errors)
            assert session.poll() is None, 'GNOME session exited during boot'
            windows = subprocess.run(['xwininfo', '-root', '-tree'], env=env,
                                     capture_output=True, text=True, timeout=5)
            assert windows.returncode == 0, 'Cannot inspect test desktop'
            assert 'gnome-session-failed' not in windows.stdout, 'GNOME failure dialog shown'
            assert 'gnome-panel' in windows.stdout, 'Desktop panel did not start'
            print('PASS: isolated GNOME boot; panel active; no failed required applications')
        finally:
            os.close(read_fd)
            if session is not None:
                try:
                    os.killpg(session.pid, signal.SIGTERM)
                    session.wait(timeout=4)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(session.pid, signal.SIGKILL)
                    session.wait()
            server.terminate()
            server.wait(timeout=4)
