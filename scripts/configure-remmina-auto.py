#!/usr/bin/env python3
"""Enable dynamic sizing for one host Remmina VNC profile, retaining a backup."""
import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('profile', type=Path, help='Host .remmina connection profile')
args = parser.parse_args()
profile = args.profile.expanduser().resolve()
original = profile.read_text()
if not re.search(r'^protocol=VNC\s*$', original, re.MULTILINE):
    parser.error('The selected profile is not a VNC connection')
if not re.search(r'^\[remmina\]\s*$', original, re.MULTILINE):
    parser.error('Missing [remmina] section')
updated = original
for key, value in [('scale', '2'), ('aspect_ratio', '')]:
    pattern = rf'^{key}=.*$'
    if re.search(pattern, updated, re.MULTILINE):
        updated = re.sub(pattern, f'{key}={value}', updated, flags=re.MULTILINE)
    else:
        updated = updated.replace('[remmina]', f'[remmina]\n{key}={value}', 1)
if updated == original:
    print('Dynamic resizing is already configured.')
else:
    backup = profile.with_name(profile.name + '.before-auto-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    shutil.copy2(profile, backup)
    profile.write_text(updated)
    print(f'Enabled dynamic resizing: {profile}')
    print(f'Backup: {backup}')
print('Open/reconnect this profile in Remmina to apply the saved setting.')
