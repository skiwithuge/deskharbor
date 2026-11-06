#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run this once on the HOST using sudo.' >&2; exit 1; }
[[ ! -e /.dockerenv ]] || { echo 'This installer must run on the host, outside Docker.' >&2; exit 1; }
source_dir=$(dirname "$(realpath "$0")")
host_user=${SUDO_USER:-deskharbor}
host_address=${1:?Usage: sudo ./sandbox/setup-host.sh HOST_ADDRESS [WORKSTATION_CONTAINER]}
container=${2:-deskharbor-workstation-1}
[[ $host_user != root ]] || { echo 'Invoke with sudo from your normal host account.' >&2; exit 1; }
[[ $host_address =~ ^[A-Za-z0-9.:-]+$ && $host_address != -* ]] || exit 1
host_uid=$(id -u "$host_user")
host_gid=$(id -g "$host_user")
host_home=$(getent passwd "$host_user" | cut -d: -f6)
[[ -c /dev/fuse ]] || { echo 'FUSE device missing. Enable FUSE on the host first.' >&2; exit 1; }
command -v fusermount3 >/dev/null
command -v sshd >/dev/null
docker image inspect deskharbor-agent-sandbox:local >/dev/null
docker inspect "$container" >/dev/null
container_user=$(docker exec "$container" printenv WORKSTATION_USER)
[[ $container_user =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "Invalid workstation username" >&2; exit 1; }
container_uid=$(docker exec "$container" id -u "$container_user")
[[ $container_uid == "$host_uid" ]] || { echo 'Host and workstation UID must match.' >&2; exit 1; }
apt-get update
apt-get install -y --no-install-recommends fuse3 libfuse2t64 python3-venv openssh-server
install -d -m 755 /opt/deskharbor-sandbox /etc/deskharbor-sandbox
cp -a "$source_dir/deskharbor_sandbox" /opt/deskharbor-sandbox/
install -m 755 "$source_dir/host-entry.py" "$source_dir/admin-entry.py" /opt/deskharbor-sandbox/
printf '%s\n' '#!/bin/sh' 'exec /opt/deskharbor-sandbox/venv/bin/python -I /opt/deskharbor-sandbox/admin-entry.py "$@"' > /usr/local/sbin/deskharbor-sandbox-admin
chmod 755 /usr/local/sbin/deskharbor-sandbox-admin
python3 -m venv /opt/deskharbor-sandbox/venv
/opt/deskharbor-sandbox/venv/bin/pip install --disable-pip-version-check -r "$source_dir/requirements.txt"
chown -R root:root /opt/deskharbor-sandbox
chmod -R go-w /opt/deskharbor-sandbox
# Docker's root daemon must be able to bind the user-owned filtered FUSE view.
if ! grep -qx 'user_allow_other' /etc/fuse.conf; then
    cp -a /etc/fuse.conf /etc/deskharbor-sandbox/fuse.conf.before-install
    printf '\nuser_allow_other\n' >> /etc/fuse.conf
fi
image_id=$(docker image inspect --format '{{.Id}}' deskharbor-agent-sandbox:local)
HOST_UID="$host_uid" HOST_GID="$host_gid" HOST_HOME="$host_home" IMAGE_ID="$image_id" python3 - <<'PY'
import json, os
from pathlib import Path
path = Path('/etc/deskharbor-sandbox/host.json')
if path.exists():
    config = json.loads(path.read_text())
    if config['uid'] != int(os.environ['HOST_UID']):
        raise SystemExit('Existing sandbox installation belongs to another user.')
else:
    config = {'version': 1, 'uid': int(os.environ['HOST_UID']),
              'gid': int(os.environ['HOST_GID']),
              'state_dir': os.environ['HOST_HOME'] + '/.local/state/deskharbor-sandbox',
              'projects': {}, 'blocked_ips': []}
config['image'] = os.environ['IMAGE_ID']
path.write_text(json.dumps(config, indent=2) + '\n')
path.chmod(0o644)
PY
install -d -m 700 -o "$host_uid" -g "$host_gid" "$host_home/.local/state/deskharbor-sandbox" "$host_home/.ssh"
key="$host_home/.local/state/deskharbor-sandbox/client-key"
if [[ ! -f $key ]]; then
    runuser -u "$host_user" -- ssh-keygen -q -t ed25519 -N '' -C deskharbor-workstation-sandbox -f "$key"
fi
entry="restrict,pty,command=\"/opt/deskharbor-sandbox/venv/bin/python -I /opt/deskharbor-sandbox/host-entry.py\" $(cat "$key.pub")"
touch "$host_home/.ssh/authorized_keys"
if ! grep -Fqx -- "$entry" "$host_home/.ssh/authorized_keys"; then
    printf '%s\n' "$entry" >> "$host_home/.ssh/authorized_keys"
fi
chown "$host_uid:$host_gid" "$host_home/.ssh/authorized_keys"
chmod 600 "$host_home/.ssh/authorized_keys"
docker exec -u "$host_uid:$host_gid" "$container" sh -c \
    'umask 077; mkdir -p "$HOME/.config/deskharbor-sandbox" "$HOME/.local/lib/deskharbor-sandbox" "$HOME/.local/bin"'
docker exec -i -u "$host_uid:$host_gid" "$container" sh -c \
    'umask 077; cat > "$HOME/.config/deskharbor-sandbox/id_ed25519"; chmod 600 "$HOME/.config/deskharbor-sandbox/id_ed25519"' < "$key"
docker exec -i -u "$host_uid:$host_gid" "$container" sh -c \
    'cat > "$HOME/.local/lib/deskharbor-sandbox/client.py"' < "$source_dir/deskharbor_sandbox/client.py"
HOST_ADDRESS="$host_address" HOST_USER="$host_user" python3 - <<'PY' | docker exec -i -u "$host_uid:$host_gid" "$container" sh -c 'umask 077; cat > "$HOME/.config/deskharbor-sandbox/client.json"'
import json, os
print(json.dumps({'host': os.environ['HOST_ADDRESS'], 'user': os.environ['HOST_USER'], 'port': 22,
                  'identity_file': '~/.config/deskharbor-sandbox/id_ed25519',
                  'known_hosts': '~/.config/deskharbor-sandbox/known_hosts'}))
PY
printf '%s %s\n' "$host_address" "$(cat /etc/ssh/ssh_host_ed25519_key.pub)" | \
    docker exec -i -u "$host_uid:$host_gid" "$container" sh -c 'cat > "$HOME/.config/deskharbor-sandbox/known_hosts"'
printf '%s\n' '#!/usr/bin/env bash' 'exec python3 -I "$HOME/.local/lib/deskharbor-sandbox/client.py" "$@"' | \
    docker exec -i -u "$host_uid:$host_gid" "$container" sh -c 'cat > "$HOME/.local/bin/deskharbor-sandbox"; chmod 755 "$HOME/.local/bin/deskharbor-sandbox"'
printf '%s\n' 'Host helper and persistent workstation client installed.' \
    'Register a project using the commands in sandbox/README.md.'
