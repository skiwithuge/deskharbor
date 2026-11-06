"""Run on the host against a synthetic project; always unmount and clean up."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

base = Path(__file__).resolve().parents[1]
allow_other = '--allow-other' in sys.argv
with tempfile.TemporaryDirectory(prefix='deskharbor-fuse-probe-') as temp:
    stage = Path(temp)
    project, view = stage / 'project', stage / 'view'
    project.mkdir()
    view.mkdir()
    (project / 'normal').write_text('visible')
    (project / '.env').write_text('synthetic-secret')
    command = [sys.executable, '-m', 'deskharbor_sandbox.projectfs', str(project), str(view)]
    if allow_other:
        command += ['--allow-other']
    process = subprocess.Popen(command,
                               env={**os.environ, 'PYTHONPATH': str(base)})
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('FUSE process failed')
            if os.path.ismount(view):
                break
            time.sleep(.05)
        else:
            raise RuntimeError('FUSE mount timed out')
        assert (view / 'normal').read_text() == 'visible'
        try:
            (view / '.env').read_text()
            raise AssertionError('Secret visible')
        except PermissionError:
            pass
        (view / 'from-view').write_text('live')
        assert (project / 'from-view').read_text() == 'live'
        (project / 'nested').mkdir()
        (project / 'nested/.env.new').write_text('late-secret')
        assert '.env.new' not in os.listdir(view / 'nested')
        try:
            (view / 'nested/.env.new').read_text()
            raise AssertionError('Late secret visible')
        except PermissionError:
            pass
        subprocess.run(['git', '-C', str(view), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(view), 'add', 'normal', 'from-view'], check=True)
        subprocess.run(['git', '-C', str(view), '-c', 'user.name=Probe',
                        '-c', 'user.email=probe@example.invalid', 'commit', '-qm', 'probe'], check=True)
        assert (project / '.git').is_dir()
        result = subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                                 '--user', str(os.getuid()), '--cap-drop', 'ALL',
                                 '--security-opt', 'no-new-privileges',
                                 '--mount', f'type=bind,src={view},dst=/project',
                                 '--entrypoint', 'python3', 'deskharbor:local', '-c',
                                 'from pathlib import Path; print(Path("/project/normal").read_text())'],
                                capture_output=True, text=True)
        print('Kernel FUSE live writes, Git commit, late-secret masking tests passed.')
        print('Docker bind without allow_other:', result.returncode, result.stdout.strip(), result.stderr.strip())
        if allow_other:
            assert result.returncode == 0
        (project / 'main.c').write_text('int main(void) { return 0; }')
        subprocess.run(['gcc', str(project / 'main.c'), '-o', str(project / 'program')], check=True)
        executable = subprocess.run([str(view / 'program')], capture_output=True)
        print('Execute compiled binary through FUSE:', executable.returncode)
        assert executable.returncode == 0
    finally:
        unmount = ['fusermount3', '-u', str(view)]
        subprocess.run(unmount, check=False)
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            subprocess.run(['kill', '-TERM', str(process.pid)])
            process.wait(5)
