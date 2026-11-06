#!/usr/bin/env bash
# Isolated check: no host settings, published ports, or production volumes.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")/.."
image=${1:-deskharbor:local}
task_tmp=$(mktemp -d /tmp/deskharbor-tools-check.XXXXXXXX)
name="tools-check-$(basename "$task_tmp")"
home_volume="$name-home"
cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker volume rm "$home_volume" >/dev/null 2>&1 || true
    rm -rf -- "$task_tmp"
}
trap cleanup EXIT
umask 077
printf 'test1234' > "$task_tmp/vnc_password"
printf 'temporary-test-only-password' > "$task_tmp/ssh_password"
docker volume create "$home_volume" >/dev/null
start() {
    docker run -d -e SSH_AUTH_MODE=password --name "$name" --shm-size=2g \
        --mount "type=bind,source=$task_tmp,target=/run/secrets,readonly" \
        --mount "type=volume,source=$home_volume,target=/home/deskharbor" "$image" >/dev/null
    for attempt in $(seq 1 60); do
        if docker exec "$name" /opt/workstation/healthcheck.sh >/dev/null 2>&1; then return; fi
        sleep 2
    done
    docker logs "$name"; exit 1
}
start
docker exec --user deskharbor "$name" install-sublime
docker exec --user deskharbor "$name" subl --version
docker exec --user deskharbor "$name" install-dev-tools 22
docker exec --user deskharbor "$name" bash -c 'set -e; command -v nvm; pyenv --version; case "$(command -v node)" in "$HOME"/.nvm/*) ;; *) exit 1 ;; esac; python3 -m venv ~/.venvs/persist-check; ~/.venvs/persist-check/bin/python -c "import ssl, sqlite3, bz2, lzma"'
# Test ordinary apt installation, not a special wrapper.
docker exec "$name" bash -c 'apt-get update -qq; apt-get install -y -qq --no-install-recommends tree'
docker exec --user deskharbor "$name" bash -c 'grep -x tree ~/.local/state/workstation/apt-packages.txt'
node_before=$(docker exec --user deskharbor "$name" bash -c 'node --version')
docker rm -f "$name" >/dev/null
start
# The second container has a fresh system layer; startup must reinstall tree.
docker exec "$name" tree --version | head -1
docker exec --user deskharbor "$name" bash -c 'set -e; nvm --version; pyenv --version; ~/.venvs/persist-check/bin/python -c "import ssl, sqlite3, bz2, lzma"; grep -x tree ~/.local/state/workstation/apt-packages.txt'
node_after=$(docker exec --user deskharbor "$name" bash -c 'node --version')
[[ $node_before == "$node_after" ]]
echo 'Passed: Sublime, nvm/Node/pyenv, agent Bash initialization, Python venv persistence, apt recording and automatic restoration after recreation.'
