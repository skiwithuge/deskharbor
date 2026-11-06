#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 ]]; then exec sudo /opt/workstation/restore-system-tools.sh; fi
user=$(cat /etc/workstation/user-name)
user_home=$(getent passwd "$user" | cut -d: -f6)
manifest="$user_home/.local/state/workstation/apt-packages.txt"
[[ -f $manifest ]] || exit 0
missing=()
while IFS= read -r package || [[ -n $package ]]; do
    [[ -n $package && $package != \#* ]] || continue
    [[ $package =~ ^[a-z0-9][a-z0-9+.-]*(:[a-z0-9][a-z0-9-]*)?$ ]] || { echo "Invalid package in $manifest: $package" >&2; exit 1; }
    status=$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)
    if [[ $status != 'install ok installed' ]]; then
        cached="$user_home/.local/share/workstation/codex-app/chatgpt_amd64.deb"
        if [[ $package == chatgpt && -f $cached ]]; then
            [[ $(dpkg-deb -f "$cached" Package) == chatgpt &&
               $(dpkg-deb -f "$cached" Architecture) == "$(dpkg --print-architecture)" ]] || {
                echo 'Invalid cached Codex desktop package.' >&2; exit 1;
            }
            missing+=("$cached")
        else
            missing+=("$package")
        fi
    fi
done < "$manifest"
[[ ${#missing[@]} -gt 0 ]] || exit 0
printf 'Restoring system tools: %s\n' "${missing[*]}"
export DEBIAN_FRONTEND=noninteractive WORKSTATION_RESTORING=1
apt-get update
apt-get install -y --no-install-recommends -- "${missing[@]}"
# The original manifest remains intact, including if restoration fails.
