#!/usr/bin/env bash
# Fixture reproduces Google's IDE bundle: GUI executable plus bin/ CLI wrapper.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")/.."
task_tmp=$(mktemp -d /tmp/deskharbor-antigravity-check.XXXXXXXX)
trap 'rm -rf -- "$task_tmp"' EXIT
mkdir -p "$task_tmp/bundle/Antigravity IDE/bin" "$task_tmp/bundle/Antigravity IDE/resources/app" "$task_tmp/home"
printf '#!/bin/sh\nprintf "gui-launcher\\n"\n' > "$task_tmp/bundle/Antigravity IDE/antigravity-ide"
printf '#!/bin/sh\nexit 99\n' > "$task_tmp/bundle/Antigravity IDE/bin/antigravity-ide"
chmod +x "$task_tmp/bundle/Antigravity IDE/antigravity-ide" "$task_tmp/bundle/Antigravity IDE/bin/antigravity-ide"
tar -czf "$task_tmp/Antigravity IDE.tar.gz" -C "$task_tmp/bundle" .
HOME="$task_tmp/home" bash scripts/install-antigravity.sh "$task_tmp/Antigravity IDE.tar.gz"
test "$(HOME="$task_tmp/home" "$task_tmp/home/.local/bin/antigravity")" = gui-launcher
HOME="$task_tmp/home" bash scripts/install-antigravity.sh "$task_tmp/Antigravity IDE.tar.gz" antigravity-ide
test -L "$task_tmp/home/.local/share/workstation/antigravity/previous"
mv "$task_tmp/bundle/Antigravity IDE/antigravity-ide" "$task_tmp/bundle/Antigravity IDE/antigravity"
mv "$task_tmp/bundle/Antigravity IDE/bin/antigravity-ide" "$task_tmp/bundle/Antigravity IDE/bin/antigravity"
tar -czf "$task_tmp/old.tar.gz" -C "$task_tmp/bundle" .
HOME="$task_tmp/home" bash scripts/install-antigravity.sh "$task_tmp/old.tar.gz"
test "$(HOME="$task_tmp/home" "$task_tmp/home/.local/bin/antigravity")" = gui-launcher
before=$(readlink "$task_tmp/home/.local/share/workstation/antigravity/current")
cp -a "$task_tmp/bundle/Antigravity IDE" "$task_tmp/bundle/Second IDE"
tar -czf "$task_tmp/ambiguous.tar.gz" -C "$task_tmp/bundle" .
if HOME="$task_tmp/home" bash scripts/install-antigravity.sh "$task_tmp/ambiguous.tar.gz" > "$task_tmp/error" 2>&1; then
    echo 'Ambiguous bundle unexpectedly accepted' >&2; exit 1
fi
grep -q 'Could not identify a unique' "$task_tmp/error"
test "$(readlink "$task_tmp/home/.local/share/workstation/antigravity/current")" = "$before"
echo 'IDE discovery, explicit updates, old bundles and ambiguous-bundle rejection passed.'
