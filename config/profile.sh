export DISPLAY=:1
export XDG_RUNTIME_DIR="/tmp/runtime-$(id -u)"
export PULSE_SERVER="unix:$XDG_RUNTIME_DIR/pulse/native"
export PULSE_SINK=workstation
export PULSE_CLIENTCONFIG=/etc/workstation/audio/client.conf
export LIBGL_ALWAYS_SOFTWARE=1
export PATH="$HOME/.local/bin:$HOME/.local/npm/bin:/usr/local/cuda/bin:$PATH"

# Shell integration for version managers in the persistent home.
if [ "$(id -u)" != 0 ] && [ -n "${BASH_VERSION:-}" ]; then
    . /etc/workstation/bash-env.sh
    if [ -x "$PYENV_ROOT/bin/pyenv" ]; then
        eval "$("$PYENV_ROOT/bin/pyenv" init - bash)"
    fi
fi
