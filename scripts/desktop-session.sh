#!/usr/bin/env bash
set -euo pipefail
export XDG_CURRENT_DESKTOP=GNOME-Flashback:GNOME
export GNOME_SHELL_SESSION_MODE=flashback
export LIBGL_ALWAYS_SOFTWARE=1
# The virtual desktop has no logind-managed power session.
export XDG_CONFIG_DIRS="/etc/workstation/desktop:${XDG_CONFIG_DIRS:-/etc/xdg}"
# Initialize defaults once; subsequent starts preserve the user's preferences.
exec dbus-run-session -- bash -c '
    /opt/workstation/configure-terminal.sh
    exec gnome-session --session=deskharbor-flashback
'
