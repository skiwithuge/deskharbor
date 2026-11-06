#!/usr/bin/env bash
set -euo pipefail
[[ $# == 0 ]] || { echo 'Usage: install-brew' >&2; exit 1; }
[[ $(id -u) != 0 ]] || { echo 'Run as the workstation user.' >&2; exit 1; }
prefix=/home/linuxbrew/.linuxbrew
# Avoid installing into an ephemeral layer before the new volume is applied.
python3 - <<'PY'
from pathlib import Path
mounts = [line.split()[4] for line in Path('/proc/self/mountinfo').read_text().splitlines()]
if '/home/linuxbrew/.linuxbrew' not in mounts:
    raise SystemExit('Homebrew volume is not mounted. Save running work and run ./workstation.sh up on the host first.')
PY
if [[ ! -x $prefix/bin/brew ]]; then
    stage=$(mktemp -d /tmp/deskharbor-brew-install.XXXXXXXX)
    trap 'rm -rf -- "$stage"' EXIT
    curl --proto '=https' --proto-redir '=https' -fsSL --retry 3 \
        https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$stage/install.sh"
    NONINTERACTIVE=1 /bin/bash "$stage/install.sh"
fi
eval "$("$prefix/bin/brew" shellenv bash)"
brew --version
echo 'Homebrew is ready in its persistent volume. Open a new shell, then use brew install PACKAGE.'
