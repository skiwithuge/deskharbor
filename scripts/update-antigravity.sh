#!/usr/bin/env bash
set -euo pipefail
# An update is a fresh, explicit archive install. No background updater.
exec /opt/workstation/install-antigravity.sh "$@"
