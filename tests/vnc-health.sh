#!/usr/bin/env bash
# Exercise repeated production health checks without touching the user's desktop.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")/.."
image=${1:-deskharbor:local}
task_tmp=$(mktemp -d /tmp/deskharbor-vnc-health.XXXXXXXX)
name="vnc-health-$(basename "$task_tmp")"
cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
    rm -rf -- "$task_tmp"
}
trap cleanup EXIT
umask 077
printf 'test1234' > "$task_tmp/vnc_password"
printf 'temporary-test-only-password' > "$task_tmp/ssh_password"
docker run -d -e SSH_AUTH_MODE=password --name "$name" --no-healthcheck \
    --mount "type=bind,source=$task_tmp,target=/run/secrets,readonly" "$image" >/dev/null
docker cp scripts/vnc-health.py "$name:/tmp/vnc-health.py"
ready=false
for attempt in $(seq 1 30); do
    if docker exec "$name" /opt/workstation/healthcheck.sh >/dev/null 2>&1; then ready=true; break; fi
    sleep 1
done
[[ $ready == true ]] || { docker logs "$name"; exit 1; }
# No intervening authenticated client: this is the idle-workstation failure pattern.
for attempt in $(seq 1 20); do
    docker exec "$name" /opt/workstation/healthcheck.sh
done
docker exec "$name" python3 /tmp/vnc-health.py
echo 'Repeated health checks preserve authenticated browser VNC access.'
