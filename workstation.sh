#!/usr/bin/env bash
# Compatibility entrypoint; use ./deskharbor for the main menu.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"
exec ./deskharbor "$@"
