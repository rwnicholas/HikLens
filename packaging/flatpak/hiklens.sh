#!/bin/sh
set -eu
export PYTHONPATH="/app/lib/hiklens-python${PYTHONPATH:+:$PYTHONPATH}"
exec python3 /app/share/hiklens/cam_viewer.py "$@"
