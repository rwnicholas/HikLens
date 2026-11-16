#!/usr/bin/env python3
"""
Hikvision Camera Viewer Application
Configure the DVR through the Settings dialog or DVR_* environment variables.
"""

import sys
import os

# AMD RX 7800 XT — use VAAPI (radeonsi) for hardware-accelerated decode.
# Do NOT set QT_FFMPEG_NO_HWACCEL; let Qt/FFmpeg pick VAAPI automatically.
os.environ.setdefault("LIBVA_DRIVER_NAME", "radeonsi")
os.environ.setdefault("LIBVA_DRI_DEVICE", "/dev/dri/renderD128")
# Suppress the irrelevant VDPAU (Nvidia-only) probe that Qt prints on startup
os.environ.setdefault("VDPAU_DRIVER", "va_gl")  # harmless redirect

import time
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

import requests
from requests.auth import HTTPDigestAuth

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer, QSize, QPoint, QUrl
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QFont, QPen, QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QSlider, QStatusBar,
    QToolBar, QFrame, QFileDialog, QMessageBox, QDialog, QLineEdit,
    QFormLayout, QDialogButtonBox, QStackedWidget, QSplitter,
    QListWidget, QListWidgetItem, QCheckBox
)


@dataclass
class DVRConfig:
    ip: str = os.getenv("DVR_IP", "192.0.2.1")
    http_port: int = 80
    rtsp_port: int = 554
    username: str = os.getenv("DVR_USERNAME", "")
    password: str = os.getenv("DVR_PASSWORD", "")
    channels: list = None

    def __post_init__(self):
        if self.channels is None:
            self.channels = [1, 2, 3, 4]

    def snapshot_url(self, channel: int, resolution_mode: str = "max") -> str:
        if resolution_mode == "max":
            return f"http://{self.ip}:{self.http_port}/ISAPI/Streaming/channels/{channel}01/picture?videoResolutionWidth=1920&videoResolutionHeight=1080"
        return f"http://{self.ip}:{self.http_port}/ISAPI/Streaming/channels/{channel}01/picture"

    def rtsp_url(self, channel: int, stream: int = 1) -> str:
        # stream 1 = main stream (high res), stream 2 = sub stream (smooth grid)
        return f"rtsp://{self.username}:{self.password}@{self.ip}:{self.rtsp_port}/Streaming/Channels/{channel}0{stream}"

    def alert_url(self) -> str:
        return f"http://{self.ip}:{self.http_port}/ISAPI/Event/notification/alertStream"


# ==============================================================================
# Camera Streaming Worker Thread
# ==============================================================================
class CameraWorker(QThread):
    frame_ready = Signal(int, QImage)
    status_changed = Signal(int, str, bool)  # channel, status_text, is_online
    fps_updated = Signal(int, float)
    log_event = Signal(int, str, str)  # channel, level, message

    def __init__(self, channel: int, config: DVRConfig, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.config = config
        self._running = True
        self._active = True
        self._target_fps = 10
        self._paused = False
        self._resolution_mode = "auto"
        self._is_focused = False

    def set_active(self, active: bool):
        self._active = active

    def set_focused(self, focused: bool):
        self._is_focused = focused

    def set_paused(self, paused: bool):
        self._paused = paused

    def set_target_fps(self, fps: int):
        self._target_fps = max(1, min(fps, 30))

    def set_resolution_mode(self, mode: str):
        self._resolution_mode = mode

    def get_effective_resolution(self) -> str:
        if self._resolution_mode == "max":
            return "max"
        elif self._resolution_mode == "standard":
            return "standard"
        else:  # "auto"
            return "max" if self._is_focused else "standard"

    def stop(self):
        self._running = False
        self.wait(1500)

    def run(self):
        import threading

        frames_counted = 0
        last_fps_time = time.time()
        self.status_changed.emit(self.channel, "Connecting...", False)

        def sub_worker(sub_id: int):
            nonlocal frames_counted
            s = requests.Session()
            s.auth = HTTPDigestAuth(self.config.username, self.config.password)
            time.sleep(sub_id * 0.08)  # Stagger requests by 80ms
            backoff = 0.5
            failure_logged = False
            while self._running:
                if not self._active or self._paused:
                    time.sleep(0.08)
                    continue

                # If low FPS selected (<= 5 FPS), only worker 0 runs
                if sub_id > 0 and self._target_fps <= 5:
                    time.sleep(0.15)
                    continue

                res_mode = self.get_effective_resolution()
                url = self.config.snapshot_url(self.channel, res_mode)
                t_req = time.time()
                try:
                    resp = s.get(url, timeout=2.5)
                    if resp.status_code == 200:
                        img = QImage.fromData(resp.content)
                        if not img.isNull():
                            self.frame_ready.emit(self.channel, img)
                            frames_counted += 1
                            self.status_changed.emit(self.channel, "Online", True)
                            backoff = 0.5
                            failure_logged = False
                    else:
                        self.status_changed.emit(self.channel, f"HTTP {resp.status_code}", False)
                        if not failure_logged:
                            self.log_event.emit(
                                self.channel,
                                "error",
                                f"HTTP snapshot request failed (HTTP {resp.status_code})",
                            )
                            failure_logged = True
                        time.sleep(backoff)
                        backoff = min(backoff * 1.5, 4.0)
                except Exception as e:
                    self.status_changed.emit(self.channel, "Offline", False)
                    if not failure_logged:
                        self.log_event.emit(
                            self.channel,
                            "error",
                            f"HTTP snapshot request failed ({type(e).__name__})",
                        )
                        failure_logged = True
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 4.0)

                # Regulate to target_fps across workers
                elapsed = time.time() - t_req
                target_gap = 2.0 / self._target_fps
                if elapsed < target_gap:
                    time.sleep(target_gap - elapsed)

        threads = [threading.Thread(target=sub_worker, args=(i,), daemon=True) for i in range(2)]
        for t in threads: t.start()

        while self._running:
            self.msleep(1000)
            now = time.time()
            dur = now - last_fps_time
            if dur >= 0.9:
                fps = frames_counted / dur
                self.fps_updated.emit(self.channel, round(fps, 1))
                frames_counted = 0
                last_fps_time = now

        for t in threads:
            t.join(timeout=0.5)


# ==============================================================================
# Hikvision Alert Stream Worker Thread (Motion Detection)
# ==============================================================================
class AlertStreamWorker(QThread):
    motion_event = Signal(int, str)  # channel, timestamp_str
    alert_status = Signal(str)

    def __init__(self, config: DVRConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._running = True

    def stop(self):
        self._running = False
        self.wait(1000)

    def run(self):
        url = self.config.alert_url()
        while self._running:
            try:
                self.alert_status.emit("Connecting to AlertStream...")
                with requests.get(
                    url,
                    auth=HTTPDigestAuth(self.config.username, self.config.password),
                    stream=True,
                    timeout=15.0
                ) as resp:
                    if resp.status_code != 200:
                        self.alert_status.emit(f"AlertStream HTTP {resp.status_code}")
                        time.sleep(5)
                        continue

                    self.alert_status.emit("AlertStream Active")
                    buffer = ""
                    for chunk in resp.iter_content(chunk_size=1024):
                        if not self._running:
                            break
                        if not chunk:
                            continue
                        buffer += chunk.decode('latin-1', errors='ignore')

                        if "</EventNotificationAlert>" in buffer:
                            parts = buffer.split("</EventNotificationAlert>")
                            for xml_block in parts[:-1]:
                                self._parse_alert(xml_block)
                            buffer = parts[-1]

                        if len(buffer) > 100000:
                            buffer = buffer[-4096:]

            except requests.exceptions.Timeout:
                # normal keepalive timeout, retry
                continue
            except Exception as e:
                self.alert_status.emit(f"AlertStream reconnecting...")
                time.sleep(3)

    def _parse_alert(self, xml: str):
        # Look for motion events matching sketch_aug14a.ino criteria
        is_motion = ("<eventType>VMD</eventType>" in xml or
                     "<eventType>motion</eventType>" in xml or
                     "<eventType>Motion alarm</eventType>" in xml)
        if not is_motion:
            return

        ch_match = re.search(r"<channelID>(\d+)</channelID>", xml)
        if ch_match:
            try:
                channel = int(ch_match.group(1))
                now_str = datetime.now().strftime("%H:%M:%S")
                self.motion_event.emit(channel, now_str)
            except ValueError:
                pass


# ==============================================================================
# Embedded RTSP Video Player (ffmpeg subprocess → JPEG pipe backend)
# Bypasses Qt Multimedia's broken H.264 decoder for Hikvision streams.
# Uses system ffmpeg with VAAPI hw-decode, falls back to software decode.
# ==============================================================================
class RTSPCameraPlayer(QThread):
    frame_ready = Signal(int, QImage)
    status_changed = Signal(int, str, bool)
    fps_updated = Signal(int, float)
    log_event = Signal(int, str, str)  # channel, level, message

    # JPEG SOI / EOI markers
    _SOI = b"\xff\xd8"
    _EOI = b"\xff\xd9"

    def __init__(self, channel: int, config: DVRConfig, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.config = config
        self._active = True
        self._paused = False
        self._is_focused = False
        self._resolution_mode = "auto"
        self._running = True
        self._proc = None
        self._restart_requested = False
        self._frames_counted = 0
        self._last_fps_time = time.time()
        self._error_logged = False

        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._calc_fps)
        self.fps_timer.start(1000)

    # ------------------------------------------------------------------
    # Public control API (matches CameraWorker interface)
    # ------------------------------------------------------------------
    def start(self):
        """(Re)start the ffmpeg pipe; called from main thread."""
        self._restart_requested = True
        if not self.isRunning():
            super().start()

    def stop(self):
        self._running = False
        self._kill_proc()
        self.wait(2000)

    def set_active(self, active: bool):
        self._active = active
        if active:
            self.start()
        else:
            self._kill_proc()
            self.status_changed.emit(self.channel, "Inactive", False)

    def set_focused(self, focused: bool):
        if self._is_focused != focused:
            self._is_focused = focused
            self._restart_requested = True

    def set_paused(self, paused: bool):
        self._paused = paused
        # ffmpeg keeps running; we just stop forwarding frames

    def set_target_fps(self, fps: int):
        pass  # native RTSP rate from DVR

    def set_resolution_mode(self, mode: str):
        if self._resolution_mode != mode:
            self._resolution_mode = mode
            self._restart_requested = True

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------
    def run(self):
        import threading as _th
        import queue as _q
        import select as _sel

        while self._running:
            if not self._active:
                self.msleep(200)
                continue

            self._restart_requested = False
            stream = self._pick_stream()
            rtsp_url = self.config.rtsp_url(self.channel, stream=stream)
            self.status_changed.emit(self.channel, "Connecting RTSP…", False)

            cmd = self._build_cmd(rtsp_url)
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
            except FileNotFoundError:
                self.status_changed.emit(self.channel, "ffmpeg not found", False)
                self._log_error("ffmpeg executable not found")
                self.msleep(5000)
                continue
            except OSError as e:
                self.status_changed.emit(self.channel, "Unable to start ffmpeg", False)
                self._log_error(f"Unable to start ffmpeg ({type(e).__name__})")
                self.msleep(5000)
                continue

            # --- Reader threads feed data into queues (never blocks control loop) ---
            stdout_q = _q.Queue(maxsize=256)
            stderr_lines = []

            def _read_stdout():
                try:
                    while True:
                        chunk = self._proc.stdout.read(32768)
                        if not chunk:
                            break
                        stdout_q.put(chunk)
                except Exception:
                    pass
                finally:
                    stdout_q.put(None)  # sentinel

            def _read_stderr():
                try:
                    for line in self._proc.stderr:
                        stderr_lines.append(line)
                except Exception:
                    pass

            _th.Thread(target=_read_stdout, daemon=True).start()
            _th.Thread(target=_read_stderr, daemon=True).start()

            buf = b""
            last_data_time = time.time()
            # Give ffmpeg up to 12 s to connect & produce first frame
            CONNECT_TIMEOUT = 12.0
            IDLE_TIMEOUT    =  8.0   # max silence once streaming started
            got_first_frame = False
            failure_message = None

            while self._running:
                if self._restart_requested:
                    break

                try:
                    chunk = stdout_q.get(timeout=0.25)
                except _q.Empty:
                    # Check timeouts
                    idle = time.time() - last_data_time
                    limit = CONNECT_TIMEOUT if not got_first_frame else IDLE_TIMEOUT
                    if idle > limit:
                        last_err = (stderr_lines[-1].decode(errors="replace").strip()
                                    if stderr_lines else "no frames / timeout")
                        self.status_changed.emit(self.channel,
                                                 f"RTSP err: {last_err[:64]}", False)
                        failure_message = f"RTSP stream failed; reconnecting: {last_err}"
                        break
                    # Also bail if ffmpeg already exited
                    if self._proc.poll() is not None and stdout_q.empty():
                        last_err = (stderr_lines[-1].decode(errors="replace").strip()
                                    if stderr_lines else "ffmpeg exited")
                        self.status_changed.emit(self.channel,
                                                 f"RTSP err: {last_err[:64]}", False)
                        failure_message = f"RTSP stream failed; reconnecting: {last_err}"
                        break
                    continue

                if chunk is None:        # stdout EOF sentinel
                    failure_message = "RTSP stream ended; reconnecting"
                    break

                last_data_time = time.time()
                buf += chunk

                # Extract complete JPEG frames
                while True:
                    start = buf.find(self._SOI)
                    if start == -1:
                        buf = b""
                        break
                    end = buf.find(self._EOI, start + 2)
                    if end == -1:
                        buf = buf[start:]
                        break
                    jpeg_data = buf[start: end + 2]
                    buf = buf[end + 2:]

                    if not self._paused:
                        img = QImage.fromData(jpeg_data, "JPEG")
                        if not img.isNull():
                            got_first_frame = True
                            self._error_logged = False
                            self._frames_counted += 1
                            self.frame_ready.emit(self.channel, img)
                            self.status_changed.emit(self.channel, "Online (RTSP)", True)

            self._kill_proc()

            if self._running and not self._restart_requested:
                if failure_message:
                    self._log_error(failure_message)
                self.status_changed.emit(self.channel, "Reconnecting…", False)
                self.msleep(3000)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _pick_stream(self) -> int:
        """Main stream (1) for focused/max; sub-stream (2) for grid."""
        if self._is_focused or self._resolution_mode in ("max",):
            return 1
        return 1  # Keep stream 1 always until sub-streams are H.264 on DVR

    def _build_cmd(self, rtsp_url: str) -> list:
        """
        Software-decode ffmpeg pipe → MJPEG frames on stdout.
        No hwaccel flags: avoids FFmpeg 9.x API changes and is robust
        against any stream quirks from the Hikvision DVR.
        The bottleneck is the DVR encoder, not the CPU decode step.
        """
        return [
            "ffmpeg",
            "-loglevel", "error",        # capture errors to stderr pipe
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer+discardcorrupt",
            "-flags", "low_delay",
            "-i", rtsp_url,
            # Output raw MJPEG frames to stdout
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-q:v", "4",                 # JPEG quality (2=best … 31=worst)
            "-",
        ]

    def _kill_proc(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdout.close()
                if self._proc.stderr:
                    self._proc.stderr.close()
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None

    def _log_error(self, message: str):
        if self._error_logged:
            return
        safe_message = re.sub(r"rtsp://\S+", "RTSP stream", message, flags=re.IGNORECASE)
        self.log_event.emit(self.channel, "error", safe_message)
        self._error_logged = True

    def _calc_fps(self):
        now = time.time()
        dur = now - self._last_fps_time
        if dur >= 0.9:
            fps = self._frames_counted / dur
            self.fps_updated.emit(self.channel, round(fps, 1))
            self._frames_counted = 0
            self._last_fps_time = now


# ==============================================================================
# Camera View Tile Widget
# ==============================================================================
class CameraViewWidget(QFrame):
    double_clicked = Signal(int)  # emits channel
    snapshot_requested = Signal(int)

    def __init__(self, channel: int, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.last_image = None
        self.status_text = "Initializing..."
        self.is_online = False
        self.fps = 0.0
        self.is_motion_active = False

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setLineWidth(2)
        self.setStyleSheet("""
            CameraViewWidget {
                background-color: #12151c;
                border: 2px solid #232936;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        self.header = QWidget()
        self.header.setStyleSheet("background-color: #1a1e28; border-top-left-radius: 6px; border-top-right-radius: 6px;")
        h_layout = QHBoxLayout(self.header)
        h_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_title = QLabel(f"Camera {self.channel}")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #e2e8f0; font-size: 13px;")

        self.lbl_fps = QLabel("0.0 FPS")
        self.lbl_fps.setStyleSheet("color: #94a3b8; font-size: 11px;")

        self.lbl_res = QLabel("---")
        self.lbl_res.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold; background-color: #0f172a; padding: 1px 5px; border-radius: 3px;")

        self.lbl_status = QLabel("Offline")
        self.lbl_status.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")

        self.lbl_motion = QLabel("🚨 MOTION")
        self.lbl_motion.setStyleSheet("""
            color: #ffffff;
            background-color: #dc2626;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: bold;
        """)
        self.lbl_motion.setVisible(False)

        self.btn_snap = QPushButton("📷")
        self.btn_snap.setToolTip("Quick Snapshot (Saved to ./snapshots)")
        self.btn_snap.setFixedSize(26, 22)
        self.btn_snap.setCursor(Qt.PointingHandCursor)
        self.btn_snap.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #ffffff;
                border: none;
                border-radius: 3px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)
        self.btn_snap.clicked.connect(lambda: self.snapshot_requested.emit(self.channel))

        h_layout.addWidget(self.lbl_title)
        h_layout.addStretch()
        h_layout.addWidget(self.lbl_motion)
        h_layout.addWidget(self.lbl_res)
        h_layout.addWidget(self.lbl_fps)
        h_layout.addWidget(self.lbl_status)
        h_layout.addWidget(self.btn_snap)

        # Video canvas label
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #0d1117; color: #64748b; font-size: 13px;")
        self.video_label.setText(f"Waiting for Camera {self.channel} stream...")

        layout.addWidget(self.header)
        layout.addWidget(self.video_label, 1)

        # Motion timer to clear alert after 4 seconds
        self.motion_clear_timer = QTimer(self)
        self.motion_clear_timer.setSingleShot(True)
        self.motion_clear_timer.timeout.connect(self._clear_motion)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.channel)

    @Slot(QImage)
    def update_frame(self, image: QImage):
        self.last_image = image
        self.lbl_res.setText(f"{image.width()}x{image.height()}")
        target_size = self.video_label.size()
        if target_size.width() > 10 and target_size.height() > 10:
            scaled = image.scaled(
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.video_label.setPixmap(QPixmap.fromImage(scaled))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.last_image is not None:
            target_size = self.video_label.size()
            if target_size.width() > 10 and target_size.height() > 10:
                scaled = self.last_image.scaled(
                    target_size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.video_label.setPixmap(QPixmap.fromImage(scaled))

    @Slot(str, bool)
    def update_status(self, text: str, is_online: bool):
        self.status_text = text
        self.is_online = is_online
        self.lbl_status.setText(text)
        if is_online:
            self.lbl_status.setStyleSheet("color: #22c55e; font-size: 11px; font-weight: bold;")
        else:
            self.lbl_status.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: bold;")

    @Slot(float)
    def update_fps(self, fps: float):
        self.fps = fps
        self.lbl_fps.setText(f"{fps:.1f} FPS")

    def trigger_motion(self):
        self.is_motion_active = True
        self.lbl_motion.setVisible(True)
        self.setStyleSheet("""
            CameraViewWidget {
                background-color: #12151c;
                border: 3px solid #ef4444;
                border-radius: 8px;
            }
        """)
        self.motion_clear_timer.start(4000)

    def _clear_motion(self):
        self.is_motion_active = False
        self.lbl_motion.setVisible(False)
        self.setStyleSheet("""
            CameraViewWidget {
                background-color: #12151c;
                border: 2px solid #232936;
                border-radius: 8px;
            }
        """)


# ==============================================================================
# Settings Dialog
# ==============================================================================
class SettingsDialog(QDialog):
    def __init__(self, config: DVRConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("DVR Connection Settings")
        self.setMinimumWidth(380)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1e28;
                color: #e2e8f0;
            }
            QLabel {
                color: #cbd5e1;
            }
            QLineEdit {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 6px;
                color: #f8fafc;
            }
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.edit_ip = QLineEdit(config.ip)
        self.edit_http_port = QLineEdit(str(config.http_port))
        self.edit_rtsp_port = QLineEdit(str(config.rtsp_port))
        self.edit_user = QLineEdit(config.username)
        self.edit_pass = QLineEdit(config.password)
        self.edit_pass.setEchoMode(QLineEdit.Password)
        self.edit_channels = QLineEdit(", ".join(map(str, config.channels)))

        form.addRow("DVR IP Address:", self.edit_ip)
        form.addRow("HTTP ISAPI Port:", self.edit_http_port)
        form.addRow("RTSP Port:", self.edit_rtsp_port)
        form.addRow("Username:", self.edit_user)
        form.addRow("Password:", self.edit_pass)
        form.addRow("Monitored Channels:", self.edit_channels)

        layout.addLayout(form)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_updated_config(self) -> DVRConfig:
        try:
            chans = [int(c.strip()) for c in self.edit_channels.text().split(",") if c.strip().isdigit()]
            if not chans:
                chans = [1, 2, 3, 4]
        except Exception:
            chans = [1, 2, 3, 4]

        return DVRConfig(
            ip=self.edit_ip.text().strip(),
            http_port=int(self.edit_http_port.text().strip() or "80"),
            rtsp_port=int(self.edit_rtsp_port.text().strip() or "554"),
            username=self.edit_user.text().strip(),
            password=self.edit_pass.text().strip(),
            channels=chans
        )


# ==============================================================================
# Main Application Window
# ==============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hikvision CCTV Stream Viewer")
        self.resize(1280, 800)
        self.setMinimumSize(800, 500)

        self.config = DVRConfig()
        self.snapshot_dir = Path("./snapshots")
        self.snapshot_dir.mkdir(exist_ok=True)

        self.workers = {}
        self.tiles = {}
        self.active_mode = "ALL"  # "ALL", "1", "2", "3", "4"
        self.backend_mode = "HTTP"  # "HTTP" or "RTSP"
        self.is_paused = False
        self.auto_save_motion = False

        self._setup_style()
        self._build_ui()
        self._start_threads()

    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0b0e14;
            }
            QToolBar {
                background-color: #161b26;
                border-bottom: 1px solid #232936;
                padding: 6px;
                spacing: 8px;
            }
            QLabel {
                color: #e2e8f0;
            }
            QComboBox {
                background-color: #1f2937;
                color: #f8fafc;
                border: 1px solid #374151;
                border-radius: 5px;
                padding: 4px 10px;
                min-width: 150px;
                font-weight: bold;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #1f2937;
                color: #f8fafc;
                selection-background-color: #2563eb;
            }
            QPushButton {
                background-color: #1f2937;
                color: #e2e8f0;
                border: 1px solid #374151;
                border-radius: 5px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #374151;
                border-color: #4b5563;
            }
            QPushButton:checked {
                background-color: #2563eb;
                border-color: #3b82f6;
                color: white;
            }
            QStatusBar {
                background-color: #161b26;
                color: #94a3b8;
                border-top: 1px solid #232936;
            }
            QListWidget {
                background-color: #12151c;
                color: #cbd5e1;
                border: 1px solid #232936;
                border-radius: 6px;
            }
        """)

    def _build_ui(self):
        # Top Toolbar
        toolbar = QToolBar("Main Controls")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Camera selection dropdown
        toolbar.addWidget(QLabel(" View: "))
        self.combo_cam = QComboBox()
        self.combo_cam.addItem("🖥️  All Cameras (2x2 Grid)", "ALL")
        for ch in self.config.channels:
            self.combo_cam.addItem(f"📹  Camera {ch}", str(ch))
        self.combo_cam.currentIndexChanged.connect(self._on_combo_selection)
        toolbar.addWidget(self.combo_cam)

        toolbar.addSeparator()

        # Backend Engine selector
        toolbar.addWidget(QLabel(" Engine: "))
        self.combo_backend = QComboBox()
        self.combo_backend.addItem("🌐 HTTP Snapshot (Fast Connect)", "HTTP")
        self.combo_backend.addItem("📡 Embedded RTSP (ffmpeg/VAAPI)", "RTSP")
        self.combo_backend.currentIndexChanged.connect(self._on_backend_changed)
        toolbar.addWidget(self.combo_backend)

        toolbar.addSeparator()

        # Pause / Play button
        self.btn_pause = QPushButton("⏸️ Pause")
        self.btn_pause.setCheckable(True)
        self.btn_pause.clicked.connect(self._toggle_pause)
        toolbar.addWidget(self.btn_pause)

        # Snapshot button
        self.btn_snapshot = QPushButton("📸 Snapshot")
        self.btn_snapshot.setToolTip("Save snapshot of current view (Key: S)")
        self.btn_snapshot.clicked.connect(self._take_snapshot)
        toolbar.addWidget(self.btn_snapshot)

        # HQ RTSP Player button
        self.btn_rtsp = QPushButton("🚀 Open HQ RTSP")
        self.btn_rtsp.setToolTip("Open full-rate hardware stream in ffplay")
        self.btn_rtsp.clicked.connect(self._launch_rtsp)
        toolbar.addWidget(self.btn_rtsp)

        toolbar.addSeparator()

        # FPS selector
        toolbar.addWidget(QLabel(" Speed: "))
        self.combo_fps = QComboBox()
        self.combo_fps.addItem("5 FPS (Low Bandwidth)", 5)
        self.combo_fps.addItem("10 FPS (Balanced)", 10)
        self.combo_fps.addItem("15 FPS (Smooth)", 15)
        self.combo_fps.addItem("Max FPS", 30)
        self.combo_fps.setCurrentIndex(1)
        self.combo_fps.currentIndexChanged.connect(self._on_fps_changed)
        toolbar.addWidget(self.combo_fps)

        toolbar.addSeparator()

        # Resolution Quality selector
        toolbar.addWidget(QLabel(" Quality: "))
        self.combo_quality = QComboBox()
        self.combo_quality.addItem("⚡ Auto (1080p Focus / 480p Grid)", "auto")
        self.combo_quality.addItem("🔥 Max (1080p Full HD Always)", "max")
        self.combo_quality.addItem("💾 Standard (480p Fast)", "standard")
        self.combo_quality.currentIndexChanged.connect(self._on_quality_changed)
        toolbar.addWidget(self.combo_quality)

        toolbar.addSeparator()

        # Auto-snapshot on motion checkbox
        self.chk_auto_motion = QCheckBox("Save on Motion")
        self.chk_auto_motion.setStyleSheet("color: #cbd5e1; margin-left: 6px;")
        toolbar.addWidget(self.chk_auto_motion)

        toolbar.addSeparator()

        # Toggle Event Log Drawer
        self.btn_toggle_log = QPushButton("📜 Events")
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.setChecked(True)
        self.btn_toggle_log.clicked.connect(self._toggle_event_log)
        toolbar.addWidget(self.btn_toggle_log)

        # Settings button
        btn_settings = QPushButton("⚙️ Settings")
        btn_settings.clicked.connect(self._open_settings)
        toolbar.addWidget(btn_settings)

        # Fullscreen button
        self.btn_fullscreen = QPushButton("⛶ Fullscreen")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        toolbar.addWidget(self.btn_fullscreen)

        # Center Video Workspace
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Splitter to allow resizing video vs event log
        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # Stacked widget for Grid vs Single Camera
        self.stacked_view = QStackedWidget()
        self.splitter.addWidget(self.stacked_view)

        # PAGE 0: 2x2 Grid View
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(8)

        # Create camera tiles
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        for idx, ch in enumerate(self.config.channels):
            tile = CameraViewWidget(ch)
            tile.double_clicked.connect(self._on_tile_double_clicked)
            tile.snapshot_requested.connect(self._save_camera_snapshot)
            self.tiles[ch] = tile
            r, c = positions[idx % 4]
            self.grid_layout.addWidget(tile, r, c)

        self.stacked_view.addWidget(self.grid_container)

        # PAGE 1: Single Camera View
        self.single_container = QWidget()
        self.single_layout = QVBoxLayout(self.single_container)
        self.single_layout.setContentsMargins(0, 0, 0, 0)
        self.single_tile = CameraViewWidget(1)
        self.single_tile.double_clicked.connect(lambda ch: self.switch_mode("ALL"))
        self.single_tile.snapshot_requested.connect(self._save_camera_snapshot)
        self.single_layout.addWidget(self.single_tile)
        self.stacked_view.addWidget(self.single_container)

        # Right Panel: Event & Motion Log
        self.log_panel = QWidget()
        self.log_panel.setMinimumWidth(240)
        self.log_panel.setMaximumWidth(360)
        log_layout = QVBoxLayout(self.log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)

        lbl_log = QLabel("🔔 Activity & Motion Log")
        lbl_log.setStyleSheet("font-weight: bold; color: #94a3b8; font-size: 12px; margin-bottom: 4px;")
        log_layout.addWidget(lbl_log)

        self.event_list = QListWidget()
        log_layout.addWidget(self.event_list)

        btn_clear_log = QPushButton("Clear Log")
        btn_clear_log.clicked.connect(self.event_list.clear)
        log_layout.addWidget(btn_clear_log)

        self.splitter.addWidget(self.log_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_status_dvr = QLabel(f"DVR: {self.config.ip} | User: {self.config.username}")
        self.lbl_status_alert = QLabel("AlertStream: Initializing...")
        self.status_bar.addWidget(self.lbl_status_dvr)
        self.status_bar.addPermanentWidget(self.lbl_status_alert)

    def _start_threads(self):
        target_fps = self.combo_fps.currentData()
        res_mode = self.combo_quality.currentData()

        # Stop existing workers
        for w in self.workers.values():
            w.stop()
        self.workers.clear()

        # Start Camera Workers / Players based on selected backend
        for ch in self.config.channels:
            is_focused = (self.active_mode == str(ch))
            if self.backend_mode == "RTSP":
                worker = RTSPCameraPlayer(ch, self.config, self)
                worker.set_resolution_mode(res_mode)
                worker.set_focused(is_focused)
            else:
                worker = CameraWorker(ch, self.config, self)
                worker.set_target_fps(target_fps)
                worker.set_resolution_mode(res_mode)
                worker.set_focused(is_focused)

            worker.frame_ready.connect(self._on_frame_ready)
            worker.status_changed.connect(self._on_worker_status)
            worker.fps_updated.connect(self._on_worker_fps)
            worker.log_event.connect(self._on_worker_log_event)
            self.workers[ch] = worker
            worker.start()

        # Start AlertStream Worker
        if not hasattr(self, 'alert_worker') or not self.alert_worker.isRunning():
            self.alert_worker = AlertStreamWorker(self.config, self)
            self.alert_worker.motion_event.connect(self._on_motion_detected)
            self.alert_worker.alert_status.connect(self.lbl_status_alert.setText)
            self.alert_worker.start()

    def _on_backend_changed(self, index: int):
        self.backend_mode = self.combo_backend.itemData(index)
        self.status_bar.showMessage(f"Switching video engine to {self.backend_mode}...", 3000)
        self._start_threads()

    # ==========================================================================
    # Slot Handlers
    # ==========================================================================
    @Slot(int, QImage)
    def _on_frame_ready(self, channel: int, image: QImage):
        # Update grid tile
        if channel in self.tiles:
            self.tiles[channel].update_frame(image)

        # If in single camera view and this is the active channel, update single view
        if self.active_mode == str(channel):
            self.single_tile.update_frame(image)

    @Slot(int, str, bool)
    def _on_worker_status(self, channel: int, text: str, is_online: bool):
        if channel in self.tiles:
            self.tiles[channel].update_status(text, is_online)
        if self.active_mode == str(channel):
            self.single_tile.update_status(text, is_online)

    @Slot(int, float)
    def _on_worker_fps(self, channel: int, fps: float):
        if channel in self.tiles:
            self.tiles[channel].update_fps(fps)
        if self.active_mode == str(channel):
            self.single_tile.update_fps(fps)

    @Slot(int, str, str)
    def _on_worker_log_event(self, channel: int, level: str, message: str):
        time_str = datetime.now().strftime("%H:%M:%S")
        level_label = level.upper()
        color = {
            "error": "#f87171",
            "warn": "#fbbf24",
            "info": "#38bdf8",
        }.get(level.lower(), "#cbd5e1")
        item = QListWidgetItem(
            f"[{time_str}] {level_label} - Camera {channel}: {message}"
        )
        item.setForeground(QtGui.QBrush(QColor(color)))
        self.event_list.insertItem(0, item)

    @Slot(int, str)
    def _on_motion_detected(self, channel: int, time_str: str):
        # Trigger visual indicator on camera tile
        if channel in self.tiles:
            self.tiles[channel].trigger_motion()
        if self.active_mode == str(channel):
            self.single_tile.trigger_motion()

        # Add to event log list
        item = QListWidgetItem(f"[{time_str}] 🚨 Motion on Camera {channel}")
        item.setForeground(QtGui.QBrush(QColor("#f87171")))
        self.event_list.insertItem(0, item)

        # Auto snapshot if enabled
        if self.chk_auto_motion.isChecked():
            self._save_camera_snapshot(channel, prefix=f"motion_cam{channel}")

    def _on_tile_double_clicked(self, channel: int):
        # Switch to single camera view
        self.switch_mode(str(channel))

    def _on_combo_selection(self, index: int):
        mode = self.combo_cam.itemData(index)
        self.switch_mode(mode)

    def _on_quality_changed(self, index: int):
        q_mode = self.combo_quality.itemData(index)
        for w in self.workers.values():
            w.set_resolution_mode(q_mode)

    def switch_mode(self, mode: str):
        self.active_mode = mode
        if mode == "ALL":
            self.stacked_view.setCurrentIndex(0)
            # Re-sync combo box if switched via double click
            idx = self.combo_cam.findData("ALL")
            if idx >= 0 and self.combo_cam.currentIndex() != idx:
                self.combo_cam.setCurrentIndex(idx)
            # Activate all workers and set focused false
            for w in self.workers.values():
                w.set_focused(False)
                w.set_active(True)
        else:
            ch = int(mode)
            self.single_tile.channel = ch
            self.single_tile.lbl_title.setText(f"Camera {ch} (Enlarged)")
            self.stacked_view.setCurrentIndex(1)
            # Re-sync combo box
            idx = self.combo_cam.findData(mode)
            if idx >= 0 and self.combo_cam.currentIndex() != idx:
                self.combo_cam.setCurrentIndex(idx)
            # Focus on selected camera, keep focused active
            for c_id, w in self.workers.items():
                is_this = (c_id == ch)
                w.set_focused(is_this)
                w.set_active(is_this)

    def _toggle_pause(self):
        self.is_paused = self.btn_pause.isChecked()
        self.btn_pause.setText("▶️ Resume" if self.is_paused else "⏸️ Pause")
        for w in self.workers.values():
            w.set_paused(self.is_paused)

    def _on_fps_changed(self, index: int):
        fps = self.combo_fps.currentData()
        for w in self.workers.values():
            w.set_target_fps(fps)

    def _toggle_event_log(self):
        self.log_panel.setVisible(self.btn_toggle_log.isChecked())

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.btn_fullscreen.setText("⛶ Fullscreen")
        else:
            self.showFullScreen()
            self.btn_fullscreen.setText("⛶ Exit Fullscreen")

    def _save_camera_snapshot(self, channel: int, prefix: str = None):
        img = None
        # Attempt to pull native 1080p max resolution frame directly from DVR
        try:
            url = self.config.snapshot_url(channel, resolution_mode="max")
            resp = requests.get(
                url,
                auth=HTTPDigestAuth(self.config.username, self.config.password),
                timeout=3.0
            )
            if resp.status_code == 200:
                img = QImage.fromData(resp.content)
        except Exception:
            pass

        # Fallback to current live frame buffer
        if img is None or img.isNull():
            if self.active_mode == "ALL":
                if channel in self.tiles and self.tiles[channel].last_image:
                    img = self.tiles[channel].last_image
            else:
                img = self.single_tile.last_image or (self.tiles.get(channel).last_image if channel in self.tiles else None)

        if img is None or img.isNull():
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = prefix or f"cam{channel}"
        fname = self.snapshot_dir / f"{prefix}_{ts}_{img.width()}x{img.height()}.jpg"
        img.save(str(fname), "JPEG", 95)
        self.status_bar.showMessage(f"Snapshot saved ({img.width()}x{img.height()}): {fname.name}", 4000)

        # Log to events
        item = QListWidgetItem(f"[{datetime.now().strftime('%H:%M:%S')}] 📸 Saved {fname.name}")
        item.setForeground(QtGui.QBrush(QColor("#38bdf8")))
        self.event_list.insertItem(0, item)

    def _take_snapshot(self):
        if self.active_mode == "ALL":
            for ch in self.config.channels:
                self._save_camera_snapshot(ch)
            self.status_bar.showMessage("Saved snapshots for all cameras!", 4000)
        else:
            self._save_camera_snapshot(int(self.active_mode))

    def _launch_rtsp(self):
        # Check if active is single or all
        ch = 1 if self.active_mode == "ALL" else int(self.active_mode)
        rtsp_url = self.config.rtsp_url(ch, stream=1)

        # Launch ffplay. Use VAAPI hw-decode via codec name (ffplay 9.x API).
        # The LIBVA_DRI_DEVICE env var (set at startup) points to renderD128.
        cmd = [
            "ffplay",
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-framedrop",
            "-hwaccel", "vaapi",
            "-vcodec", "h264_vaapi",
            "-window_title", f"Camera {ch} - Hikvision HQ RTSP Stream",
            rtsp_url,
        ]
        try:
            subprocess.Popen(cmd)
            self.status_bar.showMessage(f"Launched RTSP player for Camera {ch}", 4000)
        except Exception as ex:
            QMessageBox.warning(self, "RTSP Error", f"Failed to launch ffplay:\n{ex}")

    def _open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            new_config = dialog.get_updated_config()
            self.config = new_config
            self.lbl_status_dvr.setText(f"DVR: {self.config.ip} | User: {self.config.username}")

            # Restart workers with new config
            for w in self.workers.values():
                w.stop()
            self.alert_worker.stop()
            self.workers.clear()
            self._start_threads()
            QMessageBox.information(self, "Settings Saved", "DVR settings updated and connections refreshed!")

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            if self.isFullScreen():
                self._toggle_fullscreen()
            elif self.active_mode != "ALL":
                self.switch_mode("ALL")
        elif key in (Qt.Key_0, Qt.Key_G):
            self.switch_mode("ALL")
        elif key == Qt.Key_1 and 1 in self.config.channels:
            self.switch_mode("1")
        elif key == Qt.Key_2 and 2 in self.config.channels:
            self.switch_mode("2")
        elif key == Qt.Key_3 and 3 in self.config.channels:
            self.switch_mode("3")
        elif key == Qt.Key_4 and 4 in self.config.channels:
            self.switch_mode("4")
        elif key == Qt.Key_S:
            self._take_snapshot()
        elif key == Qt.Key_Space:
            self.btn_pause.click()
        elif key in (Qt.Key_F, Qt.Key_F11):
            self._toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        for w in self.workers.values():
            w.stop()
        if hasattr(self, 'alert_worker'):
            self.alert_worker.stop()
        event.accept()


# ==============================================================================
# Entry Point
# ==============================================================================
def main():
    # Enable High DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    app.setApplicationName("Hikvision CCTV Stream Viewer")

    # Set dark palette base
    font = QFont("Sans-Serif", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
