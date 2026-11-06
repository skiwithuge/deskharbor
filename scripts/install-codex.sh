#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) != 0 ]] || { echo 'Run as the workstation user, not root.' >&2; exit 1; }
version=${1:-latest}
[[ $version =~ ^[a-zA-Z0-9.+_-]+$ ]] || { echo 'Invalid npm version/tag' >&2; exit 1; }
npm install --global --prefix "$HOME/.local/npm" "@openai/codex@$version"
"$HOME/.local/npm/bin/codex" --version
