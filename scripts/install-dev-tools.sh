#!/usr/bin/env bash
set -eo pipefail
[[ $(id -u) != 0 ]] || { echo 'Run as the workstation user, not root.' >&2; exit 1; }
node_version=${1:-${DEV_NODE_VERSION:-22}}
python_version=${2:-${DEV_PYTHON_VERSION:-}}
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
if [[ ! -s $NVM_DIR/nvm.sh ]]; then
    [[ ! -e $NVM_DIR ]] || { echo "$NVM_DIR exists but is not a complete nvm installation" >&2; exit 1; }
    git clone --depth 1 --branch "${NVM_VERSION:-v0.40.8}" https://github.com/nvm-sh/nvm.git "$NVM_DIR"
fi
source "$NVM_DIR/nvm.sh"
nvm install "$node_version"
[[ -f $NVM_DIR/alias/default ]] || nvm alias default "$node_version"
if [[ ! -x $PYENV_ROOT/bin/pyenv ]]; then
    [[ ! -e $PYENV_ROOT ]] || { echo "$PYENV_ROOT exists but is not a complete pyenv installation" >&2; exit 1; }
    git clone --depth 1 --branch "${PYENV_VERSION:-v2.8.8}" https://github.com/pyenv/pyenv.git "$PYENV_ROOT"
fi
export PATH="$PYENV_ROOT/bin:$PATH"
if [[ -n $python_version ]]; then
    pyenv install -s "$python_version"
    [[ -f $PYENV_ROOT/version ]] || pyenv global "$python_version"
fi
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/pipx"
nvm --version
node --version
pyenv --version
pipx --version
echo 'Tools installed in persistent home. Open a new shell or source /etc/profile.d/workstation.sh.'
echo 'Use nvm install VERSION, pyenv install VERSION, and pipx install PACKAGE for more tools.'
