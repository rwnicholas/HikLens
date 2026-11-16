#!/bin/sh
set -eu
export PYTHONPATH="/app/lib/hikvision-python${PYTHONPATH:+:$PYTHONPATH}"
export FONTCONFIG_FILE="${FONTCONFIG_FILE:-/app/etc/fonts/fonts.conf}"
exec python3 /app/share/hikvision-linux/cam_viewer.py "$@"
