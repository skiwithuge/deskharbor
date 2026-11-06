#!/usr/bin/env bash
# Real package, isolated home: verify GUI and cached restore on recreation.
set -euo pipefail
package=$(realpath "${1:?Usage: bash tests/codex-app.sh /path/to/chatgpt_amd64.deb [IMAGE]}")
image=${2:-deskharbor:local}
cd "$(dirname "$(realpath "$0")")/.."
task_tmp=$(mktemp -d /tmp/deskharbor-codex-check.XXXXXXXX)
name="codex-check-$(basename "$task_tmp")"
volume="$name-home"
cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker volume rm "$volume" >/dev/null 2>&1 || true
    rm -rf -- "$task_tmp"
}
trap cleanup EXIT
umask 077
printf test1234 > "$task_tmp/vnc_password"
printf temporary-test-only-password > "$task_tmp/ssh_password"
docker volume create "$volume" >/dev/null
start() {
    docker run -d -e SSH_AUTH_MODE=password --name "$name" --shm-size=2g \
        --mount "type=bind,source=$task_tmp,target=/run/secrets,readonly" \
        --mount "type=volume,source=$volume,target=/home/deskharbor" "$image" >/dev/null
    for attempt in $(seq 1 90); do
        if docker exec "$name" /opt/workstation/healthcheck.sh >/dev/null 2>&1; then return; fi
        sleep 1
    done
    docker logs "$name"; exit 1
}
start
docker cp "$package" "$name:/tmp/chatgpt.deb"
docker exec "$name" chmod 644 /tmp/chatgpt.deb
docker exec "$name" install-codex-app /tmp/chatgpt.deb > "$task_tmp/install.log" 2>&1 || { tail -30 "$task_tmp/install.log"; exit 1; }
docker exec --user deskharbor "$name" bash -c 'grep -Fx chatgpt ~/.local/state/workstation/apt-packages.txt; test -f ~/.local/share/workstation/codex-app/chatgpt_amd64.deb'
docker cp tests/codex-window.py "$name:/tmp/codex-window.py"
docker exec --user deskharbor "$name" python3 /tmp/codex-window.py
before=$(docker exec "$name" dpkg-query -W -f='${Version}' chatgpt)
docker rm -f "$name" >/dev/null
start
after=$(docker exec "$name" dpkg-query -W -f='${Version}' chatgpt)
[[ $before == "$after" ]]
docker cp tests/codex-window.py "$name:/tmp/codex-window.py"
docker exec --user deskharbor "$name" python3 /tmp/codex-window.py
echo "Codex desktop $after passed GUI startup and cached-package restoration."
