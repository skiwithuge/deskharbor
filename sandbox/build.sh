#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
exec docker build --tag deskharbor-agent-sandbox:local \
    --build-arg "WORKSTATION_IMAGE=${WORKSTATION_IMAGE:-deskharbor:local}" \
    --build-arg "USER_UID=${WORKSTATION_UID:-$(id -u)}" \
    --build-arg "USER_GID=${WORKSTATION_GID:-$(id -g)}" \
    --build-arg "CODEX_VERSION=${CODEX_VERSION:-0.167.0}" .
