#!/usr/bin/env bash
set -euo pipefail
[[ -x /usr/bin/chatgpt ]] || { echo 'Run install-codex-app first.' >&2; exit 1; }
exec /usr/bin/chatgpt --no-sandbox --disable-dev-shm-usage --ozone-platform=x11 "$@"
