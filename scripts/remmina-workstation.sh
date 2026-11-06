#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
usage() { echo 'Usage: remmina-workstation.sh [--zoom 100|125|150] [--fullscreen] PROFILE.remmina'; }
zoom=100
profile=
window_options=()
while (($#)); do
    case $1 in
        --zoom)
            [[ $# -ge 2 ]] || { usage >&2; exit 1; }
            zoom=$2; shift 2 ;;
        --fullscreen) window_options=(--enable-fullscreen); shift ;;
        --zoom=*) zoom=${1#*=}; shift ;;
        -h|--help) usage; exit 0 ;;
        --)
            shift
            [[ $# == 1 && -z $profile ]] || { usage >&2; exit 1; }
            profile=$1; shift ;;
        -*) usage >&2; exit 1 ;;
        *)
            [[ -z $profile ]] || { usage >&2; exit 1; }
            profile=$1; shift ;;
    esac
done
[[ $zoom == 100 || $zoom == 125 || $zoom == 150 ]] || { echo 'Zoom must be 100, 125 or 150.' >&2; exit 1; }
[[ -n $profile && -f $profile ]] || { usage >&2; exit 1; }
python3 - "$profile" <<'PY'
import configparser
import sys
config = configparser.ConfigParser(interpolation=None)
try:
    config.read(sys.argv[1])
except (configparser.Error, OSError):
    sys.exit('Cannot read a valid Remmina profile.')
if config.get('remmina', 'protocol', fallback='') != 'VNC':
    sys.exit('Select a saved VNC profile.')
if config.get('remmina', 'scale', fallback='0') != '2':
    sys.exit('Enable dynamic resolution in this profile first: scripts/configure-remmina-auto.py PROFILE.remmina')
PY
[[ -f $root/.local/remmina/lib/libvncclient.so.1 ]] || { echo 'Run scripts/build-remmina-client.sh first.' >&2; exit 1; }
if pgrep -u "$(id -u)" -x remmina >/dev/null; then
    echo 'Close Remmina completely first; an existing process cannot load this library or zoom setting.' >&2
    exit 1
fi
echo "Opening Remmina with ${zoom}% enlargement and automatic resolution."
exec env GDK_BACKEND=x11 LEGION_REMMINA_ZOOM="$zoom" \
    LD_LIBRARY_PATH="$root/.local/remmina/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    remmina "${window_options[@]}" --connect "$profile"
