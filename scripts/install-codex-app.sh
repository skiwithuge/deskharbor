#!/usr/bin/env bash
# Official Linux desktop package, cached in persistent home for recreation.
set -euo pipefail
[[ $# -le 1 ]] || { echo 'Usage: install-codex-app [HTTPS_DEB_URL_OR_LOCAL_FILE]' >&2; exit 1; }
source=${1:-https://persistent.oaistatic.com/codex-app-prod/linux/deb/latest/chatgpt_amd64.deb}
if [[ $source != https://* ]]; then
    [[ -f $source ]] || { echo 'Provide an HTTPS URL or existing .deb file.' >&2; exit 1; }
    source=$(realpath "$source")
fi
if [[ $(id -u) != 0 ]]; then exec sudo /opt/workstation/install-codex-app.sh "$source"; fi
[[ $(dpkg --print-architecture) == amd64 ]] || { echo 'This workstation installer requires Linux amd64.' >&2; exit 1; }
user=$(cat /etc/workstation/user-name)
user_home=$(getent passwd "$user" | cut -d: -f6)
cache="$user_home/.local/share/workstation/codex-app"
stage=$(mktemp -d /tmp/deskharbor-codex-app.XXXXXXXX)
trap 'rm -rf -- "$stage"' EXIT
chmod 755 "$stage"
if [[ $source == https://* ]]; then
    curl --proto '=https' --proto-redir '=https' -fL --retry 3 "$source" -o "$stage/chatgpt.deb"
else
    cp -- "$source" "$stage/chatgpt.deb"
fi
[[ $(dpkg-deb -f "$stage/chatgpt.deb" Package) == chatgpt &&
   $(dpkg-deb -f "$stage/chatgpt.deb" Architecture) == amd64 ]] || {
    echo 'Expected the official chatgpt amd64 desktop package.' >&2; exit 1;
}
chmod 644 "$stage/chatgpt.deb"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends "$stage/chatgpt.deb"
install -d -m 755 -o "$user" -g "$(id -gn "$user")" "$cache"
install -m 644 -o "$user" -g "$(id -gn "$user")" "$stage/chatgpt.deb" "$cache/chatgpt_amd64.deb.new"
mv -f -- "$cache/chatgpt_amd64.deb.new" "$cache/chatgpt_amd64.deb"
echo 'Codex desktop installed. Open Codex (ChatGPT) from the menu, or run codex-app.'
echo 'Sign in inside the container desktop and select Codex.'
