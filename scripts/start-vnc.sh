#!/usr/bin/env bash
set -euo pipefail
mode=${DISPLAY_MODE:-auto}
# User choice survives VNC service/container restarts.
[[ ! -f $HOME/.vnc/display-mode ]] || mode=$(cat "$HOME/.vnc/display-mode")
width=${DISPLAY_WIDTH:-1920}; height=${DISPLAY_HEIGHT:-1080}
if [[ $mode == fixed && -f $HOME/.vnc/geometry ]]; then read -r width height < "$HOME/.vnc/geometry"; fi
[[ $width =~ ^[0-9]+$ && $height =~ ^[0-9]+$ ]] || exit 1
accept=1; [[ $mode != fixed ]] || accept=0
exec tigervncserver :1 -fg -geometry "${width}x${height}" -depth 24 \
    -localhost no -SecurityTypes VncAuth -rfbauth "$HOME/.vnc/passwd" \
    -AlwaysShared=1 -AllowOverride=AcceptSetDesktopSize -AcceptSetDesktopSize="$accept" \
    -xstartup /opt/workstation/desktop-session.sh
