#!/usr/bin/env bash
set -euo pipefail
mode=${1:-}
[[ $mode == auto || $mode == fixed ]] || { echo 'Usage: display-mode auto | display-mode fixed WIDTH HEIGHT' >&2; exit 1; }
export DISPLAY=:1
set_resize() {
    tigervncconfig -set "AcceptSetDesktopSize=$1"
    actual=$(tigervncconfig -get AcceptSetDesktopSize)
    [[ $actual == "$1" ]] || { echo 'VNC server did not apply the resizing policy' >&2; return 1; }
}
if [[ $mode == fixed ]]; then
    width=${2:-}; height=${3:-}
    [[ $width =~ ^[0-9]+$ && $height =~ ^[0-9]+$ ]] || { echo 'Supply numeric width and height' >&2; exit 1; }
    previous=$(tigervncconfig -get AcceptSetDesktopSize)
    trap 'tigervncconfig -set "AcceptSetDesktopSize=$previous" >/dev/null 2>&1 || true' ERR
    # Temporarily accept resizing to set geometry, then lock it for all clients.
    set_resize 1
    output=$(xrandr --query | awk '/ connected/{print $1; exit}')
    [[ -n $output ]] || { echo 'No connected VNC output' >&2; exit 1; }
    xrandr --output "$output" --mode "${width}x${height}"
    set_resize 0
    trap - ERR
    printf '%s %s\n' "$width" "$height" > "$HOME/.vnc/geometry"
else
    set_resize 1
    rm -f -- "$HOME/.vnc/geometry"
fi
printf '%s\n' "$mode" > "$HOME/.vnc/display-mode"
echo "Display mode: $mode. Use noVNC local scaling with multiple clients; remote resize with one client."
