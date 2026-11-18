#!/bin/sh
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
TOOLS_DIR="$PROJECT_ROOT/.appimage-tools"
BUILD_DIR="$PROJECT_ROOT/.appimage-build"
OUTPUT_DIR="$PROJECT_ROOT/dist"
APPDIR="$BUILD_DIR/AppDir"
OUTPUT="$OUTPUT_DIR/HikvisionCameraViewer-x86_64.AppImage"

if [ -n "${CONTAINER_ENGINE:-}" ]; then
    case "$CONTAINER_ENGINE" in
        podman|docker) ;;
        *)
            echo "CONTAINER_ENGINE must be 'podman' or 'docker'." >&2
            exit 1
            ;;
    esac
    command -v "$CONTAINER_ENGINE" >/dev/null 2>&1 || {
        echo "$CONTAINER_ENGINE is required to build the AppImage." >&2
        exit 1
    }
elif command -v podman >/dev/null 2>&1; then
    CONTAINER_ENGINE=podman
elif command -v docker >/dev/null 2>&1; then
    CONTAINER_ENGINE=docker
else
    echo "Podman or Docker is required to build the AppImage." >&2
    exit 1
fi
command -v curl >/dev/null 2>&1 || {
    echo "curl is required to download AppImage build tools." >&2
    exit 1
}
command -v sha256sum >/dev/null 2>&1 || {
    echo "sha256sum is required to verify AppImage build tools." >&2
    exit 1
}

mkdir -p "$TOOLS_DIR" "$BUILD_DIR" "$OUTPUT_DIR"

download_tool() {
    url="$1"
    checksum="$2"
    path="$3"
    if [ ! -f "$path" ]; then
        curl --fail --location --silent --show-error "$url" --output "$path"
    fi
    printf '%s  %s\n' "$checksum" "$path" | sha256sum --check --status || {
        echo "Checksum verification failed for $path." >&2
        exit 1
    }
    chmod +x "$path"
}

download_tool \
    "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage" \
    "df908b19f1ed1cdafa79508d415aa12d6c56ce4d56d4149aa8c09286718706e5" \
    "$TOOLS_DIR/linuxdeploy-x86_64.AppImage"
download_tool \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" \
    "e8c1169c4af66c3184d7ee110713d4be04befe671fa358e2c1591ee840553b03" \
    "$TOOLS_DIR/appimagetool-x86_64.AppImage"

rm -rf "$APPDIR" "$BUILD_DIR/build" "$BUILD_DIR/dist"
rm -f "$OUTPUT"

run_builder() {
    if [ "$CONTAINER_ENGINE" = podman ]; then
        podman run --rm --security-opt label=disable "$@"
    else
        docker run --rm "$@"
    fi
}

run_builder \
    --volume "$PROJECT_ROOT:/src:ro" \
    --volume "$BUILD_DIR:/out:rw" \
    --volume "$TOOLS_DIR:/tools:ro" \
    docker.io/library/python:3.12-slim-bookworm \
    sh -eu -c '
        apt-get update >/dev/null
        apt-get install -y --no-install-recommends \
            binutils \
            libdbus-1-3 \
            libegl1 \
            libfontconfig1 \
            libgl1 \
            libglib2.0-0 \
            libice6 \
            librsvg2-bin \
            libopengl0 \
            libsm6 \
            libwayland-client0 \
            libwayland-cursor0 \
            libwayland-egl1 \
            libwayland-server0 \
            libx11-xcb1 \
            libxcb-cursor0 \
            libxcb-icccm4 \
            libxcb-image0 \
            libxcb-keysyms1 \
            libxcb-randr0 \
            libxcb-render-util0 \
            libxcb-render0 \
            libxcb-shape0 \
            libxcb-shm0 \
            libxcb-sync1 \
            libxcb-util1 \
            libxcb-xfixes0 \
            libxcb-xinerama0 \
            libxcb-xkb1 \
            libxkbcommon-x11-0 >/dev/null

        python -m pip install --disable-pip-version-check --no-cache-dir \
            --root-user-action=ignore \
            -r /src/requirements.txt \
            -r /src/packaging/appimage/requirements-build.txt

        python -m PyInstaller \
            --noconfirm \
            --clean \
            --onedir \
            --windowed \
            --name HikvisionCameraViewer \
            --add-data /src/hikvision-sdk:hikvision-sdk \
            --distpath /out/dist \
            --workpath /out/build \
            /src/cam_viewer.py

        appdir=/out/AppDir
        install -d "$appdir/usr/lib/hikvision-camera-viewer"
        cp -a /out/dist/HikvisionCameraViewer/. "$appdir/usr/lib/hikvision-camera-viewer/"
        rm -f \
            "$appdir/usr/lib/hikvision-camera-viewer/_internal/libfontconfig.so.1" \
            "$appdir/usr/lib/hikvision-camera-viewer/_internal/libfreetype.so.6"
        # The optional GTK theme plugin pulls in GTK3; the app uses its own palette.
        rm -f "$appdir/usr/lib/hikvision-camera-viewer/_internal/PySide6/Qt/plugins/platformthemes/libqgtk3.so"
        install -Dm755 /src/packaging/appimage/AppRun "$appdir/AppRun"
        install -Dm644 \
            /src/packaging/appimage/io.github.rwnicholas.HikvisionLinux.desktop \
            "$appdir/io.github.rwnicholas.HikvisionLinux.desktop"
        install -Dm644 \
            /src/packaging/io.github.rwnicholas.HikvisionLinux.appdata.xml \
            "$appdir/usr/share/metainfo/io.github.rwnicholas.HikvisionLinux.appdata.xml"
        install -Dm644 /src/packaging/flatpak/io.github.rwnicholas.HikvisionLinux.svg \
            "$appdir/usr/share/icons/hicolor/scalable/apps/io.github.rwnicholas.HikvisionLinux.svg"
        rsvg-convert -w 256 -h 256 \
            /src/packaging/flatpak/io.github.rwnicholas.HikvisionLinux.svg \
            -o "$appdir/.DirIcon"
        install -Dm644 /src/LICENSE \
            "$appdir/usr/share/licenses/hikvision-camera-viewer/LICENSE"
        install -Dm644 /usr/share/common-licenses/LGPL-3 \
            "$appdir/usr/share/licenses/hikvision-camera-viewer/LGPL-3.0.txt"

        python - "$appdir/usr/share/doc/hikvision-camera-viewer/licenses" <<'"'"'PY'"'"'
import shutil
import sys
from pathlib import Path

destination = Path(sys.argv[1])
site_packages = Path("/usr/local/lib/python3.12/site-packages")
for license_dir in site_packages.glob("*.dist-info/licenses"):
    if license_dir.is_dir():
        shutil.copytree(
            license_dir,
            destination / license_dir.parent.name,
            dirs_exist_ok=True,
        )
PY

        for copyright_file in /usr/share/doc/*/copyright; do
            [ -f "$copyright_file" ] || continue
            package=$(basename "$(dirname "$copyright_file")")
            install -Dm644 "$copyright_file" \
                "$appdir/usr/share/doc/hikvision-camera-viewer/licenses/system/$package/copyright"
        done

        /tools/linuxdeploy-x86_64.AppImage --appimage-extract-and-run \
            --appdir "$appdir" \
            --custom-apprun /src/packaging/appimage/AppRun \
            --desktop-file /src/packaging/appimage/io.github.rwnicholas.HikvisionLinux.desktop \
            --exclude-library=libfontconfig.so.1 \
            --exclude-library=libfreetype.so.6 \
            --deploy-deps-only "$appdir/usr/lib/hikvision-camera-viewer"
    '

ARCH=x86_64 "$TOOLS_DIR/appimagetool-x86_64.AppImage" \
    --appimage-extract-and-run "$APPDIR" "$OUTPUT"

echo "Created $OUTPUT"
