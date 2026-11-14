#!/usr/bin/env bash
set -euo pipefail
renderer=${DESKHARBOR_BROWSER_RENDERER:-auto}
gpu_options=()
has_nvidia_graphics() {
    command -v nvidia-smi >/dev/null 2>&1 &&
        nvidia-smi -L >/dev/null 2>&1 &&
        ldconfig -p 2>/dev/null | grep -F 'libGLX_nvidia.so.0' >/dev/null
}
case "$renderer" in
    auto)
        if has_nvidia_graphics; then renderer=nvidia; else renderer=software; fi ;;
    nvidia)
        has_nvidia_graphics || {
            echo 'NVIDIA graphics are unavailable. Enable GPU mode and apply the updated image with graphics driver support.' >&2
            exit 1
        } ;;
    software) ;;
    *) echo 'DESKHARBOR_BROWSER_RENDERER must be auto, nvidia or software.' >&2; exit 1 ;;
esac
if [[ $renderer == nvidia ]]; then
    # Xvnc's desktop remains software-rendered. ANGLE can render Chrome's
    # content on NVIDIA through Vulkan without a GPU-backed X11 screen.
    unset LIBGL_ALWAYS_SOFTWARE
    gpu_options+=(--use-angle=vulkan)
else
    export LIBGL_ALWAYS_SOFTWARE=1
fi
exec /usr/bin/google-chrome-stable --no-sandbox --disable-dev-shm-usage "${gpu_options[@]}" "$@"
