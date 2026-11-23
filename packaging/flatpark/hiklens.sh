#!/bin/sh
set -eu

export APPDIR="/app/extra/app"
export PATH="$APPDIR/usr/bin:$PATH"
exec "$APPDIR/AppRun" "$@"
