#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $(uname -m) == x86_64 ]] || { echo 'This Ubuntu 24.04 host workaround requires x86_64.' >&2; exit 1; }
mkdir -p "$root/.local/remmina/lib"
docker build --network=host -t deskharbor-remmina-client-fix -f "$root/scripts/remmina-client.Dockerfile" "$root/scripts"
docker run --rm -e "OUTPUT_UID=$(id -u)" -e "OUTPUT_GID=$(id -g)" \
    -v "$root/.local/remmina/lib:/out" deskharbor-remmina-client-fix
echo 'Ready. Close existing Remmina windows, then run scripts/remmina-workstation.sh [--zoom 100|125|150] PROFILE.remmina'
