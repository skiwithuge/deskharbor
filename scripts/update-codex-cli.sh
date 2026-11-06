#!/usr/bin/env bash
set -euo pipefail
exec /opt/workstation/install-codex.sh "${1:-latest}"
