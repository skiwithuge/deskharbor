#!/usr/bin/env bash
# Verify real Homebrew bottles and persistence using isolated volumes.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")/.."
image=${1:-deskharbor:local}
task_tmp=$(mktemp -d /tmp/deskharbor-brew-check.XXXXXXXX)
name="brew-check-$(basename "$task_tmp")"
home_volume="$name-home"; brew_volume="$name-brew"
cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker volume rm "$home_volume" "$brew_volume" >/dev/null 2>&1 || true
    rm -rf -- "$task_tmp"
}
trap cleanup EXIT
umask 077
printf test1234 > "$task_tmp/vnc_password"
printf temporary-test-only-password > "$task_tmp/ssh_password"
docker volume create "$home_volume" >/dev/null
docker volume create "$brew_volume" >/dev/null
start() {
    docker run -d -e SSH_AUTH_MODE=password --name "$name" --shm-size=2g \
        --mount "type=bind,source=$task_tmp,target=/run/secrets,readonly" \
        --mount "type=volume,source=$home_volume,target=/home/deskharbor" \
        --mount "type=volume,source=$brew_volume,target=/home/linuxbrew/.linuxbrew" "$image" >/dev/null
    for attempt in $(seq 1 45); do
        if docker exec "$name" /opt/workstation/healthcheck.sh >/dev/null 2>&1; then return; fi
        sleep 1
    done
    docker logs "$name"; exit 1
}
start
docker exec --user deskharbor "$name" install-brew
docker exec --user deskharbor "$name" bash -c 'set -e; test "$(brew --prefix)" = /home/linuxbrew/.linuxbrew; HOMEBREW_NO_AUTO_UPDATE=1 brew install hello; test "$(hello)" = "Hello, world!"'
docker rm -f "$name" >/dev/null
start
docker exec --user deskharbor "$name" bash -c 'set -e; brew --version; test "$(hello)" = "Hello, world!"; test "$(stat -c %U /home/linuxbrew/.linuxbrew)" = deskharbor'
docker exec --user deskharbor "$name" bash -lc 'test "$(hello)" = "Hello, world!"'
echo 'Homebrew default prefix, bottle execution, agent/login Bash and volume persistence passed.'
