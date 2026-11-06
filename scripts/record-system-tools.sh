#!/usr/bin/env bash
set -euo pipefail
[[ ${WORKSTATION_RESTORING:-0} != 1 ]] || exit 0
user=$(cat /etc/workstation/user-name)
uid=$(id -u "$user"); gid=$(id -g "$user")
user_home=$(getent passwd "$user" | cut -d: -f6)
state="$user_home/.local/state/workstation"
install -d -o "$uid" -g "$gid" "$user_home/.local" "$user_home/.local/state" "$state"
temporary=$(mktemp "$state/apt-packages.XXXXXXXX")
trap 'rm -f -- "$temporary"' EXIT
# Only additions to this image's baseline; dependencies are restored by apt.
LC_ALL=C comm -23 <(apt-mark showmanual | LC_ALL=C sort -u) /etc/workstation/base-manual-packages > "$temporary"
chmod 644 "$temporary"
chown "$uid:$gid" "$temporary"
mv -f -- "$temporary" "$state/apt-packages.txt"
