#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 ]]; then exec sudo "$0" "$@"; fi
apt-get update
apt-get install -y --only-upgrade sublime-text
