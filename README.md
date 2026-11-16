# Hikvision Camera Viewer Application

A modern desktop application built in Python (PySide6) to monitor Hikvision DVR cameras.

---

## 🌟 Key Features

1. **Dual Video Engines (HTTP Snapshot vs Embedded RTSP)**:
   - **`HTTP Snapshot (5 FPS)`**: Uses persistent HTTP Digest sessions to grab frames with zero buffering. Highly stable across all codecs (including H.265+).
   - **`Embedded RTSP (Selectable FPS)`**: Connects directly to the DVR's RTSP hardware stream and embeds video in the app tiles. The **Speed** selector limits the displayed frame rate in this mode.
   - Easily switch between engines on the fly from the **Engine** dropdown on the toolbar. The Speed selector is disabled for HTTP.

2. **Flexible Camera Selection**:
   - Choose how many configured cameras to show in the grid; layouts adapt from `1x1` and `2x1` to `2x2`, `3x2`, and larger grids.
   - **Grid View**: Monitor the selected number of cameras simultaneously in real time.
   - **Single Camera Mode**: Focus on any configured camera with high-resolution scaling.
   - **Quick Zoom**: Double-click any camera tile in the grid to zoom in immediately; double-click again or press `Esc` to return to the grid.

3. **Max Resolution (1080p Full HD)**:
   - **Native Max Resolution**: Supports the hardware's native **1920x1080 Full HD (1920x1088)** stream directly from the DVR.
   - **Quality Selector**:
     - `Auto (1080p Focus / 480p Grid)`: Uses smooth sub-stream for the 4-camera grid, and automatically switches to **Full HD 1080p** whenever you focus on an individual camera.
     - `Max (1080p Full HD Always)`: Forces all cameras to stream at full 1080p resolution.
     - `Standard (480p Fast)`: Low-bandwidth mode.
   - Live resolution badge (e.g. `1920x1088`) is displayed on each camera tile in real time.

4. **Real-Time Motion Detection (AlertStream Integration)**:
   - Connects to `/ISAPI/Event/notification/alertStream` while the Events panel is visible; hiding the panel pauses the connection.
   - When motion is detected, the corresponding camera flashes a red border and a `MOTION` badge appears.
   - Activity log tracks timestamps of all motion events.
   - Camera connection failures are also recorded in the Activity & Motion Log.
   - Optional **"Save on Motion"** toggle automatically captures full-resolution snapshots upon motion.

5. **Instant Snapshots**:
   - Click the **Snapshot** button (or press `S`) to save uncompressed high-resolution snapshots.
   - Click **Record** (or press `R`) to save one camera as an MP4; in grid view, choose the camera to record. FFmpeg is required.
   - Choose the destination for snapshots and recordings in **Settings**. The default is `./snapshots/` natively and `Pictures/Hikvision Camera Viewer/` in Flatpak.

5. **HQ RTSP Stream Launcher**:
   - Click **"Open HQ RTSP"** to spawn `ffplay` with low-latency flags (`-fflags nobuffer -flags low_delay -framedrop`) for full-framerate hardware decoding when needed.

6. **Interactive Hotkeys**:
   - `0` or `G`: Switch to Grid View
   - `1`, `2`, `3`, `4`: Switch to Camera 1, 2, 3, 4
   - `Double-Click`: Zoom in on clicked camera / Zoom out to grid
   - `Space`: Pause / Resume stream
   - `S`: Take snapshot
   - `R`: Start / stop video recording
   - `F` or `F11`: Fullscreen toggle
   - `Esc`: Return from single camera to grid, or exit fullscreen

The application restores the last-used video engine, FPS, quality, camera count,
view mode, Events panel visibility, window size, and panel layout when reopened.

---

## 🚀 How to Run

From this directory:

```bash
./start_viewer.sh
```

Or directly with Python:

```bash
python3 cam_viewer.py
```

---

## 📦 Flatpak

The Flatpak manifest and desktop integration are in `packaging/flatpak/`.
Both package builds include the shared AppStream metadata from `packaging/`.
With Flatpak, Flatpak Builder, and the Flathub runtime available, build and
install the app with:

```bash
flatpak-builder --user --install --force-clean flatpak-build packaging/flatpak/io.github.rwnicholas.HikvisionLinux.yml
flatpak run io.github.rwnicholas.HikvisionLinux
```

To create a distributable `.flatpak` bundle instead:

```bash
flatpak-builder --repo=flatpak-repo flatpak-build packaging/flatpak/io.github.rwnicholas.HikvisionLinux.yml
flatpak build-bundle flatpak-repo HikvisionCameraViewer.flatpak io.github.rwnicholas.HikvisionLinux stable
```

The first build downloads the pinned Python dependencies. The Flatpak includes
the app runtime's FFmpeg and requests LAN access for DVR streams. The target
runtime must be installed locally or available from a configured Flatpak remote.

## AppImage

Build the x86_64 AppImage with Podman or Docker, `curl`, and `sha256sum`:

```bash
./packaging/appimage/build-appimage.sh
```

The output is `dist/HikvisionCameraViewer-x86_64.AppImage`. The AppImage
bundles Python and Qt; install FFmpeg on the host for embedded RTSP and video
recording, and `ffplay` for the separate HQ RTSP player. Both Linux packages
use embedded vector icons for consistent control rendering across hosts.
The AppImage build downloads and verifies its packaging tools and targets
Linux systems with glibc 2.36 or newer.

On each push to `main`, [GitHub Actions](./.github/workflows/build-packages.yml)
builds both packages, automatically generates patch versions starting with
`v1.0.0`, and creates a GitHub Release with the AppImage and Flatpak bundle
attached. Download them from the Releases page; the workflow can also be
started manually from the Actions tab to build artifacts without publishing a
release.

## ⚙️ DVR Configuration

Configure the DVR by clicking **Settings**. Values are saved in the current
user's application settings and restored on the next launch. `DVR_IP`,
`DVR_USERNAME`, and `DVR_PASSWORD` environment variables are used when no saved
setting exists. The default IP is the documentation-only address `192.0.2.1`;
set it to your DVR's address before connecting. HTTP and RTSP ports default to
`80` and `554`.

The password is stored locally in the user's application settings and is not
encrypted. On Linux, the settings file is restricted to the current user.

## License

This project is licensed under the [MIT License](./LICENSE).
