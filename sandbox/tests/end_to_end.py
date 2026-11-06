"""Run the real broker against disposable fixtures after host FUSE activation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deskharbor_sandbox.broker import run

parser = argparse.ArgumentParser()
parser.add_argument('--image', default='deskharbor-agent-sandbox:local')
parser.add_argument('--gpu', action='store_true')
args = parser.parse_args()
image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', args.image], text=True).strip()
with tempfile.TemporaryDirectory(prefix='deskharbor-full-probe-') as directory:
    root = Path(directory)
    project, state = root / 'project', root / 'state'
    project.mkdir()
    state.mkdir(mode=0o700)
    (project / '.env').write_text('synthetic-secret')
    (root / 'outside').write_text('synthetic-outside-secret')
    (project / 'outside-link').symlink_to(root / 'outside')
    config = {'uid': os.getuid(), 'gid': os.getgid(), 'image': image,
              'state_dir': str(state), 'projects': {'probe': {'host_path': str(project),
              'workstation_path': '/probe', 'allow_gpu': args.gpu}}, 'blocked_ips': []}
    script = '''set -eu
! test -e /project/.env
! test -e /project/outside-link
printf verified > /project/output
git init -q
git -c user.name=Probe -c user.email=probe@example.invalid add output
git -c user.name=Probe -c user.email=probe@example.invalid commit -qm probe
curl --fail --silent https://example.com > /tmp/public-response
printf persisted > "$HOME/persistence-probe"
'''
    if args.gpu:
        script += 'nvidia-smi\n'
    request = {'action': 'run', 'project': 'probe', 'agent': 'shell', 'gpu': args.gpu, 'args': ['-c', script]}
    assert run(config, request) == 0
    assert (project / 'output').read_text() == 'verified'
    assert (project / '.env').read_text() == 'synthetic-secret'
    assert (root / 'outside').read_text() == 'synthetic-outside-secret'
    request['args'] = ['-c', 'test "$(cat "$HOME/persistence-probe")" = persisted']
    assert run(config, request) == 0
    assert not list((state / 'active').iterdir())
    assert not list((state / 'runs').iterdir())
    print('Broker/FUSE/container live edits, Git, public HTTPS, secret masking, private home and cleanup passed.')
