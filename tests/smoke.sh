#!/usr/bin/env bash
# Runs an isolated container: no published ports, real passwords, or host settings mounts.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")/.."
image=${1:-deskharbor:local}
task_tmp=$(mktemp -d /tmp/deskharbor-workstation-check.XXXXXXXX)
name="workstation-check-$(basename "$task_tmp")"
home_volume="$name-home"; key_volume="$name-keys"
cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
    docker volume rm "$home_volume" "$key_volume" >/dev/null 2>&1 || true
    rm -rf -- "$task_tmp"
}
trap cleanup EXIT
umask 077
printf 'test1234' > "$task_tmp/vnc_password"
printf 'temporary-test-only-password' > "$task_tmp/ssh_password"
docker volume create "$home_volume" >/dev/null
docker volume create "$key_volume" >/dev/null
start() {
    docker run -d --name "$name" "${gpu_args[@]}" --shm-size=2g -e SSH_AUTH_MODE=password \
      --mount "type=bind,source=$task_tmp,target=/run/secrets,readonly" \
      --mount "type=volume,source=$home_volume,target=/home/deskharbor" \
      --mount "type=volume,source=$key_volume,target=/var/lib/workstation/ssh" "$image" >/dev/null
    for attempt in $(seq 1 45); do
        if docker exec "$name" /opt/workstation/healthcheck.sh >/dev/null 2>&1; then return; fi
        sleep 2
    done
    docker logs "$name"
    exit 1
}
start
docker exec --user deskharbor "$name" bash -c '
    fc-match -f "%{family}\n" "Fira Code" | grep -Fx "Fira Code"
    fc-match -f "%{family}\n" "emoji:charset=1f600" | grep -Fx "Noto Color Emoji"
    gsettings get com.gexperts.Tilix.Settings theme-variant | grep -w dark
    test -f ~/.local/state/workstation/terminal-defaults-v1
    tilix --version
    dbus-run-session -- tilix -e /usr/bin/true
'
if [[ ${DESKHARBOR_TEST_GPU:-0} == 1 ]]; then
docker exec "$name" nvidia-smi --query-gpu=name --format=csv,noheader
docker exec "$name" nvcc --version | tail -2
# Check actual CUDA computation, not just driver visibility.
docker exec -i "$name" bash <<'CUDA'
set -e
cat > /tmp/check.cu <<'CODE'
#include <cuda_runtime.h>
#include <stdio.h>
__global__ void kernel(int *x) { *x=7; }
int main() {
  int *device=nullptr, result=0;
  if(cudaMalloc(&device,sizeof(int))!=cudaSuccess) return 1;
  kernel<<<1,1>>>(device);
  if(cudaMemcpy(&result,device,sizeof(int),cudaMemcpyDeviceToHost)!=cudaSuccess) return 2;
  cudaFree(device);
  if(result!=7) return 3;
  puts("CUDA kernel passed");
}
CODE
nvcc /tmp/check.cu -o /tmp/check
/tmp/check
CUDA
fi
docker cp tests/audio.py "$name:/tmp/audio.py"
# The integration check expects the repository layout; mount a temporary test copy.
docker exec "$name" mkdir -p /tmp/audio-check/scripts /tmp/audio-check/config /tmp/audio-check/tests
docker exec "$name" cp /opt/workstation/audio-server.py /tmp/audio-check/scripts/
docker exec "$name" cp -r /etc/workstation/audio /tmp/audio-check/config/
docker exec "$name" cp /tmp/audio.py /tmp/audio-check/tests/audio.py
docker exec --user deskharbor "$name" python3 /tmp/audio-check/tests/audio.py
docker cp tests/desktop-boot.py "$name:/tmp/desktop-boot.py"
docker exec --user deskharbor "$name" python3 /tmp/desktop-boot.py
docker cp tests/vnc-resize.py "$name:/tmp/vnc-resize.py"
docker exec "$name" python3 /tmp/vnc-resize.py 1440 900
docker exec --user deskharbor "$name" bash -c 'xrandr --current | head -1 | grep "current 1440 x 900"'
docker exec --user deskharbor "$name" display-mode fixed 1920 1080
docker exec "$name" python3 /tmp/vnc-resize.py 1280 720
docker exec --user deskharbor "$name" bash -c 'xrandr --current | head -1 | grep "current 1920 x 1080"'
docker exec --user deskharbor "$name" bash -c 'pgrep -x metacity; printf persistence > ~/.workstation-check'
key_before=$(docker exec "$name" sha256sum /var/lib/workstation/ssh/ssh_host_ed25519_key)
# Exercise both public commands without supplying the wrapper's flags ourselves.
for browser in google-chrome google-chrome-stable; do
    docker exec --user deskharbor "$name" "$browser" --headless --dump-dom 'data:text/html,<title>workstation-check</title>' 2>/dev/null | grep workstation-check
done
# Password authentication without an interactive terminal.
docker exec "$name" bash -c 'printf "#!/bin/sh\ncat /run/secrets/ssh_password\n" > /tmp/check-askpass; chmod 755 /tmp/check-askpass'
# Run askpass as root only in this disposable test so it can read the test secret.
docker exec "$name" bash -c 'SSH_ASKPASS_REQUIRE=force SSH_ASKPASS=/tmp/check-askpass setsid -w ssh -o PubkeyAuthentication=no -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null deskharbor@127.0.0.1 "test \"\$(id -un)\" = deskharbor"'
# Key auth plus direct forwarding: SSH reaches the same noVNC listener.
docker exec --user deskharbor "$name" bash -c 'ssh-keygen -q -t ed25519 -N "" -f ~/.ssh/check; cat ~/.ssh/check.pub >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys'
docker exec --user deskharbor "$name" bash -c 'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ~/.ssh/check -L 127.0.0.1:16080:127.0.0.1:6080 -fN "$(id -un)@127.0.0.1"; curl -fsS http://127.0.0.1:16080/ >/dev/null'
docker rm -f "$name" >/dev/null
start
key_after=$(docker exec "$name" sha256sum /var/lib/workstation/ssh/ssh_host_ed25519_key)
[[ $key_before == "$key_after" ]]
docker exec --user deskharbor "$name" bash -c 'test "$(cat ~/.workstation-check)" = persistence; xrandr --current | head -1 | grep "current 1920 x 1080"'
docker exec --user deskharbor "$name" display-mode auto
docker exec --user deskharbor "$name" bash -c 'test ! -e ~/.vnc/geometry; test "$(cat ~/.vnc/display-mode)" = auto'
echo 'Smoke checks passed: desktop/services, VNC auth/resize lock, CUDA kernel, Chrome, SSH tunnel, persistent home/host keys.'
