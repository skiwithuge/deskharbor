#!/usr/bin/env bash
# Apply terminal defaults once per persistent home; --force reapplies on request.
set -euo pipefail
[[ $# == 0 || ( $# == 1 && $1 == --force ) ]] || { echo 'Usage: configure-terminal [--force]' >&2; exit 1; }
[[ $(id -u) != 0 ]] || { echo 'Run as the desktop user.' >&2; exit 1; }
state="$HOME/.local/state/workstation"
marker="$state/terminal-defaults-v1"
[[ ! -f $marker || ${1:-} == --force ]] || exit 0
if [[ -z ${DBUS_SESSION_BUS_ADDRESS:-} ]]; then
    exec dbus-run-session -- "$0" "$@"
fi
mkdir -p "$state"
backup=$(mktemp -d "$state/terminal-settings-before.XXXXXXXX")
chmod 700 "$backup"
dconf dump /com/gexperts/Tilix/ > "$backup/tilix.ini"
dconf dump /org/gnome/terminal/ > "$backup/gnome-terminal.ini"
dconf dump /org/gnome/desktop/interface/ > "$backup/interface.ini"
dconf dump /org/gnome/desktop/default-applications/terminal/ > "$backup/default-terminal.ini"

gsettings set org.gnome.desktop.interface monospace-font-name 'Fira Code 11'
gsettings set org.gnome.desktop.default-applications.terminal exec 'tilix'
gsettings set org.gnome.desktop.default-applications.terminal exec-arg '-e'
gsettings set com.gexperts.Tilix.Settings theme-variant 'dark'
for list in com.gexperts.Tilix.ProfilesList org.gnome.Terminal.ProfilesList; do
    profile=$(gsettings get "$list" default)
    profile=${profile//\'/}
    if [[ $list == com.gexperts.Tilix.ProfilesList ]]; then
        schema="com.gexperts.Tilix.Profile:/com/gexperts/Tilix/profiles/$profile/"
    else
        schema="org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:$profile/"
    fi
    gsettings set "$schema" use-system-font false
    gsettings set "$schema" font 'Fira Code 11'
    gsettings set "$schema" cell-width-scale 1.0
    gsettings set "$schema" cell-height-scale 1.0
    gsettings set "$schema" use-theme-colors false
    gsettings set "$schema" background-color '#1e1e1e'
    gsettings set "$schema" foreground-color '#d8dee9'
done
touch "$marker"
echo "Terminal defaults applied: Fira Code 11, normal spacing, dark Tilix. Backup: $backup"
