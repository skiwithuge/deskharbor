"""Check launcher zoom isolation and profile validation without opening a GUI."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

source = Path(__file__).resolve().parents[1] / 'scripts/remmina-workstation.sh'
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'scripts').mkdir()
    launcher = root / 'scripts/remmina-workstation.sh'
    shutil.copy2(source, launcher)
    library = root / '.local/remmina/lib/libvncclient.so.1'
    library.parent.mkdir(parents=True)
    library.touch()
    binaries = root / 'bin'
    binaries.mkdir()
    for name, content in {
        'pgrep': '#!/bin/sh\nexit 1\n',
        'remmina': '#!/bin/sh\nprintf "ZOOM=%s BACKEND=%s\\n" "$DESKHARBOR_REMMINA_ZOOM" "$GDK_BACKEND"\nprintf "ARG=%s\\n" "$@"\n',
    }.items():
        path = binaries / name
        path.write_text(content)
        path.chmod(0o755)
    profile = root / 'profile with spaces.remmina'
    original = '[remmina]\nprotocol=VNC\nscale=2\npassword=public-test-fixture\n'
    profile.write_text(original)
    environment = dict(os.environ, PATH=f'{binaries}:{os.environ["PATH"]}', DESKHARBOR_REMMINA_ZOOM='150')

    def run(arguments):
        return subprocess.run([str(launcher), *arguments], env=environment, capture_output=True, text=True)

    for arguments, zoom in [
        ([str(profile)], '100'),
        (['--zoom', '150', str(profile)], '150'),
        (['--zoom', '125', str(profile)], '125'),
        ([str(profile), '--zoom=125'], '125'),
        ([str(profile), '--zoom=150'], '150'),
        (['--zoom', '100', '--', str(profile)], '100'),
    ]:
        result = run(arguments)
        assert result.returncode == 0, result.stderr
        assert f'ZOOM={zoom} BACKEND=x11' in result.stdout, result.stdout
        assert profile.read_text() == original, 'Launcher modified the saved profile'
    result = run(['--zoom', '150', '--fullscreen', str(profile)])
    assert result.returncode == 0, result.stderr
    assert 'ZOOM=150 BACKEND=x11' in result.stdout
    assert 'ARG=--enable-fullscreen' in result.stdout
    for arguments in [[], ['--zoom'], ['--zoom', '126', str(profile)], [str(profile), str(profile)]]:
        result = run(arguments)
        assert result.returncode != 0, arguments
        assert 'ZOOM=' not in result.stdout, 'Invalid arguments launched Remmina'
    for contents in ['[remmina]\nprotocol=RDP\nscale=2\n', '[remmina]\nprotocol=VNC\nscale=1\n']:
        profile.write_text(contents)
        result = run(['--zoom', '150', str(profile)])
        assert result.returncode != 0
        assert 'ZOOM=' not in result.stdout
        assert profile.read_text() == contents
print('PASS: default 100%, optional 125%/150%, process isolation and profile validation')
