#!/usr/bin/env bash
set -euo pipefail
exec pulseaudio --daemonize=no --exit-idle-time=-1 --disallow-exit --use-pid-file=yes \
    --log-target=stderr --log-level=warning --high-priority=no --realtime=no \
    -n --file=/etc/workstation/audio/pulse.pa
