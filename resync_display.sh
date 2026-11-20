#!/bin/sh
# Clears the round panel's occasional torn/shifted picture by making the Pi send its video mode again.
# Asking for a different mode and going back makes the panel re-sync; it's the panel, not the app's drawing.
#   ./resync_display.sh [output]     (default HDMI-A-1; `wlr-randr` lists outputs)
OUTPUT=${1:-HDMI-A-1}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
export WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0}

wlr-randr --output "$OUTPUT" --custom-mode 640x480@60
sleep 1
wlr-randr --output "$OUTPUT" --preferred
