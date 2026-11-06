#!/usr/bin/env bash
set -euo pipefail
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
curl --proto '=https' --proto-redir '=https' -fsSL --retry 3 \
    https://antigravity.google/cli/install.sh -o "$stage/install.sh"
mkdir -p "$stage/home" "$HOME/.local/bin"
# Google's installer verifies the downloaded release checksum.
HOME="$stage/home" bash "$stage/install.sh" --dir "$HOME/.local/bin"
"$HOME/.local/bin/agy" --version
