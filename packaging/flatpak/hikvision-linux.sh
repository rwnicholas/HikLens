#!/bin/sh
set -eu
export PYTHONPATH="/app/lib/hikvision-python${PYTHONPATH:+:$PYTHONPATH}"
exec python3 /app/share/hikvision-linux/cam_viewer.py "$@"
