# Hikvision Camera Viewer Application

A modern desktop application built in Python (PySide6) to monitor Hikvision DVR cameras.

---

## 🌟 Key Features

1. **Selectable Video Engines (HTTP, Embedded RTSP, or Hikvision SDK)**:
   - **`HTTP Snapshot (5 FPS)`**: Uses persistent HTTP Digest sessions to grab frames with zero buffering. Highly stable across all codecs (including H.265+).
   - **`Embedded RTSP (Selectable FPS)`**: Connects directly to the DVR's RTSP hardware stream and embeds video in the app tiles. The **Speed** selector limits the displayed frame rate in this mode.
   - RTSP/FFmpeg remains the default backend; existing saved backend choices
     are preserved. Switch engines from the **Engine** dropdown on the toolbar.
     The Speed selector applies to RTSP and Hikvision SDK display output; HTTP
     snapshot mode remains fixed at 5 FPS.
   - **`Hikvision SDK (encrypted stream)`** is an optional Linux backend that
     uses the separately installed official HCNetSDK and PlayCtrl package.
     Its decryption status is reported explicitly; no frame is displayed unless
     PlayCtrl actually decodes one.

2. **Flexible Camera Selection**:
   - Click **Cameras** on the toolbar to choose the configured cameras shown in Grid View with a checklist.
   - The grid layout adapts to the number selected: `1` camera uses `1x1`, `2` use `2x1`, `3–4` use `2x2`, and larger selections expand automatically.
   - The selected camera set is restored when the application is reopened.
   - **Grid View**: Monitor the selected cameras simultaneously in real time.
   - **Single Camera Mode**: Focus on any configured camera with high-resolution scaling.
   - **Quick Zoom**: Double-click any camera tile in the grid to zoom in immediately; double-click again or press `Esc` to return to the grid.

3. **Max Resolution (1080p Full HD)**:
   - **Native Max Resolution**: Supports the hardware's native **1920x1080 Full HD (1920x1088)** stream directly from the DVR.
   - **Quality Selector**:
     - `Auto (1080p Focus / 480p Grid)`: Uses smooth sub-stream for the 4-camera grid, and automatically switches to **Full HD 1080p** whenever you focus on an individual camera.
     - `Max (1080p Full HD Always)`: Forces all cameras to stream at full 1080p resolution.
     - `Standard (480p Fast)`: Low-bandwidth mode.
     - These modes also select the Hikvision SDK main/sub-stream; switching
       quality or focus restarts that camera's SDK preview.
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

The application restores the last-used video engine, FPS, quality, selected cameras,
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

The **Password** field is the DVR account password. **Streaming Verification
Code** is a separate, optional Hikvision stream-encryption value and is not
interchangeable with the account password. It can also be supplied through
`HIKVISION_STREAM_VERIFICATION_CODE`. Both values are stored locally in the
user's application settings and are not encrypted; on Linux, the settings file
is restricted to the current user.

### Optional Hikvision Linux SDK backend

The HTTP and RTSP/FFmpeg backends remain available and do not require vendor
libraries. RTSP/FFmpeg remains the default. To use the optional Hikvision
backend:

1. In the viewer, open **Settings** and click **Get SDK**. This opens
   Hikvision's official [HiTools SDK download page](https://www.hikvision.com/en/support/tools/hitools/clf4633a00e385d6ea/)
   in your browser. Download the **Device Network SDK for Linux 64-bit**
   package matching your computer's CPU architecture. For x86-64,
   **V6.1.11.40, build 20260922** is the version validated with this
   application. Hikvision may require an account or acceptance of its license
   terms to access the download.
2. Extract the archive outside the application source directory. For example:

   ```text
   ~/Downloads/EN-HCNetSDKV6.1.11.40_build20260922_linux64/
   ```

   Use the extracted SDK root containing `lib/`, `incEn/`, and `QtDemo/`—not
   the `lib/` subdirectory—as the SDK directory.
3. Back in **Settings**, use **Browse...** to select the SDK root and click
   **Build / Verify Helper**. This builds the open integration helper locally
   against your SDK, installs it under
   `~/.local/lib/hikvision-camera-viewer/`, and checks that the libraries load.
   The build requires `make` and a C++17 compiler (`g++`) available to the app.
   No vendor binaries are downloaded or bundled by the application.
4. Set these values in **Settings**:
   - **Hikvision SDK Directory** to the extracted SDK root (or set
     `HIKVISION_SDK_DIR` before starting the application).
   - **Hikvision SDK Port** to the DVR's SDK port, usually `8000`.
   - **Username** and **Password** to a DVR account with live-view permission.
   - **Streaming Verification Code** to the separate Platform Access stream
     encryption code; it is not the DVR account password.

Select **Hikvision SDK (encrypted stream)** in the toolbar's **Engine**
selector. Choose the SDK directory itself, not its `lib/` folder. Before
capture, the application checks the SDK architecture and required libraries
and runs a local HCNetSDK initialization / PlayCtrl allocation check during
**Build / Verify Helper**. Missing compilers, libraries, or incompatible
architectures are reported explicitly; the application does not silently fall
back to RTSP. Flatpak runtimes may not include a C++ compiler, so use a native
installation or an AppImage with host `make` and `g++` available for this setup
flow.

PlayCtrl runs in a separate helper process with a headless/surfaceless
environment so its EGL settings cannot change the Qt application's Wayland or
X11 session. The helper passes the retrieved 16-byte AES key to
`NET_DVR_SetSDKSecretKey` and the separate Streaming Verification Code to
`PlayM4_SetSecretKey` before opening the decoder stream. The application
reports the verification code as applied only when the PlayCtrl call succeeds.
On the `iDS-7204HQHI-M1/T`, channel 1 has been verified through the application
frame pipeline at 960x480 on the sub-stream and 1920x1088 on the main stream.
This verifies the tested device and configuration, not every Hikvision model
or firmware. See the [Hikvision SDK helper guide](./hikvision-sdk/README.md)
for build and diagnostic details.
The documented ISAPI `PUT /ISAPI/System/Network/EZVIZ/secretKey?format=json`
edits the Guarding Vision verification code on the device; it is not called by
the viewer and is not required for local decoder configuration.

Hikvision SDK and PlayCtrl are proprietary vendor components. Obtain them
through Hikvision and review the package's license and redistribution terms.
This project does not ship, download, or redistribute their binaries. The
helper is built locally from the included integration source against the
separately obtained SDK. The Flatpak sandbox does not grant access to arbitrary
host SDK directories. Use a native installation or AppImage for the external
SDK backend unless you deliberately grant the Flatpak access to the separately
installed SDK. The
existing HTTP and RTSP features remain usable without those permissions or
libraries.

## License

This project is licensed under the [MIT License](./LICENSE).
