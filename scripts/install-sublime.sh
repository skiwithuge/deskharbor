#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 ]]; then exec sudo "$0" "$@"; fi
apt-get update
apt-get install -y --no-install-recommends sublime-text
