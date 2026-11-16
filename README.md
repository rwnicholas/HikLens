# Hikvision Camera Viewer Application

A modern desktop application built in Python (PySide6) to monitor Hikvision DVR cameras.

---

## 🌟 Key Features

1. **Dual Video Engines (HTTP Snapshot vs Embedded RTSP)**:
   - **`🌐 HTTP Snapshot (Fast Connect)`**: Uses persistent HTTP Digest sessions to grab frames instantly with zero buffering. Highly stable across all codecs (including H.265+).
   - **`📡 Embedded RTSP (15 FPS Video)`**: Connects directly to the DVR's RTSP hardware stream (`rtsp://.../Streaming/Channels/X01`) using Qt's internal video pipeline. Delivers continuous, full-framerate video **embedded directly inside the app tiles** — no external windows or players required!
   - Easily switch between engines on the fly from the **Engine** dropdown on the toolbar.

2. **Flexible Camera Selection**:
   - **All Cameras (2x2 Grid View)**: Monitor all 4 cameras (Cam 1, Cam 2, Cam 3, Cam 4) simultaneously in real-time.
   - **Single Camera Mode**: Focus on any individual camera (1, 2, 3, or 4) with high-resolution scaling.
   - **Quick Zoom**: Double-click any camera tile in the grid to zoom in immediately; double-click again or press `Esc` to return to the 2x2 grid.

3. **Max Resolution (1080p Full HD)**:
   - **Native Max Resolution**: Supports the hardware's native **1920x1080 Full HD (1920x1088)** stream directly from the DVR.
   - **Quality Selector**:
     - `⚡ Auto (1080p Focus / 480p Grid)`: Uses smooth sub-stream for the 4-camera grid, and automatically switches to **Full HD 1080p** whenever you focus on an individual camera.
     - `🔥 Max (1080p Full HD Always)`: Forces all cameras to stream at full 1080p resolution.
     - `💾 Standard (480p Fast)`: Low-bandwidth mode.
   - Live resolution badge (e.g. `1920x1088`) is displayed on each camera tile in real time.

4. **Real-Time Motion Detection (AlertStream Integration)**:
   - Connects to `/ISAPI/Event/notification/alertStream` in real time (identical to the Arduino firmware).
   - When motion is detected, the corresponding camera flashes a red border and a `🚨 MOTION` badge appears.
   - Activity log tracks timestamps of all motion events.
   - Camera connection failures are also recorded in the Activity & Motion Log.
   - Optional **"Save on Motion"** toggle automatically captures full-resolution snapshots to `./snapshots/` upon motion.

5. **Instant Snapshots**:
   - Click the 📸 button (or press `S`) to save uncompressed high-resolution snapshots directly to `./snapshots/`.

5. **HQ RTSP Stream Launcher**:
   - Click **"Open HQ RTSP"** to spawn `ffplay` with low-latency flags (`-fflags nobuffer -flags low_delay -framedrop`) for full-framerate hardware decoding when needed.

6. **Interactive Hotkeys**:
   - `0` or `G`: Switch to All Cameras (2x2 Grid)
   - `1`, `2`, `3`, `4`: Switch to Camera 1, 2, 3, 4
   - `Double-Click`: Zoom in on clicked camera / Zoom out to grid
   - `Space`: Pause / Resume stream
   - `S`: Take snapshot
   - `F` or `F11`: Fullscreen toggle
   - `Esc`: Return from single camera to grid, or exit fullscreen

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

## ⚙️ DVR Configuration

Configure the DVR by clicking **⚙️ Settings**. Values are saved in the current
user's application settings and restored on the next launch. `DVR_IP`,
`DVR_USERNAME`, and `DVR_PASSWORD` environment variables are used when no saved
setting exists. The default IP is the documentation-only address `192.0.2.1`;
set it to your DVR's address before connecting. HTTP and RTSP ports default to
`80` and `554`.

The password is stored locally in the user's application settings and is not
encrypted. On Linux, the settings file is restricted to the current user.
