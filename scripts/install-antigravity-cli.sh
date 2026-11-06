#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) != 0 ]] || { echo 'Run as the workstation user, not root.' >&2; exit 1; }
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
curl --proto '=https' --proto-redir '=https' -fsSL --retry 3 \
    https://antigravity.google/cli/install.sh -o "$stage/install.sh"
mkdir -p "$stage/home" "$HOME/.local/bin"
# Google's installer verifies its release checksum and configures shell profiles.
# Isolate that configuration step; our workstation PATH already includes ~/.local/bin.
HOME="$stage/home" bash "$stage/install.sh" --dir "$stage/bin"
HOME="$stage/home" "$stage/bin/agy" --version
if [[ -f $HOME/.local/bin/agy ]]; then
    cp -p -- "$HOME/.local/bin/agy" "$HOME/.local/bin/agy.previous"
fi
install -m 755 "$stage/bin/agy" "$HOME/.local/bin/agy.new"
mv -f -- "$HOME/.local/bin/agy.new" "$HOME/.local/bin/agy"
"$HOME/.local/bin/agy" --version
