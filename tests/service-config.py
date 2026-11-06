#!/usr/bin/env python3
"""Parse the real Supervisor template against all enabled-service combinations."""
import itertools
import os
import pwd
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from deskharbor import config
from supervisor.options import ServerOptions
root = Path(__file__).resolve().parents[1]
count = 0
for browser, vnc, ssh, audio in itertools.product((False, True), repeat=4):
    if not (browser or vnc or ssh) or (audio and not (browser or vnc)): continue
    c = config.defaults();c.update(uid=1000,gid=1000)
    c['features'].update(browser=browser,vnc=vnc,ssh=ssh,audio=audio)
    env=config.compose(root,c)['services']['workstation']['environment']
    os.environ.update(env,WORKSTATION_USER=pwd.getpwuid(os.getuid()).pw_name,HOME=pwd.getpwuid(os.getuid()).pw_dir,XDG_RUNTIME_DIR='/tmp/runtime-1000')
    options=ServerOptions()
    options.realize(['-c',str(root/'config/supervisord.conf')],doc='service test')
    enabled={process.name for group in options.process_group_configs for process in group.process_configs if process.autostart}
    expected={name for name in ('dbus','ssh','vnc','web','pulse','audio') if env['ENABLE_'+name.upper()]=='true'}
    assert enabled==expected,(enabled,expected)
    count+=1
print(f'PASS: Supervisor parsed {count} feature combinations with matching service activation')
