#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) == 0 ]]; then
    exec /opt/workstation/record-system-tools.sh
fi
exec sudo /opt/workstation/record-system-tools.sh
