# Also loaded by non-interactive Bash commands used by CLI agents.
if [ "$(id -u)" = 0 ]; then return 0; fi
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
export PIPX_HOME="${PIPX_HOME:-$HOME/.local/share/pipx}"
export PIPX_BIN_DIR="$HOME/.local/bin"
if [ -x /home/linuxbrew/.linuxbrew/bin/brew ]; then
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv bash)"
fi
export PATH="$HOME/.local/bin:$HOME/.local/npm/bin:$PYENV_ROOT/shims:$PYENV_ROOT/bin:$PATH"
if [ -s "$NVM_DIR/nvm.sh" ]; then . "$NVM_DIR/nvm.sh"; fi
# pyenv shims work without shell integration; avoid recursively running pyenv init here.
:
