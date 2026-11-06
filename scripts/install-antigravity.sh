#!/usr/bin/env bash
set -euo pipefail
[[ $(id -u) != 0 ]] || { echo 'Run as the workstation user, not root.' >&2; exit 1; }
source=${1:-}
if [[ -z $source ]]; then
    echo 'Usage: install-antigravity HTTPS_TARBALL_URL_OR_LOCAL_FILE [BINARY_NAME]'
    echo 'Copy a Linux x64 download link from https://antigravity.google/download.'
    echo 'Choose Antigravity 2.0 or standalone IDE. This installer never guesses the latest URL.'
    exit 1
fi
binary_name=${2:-}
[[ -z $binary_name || $binary_name =~ ^[A-Za-z0-9._-]+$ ]] || exit 1
apps="$HOME/.local/share/workstation/antigravity"
mkdir -p "$apps" "$HOME/.local/bin" "$HOME/.local/share/applications"
stage=$(mktemp -d "$apps/release.XXXXXXXX")
trap 'if [[ -n ${stage:-} ]]; then rm -rf -- "$stage"; fi' EXIT
if [[ $source == https://* ]]; then
    curl --proto '=https' --proto-redir '=https' -fL --retry 3 "$source" -o "$stage/download.tar.gz"
elif [[ -f $source ]]; then
    cp -- "$source" "$stage/download.tar.gz"
else
    echo 'Provide an HTTPS URL or existing local tar.gz file.' >&2; exit 1
fi
if [[ -n ${ANTIGRAVITY_SHA256:-} ]]; then
    printf '%s  %s\n' "$ANTIGRAVITY_SHA256" "$stage/download.tar.gz" | sha256sum -c -
fi
python3 - "$stage" <<'PY'
import pathlib, sys, tarfile
stage = pathlib.Path(sys.argv[1])
with tarfile.open(stage/'download.tar.gz') as archive:
    archive.extractall(stage/'app', filter='data')
PY
python3 - "$stage" "$binary_name" <<'PY'
import os, pathlib, sys
stage = pathlib.Path(sys.argv[1])
names = {sys.argv[2]} if sys.argv[2] else {'antigravity', 'antigravity-ide'}
candidates = [p for p in (stage/'app').rglob('*')
              if p.name in names and not p.is_symlink() and p.is_file()
              and os.access(p, os.X_OK)]
# Electron bundles also contain bin/<name>, a CLI wrapper. The GUI launcher
# sits beside resources/app; select it rather than the wrapper.
desktop = [p for p in candidates if (p.parent/'resources'/'app').is_dir()]
choices = desktop or candidates
if len(choices) != 1:
    print('Could not identify a unique Antigravity desktop executable.', file=sys.stderr)
    for p in candidates:
        print('  Candidate: ' + str(p.relative_to(stage/'app')), file=sys.stderr)
    print('Supported names: antigravity, antigravity-ide. For another name, pass argument 2.', file=sys.stderr)
    sys.exit(1)
(stage/'executable-path').write_text(str(choices[0].relative_to(stage)) + '\n')
PY
printf '%s\n' "$source" > "$stage/source"
rm "$stage/download.tar.gz"
if [[ -L $apps/current ]]; then
    ln -sfn "$(readlink "$apps/current")" "$apps/previous"
fi
ln -s "$(basename "$stage")" "$apps/current.new"
mv -Tf "$apps/current.new" "$apps/current"
cat > "$HOME/.local/bin/antigravity" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
base="$HOME/.local/share/workstation/antigravity/current"
executable=$(cat "$base/executable-path")
exec "$base/$executable" --no-sandbox "$@"
LAUNCH
chmod +x "$HOME/.local/bin/antigravity"
cat > "$HOME/.local/share/applications/workstation-antigravity.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Antigravity
Exec=antigravity %U
Icon=applications-development
Categories=Development;
DESKTOP
stage=''
echo 'Antigravity installed in persistent home. Start with: antigravity'
echo 'Previous release retained in ~/.local/share/workstation/antigravity/previous.'
