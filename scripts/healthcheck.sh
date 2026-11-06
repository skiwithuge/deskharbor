#!/usr/bin/env bash
set -euo pipefail
for service in dbus ssh vnc web pulse audio; do
    flag="ENABLE_${service^^}"
    [[ ${!flag:-false} != true ]] || supervisorctl -c /etc/workstation/supervisord.conf status "$service" | awk '$2 != "RUNNING" {exit 1}'
done
if [[ ${ENABLE_WEB:-false} == true ]]; then
    curl -fsS http://127.0.0.1:6080/ > /dev/null
    python3 /opt/workstation/vnc-health.py
elif [[ ${ENABLE_VNC:-false} == true ]]; then
    # An authenticated RFB check is required; never make unauthenticated TCP probes.
    python3 /opt/workstation/vnc-health.py --direct
fi
if [[ ${ENABLE_AUDIO:-false} == true ]]; then
    audio_runtime="/tmp/runtime-$(id -u "$WORKSTATION_USER")"
    runuser -u "$WORKSTATION_USER" -- env XDG_RUNTIME_DIR="$audio_runtime" PULSE_SERVER="unix:$audio_runtime/pulse/native" pactl list short sinks | awk '$2 == "workstation" {found=1} END {exit !found}'
    [[ $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:6081/) == 401 ]]
fi
