#!/usr/bin/env bash
set -euo pipefail
exec python3 -I "$(dirname "$(realpath "$0")")/wizard.py" "$@"
