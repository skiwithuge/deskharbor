#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/google-chrome-stable --no-sandbox --disable-dev-shm-usage "$@"
