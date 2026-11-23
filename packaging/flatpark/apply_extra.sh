#!/bin/sh
set -eu

(set -o pipefail) 2>/dev/null && set -o pipefail || true

LC_ALL=C
export LC_ALL

extra_root="${EXTRA_ROOT:-/app/extra}"
cd "$extra_root"

[ -f HikLens.AppImage ] || {
    echo "missing extra-data: HikLens.AppImage" >&2
    exit 1
}

rm -rf app squashfs-root

if command -v appimage-offset >/dev/null 2>&1 && command -v unsquashfs >/dev/null 2>&1; then
    offset="$(appimage-offset HikLens.AppImage)"
    unsquashfs -no-progress -o "$offset" -d app HikLens.AppImage >/dev/null
elif [ -x ./appimage-tools/appimage-offset ] && [ -x ./appimage-tools/unsquashfs ]; then
    offset="$(./appimage-tools/appimage-offset HikLens.AppImage)"
    ./appimage-tools/unsquashfs -no-progress -o "$offset" -d app HikLens.AppImage >/dev/null
else
    chmod +x HikLens.AppImage
    ./HikLens.AppImage --appimage-extract >/dev/null
    mv squashfs-root app
fi

rm -f HikLens.AppImage
rm -rf appimage-tools
