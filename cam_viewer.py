#!/usr/bin/env python3
"""
HikLens — DVR & CCTV Camera Viewer for Linux and Steam Deck
Configure the DVR through the Settings dialog or DVR_* environment variables.
"""

import sys
import os
import queue
import threading
import math
from urllib.parse import quote

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
from dataclasses import dataclass, field
from datetime import datetime

import requests
from requests.auth import HTTPDigestAuth

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import (
    Qt, QBuffer, QIODevice, QThread, Signal, Slot, QTimer, QSize, QPoint,
    QDateTime, QStandardPaths, QUrl,
)
from PySide6.QtGui import (
    QImage,
    QPixmap,
    QPainter,
    QColor,
    QFont,
    QPen,
    QAction,
    QIcon,
    QDesktopServices,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QInputDialog, QSlider, QStatusBar,
    QToolBar, QFrame, QFileDialog, QMessageBox, QDialog, QLineEdit,
    QFormLayout, QDialogButtonBox, QStackedWidget, QSplitter,
    QListWidget, QListWidgetItem, QCheckBox, QDateTimeEdit,
)
from PySide6.QtSvg import QSvgRenderer

from capture_backends import (
    CaptureBackend,
    create_capture_backend,
    supports_selectable_fps,
)
from hikvision_backend import HikvisionCameraPlayer, HikvisionPlaybackPlayer
from hikvision_sdk import (
    HIKVISION_SDK_DOWNLOAD_URL,
    HikvisionRecording,
    HikvisionSDKError,
    build_hikvision_helper,
    list_hikvision_recordings,
    recording_file_type_label,
)
from steam_deck import (
    STEAM_DECK_HEIGHT,
    STEAM_DECK_WIDTH,
    LinuxGamepadReader,
    is_steam_deck_hardware,
    is_steam_gaming_mode,
    register_steam_shortcut,
    trigger_steam_osk,
)


_ICON_SVGS = {
    "grid": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/><rect x="13" y="13" width="8" height="8" rx="1"/></svg>',
    "camera": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h3l2-3h6l2 3h3a2 2 0 0 1 2 2v10H2V9a2 2 0 0 1 2-2Z"/><circle cx="12" cy="13" r="3.5"/></svg>',
    "network": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>',
    "stream": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2"/><path d="M7.8 7.8a6 6 0 0 0 0 8.4M16.2 7.8a6 6 0 0 1 0 8.4M4.3 4.3a11 11 0 0 0 0 15.4M19.7 4.3a11 11 0 0 1 0 15.4"/></svg>',
    "pause": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#cbd5e1" d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>',
    "play": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#cbd5e1" d="M6 3.8v16.4L20 12z"/></svg>',
    "record": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="#ef4444"/></svg>',
    "playback": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path fill="#38bdf8" stroke="none" d="M10 8.5v7l6-3.5-6-3.5z"/></svg>',
    "stop": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14" rx="2" fill="#ef4444"/></svg>',
    "auto": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#fbbf24" d="M13.5 2 5 13h5l-.5 9L19 10h-5z"/></svg>',
    "max": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#fb923c" d="m12 2 2.8 6.1 6.7.7-5 4.5 1.4 6.6-5.9-3.4-5.9 3.4 1.4-6.6-5-4.5 6.7-.7z"/></svg>',
    "standard": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/></svg>',
    "events": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>',
    "settings": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.7 2.9-.2-.1a1.7 1.7 0 0 0-1.8.2l-.2.1h-3.4l-.1-.2a1.7 1.7 0 0 0-1.6-1l-.2.1-3-1.7.1-.2a1.7 1.7 0 0 0-.2-1.8l-.1-.2v-3.4l.2-.1a1.7 1.7 0 0 0 1-1.6l-.1-.2 1.7-3 .2.1a1.7 1.7 0 0 0 1.8-.2l.2-.1h3.4l.1.2a1.7 1.7 0 0 0 1.6 1l.2-.1 3 1.7-.1.2a1.7 1.7 0 0 0 .2 1.8l.1.2v3.4z"/></svg>',
    "fullscreen": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#cbd5e1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5"/></svg>',
    "gamepad": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="4"/><path d="M6 12h4M8 10v4"/><circle cx="15" cy="11" r="1" fill="#38bdf8"/><circle cx="17" cy="13" r="1" fill="#38bdf8"/></svg>',
}


def _make_icon(name: str) -> QIcon:
    renderer = QSvgRenderer(QtCore.QByteArray(_ICON_SVGS[name].encode("utf-8")))
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def _configure_dark_theme(app: QApplication):
    app.setStyle("Fusion")
    palette = QtGui.QPalette()
    for role, color in (
        (QtGui.QPalette.ColorRole.Window, "#0b0e14"),
        (QtGui.QPalette.ColorRole.WindowText, "#e2e8f0"),
        (QtGui.QPalette.ColorRole.Base, "#12151c"),
        (QtGui.QPalette.ColorRole.AlternateBase, "#1f2937"),
        (QtGui.QPalette.ColorRole.ToolTipBase, "#1f2937"),
        (QtGui.QPalette.ColorRole.ToolTipText, "#f8fafc"),
        (QtGui.QPalette.ColorRole.Text, "#f8fafc"),
        (QtGui.QPalette.ColorRole.Button, "#1f2937"),
        (QtGui.QPalette.ColorRole.ButtonText, "#e2e8f0"),
        (QtGui.QPalette.ColorRole.BrightText, "#ffffff"),
        (QtGui.QPalette.ColorRole.Link, "#38bdf8"),
        (QtGui.QPalette.ColorRole.Highlight, "#2563eb"),
        (QtGui.QPalette.ColorRole.HighlightedText, "#ffffff"),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.Text,
        QColor("#6b7280"),
    )
    palette.setColor(
        QtGui.QPalette.ColorGroup.Disabled,
        QtGui.QPalette.ColorRole.ButtonText,
        QColor("#6b7280"),
    )
    app.setPalette(palette)


@dataclass
class DVRConfig:
    ip: str = os.getenv("DVR_IP", "192.0.2.1")
    http_port: int = 80
    rtsp_port: int = 554
    username: str = os.getenv("DVR_USERNAME", "")
    password: str = os.getenv("DVR_PASSWORD", "")
    stream_verification_code: str = os.getenv(
        "HIKVISION_STREAM_VERIFICATION_CODE", ""
    )
    channels: list = None
    sdk_port: int = 8000
    sdk_directory: str = os.getenv("HIKVISION_SDK_DIR", "")

    def __post_init__(self):
        if self.channels is None:
            self.channels = [1, 2, 3, 4]

    def snapshot_url(self, channel: int, resolution_mode: str = "max") -> str:
        if resolution_mode == "max":
            return f"http://{self.ip}:{self.http_port}/ISAPI/Streaming/channels/{channel}01/picture?videoResolutionWidth=1920&videoResolutionHeight=1080"
        return f"http://{self.ip}:{self.http_port}/ISAPI/Streaming/channels/{channel}01/picture"

    def rtsp_url(self, channel: int, stream: int = 1) -> str:
        # stream 1 = main stream (high res), stream 2 = sub stream (smooth grid)
        credentials = ""
        if self.username or self.password:
            username = quote(self.username, safe="")
            password = quote(self.password, safe="")
            credentials = f"{username}:{password}@"
        return (
            f"rtsp://{credentials}{self.ip}:{self.rtsp_port}"
            f"/Streaming/Channels/{channel}0{stream}"
        )

    def alert_url(self) -> str:
        return f"http://{self.ip}:{self.http_port}/ISAPI/Event/notification/alertStream"


@dataclass
class ViewerState:
    backend_mode: str = "RTSP"
    fps: int = 10
    quality_mode: str = "auto"
    active_mode: str = "ALL"
    visible_channels: list = field(default_factory=list)
    events_visible: bool = True
    auto_save_motion: bool = False
    artifact_directory: str = ""


def default_artifact_directory():
    if os.environ.get("FLATPAK_ID"):
        pictures_dir = QStandardPaths.writableLocation(
            QStandardPaths.PicturesLocation
        )
        return str((Path(pictures_dir) / "HikLens").resolve())
    return str(Path("./snapshots").resolve())


def camera_grid_dimensions(camera_count: int):
    if camera_count < 1:
        raise ValueError("Camera count must be at least one.")
    columns = math.ceil(math.sqrt(camera_count))
    rows = math.ceil(camera_count / columns)
    return rows, columns


def load_dvr_config(settings: QtCore.QSettings) -> DVRConfig:
    defaults = DVRConfig()
    ip = str(settings.value("dvr/ip", defaults.ip) or "").strip()
    username = str(settings.value("dvr/username", defaults.username) or "").strip()
    password = str(settings.value("dvr/password", defaults.password) or "")
    stream_verification_code = str(
        settings.value(
            "dvr/stream_verification_code",
            defaults.stream_verification_code,
        )
        or ""
    )

    def read_port(key: str, default: int) -> int:
        try:
            port = int(settings.value(key, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Saved setting {key} must be a port number.") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"Saved setting {key} must be between 1 and 65535.")
        return port

    raw_channels = settings.value("dvr/channels", ",".join(map(str, defaults.channels)))
    channel_tokens = (
        [str(channel).strip() for channel in raw_channels]
        if isinstance(raw_channels, (list, tuple))
        else str(raw_channels).split(",")
    )
    if not channel_tokens or any(not token.strip().isdigit() for token in channel_tokens):
        raise ValueError("Saved monitored channels must be comma-separated numbers.")
    channels = [int(token) for token in channel_tokens]
    if any(channel < 1 for channel in channels) or len(set(channels)) != len(channels):
        raise ValueError("Saved monitored channels must be positive and unique.")
    if not ip:
        raise ValueError("Saved DVR IP address cannot be empty.")

    return DVRConfig(
        ip=ip,
        http_port=read_port("dvr/http_port", defaults.http_port),
        rtsp_port=read_port("dvr/rtsp_port", defaults.rtsp_port),
        sdk_port=read_port("dvr/sdk_port", defaults.sdk_port),
        username=username,
        password=password,
        stream_verification_code=stream_verification_code,
        channels=channels,
        sdk_directory=str(
            settings.value("dvr/sdk_directory", defaults.sdk_directory) or ""
        ).strip(),
    )


def save_dvr_config(settings: QtCore.QSettings, config: DVRConfig):
    settings_path = Path(settings.fileName())
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        fd = os.open(settings_path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        os.chmod(settings_path, 0o600)

    settings.setValue("dvr/ip", config.ip)
    settings.setValue("dvr/http_port", config.http_port)
    settings.setValue("dvr/rtsp_port", config.rtsp_port)
    settings.setValue("dvr/sdk_port", config.sdk_port)
    settings.setValue("dvr/sdk_directory", config.sdk_directory)
    settings.setValue("dvr/username", config.username)
    settings.setValue("dvr/password", config.password)
    settings.setValue(
        "dvr/stream_verification_code",
        config.stream_verification_code,
    )
    settings.setValue("dvr/channels", ",".join(map(str, config.channels)))
    settings.sync()

    if settings.status() != QtCore.QSettings.NoError:
        raise OSError(f"Could not save DVR settings to {settings_path}.")
    if os.name == "posix":
        os.chmod(settings_path, 0o600)


def load_viewer_state(
    settings: QtCore.QSettings, channels: list, default_directory: str
) -> ViewerState:
    defaults = ViewerState(
        visible_channels=list(channels), artifact_directory=default_directory
    )
    try:
        raw_visible_channels = settings.value("viewer/visible_channels")
        if raw_visible_channels is None:
            legacy_count = int(
                settings.value("viewer/camera_count", len(channels))
            )
            legacy_count = min(max(legacy_count, 1), len(channels))
            visible_channels = list(channels[:legacy_count])
        else:
            channel_tokens = (
                [str(channel).strip() for channel in raw_visible_channels]
                if isinstance(raw_visible_channels, (list, tuple))
                else str(raw_visible_channels).split(",")
            )
            if not channel_tokens or any(not token.isdigit() for token in channel_tokens):
                raise ValueError("Saved visible cameras must be comma-separated numbers.")
            saved_channels = [int(token) for token in channel_tokens]
            if any(channel < 1 for channel in saved_channels) or len(
                set(saved_channels)
            ) != len(saved_channels):
                raise ValueError("Saved visible cameras must be positive and unique.")
            selected = set(saved_channels)
            visible_channels = [
                channel for channel in channels if channel in selected
            ]
            if not visible_channels:
                visible_channels = list(channels)

        state = ViewerState(
            backend_mode=str(settings.value("viewer/backend", defaults.backend_mode)),
            fps=int(settings.value("viewer/fps", defaults.fps)),
            quality_mode=str(settings.value("viewer/quality", defaults.quality_mode)),
            active_mode=str(settings.value("viewer/mode", defaults.active_mode)),
            visible_channels=visible_channels,
            events_visible=settings.value(
                "viewer/events_visible", defaults.events_visible, type=bool
            ),
            auto_save_motion=settings.value(
                "viewer/auto_save_motion", defaults.auto_save_motion, type=bool
            ),
            artifact_directory=str(
                settings.value("viewer/artifact_directory", default_directory)
            ).strip(),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Saved viewer state contains invalid values.") from exc

    if state.backend_mode not in {"HTTP", "RTSP", "HIKVISION"}:
        raise ValueError("Saved video engine is not supported.")
    if state.fps not in {5, 10, 15, 30}:
        raise ValueError("Saved frame-rate selection is invalid.")
    if state.quality_mode not in {"auto", "max", "standard"}:
        raise ValueError("Saved quality mode is invalid.")
    if state.active_mode != "ALL" and state.active_mode not in {
        str(channel) for channel in channels
    }:
        raise ValueError("Saved camera view is not in the monitored channel list.")
    if not state.visible_channels:
        raise ValueError("At least one grid camera must be selected.")
    if not state.artifact_directory:
        raise ValueError("Saved artifact directory cannot be empty.")
    state.artifact_directory = str(
        Path(state.artifact_directory).expanduser().resolve()
    )
    return state


def save_viewer_state(
    settings: QtCore.QSettings,
    state: ViewerState,
    geometry: QtCore.QByteArray,
    splitter_state: QtCore.QByteArray,
):
    settings.setValue("viewer/backend", state.backend_mode)
    settings.setValue("viewer/fps", state.fps)
    settings.setValue("viewer/quality", state.quality_mode)
    settings.setValue("viewer/mode", state.active_mode)
    settings.setValue(
        "viewer/visible_channels",
        ",".join(map(str, state.visible_channels)),
    )
    settings.setValue("viewer/events_visible", state.events_visible)
    settings.setValue("viewer/auto_save_motion", state.auto_save_motion)
    settings.setValue("viewer/artifact_directory", state.artifact_directory)
    settings.setValue("viewer/window_geometry", geometry)
    settings.setValue("viewer/splitter_state", splitter_state)
    settings.sync()

    if settings.status() != QtCore.QSettings.NoError:
        raise OSError(f"Could not save viewer settings to {settings.fileName()}.")


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
        self._stop_event = threading.Event()

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
        self._stop_event.set()
        self.wait()

    def run(self):
        frames_counted = 0
        last_fps_time = time.time()
        self.status_changed.emit(self.channel, "Connecting...", False)

        def sub_worker(sub_id: int):
            nonlocal frames_counted
            s = requests.Session()
            s.auth = HTTPDigestAuth(self.config.username, self.config.password)
            if self._stop_event.wait(sub_id * 0.08):
                return
            backoff = 0.5
            failure_logged = False
            while self._running:
                if not self._active or self._paused:
                    self._stop_event.wait(0.08)
                    continue

                # If low FPS selected (<= 5 FPS), only worker 0 runs
                if sub_id > 0 and self._target_fps <= 5:
                    self._stop_event.wait(0.15)
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
                        self._stop_event.wait(backoff)
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
                    self._stop_event.wait(backoff)
                    backoff = min(backoff * 1.5, 4.0)

                # Regulate to target_fps across workers
                elapsed = time.time() - t_req
                worker_count = 1 if self._target_fps <= 5 else 2
                target_gap = worker_count / self._target_fps
                if elapsed < target_gap:
                    self._stop_event.wait(target_gap - elapsed)

        threads = [threading.Thread(target=sub_worker, args=(i,), daemon=True) for i in range(2)]
        for t in threads: t.start()

        while self._running:
            self.msleep(100)
            now = time.time()
            dur = now - last_fps_time
            if dur >= 0.9:
                fps = frames_counted / dur
                self.fps_updated.emit(self.channel, round(fps, 1))
                frames_counted = 0
                last_fps_time = now

        for t in threads:
            t.join()


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
        self._stop_event = threading.Event()

    def stop(self):
        self._running = False
        self._stop_event.set()
        self.wait()

    def run(self):
        url = self.config.alert_url()
        while self._running:
            try:
                self.alert_status.emit("Connecting to AlertStream...")
                with requests.get(
                    url,
                    auth=HTTPDigestAuth(self.config.username, self.config.password),
                    stream=True,
                    timeout=(5.0, 1.0)
                ) as resp:
                    if resp.status_code != 200:
                        self.alert_status.emit(f"AlertStream HTTP {resp.status_code}")
                        self._stop_event.wait(5)
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
                self._stop_event.wait(3)

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
        self._target_fps = 10
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
        self.wait()

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
        self._target_fps = max(1, min(fps, 30))

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

        last_frame_time = 0.0
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
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
                self._proc = proc
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
                        chunk = proc.stdout.read(32768)
                        if not chunk:
                            break
                        stdout_q.put(chunk)
                except Exception:
                    pass
                finally:
                    stdout_q.put(None)  # sentinel

            def _read_stderr():
                try:
                    for line in proc.stderr:
                        stderr_lines.append(line)
                except Exception:
                    pass

            _th.Thread(target=_read_stdout, daemon=True).start()
            stderr_reader = _th.Thread(target=_read_stderr, daemon=True)
            stderr_reader.start()

            buf = b""
            last_data_time = time.time()
            # Allow RTSP negotiation and decoder startup before reconnecting.
            CONNECT_TIMEOUT = 18.0
            IDLE_TIMEOUT    = 18.0
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
                        last_err = self._sanitize_error(
                            stderr_lines[-1].decode(errors="replace").strip()
                            if stderr_lines
                            else "no frames / timeout"
                        )
                        self.status_changed.emit(self.channel,
                                                 f"RTSP err: {last_err[:64]}", False)
                        failure_message = f"RTSP stream failed; reconnecting: {last_err}"
                        break
                    # Also bail if ffmpeg already exited
                    if proc.poll() is not None and stdout_q.empty():
                        last_err = self._process_exit_reason(
                            proc, stderr_lines, stderr_reader
                        )
                        self.status_changed.emit(self.channel,
                                                 f"RTSP err: {last_err[:64]}", False)
                        failure_message = f"RTSP stream failed; reconnecting: {last_err}"
                        break
                    continue

                if chunk is None:        # stdout EOF sentinel
                    last_err = self._process_exit_reason(
                        proc, stderr_lines, stderr_reader
                    )
                    self.status_changed.emit(
                        self.channel, f"RTSP err: {last_err[:64]}", False
                    )
                    failure_message = f"RTSP stream ended; reconnecting: {last_err}"
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

                    now = time.monotonic()
                    if not self._paused and now - last_frame_time >= 1 / self._target_fps:
                        img = QImage.fromData(jpeg_data, "JPEG")
                        if not img.isNull():
                            last_frame_time = now
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
    @staticmethod
    def _process_exit_reason(proc, stderr_lines: list, stderr_reader) -> str:
        try:
            proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
        stderr_reader.join(timeout=0.5)
        if stderr_lines:
            details = " | ".join(
                line.decode(errors="replace").strip()
                for line in stderr_lines[-12:]
                if line.strip()
            )
            return RTSPCameraPlayer._sanitize_error(details)[-1800:]
        returncode = proc.poll()
        if returncode is not None:
            return f"ffmpeg exited with code {returncode}"
        return "ffmpeg closed its output without an error"

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
            "-hide_banner",
            "-loglevel", "verbose",
            "-rtsp_transport", "tcp",
            "-timeout", "15000000",      # RTSP socket I/O timeout in microseconds
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
        proc = self._proc
        self._proc = None
        if not proc:
            return

        if proc.poll() is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                proc.wait()

        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()

    @staticmethod
    def _sanitize_error(message: str) -> str:
        return re.sub(r"rtsp://\S+", "RTSP stream", message, flags=re.IGNORECASE)

    def _log_error(self, message: str):
        if self._error_logged:
            return
        self.log_event.emit(
            self.channel, "error", self._sanitize_error(message)
        )
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
# Video Recording Worker
# ==============================================================================
class VideoRecorder(QThread):
    recording_started = Signal()
    recording_saved = Signal(str, int)
    recording_error = Signal(str)

    def __init__(self, path: Path, fps: int, frame_size: QSize, parent=None):
        super().__init__(parent)
        self.path = str(path)
        self.fps = max(1, min(fps, 30))
        self.frame_size = QSize(
            max(2, frame_size.width() // 2 * 2),
            max(2, frame_size.height() // 2 * 2),
        )
        self._frames = queue.Queue(maxsize=30)
        self._running = True
        self.dropped_frames = 0

    def add_frame(self, image: QImage):
        if not self._running or image.isNull():
            return
        try:
            self._frames.put_nowait(image.copy())
        except queue.Full:
            self.dropped_frames += 1

    def stop(self):
        self._running = False
        self.wait()

    def run(self):
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-framerate", str(self.fps),
            "-i", "-",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            self.path,
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self.recording_error.emit("FFmpeg was not found. Install FFmpeg to record video.")
            return
        except OSError as exc:
            self.recording_error.emit(f"Could not start FFmpeg: {exc}")
            return

        self.recording_started.emit()
        try:
            while self._running or not self._frames.empty():
                try:
                    image = self._frames.get(timeout=0.1)
                except queue.Empty:
                    if process.poll() is not None:
                        raise RuntimeError(f"FFmpeg exited with status {process.returncode}.")
                    continue

                if image.size() != self.frame_size:
                    image = image.scaled(
                        self.frame_size,
                        Qt.IgnoreAspectRatio,
                        Qt.SmoothTransformation,
                    )

                buffer = QBuffer()
                if not buffer.open(QIODevice.WriteOnly) or not image.save(buffer, "JPEG", 90):
                    raise RuntimeError("Could not encode a video frame.")
                process.stdin.write(bytes(buffer.data()))

            process.stdin.close()
            return_code = process.wait()
            if return_code != 0:
                raise RuntimeError(f"FFmpeg exited with status {return_code}.")
        except (OSError, RuntimeError) as exc:
            self._terminate_process(process)
            self.recording_error.emit(f"Video recording failed: {exc}")
            return

        self.recording_saved.emit(self.path, self.dropped_frames)

    @staticmethod
    def _terminate_process(process):
        if process.stdin and not process.stdin.closed:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait()


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
        self.is_gamepad_selected = False

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

        self.lbl_motion = QLabel("MOTION")
        self.lbl_motion.setStyleSheet("""
            color: #ffffff;
            background-color: #dc2626;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: bold;
        """)
        self.lbl_motion.setVisible(False)

        self.btn_snap = QPushButton()
        self.btn_snap.setIcon(_make_icon("camera"))
        self.btn_snap.setIconSize(QSize(16, 16))
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

    def _refresh_border_style(self):
        if self.is_motion_active:
            border = "3px solid #ef4444"
        elif self.is_gamepad_selected:
            border = "3px solid #38bdf8"
        else:
            border = "2px solid #232936"
        self.setStyleSheet(f"""
            CameraViewWidget {{
                background-color: #12151c;
                border: {border};
                border-radius: 8px;
            }}
        """)

    def set_gamepad_selected(self, selected: bool):
        if self.is_gamepad_selected != bool(selected):
            self.is_gamepad_selected = bool(selected)
            self._refresh_border_style()

    def trigger_motion(self):
        self.is_motion_active = True
        self.lbl_motion.setVisible(True)
        self._refresh_border_style()
        self.motion_clear_timer.start(4000)

    def _clear_motion(self):
        self.is_motion_active = False
        self.lbl_motion.setVisible(False)
        self._refresh_border_style()


# ==============================================================================
# Settings Dialog
# ==============================================================================
class SettingsDialog(QDialog):
    def __init__(self, config: DVRConfig, artifact_directory: Path, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Application Settings")
        self.setMinimumWidth(500)
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
        self.edit_sdk_port = QLineEdit(str(config.sdk_port))
        self.edit_http_port.setValidator(QtGui.QIntValidator(1, 65535, self))
        self.edit_rtsp_port.setValidator(QtGui.QIntValidator(1, 65535, self))
        self.edit_sdk_port.setValidator(QtGui.QIntValidator(1, 65535, self))
        self.edit_user = QLineEdit(config.username)
        self.edit_pass = QLineEdit(config.password)
        self.edit_pass.setEchoMode(QLineEdit.Password)
        self.edit_stream_verification_code = QLineEdit(
            config.stream_verification_code
        )
        self.edit_stream_verification_code.setEchoMode(QLineEdit.Password)
        self.edit_stream_verification_code.setToolTip(
            "This is distinct from the DVR account password. The current "
            "Hikvision helper passes it to PlayCtrl for encrypted-stream "
            "decoding; decoded frames still need to be verified."
        )
        self.edit_channels = QLineEdit(", ".join(map(str, config.channels)))
        self.edit_sdk_directory = QLineEdit(config.sdk_directory)
        self.edit_sdk_directory.setPlaceholderText(
            "Auto-detect or set HIKVISION_SDK_DIR"
        )
        btn_browse_sdk_directory = QPushButton("Browse...")
        btn_browse_sdk_directory.clicked.connect(self._browse_sdk_directory)
        sdk_directory_row = QWidget()
        sdk_directory_layout = QHBoxLayout(sdk_directory_row)
        sdk_directory_layout.setContentsMargins(0, 0, 0, 0)
        sdk_directory_layout.addWidget(self.edit_sdk_directory)
        sdk_directory_layout.addWidget(btn_browse_sdk_directory)
        sdk_actions_row = QWidget()
        sdk_actions_layout = QHBoxLayout(sdk_actions_row)
        sdk_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_get_hikvision_sdk = QPushButton("Get SDK")
        self.btn_get_hikvision_sdk.clicked.connect(self._open_hikvision_sdk_page)
        self.btn_build_hikvision_helper = QPushButton("Build / Verify Helper")
        self.btn_build_hikvision_helper.clicked.connect(
            self._build_hikvision_helper
        )
        sdk_actions_layout.addWidget(self.btn_get_hikvision_sdk)
        sdk_actions_layout.addWidget(self.btn_build_hikvision_helper)
        self.edit_artifact_directory = QLineEdit(str(artifact_directory))
        btn_browse_artifact_directory = QPushButton("Browse...")
        btn_browse_artifact_directory.clicked.connect(
            self._browse_artifact_directory
        )
        artifact_directory_row = QWidget()
        artifact_directory_layout = QHBoxLayout(artifact_directory_row)
        artifact_directory_layout.setContentsMargins(0, 0, 0, 0)
        artifact_directory_layout.addWidget(self.edit_artifact_directory)
        artifact_directory_layout.addWidget(btn_browse_artifact_directory)

        steam_actions_row = QWidget()
        steam_actions_layout = QHBoxLayout(steam_actions_row)
        steam_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_add_to_steam = QPushButton("Add to Steam Library")
        self.btn_add_to_steam.setIcon(_make_icon("gamepad"))
        self.btn_add_to_steam.setToolTip(
            "Register HikLens as a Non-Steam shortcut for Steam Deck Gaming Mode"
        )
        self.btn_add_to_steam.clicked.connect(self._add_to_steam_library)
        self.btn_open_steam_osk = QPushButton("Show Steam Keyboard")
        self.btn_open_steam_osk.setToolTip(
            "Summon the Steam On-Screen Keyboard (steam://open/keyboard)"
        )
        self.btn_open_steam_osk.clicked.connect(lambda: trigger_steam_osk())
        steam_actions_layout.addWidget(self.btn_add_to_steam)
        steam_actions_layout.addWidget(self.btn_open_steam_osk)

        form.addRow("DVR IP Address:", self.edit_ip)
        form.addRow("HTTP ISAPI Port:", self.edit_http_port)
        form.addRow("RTSP Port:", self.edit_rtsp_port)
        form.addRow("Hikvision SDK Port:", self.edit_sdk_port)
        form.addRow("Username:", self.edit_user)
        form.addRow("Password:", self.edit_pass)
        form.addRow(
            "Streaming Verification Code:",
            self.edit_stream_verification_code,
        )
        form.addRow("Monitored Channels:", self.edit_channels)
        form.addRow("Hikvision SDK Directory:", sdk_directory_row)
        form.addRow("SDK Setup:", sdk_actions_row)
        form.addRow("Save snapshots and recordings to:", artifact_directory_row)
        form.addRow("Steam Deck Integration:", steam_actions_row)

        for line_edit in (
            self.edit_ip,
            self.edit_http_port,
            self.edit_rtsp_port,
            self.edit_sdk_port,
            self.edit_user,
            self.edit_pass,
            self.edit_stream_verification_code,
            self.edit_channels,
            self.edit_sdk_directory,
            self.edit_artifact_directory,
        ):
            line_edit.installEventFilter(self)

        layout.addLayout(form)

        storage_note = QLabel(
            "Settings are saved locally for this user. The DVR password and "
            "Streaming Verification Code are not encrypted. The verification "
            "code is separate from the DVR password and is sent only to the "
            "optional Hikvision PlayCtrl helper. "
            "The optional Hikvision SDK is proprietary, must be obtained separately, "
            "and is not bundled with this application. Get SDK opens Hikvision's "
            "official download page; choose an extracted SDK directory before "
            "clicking Build / Verify Helper. Flatpak and AppImage packages include "
            "a pre-built open-source helper; source installations build it locally "
            "with make and a C++17 compiler."
        )
        storage_note.setWordWrap(True)
        layout.addWidget(storage_note)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._validate_and_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def eventFilter(self, watched, event):
        if (
            event.type() == QtCore.QEvent.MouseButtonPress
            and isinstance(watched, QLineEdit)
            and (is_steam_deck_hardware() or is_steam_gaming_mode())
        ):
            trigger_steam_osk()
        return super().eventFilter(watched, event)

    def _add_to_steam_library(self):
        try:
            updated_paths = register_steam_shortcut()
        except FileNotFoundError:
            default_steam_dir = str(Path.home() / ".local/share/Steam")
            selected_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Steam Directory (~/.local/share/Steam or userdata)",
                default_steam_dir,
            )
            if not selected_dir:
                return
            try:
                updated_paths = register_steam_shortcut(steam_dir=selected_dir)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Steam Shortcut Error",
                    f"Could not register Non-Steam shortcut:\n{exc}",
                )
                return
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Steam Shortcut Error",
                f"Could not register Non-Steam shortcut:\n{exc}",
            )
            return
        formatted = "\n".join(str(p) for p in updated_paths)
        QMessageBox.information(
            self,
            "Added to Steam Library",
            "HikLens was added to your Steam Non-Steam shortcuts:\n\n"
            f"{formatted}\n\n"
            "Restart Steam or switch to Gaming Mode on your Steam Deck to launch it.",
        )

    def _browse_artifact_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Artifact Directory",
            self.edit_artifact_directory.text(),
        )
        if directory:
            self.edit_artifact_directory.setText(directory)

    def _browse_sdk_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Hikvision Linux SDK Directory",
            self.edit_sdk_directory.text(),
        )
        if directory:
            self.edit_sdk_directory.setText(directory)

    def _open_hikvision_sdk_page(self):
        if not QDesktopServices.openUrl(QUrl(HIKVISION_SDK_DOWNLOAD_URL)):
            QMessageBox.warning(
                self,
                "Could Not Open SDK Page",
                "Open Hikvision's official SDK page in a browser:\n"
                f"{HIKVISION_SDK_DOWNLOAD_URL}",
            )

    def _build_hikvision_helper(self):
        sdk_directory = self.edit_sdk_directory.text().strip()
        if not sdk_directory:
            QMessageBox.warning(
                self,
                "SDK Directory Required",
                "Download and extract the Linux SDK, then choose its root "
                "directory first.",
            )
            return

        self.btn_build_hikvision_helper.setEnabled(False)
        self.btn_build_hikvision_helper.setText("Building...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            installation = build_hikvision_helper(sdk_directory)
        except HikvisionSDKError as exc:
            QMessageBox.critical(self, "Hikvision SDK Setup Failed", str(exc))
        else:
            self.edit_sdk_directory.setText(str(installation.root))
            QMessageBox.information(
                self,
                "Hikvision SDK Ready",
                "The local helper was built and its SDK dependencies passed "
                "the initialization check.\n\n"
                "This check does not verify video decryption. Save the settings "
                "and select the Hikvision SDK engine to test live decoded frames.",
            )
        finally:
            QApplication.restoreOverrideCursor()
            self.btn_build_hikvision_helper.setEnabled(True)
            self.btn_build_hikvision_helper.setText("Build / Verify Helper")

    def get_artifact_directory(self) -> Path:
        directory = self.edit_artifact_directory.text().strip()
        if not directory:
            raise ValueError("Artifact save directory cannot be empty.")
        return Path(directory).expanduser().resolve()

    def get_updated_config(self) -> DVRConfig:
        ip = self.edit_ip.text().strip()
        if not ip:
            raise ValueError("DVR IP address cannot be empty.")

        channels_text = self.edit_channels.text().strip()
        channel_tokens = channels_text.split(",")
        if not channel_tokens or any(not token.strip().isdigit() for token in channel_tokens):
            raise ValueError("Enter monitored channels as comma-separated numbers.")
        channels = [int(token.strip()) for token in channel_tokens]
        if any(channel < 1 for channel in channels) or len(set(channels)) != len(channels):
            raise ValueError("Channels must be positive and cannot be repeated.")

        return DVRConfig(
            ip=ip,
            http_port=self._parse_port(self.edit_http_port, "HTTP"),
            rtsp_port=self._parse_port(self.edit_rtsp_port, "RTSP"),
            sdk_port=self._parse_port(self.edit_sdk_port, "SDK"),
            username=self.edit_user.text().strip(),
            password=self.edit_pass.text(),
            stream_verification_code=self.edit_stream_verification_code.text(),
            channels=channels,
            sdk_directory=self.edit_sdk_directory.text().strip(),
        )

    @staticmethod
    def _parse_port(field: QLineEdit, name: str) -> int:
        try:
            port = int(field.text().strip())
        except ValueError as exc:
            raise ValueError(f"{name} port must be a number between 1 and 65535.") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"{name} port must be a number between 1 and 65535.")
        return port

    def _validate_and_accept(self):
        try:
            self.get_updated_config()
            self.get_artifact_directory()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid DVR Settings", str(exc))
            return
        self.accept()


class CameraSelectionDialog(QDialog):
    def __init__(self, channels: list, selected_channels: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Grid Cameras")
        self.setMinimumSize(320, 360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose the cameras to show in Grid View:"))
        self.camera_list = QListWidget()
        selected = set(selected_channels)
        for channel in channels:
            item = QListWidgetItem(f"Camera {channel}")
            item.setData(Qt.UserRole, channel)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if channel in selected else Qt.Unchecked)
            self.camera_list.addItem(item)
        layout.addWidget(self.camera_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_selected_channels(self) -> list:
        return [
            self.camera_list.item(index).data(Qt.UserRole)
            for index in range(self.camera_list.count())
            if self.camera_list.item(index).checkState() == Qt.Checked
        ]

    def _validate_and_accept(self):
        if not self.get_selected_channels():
            QMessageBox.warning(
                self, "No Cameras Selected", "Select at least one camera for Grid View."
            )
            return
        self.accept()


class RecordingTimelineWidget(QWidget):
    """Interactive visual timeline scrubber for seeking inside a DVR capture."""

    seek_requested = Signal(int)
    scrub_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(64)
        self.setMaximumHeight(74)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        self._start_dt = QDateTime()
        self._end_dt = QDateTime()
        self._duration_seconds = 0
        self._offset_seconds = 0
        self._hover_seconds: int | None = None
        self._dragging = False
        self._segments: list[tuple[int, int, int]] = []

    @property
    def duration_seconds(self) -> int:
        return self._duration_seconds

    @property
    def offset_seconds(self) -> int:
        return self._offset_seconds

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def set_time_span(
        self,
        start_dt: QDateTime,
        end_dt: QDateTime,
        segments: list[tuple[int, int, int]] | None = None,
    ):
        self._start_dt = QDateTime(start_dt)
        self._end_dt = QDateTime(end_dt)
        if self._start_dt.isValid() and self._end_dt.isValid():
            self._duration_seconds = max(0, int(self._start_dt.secsTo(self._end_dt)))
        else:
            self._duration_seconds = 0
        self._offset_seconds = 0
        self._hover_seconds = None
        self._segments = list(segments or [])
        self.update()

    def set_offset_seconds(self, offset_seconds: int):
        if self._duration_seconds <= 0:
            self._offset_seconds = 0
        else:
            self._offset_seconds = max(
                0, min(self._duration_seconds, int(offset_seconds))
            )
        self.update()

    def timestamp_at_offset(self, offset_seconds: int) -> QDateTime:
        if not self._start_dt.isValid():
            return QDateTime()
        clamped = max(0, min(self._duration_seconds, int(offset_seconds)))
        return self._start_dt.addSecs(clamped)

    def current_timestamp(self) -> QDateTime:
        return self.timestamp_at_offset(self._offset_seconds)

    def _track_bounds(self) -> tuple[int, int, int, int]:
        margin_x = 16
        track_y = 24
        track_h = 16
        track_w = max(1, self.width() - (2 * margin_x))
        return margin_x, track_y, track_w, track_h

    def _x_to_offset(self, x_pos: float) -> int:
        if self._duration_seconds <= 0:
            return 0
        track_x, _track_y, track_w, _track_h = self._track_bounds()
        ratio = max(0.0, min(1.0, (x_pos - track_x) / float(track_w)))
        return int(round(ratio * self._duration_seconds))

    def _offset_to_x(self, offset_seconds: int) -> int:
        track_x, _track_y, track_w, _track_h = self._track_bounds()
        if self._duration_seconds <= 0:
            return track_x
        ratio = max(
            0.0, min(1.0, float(offset_seconds) / float(self._duration_seconds))
        )
        return track_x + int(round(ratio * track_w))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._duration_seconds > 0:
            self._dragging = True
            self._offset_seconds = self._x_to_offset(event.position().x())
            self.scrub_changed.emit(self._offset_seconds)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._duration_seconds > 0:
            hovered = self._x_to_offset(event.position().x())
            self._hover_seconds = hovered
            if self._dragging:
                self._offset_seconds = hovered
                self.scrub_changed.emit(self._offset_seconds)
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._offset_seconds = self._x_to_offset(event.position().x())
            self.scrub_changed.emit(self._offset_seconds)
            self.seek_requested.emit(self._offset_seconds)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._hover_seconds = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.fillRect(self.rect(), QColor("#12151c"))
        border_pen = QPen(QColor("#232936"), 1)
        painter.setPen(border_pen)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)

        track_x, track_y, track_w, track_h = self._track_bounds()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1f2937"))
        painter.drawRoundedRect(track_x, track_y, track_w, track_h, 5, 5)

        if self._duration_seconds <= 0 or not self._start_dt.isValid():
            painter.setPen(QColor("#64748b"))
            font = QFont(self.font())
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "Select a capture to scrub its timeline",
            )
            return

        # Draw recorded segment bars inside the timeline window
        if self._segments:
            for seg_start, seg_end, file_type in self._segments:
                x1 = self._offset_to_x(seg_start)
                x2 = max(x1 + 2, self._offset_to_x(seg_end))
                color = QColor("#1e40af") if file_type == 0 else QColor("#b45309")
                painter.setBrush(color)
                painter.drawRoundedRect(x1, track_y + 2, x2 - x1, track_h - 4, 3, 3)
        else:
            painter.setBrush(QColor("#1e3a8a"))
            painter.drawRoundedRect(track_x, track_y + 2, track_w, track_h - 4, 4, 4)

        # Draw elapsed / selected region up to the playhead
        playhead_x = self._offset_to_x(self._offset_seconds)
        if playhead_x > track_x:
            painter.setBrush(QColor("#3b82f6"))
            painter.drawRoundedRect(
                track_x,
                track_y + 2,
                playhead_x - track_x,
                track_h - 4,
                4,
                4,
            )

        # Draw time ruler ticks and HH:mm:ss labels below the track
        tick_count = 6
        font = QFont(self.font())
        font.setPointSize(8)
        painter.setFont(font)
        for idx in range(tick_count + 1):
            ratio = idx / float(tick_count)
            tx = track_x + int(round(ratio * track_w))
            painter.setPen(QPen(QColor("#475569"), 1))
            painter.drawLine(tx, track_y + track_h + 1, tx, track_y + track_h + 5)

            tick_secs = int(round(ratio * self._duration_seconds))
            tick_label = self.timestamp_at_offset(tick_secs).toString("HH:mm:ss")
            text_w = 56
            if idx == 0:
                text_x = track_x
                align = Qt.AlignLeft | Qt.AlignVCenter
            elif idx == tick_count:
                text_x = tx - text_w
                align = Qt.AlignRight | Qt.AlignVCenter
            else:
                text_x = tx - (text_w // 2)
                align = Qt.AlignHCenter | Qt.AlignVCenter
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(
                text_x,
                track_y + track_h + 6,
                text_w,
                16,
                int(align),
                tick_label,
            )

        # Draw hover indicator if the cursor is over the timeline
        if self._hover_seconds is not None and not self._dragging:
            hover_x = self._offset_to_x(self._hover_seconds)
            painter.setPen(QPen(QColor("#93c5fd"), 1, Qt.DashLine))
            painter.drawLine(hover_x, track_y - 4, hover_x, track_y + track_h + 4)
            hover_text = self.timestamp_at_offset(self._hover_seconds).toString(
                "HH:mm:ss"
            )
            pill_w = 58
            pill_x = max(4, min(self.width() - pill_w - 4, hover_x - (pill_w // 2)))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#1e293b"))
            painter.drawRoundedRect(pill_x, 3, pill_w, 16, 4, 4)
            painter.setPen(QColor("#bfdbfe"))
            painter.drawText(pill_x, 3, pill_w, 16, Qt.AlignCenter, hover_text)

        # Draw playhead line, handle, and current timestamp badge
        painter.setPen(QPen(QColor("#f8fafc"), 2))
        painter.drawLine(playhead_x, track_y - 3, playhead_x, track_y + track_h + 3)
        painter.setBrush(QColor("#60a5fa"))
        painter.drawEllipse(QPoint(playhead_x, track_y + (track_h // 2)), 6, 6)

        badge_text = self.current_timestamp().toString("HH:mm:ss")
        badge_w = 62
        badge_x = max(4, min(self.width() - badge_w - 4, playhead_x - (badge_w // 2)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2563eb"))
        painter.drawRoundedRect(badge_x, 3, badge_w, 17, 4, 4)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge_x, 3, badge_w, 17, Qt.AlignCenter, badge_text)


class RecordingsDialog(QDialog):
    """Browse and play back previous DVR recordings using the Hikvision SDK."""

    def __init__(
        self,
        config: DVRConfig,
        artifact_directory: Path,
        default_channel: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.artifact_directory = artifact_directory
        self.recordings: list[HikvisionRecording] = []
        self.player: HikvisionPlaybackPlayer | None = None
        self.is_paused = False
        self._capture_channel: int | None = None
        self._capture_recording_name: str = ""
        self._capture_start_dt = QDateTime()
        self._capture_end_dt = QDateTime()
        self._playback_started_receiving_frames = False

        self.setWindowTitle("DVR Recordings Playback (Hikvision SDK)")
        self.resize(1260, 760)
        self.setMinimumSize(1020, 580)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0e14;
                color: #e2e8f0;
            }
            QLabel {
                color: #cbd5e1;
            }
            QComboBox, QDateTimeEdit {
                background-color: #1f2937;
                color: #f8fafc;
                border: 1px solid #374151;
                border-radius: 5px;
                padding: 4px 8px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #1f2937;
                color: #e2e8f0;
                border: 1px solid #374151;
                border-radius: 5px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: bold;
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
            QListWidget {
                background-color: #12151c;
                color: #cbd5e1;
                border: 1px solid #232936;
                border-radius: 6px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #1f2937;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #2563eb;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #60a5fa;
                border: 1px solid #f8fafc;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
        """)

        layout = QVBoxLayout(self)
        controls_row = QHBoxLayout()

        controls_row.addWidget(QLabel("Camera:"))
        self.combo_channel = QComboBox()
        for channel in self.config.channels:
            self.combo_channel.addItem(
                _make_icon("camera"), f"Camera {channel}", channel
            )
        if default_channel in self.config.channels:
            self.combo_channel.setCurrentIndex(
                self.config.channels.index(default_channel)
            )
        self.combo_channel.currentIndexChanged.connect(
            self._on_selected_channel_changed
        )
        controls_row.addWidget(self.combo_channel)

        controls_row.addWidget(QLabel("From:"))
        now = QDateTime.currentDateTime()
        self.start_time_edit = QDateTimeEdit(now.addDays(-1))
        self.start_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.start_time_edit.setCalendarPopup(True)
        self.start_time_edit.setMinimumWidth(185)
        controls_row.addWidget(self.start_time_edit)

        controls_row.addWidget(QLabel("To:"))
        self.end_time_edit = QDateTimeEdit(now)
        self.end_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.end_time_edit.setCalendarPopup(True)
        self.end_time_edit.setMinimumWidth(185)
        controls_row.addWidget(self.end_time_edit)

        controls_row.addWidget(QLabel("Stream:"))
        self.combo_stream = QComboBox()
        self.combo_stream.addItem("Main Stream", 0)
        self.combo_stream.addItem("Sub-Stream", 1)
        controls_row.addWidget(self.combo_stream)

        self.btn_search = QPushButton("Search Recordings")
        self.btn_search.setIcon(_make_icon("playback"))
        self.btn_search.clicked.connect(self._search_recordings)
        controls_row.addWidget(self.btn_search)

        self.btn_play_range = QPushButton("Play Time Range")
        self.btn_play_range.setIcon(_make_icon("play"))
        self.btn_play_range.clicked.connect(self._play_time_range)
        controls_row.addWidget(self.btn_play_range)
        controls_row.addStretch()
        layout.addLayout(controls_row)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_results = QLabel("Recorded segments:")
        left_layout.addWidget(self.lbl_results)
        self.recording_list = QListWidget()
        self.recording_list.currentRowChanged.connect(
            self._on_selected_recording_changed
        )
        self.recording_list.itemDoubleClicked.connect(
            lambda _item: self._play_selected_recording()
        )
        left_layout.addWidget(self.recording_list, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        initial_channel = int(self.combo_channel.currentData())
        self.playback_tile = CameraViewWidget(initial_channel)
        self.playback_tile.video_label.setText(
            "Search for recordings and select a segment, or click Play Time Range."
        )
        self.playback_tile.snapshot_requested.connect(
            self._save_playback_snapshot
        )
        right_layout.addWidget(self.playback_tile, 1)

        # Interactive capture timeline section
        timeline_header = QHBoxLayout()
        self.lbl_timeline_start = QLabel("Start: --:--:--")
        timeline_header.addWidget(self.lbl_timeline_start)
        timeline_header.addStretch()
        self.lbl_timeline_current = QLabel("Selected Time: --")
        self.lbl_timeline_current.setStyleSheet(
            "color: #60a5fa; font-weight: bold;"
        )
        timeline_header.addWidget(self.lbl_timeline_current)
        timeline_header.addStretch()
        self.lbl_timeline_end = QLabel("End: --:--:--")
        timeline_header.addWidget(self.lbl_timeline_end)
        right_layout.addLayout(timeline_header)

        self.timeline_widget = RecordingTimelineWidget()
        self.timeline_widget.scrub_changed.connect(
            self._on_timeline_scrub_changed
        )
        self.timeline_widget.seek_requested.connect(self.seek_to_timeline_offset)
        right_layout.addWidget(self.timeline_widget)

        scrubber_row = QHBoxLayout()
        self.btn_seek_back = QPushButton("-30s")
        self.btn_seek_back.setToolTip("Jump backward 30 seconds in this capture")
        self.btn_seek_back.setEnabled(False)
        self.btn_seek_back.clicked.connect(lambda: self.skip_seconds(-30))
        scrubber_row.addWidget(self.btn_seek_back)

        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.setRange(0, 0)
        self.timeline_slider.setEnabled(False)
        self.timeline_slider.sliderMoved.connect(self._on_slider_moved)
        self.timeline_slider.sliderReleased.connect(self._on_slider_released)
        scrubber_row.addWidget(self.timeline_slider, 1)

        self.btn_seek_forward = QPushButton("+30s")
        self.btn_seek_forward.setToolTip("Jump forward 30 seconds in this capture")
        self.btn_seek_forward.setEnabled(False)
        self.btn_seek_forward.clicked.connect(lambda: self.skip_seconds(30))
        scrubber_row.addWidget(self.btn_seek_forward)
        right_layout.addLayout(scrubber_row)

        player_controls = QHBoxLayout()
        self.btn_play_selected = QPushButton("Play Selected")
        self.btn_play_selected.setIcon(_make_icon("play"))
        self.btn_play_selected.clicked.connect(self._play_selected_recording)
        player_controls.addWidget(self.btn_play_selected)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setIcon(_make_icon("pause"))
        self.btn_pause.setCheckable(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._toggle_pause)
        player_controls.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setIcon(_make_icon("stop"))
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_playback)
        player_controls.addWidget(self.btn_stop)

        player_controls.addWidget(QLabel("Speed:"))
        self.combo_speed = QComboBox()
        for label, factor in (
            ("0.25x", 0.25),
            ("0.5x", 0.5),
            ("1x", 1.0),
            ("2x", 2.0),
            ("4x", 4.0),
        ):
            self.combo_speed.addItem(label, factor)
        self.combo_speed.setCurrentIndex(2)  # 1x default
        self.combo_speed.setFixedWidth(90)
        self.combo_speed.setToolTip("Playback speed (0.25x, 0.5x, 1x, 2x, 4x)")
        self.combo_speed.currentIndexChanged.connect(
            self._on_playback_speed_changed
        )
        player_controls.addWidget(self.combo_speed)

        self.lbl_status = QLabel("Idle")
        player_controls.addWidget(self.lbl_status, 1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        player_controls.addWidget(btn_close)

        right_layout.addLayout(player_controls)
        splitter.addWidget(right_panel)
        splitter.setSizes([380, 880])

        self._clock_fraction = 0.0
        self.playback_clock_timer = QTimer(self)
        self.playback_clock_timer.setInterval(1000)
        self.playback_clock_timer.timeout.connect(self._advance_playback_clock)

    @staticmethod
    def _parse_datetime(value: str) -> QDateTime:
        return QDateTime.fromString(value.strip(), "yyyy-MM-dd HH:mm:ss")

    @staticmethod
    def _format_duration(seconds: int) -> str:
        seconds = max(0, int(seconds))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _set_timeline_capture(
        self,
        channel: int,
        start_time: str,
        end_time: str,
        recording_name: str = "",
        segments: list[tuple[int, int, int]] | None = None,
        initial_offset_seconds: int = 0,
    ):
        start_dt = self._parse_datetime(start_time)
        end_dt = self._parse_datetime(end_time)
        self._capture_channel = channel
        self._capture_recording_name = recording_name
        self._capture_start_dt = start_dt
        self._capture_end_dt = end_dt

        self.timeline_widget.set_time_span(start_dt, end_dt, segments=segments)
        duration = self.timeline_widget.duration_seconds
        has_span = duration > 0 and start_dt.isValid() and end_dt.isValid()
        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setRange(0, max(0, duration))
        self.timeline_slider.setValue(0)
        self.timeline_slider.blockSignals(False)
        self.timeline_slider.setEnabled(has_span)
        self.btn_seek_back.setEnabled(has_span)
        self.btn_seek_forward.setEnabled(has_span)

        if has_span:
            self.lbl_timeline_start.setText(
                f"Start: {start_dt.toString('yyyy-MM-dd HH:mm:ss')}"
            )
            self.lbl_timeline_end.setText(
                f"End: {end_dt.toString('yyyy-MM-dd HH:mm:ss')}"
            )
            self._set_timeline_offset(initial_offset_seconds)
        else:
            self.lbl_timeline_start.setText("Start: --:--:--")
            self.lbl_timeline_current.setText("Selected Time: --")
            self.lbl_timeline_end.setText("End: --:--:--")

    def _set_timeline_offset(self, offset_seconds: int):
        duration = self.timeline_widget.duration_seconds
        clamped = max(0, min(duration, int(offset_seconds)))
        self.timeline_widget.set_offset_seconds(clamped)
        if not self.timeline_slider.isSliderDown():
            self.timeline_slider.blockSignals(True)
            self.timeline_slider.setValue(clamped)
            self.timeline_slider.blockSignals(False)
        self._update_timeline_current_label(clamped)

    def _update_timeline_current_label(self, offset_seconds: int):
        duration = self.timeline_widget.duration_seconds
        ts = self.timeline_widget.timestamp_at_offset(offset_seconds)
        if not ts.isValid() or duration <= 0:
            self.lbl_timeline_current.setText("Selected Time: --")
            return
        elapsed = self._format_duration(offset_seconds)
        total = self._format_duration(duration)
        self.lbl_timeline_current.setText(
            f"Selected Time: {ts.toString('yyyy-MM-dd HH:mm:ss')} ({elapsed} / {total})"
        )

    def _on_selected_recording_changed(self, row: int):
        if not (0 <= row < len(self.recordings)):
            return
        recording = self.recordings[row]
        start_dt = self._parse_datetime(recording.start_time)
        end_dt = self._parse_datetime(recording.end_time)
        duration = max(0, int(start_dt.secsTo(end_dt))) if start_dt.isValid() and end_dt.isValid() else 0
        segments = [(0, duration, recording.file_type)] if duration > 0 else []
        self._set_timeline_capture(
            channel=recording.channel,
            start_time=recording.start_time,
            end_time=recording.end_time,
            recording_name=recording.name,
            segments=segments,
            initial_offset_seconds=0,
        )

    def _on_timeline_scrub_changed(self, offset_seconds: int):
        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setValue(offset_seconds)
        self.timeline_slider.blockSignals(False)
        self._update_timeline_current_label(offset_seconds)

    def _on_slider_moved(self, value: int):
        self.timeline_widget.set_offset_seconds(value)
        self._update_timeline_current_label(value)

    def _on_slider_released(self):
        self.seek_to_timeline_offset(self.timeline_slider.value())

    def selected_playback_speed(self) -> float:
        data = self.combo_speed.currentData()
        return float(data) if data is not None else 1.0

    def _on_playback_speed_changed(self):
        self._clock_fraction = 0.0
        if self.player is not None and self.timeline_widget.duration_seconds > 0:
            self.seek_to_timeline_offset(self.timeline_widget.offset_seconds)

    def skip_seconds(self, delta_seconds: int):
        if self.timeline_widget.duration_seconds <= 0:
            return
        target = self.timeline_widget.offset_seconds + int(delta_seconds)
        self.seek_to_timeline_offset(target)

    def seek_to_timeline_offset(self, offset_seconds: int):
        duration = self.timeline_widget.duration_seconds
        if (
            duration <= 0
            or not self._capture_start_dt.isValid()
            or not self._capture_end_dt.isValid()
        ):
            return
        clamped = max(0, min(duration, int(offset_seconds)))
        if clamped >= duration and duration > 1:
            clamped = duration - 1
        self._set_timeline_offset(clamped)

        seek_dt = self._capture_start_dt.addSecs(clamped)
        seek_start_str = seek_dt.toString("yyyy-MM-dd HH:mm:ss")
        capture_end_str = self._capture_end_dt.toString("yyyy-MM-dd HH:mm:ss")
        pos_percent = int(round((clamped * 99.0) / float(duration)))
        pos_percent = max(0, min(99, pos_percent))
        channel = (
            self._capture_channel
            if self._capture_channel is not None
            else int(self.combo_channel.currentData())
        )
        self._start_playback(
            channel=channel,
            start_time=seek_start_str,
            end_time=capture_end_str,
            recording_name=self._capture_recording_name,
            playback_position_percent=pos_percent,
            preserve_timeline=True,
        )

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes >= 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        if size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes} B"

    def _selected_time_range(self) -> tuple[str, str]:
        start_dt = self.start_time_edit.dateTime()
        end_dt = self.end_time_edit.dateTime()
        if start_dt >= end_dt:
            raise ValueError("The start time must be earlier than the end time.")
        return (
            start_dt.toString("yyyy-MM-dd HH:mm:ss"),
            end_dt.toString("yyyy-MM-dd HH:mm:ss"),
        )

    def _on_selected_channel_changed(self):
        channel = int(self.combo_channel.currentData())
        if self.player is None:
            self.playback_tile.channel = channel
            self.playback_tile.lbl_title.setText(f"CAMERA {channel}")

    def _search_recordings(self):
        try:
            start_time, end_time = self._selected_time_range()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Time Range", str(exc))
            return

        channel = int(self.combo_channel.currentData())
        self.btn_search.setEnabled(False)
        self.lbl_status.setText(f"Searching Camera {channel} recordings…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            recordings = list_hikvision_recordings(
                self.config,
                channel=channel,
                start_time=start_time,
                end_time=end_time,
            )
        except HikvisionSDKError as exc:
            self.lbl_status.setText("Search failed")
            QMessageBox.critical(self, "Recording Search Failed", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.btn_search.setEnabled(True)

        self.recordings = recordings
        self.recording_list.clear()
        for index, recording in enumerate(recordings):
            kind = recording_file_type_label(recording.file_type)
            size_text = self._format_size(recording.size_bytes)
            label = (
                f"{recording.start_time} → {recording.end_time}\n"
                f"{kind} • {size_text} • {recording.name}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, index)
            self.recording_list.addItem(item)

        if recordings:
            self.recording_list.setCurrentRow(0)
            self.lbl_results.setText(f"Recorded segments ({len(recordings)}):")
            self.lbl_status.setText(
                f"Found {len(recordings)} recording(s) for Camera {channel}."
            )
        else:
            self.lbl_results.setText("Recorded segments (0):")
            self.lbl_status.setText(
                f"No recordings found for Camera {channel} in the selected window."
            )

    def _play_selected_recording(self):
        item = self.recording_list.currentItem()
        if item is None:
            QMessageBox.information(
                self,
                "Select a Recording",
                "Search and select a recorded segment first, or use Play Time Range.",
            )
            return
        index = item.data(Qt.UserRole)
        if index is None or not (0 <= int(index) < len(self.recordings)):
            return
        recording = self.recordings[int(index)]
        capture_matches = (
            self._capture_channel == recording.channel
            and self._capture_recording_name == recording.name
            and self._capture_start_dt == self._parse_datetime(recording.start_time)
            and self._capture_end_dt == self._parse_datetime(recording.end_time)
            and self.timeline_widget.duration_seconds > 0
        )
        if capture_matches and self.timeline_widget.offset_seconds > 0:
            self.seek_to_timeline_offset(self.timeline_widget.offset_seconds)
            return

        start_dt = self._parse_datetime(recording.start_time)
        end_dt = self._parse_datetime(recording.end_time)
        duration = (
            max(0, int(start_dt.secsTo(end_dt)))
            if start_dt.isValid() and end_dt.isValid()
            else 0
        )
        segments = [(0, duration, recording.file_type)] if duration > 0 else []
        self._set_timeline_capture(
            channel=recording.channel,
            start_time=recording.start_time,
            end_time=recording.end_time,
            recording_name=recording.name,
            segments=segments,
            initial_offset_seconds=0,
        )
        self._start_playback(
            channel=recording.channel,
            start_time=recording.start_time,
            end_time=recording.end_time,
            recording_name=recording.name,
            playback_position_percent=0,
            preserve_timeline=True,
        )

    def _play_time_range(self):
        try:
            start_time, end_time = self._selected_time_range()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Time Range", str(exc))
            return
        channel = int(self.combo_channel.currentData())
        start_dt = self._parse_datetime(start_time)
        end_dt = self._parse_datetime(end_time)
        segments: list[tuple[int, int, int]] = []
        if start_dt.isValid() and end_dt.isValid():
            total_secs = max(0, int(start_dt.secsTo(end_dt)))
            for rec in self.recordings:
                if rec.channel != channel:
                    continue
                rec_s = self._parse_datetime(rec.start_time)
                rec_e = self._parse_datetime(rec.end_time)
                if not rec_s.isValid() or not rec_e.isValid():
                    continue
                s_off = max(0, min(total_secs, int(start_dt.secsTo(rec_s))))
                e_off = max(0, min(total_secs, int(start_dt.secsTo(rec_e))))
                if e_off > s_off:
                    segments.append((s_off, e_off, rec.file_type))
        self._set_timeline_capture(
            channel=channel,
            start_time=start_time,
            end_time=end_time,
            recording_name="",
            segments=segments,
            initial_offset_seconds=0,
        )
        self._start_playback(
            channel=channel,
            start_time=start_time,
            end_time=end_time,
            recording_name="",
            playback_position_percent=0,
            preserve_timeline=True,
        )

    def _start_playback(
        self,
        channel: int,
        start_time: str,
        end_time: str,
        recording_name: str,
        playback_position_percent: int = 0,
        preserve_timeline: bool = False,
    ):
        self.stop_playback()
        if not preserve_timeline or self.timeline_widget.duration_seconds <= 0:
            self._set_timeline_capture(
                channel=channel,
                start_time=start_time,
                end_time=end_time,
                recording_name=recording_name,
                initial_offset_seconds=0,
            )

        self.playback_tile.channel = channel
        self.playback_tile.lbl_title.setText(f"CAMERA {channel} (PLAYBACK)")
        self.is_paused = False
        self._playback_started_receiving_frames = False
        self._clock_fraction = 0.0
        self.btn_pause.setChecked(False)
        self.btn_pause.setText("Pause")
        self.btn_pause.setIcon(_make_icon("pause"))
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

        stream_type = int(self.combo_stream.currentData())
        playback_speed = self.selected_playback_speed()
        player = HikvisionPlaybackPlayer(
            channel=channel,
            config=self.config,
            start_time=start_time,
            end_time=end_time,
            recording_name=recording_name,
            stream_type=stream_type,
            playback_position_percent=playback_position_percent,
            playback_speed=playback_speed,
            parent=self,
        )
        player.frame_ready.connect(self._on_playback_frame)
        player.status_changed.connect(self._on_playback_status)
        player.fps_updated.connect(self._on_playback_fps)
        player.progress_updated.connect(self._on_playback_progress)
        player.osd_time_updated.connect(self._on_playback_osd_time)
        player.playback_finished.connect(self._on_playback_finished)
        self.player = player
        target_label = recording_name or f"{start_time} → {end_time}"
        speed_text = self.combo_speed.currentText()
        if playback_position_percent > 0:
            self.lbl_status.setText(
                f"Playing {target_label} from {start_time} ({playback_position_percent}%, {speed_text})"
            )
        else:
            self.lbl_status.setText(
                f"Starting playback ({speed_text}): {target_label}"
            )
        player.start()
        self.playback_clock_timer.start()

    @Slot(int, QImage)
    def _on_playback_frame(self, _channel: int, image: QImage):
        self._playback_started_receiving_frames = True
        self.playback_tile.update_frame(image)

    @Slot(int, str, bool)
    def _on_playback_status(self, _channel: int, status_text: str, is_online: bool):
        self.playback_tile.update_status(status_text, is_online)

    @Slot(int, float)
    def _on_playback_fps(self, _channel: int, fps: float):
        self.playback_tile.update_fps(fps)

    @Slot(int, int)
    def _on_playback_progress(self, channel: int, progress: int):
        current_ts = self.timeline_widget.current_timestamp()
        if current_ts.isValid():
            self.lbl_status.setText(
                f"Camera {channel} playback: {current_ts.toString('HH:mm:ss')} ({progress}%)"
            )
        else:
            self.lbl_status.setText(f"Camera {channel} playback: {progress}%")

    @Slot(int, str)
    def _on_playback_osd_time(self, channel: int, osd_time: str):
        osd_dt = self._parse_datetime(osd_time)
        duration = self.timeline_widget.duration_seconds
        if (
            osd_dt.isValid()
            and self._capture_start_dt.isValid()
            and duration > 0
            and not self.timeline_widget.is_dragging
            and not self.timeline_slider.isSliderDown()
        ):
            offset = int(self._capture_start_dt.secsTo(osd_dt))
            if 0 <= offset <= duration:
                self._set_timeline_offset(offset)
                pct = int(round((offset * 100.0) / float(duration)))
                self.lbl_status.setText(
                    f"Camera {channel} playback: {osd_dt.toString('HH:mm:ss')} ({pct}%)"
                )

    def _advance_playback_clock(self):
        if (
            self.player is None
            or self.is_paused
            or not self._playback_started_receiving_frames
            or self.timeline_widget.is_dragging
            or self.timeline_slider.isSliderDown()
        ):
            return
        duration = self.timeline_widget.duration_seconds
        if duration <= 0:
            return
        self._clock_fraction += self.selected_playback_speed()
        whole_seconds = int(self._clock_fraction)
        if whole_seconds <= 0:
            return
        self._clock_fraction -= whole_seconds
        next_offset = min(
            duration, self.timeline_widget.offset_seconds + whole_seconds
        )
        self._set_timeline_offset(next_offset)

    @Slot(int, bool, str)
    def _on_playback_finished(self, _channel: int, success: bool, message: str):
        self.playback_clock_timer.stop()
        self._playback_started_receiving_frames = False
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText(message)
        if not success:
            QMessageBox.warning(self, "Playback Error", message)

    def _toggle_pause(self):
        if self.player is None:
            return
        self.is_paused = self.btn_pause.isChecked()
        self.player.set_paused(self.is_paused)
        self.btn_pause.setText("Resume" if self.is_paused else "Pause")
        self.btn_pause.setIcon(
            _make_icon("play" if self.is_paused else "pause")
        )

    def _save_playback_snapshot(self, channel: int):
        image = self.playback_tile.last_image
        if image is None or image.isNull():
            QMessageBox.information(
                self, "Snapshot", "No playback frame available yet."
            )
            return
        self.artifact_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        res_tag = f"{image.width()}x{image.height()}"
        output = (
            self.artifact_directory
            / f"cam{channel}_playback_{timestamp}_{res_tag}.jpg"
        )
        image.save(str(output), "JPG", 100)
        self.lbl_status.setText(f"Saved playback snapshot: {output.name}")

    def stop_playback(self):
        self.playback_clock_timer.stop()
        self._playback_started_receiving_frames = False
        if self.player is not None:
            player = self.player
            self.player = None
            try:
                player.playback_finished.disconnect(self._on_playback_finished)
            except (RuntimeError, TypeError):
                pass
            player.stop()
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)

    def handle_gamepad_action(self, action: str) -> bool:
        """Handle a semantic Steam Deck / Linux gamepad action inside RecordingsDialog."""
        if action == "dpad_left" or action == "seek_back":
            self.skip_seconds(-30)
            return True
        if action == "dpad_right" or action == "seek_forward":
            self.skip_seconds(30)
            return True
        if action == "dpad_up":
            if self.recording_list.count() > 0:
                row = max(0, self.recording_list.currentRow() - 1)
                self.recording_list.setCurrentRow(row)
            return True
        if action == "dpad_down":
            if self.recording_list.count() > 0:
                row = min(
                    self.recording_list.count() - 1,
                    self.recording_list.currentRow() + 1,
                )
                self.recording_list.setCurrentRow(row)
            return True
        if action == "activate":
            if self.recording_list.count() > 0:
                self._play_selected_recording()
            else:
                self._search_recordings()
            return True
        if action == "back":
            if self.player is not None:
                self.stop_playback()
            else:
                self.close()
            return True
        if action == "pause":
            if self.btn_pause.isEnabled():
                self.btn_pause.click()
            elif self.recording_list.count() > 0:
                self._play_selected_recording()
            return True
        if action == "snapshot":
            channel = (
                self._capture_channel
                if self._capture_channel is not None
                else int(self.combo_channel.currentData())
            )
            self._save_playback_snapshot(channel)
            return True
        if action == "prev_camera":
            idx = max(0, self.combo_speed.currentIndex() - 1)
            self.combo_speed.setCurrentIndex(idx)
            return True
        if action == "next_camera":
            idx = min(
                self.combo_speed.count() - 1,
                self.combo_speed.currentIndex() + 1,
            )
            self.combo_speed.setCurrentIndex(idx)
            return True
        return False

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Left:
            self.skip_seconds(-30)
            return
        if key == Qt.Key_Right:
            self.skip_seconds(30)
            return
        if key == Qt.Key_Space and self.btn_pause.isEnabled():
            self.btn_pause.click()
            return
        if key == Qt.Key_S:
            channel = (
                self._capture_channel
                if self._capture_channel is not None
                else int(self.combo_channel.currentData())
            )
            self._save_playback_snapshot(channel)
            return
        if key == Qt.Key_BracketLeft:
            self.handle_gamepad_action("prev_camera")
            return
        if key == Qt.Key_BracketRight:
            self.handle_gamepad_action("next_camera")
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.stop_playback()
        super().closeEvent(event)

    def reject(self):
        self.stop_playback()
        super().reject()


# ==============================================================================
# Main Application Window
# ==============================================================================
class MainWindow(QMainWindow):
    def __init__(
        self,
        steam_deck_mode: bool | None = None,
        enable_gamepad: bool = True,
    ):
        super().__init__()
        self.setWindowTitle("HikLens — DVR & CCTV Stream Viewer")
        self.steam_deck_mode = (
            bool(steam_deck_mode)
            if steam_deck_mode is not None
            else (is_steam_deck_hardware() or is_steam_gaming_mode())
        )
        self.resize(STEAM_DECK_WIDTH, STEAM_DECK_HEIGHT)
        self.setMinimumSize(800, 500)

        self.settings = QtCore.QSettings(
            QtCore.QSettings.IniFormat,
            QtCore.QSettings.UserScope,
            "Hikvision",
            "CameraViewer",
        )
        self.settings.setFallbacksEnabled(False)
        try:
            self.config = load_dvr_config(self.settings)
        except ValueError as exc:
            self.config = DVRConfig()
            QMessageBox.warning(self, "Invalid Saved DVR Settings", str(exc))
        default_directory = default_artifact_directory()
        try:
            self.viewer_state = load_viewer_state(
                self.settings, self.config.channels, default_directory
            )
        except ValueError as exc:
            self.viewer_state = ViewerState(
                visible_channels=list(self.config.channels),
                artifact_directory=default_directory,
            )
            QMessageBox.warning(self, "Invalid Saved Viewer State", str(exc))

        self.snapshot_dir = Path(
            self.viewer_state.artifact_directory
        ).expanduser().resolve()
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        self.workers: dict[int, CaptureBackend] = {}
        self.tiles = {}
        self.recorder = None
        self.recording_channel = None
        self.active_mode = "ALL"  # "ALL", "1", "2", "3", "4"
        self.backend_mode = "HTTP"
        self.selected_channels = list(self.viewer_state.visible_channels)
        self.is_paused = False
        self.auto_save_motion = False
        self.gamepad_selected_channel: int | None = (
            self.selected_channels[0] if self.selected_channels else None
        )
        self.active_recordings_dialog: RecordingsDialog | None = None
        self.gamepad_reader: LinuxGamepadReader | None = None

        self._setup_style()
        self._build_ui()
        self._restore_viewer_state()
        self._update_gamepad_tile_highlight()
        self._start_threads()
        if enable_gamepad:
            self._start_gamepad_reader()

    def _setup_style(self):
        btn_padding = "7px 14px" if self.steam_deck_mode else "5px 12px"
        combo_padding = "6px 10px" if self.steam_deck_mode else "4px 10px"
        toolbar_padding = "8px" if self.steam_deck_mode else "6px"
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: #0b0e14;
            }}
            QToolBar {{
                background-color: #161b26;
                border-bottom: 1px solid #232936;
                padding: {toolbar_padding};
                spacing: 8px;
            }}
            QLabel {{
                color: #e2e8f0;
            }}
            QComboBox {{
                background-color: #1f2937;
                color: #f8fafc;
                border: 1px solid #374151;
                border-radius: 5px;
                padding: {combo_padding};
                min-width: 150px;
                font-weight: bold;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: #1f2937;
                color: #f8fafc;
                border: 1px solid #374151;
                outline: 0;
                selection-background-color: #2563eb;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 5px 8px;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #374151;
            }}
            QPushButton {{
                background-color: #1f2937;
                color: #e2e8f0;
                border: 1px solid #374151;
                border-radius: 5px;
                padding: {btn_padding};
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #374151;
                border-color: #4b5563;
            }}
            QPushButton:checked {{
                background-color: #2563eb;
                border-color: #3b82f6;
                color: white;
            }}
            QStatusBar {{
                background-color: #161b26;
                color: #94a3b8;
                border-top: 1px solid #232936;
            }}
            QListWidget {{
                background-color: #12151c;
                color: #cbd5e1;
                border: 1px solid #232936;
                border-radius: 6px;
            }}
        """)

    def _build_ui(self):
        # Top Toolbar
        toolbar = QToolBar("Main Controls")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Camera selection dropdown
        toolbar.addWidget(QLabel(" View: "))
        self.combo_cam = QComboBox()
        self.combo_cam.addItem(_make_icon("grid"), "Grid View", "ALL")
        for ch in self.config.channels:
            self.combo_cam.addItem(_make_icon("camera"), f"Camera {ch}", str(ch))
        self.combo_cam.setIconSize(QSize(16, 16))
        self.combo_cam.currentIndexChanged.connect(self._on_combo_selection)
        toolbar.addWidget(self.combo_cam)

        self.btn_select_cameras = QPushButton()
        self.btn_select_cameras.setIcon(_make_icon("grid"))
        self.btn_select_cameras.setIconSize(QSize(16, 16))
        self.btn_select_cameras.setToolTip(
            "Choose which cameras appear in Grid View"
        )
        self.btn_select_cameras.clicked.connect(self._select_grid_cameras)
        toolbar.addWidget(self.btn_select_cameras)

        toolbar.addSeparator()

        # Backend Engine selector
        toolbar.addWidget(QLabel(" Engine: "))
        self.combo_backend = QComboBox()
        self.combo_backend.addItem(_make_icon("network"), "HTTP Snapshot (Fast Connect)", "HTTP")
        self.combo_backend.addItem(_make_icon("stream"), "Embedded RTSP (ffmpeg/VAAPI)", "RTSP")
        self.combo_backend.addItem(
            _make_icon("stream"),
            "Hikvision SDK (encrypted stream)",
            "HIKVISION",
        )
        self.combo_backend.setToolTip(
            "Hikvision SDK requires the separately obtained Linux SDK and a "
            "locally built stream helper."
        )
        self.combo_backend.setIconSize(QSize(16, 16))
        self.combo_backend.currentIndexChanged.connect(self._on_backend_changed)
        toolbar.addWidget(self.combo_backend)

        toolbar.addSeparator()

        # Pause / Play button
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setIcon(_make_icon("pause"))
        self.btn_pause.setIconSize(QSize(16, 16))
        self.btn_pause.setCheckable(True)
        self.btn_pause.clicked.connect(self._toggle_pause)
        toolbar.addWidget(self.btn_pause)

        # Snapshot button
        self.btn_snapshot = QPushButton("Snapshot")
        self.btn_snapshot.setIcon(_make_icon("camera"))
        self.btn_snapshot.setIconSize(QSize(16, 16))
        self.btn_snapshot.setToolTip("Save snapshot of current view (Key: S)")
        self.btn_snapshot.clicked.connect(self._take_snapshot)
        toolbar.addWidget(self.btn_snapshot)

        self.btn_record = QPushButton("Record")
        self.btn_record.setIcon(_make_icon("record"))
        self.btn_record.setIconSize(QSize(16, 16))
        self.btn_record.setToolTip("Record one camera to an MP4 video")
        self.btn_record.clicked.connect(self._toggle_recording)
        toolbar.addWidget(self.btn_record)

        self.btn_recordings = QPushButton("Recordings")
        self.btn_recordings.setIcon(_make_icon("playback"))
        self.btn_recordings.setIconSize(QSize(16, 16))
        self.btn_recordings.setToolTip(
            "Browse and watch previous DVR recordings via Hikvision SDK (Key: P)"
        )
        self.btn_recordings.clicked.connect(self._open_recordings_dialog)
        toolbar.addWidget(self.btn_recordings)

        # HQ RTSP Player button
        self.btn_rtsp = QPushButton("Open HQ RTSP")
        self.btn_rtsp.setIcon(_make_icon("stream"))
        self.btn_rtsp.setIconSize(QSize(16, 16))
        self.btn_rtsp.setToolTip("Open full-rate hardware stream in ffplay")
        self.btn_rtsp.clicked.connect(self._launch_rtsp)
        toolbar.addWidget(self.btn_rtsp)

        toolbar.addSeparator()

        # FPS selector
        toolbar.addWidget(QLabel(" Speed (FPS): "))
        self.combo_fps = QComboBox()
        self.combo_fps.addItem("5 FPS (Low Bandwidth)", 5)
        self.combo_fps.addItem("10 FPS (Balanced)", 10)
        self.combo_fps.addItem("15 FPS (Smooth)", 15)
        self.combo_fps.addItem("Max FPS", 30)
        self.combo_fps.setCurrentIndex(1)
        self.combo_fps.setToolTip(
            "Limits displayed frame rate for RTSP and Hikvision SDK. "
            "HTTP snapshot mode is fixed at 5 FPS."
        )
        self.combo_fps.setEnabled(supports_selectable_fps(self.backend_mode))
        self.combo_fps.currentIndexChanged.connect(self._on_fps_changed)
        toolbar.addWidget(self.combo_fps)

        toolbar.addSeparator()

        # Resolution Quality selector
        toolbar.addWidget(QLabel(" Quality: "))
        self.combo_quality = QComboBox()
        self.combo_quality.addItem(_make_icon("auto"), "Auto (1080p Focus / 480p Grid)", "auto")
        self.combo_quality.addItem(_make_icon("max"), "Max (1080p Full HD Always)", "max")
        self.combo_quality.addItem(_make_icon("standard"), "Standard (480p Fast)", "standard")
        self.combo_quality.setIconSize(QSize(16, 16))
        self.combo_quality.currentIndexChanged.connect(self._on_quality_changed)
        toolbar.addWidget(self.combo_quality)

        toolbar.addSeparator()

        # Auto-snapshot on motion checkbox
        self.chk_auto_motion = QCheckBox("Save on Motion")
        self.chk_auto_motion.setStyleSheet("color: #cbd5e1; margin-left: 6px;")
        toolbar.addWidget(self.chk_auto_motion)

        toolbar.addSeparator()

        # Toggle Event Log Drawer
        self.btn_toggle_log = QPushButton("Events")
        self.btn_toggle_log.setIcon(_make_icon("events"))
        self.btn_toggle_log.setIconSize(QSize(16, 16))
        self.btn_toggle_log.setCheckable(True)
        self.btn_toggle_log.setChecked(True)
        self.btn_toggle_log.clicked.connect(self._toggle_event_log)
        toolbar.addWidget(self.btn_toggle_log)

        # Settings button
        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setIcon(_make_icon("settings"))
        self.btn_settings.setIconSize(QSize(16, 16))
        self.btn_settings.clicked.connect(self._open_settings)
        toolbar.addWidget(self.btn_settings)

        # Fullscreen button
        self.btn_fullscreen = QPushButton("Fullscreen")
        self.btn_fullscreen.setIcon(_make_icon("fullscreen"))
        self.btn_fullscreen.setIconSize(QSize(16, 16))
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

        # PAGE 0: Camera Grid View
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(8)

        # Create camera tiles
        for ch in self.config.channels:
            tile = CameraViewWidget(ch)
            tile.double_clicked.connect(self._on_tile_double_clicked)
            tile.snapshot_requested.connect(self._save_camera_snapshot)
            self.tiles[ch] = tile

        self.stacked_view.addWidget(self.grid_container)
        self._update_camera_grid()

        # PAGE 1: Single Camera View
        self.single_container = QWidget()
        self.single_layout = QVBoxLayout(self.single_container)
        self.single_layout.setContentsMargins(0, 0, 0, 0)
        self.single_tile = CameraViewWidget(self.config.channels[0])
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

        lbl_log = QLabel("Activity & Motion Log")
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
        self.lbl_status_deck = QLabel(
            "Steam Deck Mode: Active (A: Zoom • B: Back • X: Snap • Y: Recordings • L1/R1: Cam)"
            if self.steam_deck_mode
            else ""
        )
        self.lbl_status_deck.setStyleSheet("color: #38bdf8; font-weight: bold;")
        self.lbl_status_deck.setVisible(self.steam_deck_mode)
        self.lbl_status_alert = QLabel("AlertStream: Initializing...")
        self.status_bar.addWidget(self.lbl_status_dvr)
        self.status_bar.addWidget(self.lbl_status_deck)
        self.status_bar.addPermanentWidget(self.lbl_status_alert)

    def _update_camera_grid(self):
        selected_channels = [
            channel
            for channel in self.config.channels
            if channel in self.selected_channels
        ]
        camera_count = len(selected_channels)
        rows, columns = camera_grid_dimensions(camera_count)
        self.combo_cam.setItemText(
            0, f"Grid View ({camera_count}, {columns}x{rows})"
        )
        self.btn_select_cameras.setText(
            f"Cameras ({camera_count}, {columns}x{rows})"
        )
        for tile in self.tiles.values():
            self.grid_layout.removeWidget(tile)

        for index, channel in enumerate(selected_channels):
            tile = self.tiles[channel]
            self.grid_layout.addWidget(tile, index // columns, index % columns)
            tile.show()
        for channel, tile in self.tiles.items():
            if channel not in selected_channels:
                tile.hide()
        if selected_channels and self.gamepad_selected_channel not in selected_channels:
            self.gamepad_selected_channel = selected_channels[0]
        self._update_gamepad_tile_highlight()

    def _update_gamepad_tile_highlight(self):
        show_highlight = self.active_mode == "ALL" and len(self.selected_channels) > 1
        for channel, tile in self.tiles.items():
            tile.set_gamepad_selected(
                show_highlight and channel == self.gamepad_selected_channel
            )

    def _rebuild_camera_views(self, previous_channels: list):
        mode = self.active_mode
        if mode != "ALL" and int(mode) not in self.config.channels:
            mode = "ALL"
        was_all_selected = set(self.selected_channels) == set(previous_channels)
        if was_all_selected:
            self.selected_channels = list(self.config.channels)
        else:
            selected = set(self.selected_channels)
            self.selected_channels = [
                channel for channel in self.config.channels if channel in selected
            ]
            if not self.selected_channels:
                self.selected_channels = list(self.config.channels)

        for tile in self.tiles.values():
            self.grid_layout.removeWidget(tile)
            tile.deleteLater()
        self.tiles.clear()

        signals_were_blocked = self.combo_cam.blockSignals(True)
        self.combo_cam.clear()
        self.combo_cam.addItem(_make_icon("grid"), "Grid View", "ALL")
        for channel in self.config.channels:
            self.combo_cam.addItem(
                _make_icon("camera"), f"Camera {channel}", str(channel)
            )
        self.combo_cam.blockSignals(signals_were_blocked)

        for channel in self.config.channels:
            tile = CameraViewWidget(channel)
            tile.double_clicked.connect(self._on_tile_double_clicked)
            tile.snapshot_requested.connect(self._save_camera_snapshot)
            self.tiles[channel] = tile

        self.single_tile.channel = (
            int(mode) if mode != "ALL" else self.config.channels[0]
        )
        self.single_tile.lbl_title.setText(
            f"Camera {self.single_tile.channel} (Enlarged)"
        )
        self._update_camera_grid()

        signals_were_blocked = self.combo_cam.blockSignals(True)
        self.combo_cam.setCurrentIndex(self.combo_cam.findData(mode))
        self.combo_cam.blockSignals(signals_were_blocked)
        self.switch_mode(mode)

    def _restore_viewer_state(self):
        state = self.viewer_state
        self.backend_mode = state.backend_mode
        self.selected_channels = list(state.visible_channels)

        for combo, value in (
            (self.combo_backend, state.backend_mode),
            (self.combo_fps, state.fps),
            (self.combo_quality, state.quality_mode),
            (self.combo_cam, state.active_mode),
        ):
            index = combo.findData(value)
            if index >= 0:
                signals_were_blocked = combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(signals_were_blocked)

        self.combo_fps.setEnabled(supports_selectable_fps(self.backend_mode))
        self.chk_auto_motion.setChecked(state.auto_save_motion)
        self.btn_toggle_log.setChecked(state.events_visible)
        self.log_panel.setVisible(state.events_visible)
        self._update_camera_grid()
        self.switch_mode(state.active_mode)

        geometry = self.settings.value("viewer/window_geometry")
        if geometry is not None and (
            not isinstance(geometry, QtCore.QByteArray)
            or not self.restoreGeometry(geometry)
        ):
            QMessageBox.warning(
                self, "Window State", "The saved window size could not be restored."
            )
        splitter_state = self.settings.value("viewer/splitter_state")
        if splitter_state is not None and (
            not isinstance(splitter_state, QtCore.QByteArray)
            or not self.splitter.restoreState(splitter_state)
        ):
            QMessageBox.warning(
                self, "Window State", "The saved panel layout could not be restored."
            )

    def _start_threads(self):
        target_fps = self.combo_fps.currentData()
        res_mode = self.combo_quality.currentData()
        self.combo_fps.setEnabled(supports_selectable_fps(self.backend_mode))

        # Stop existing workers
        for w in self.workers.values():
            w.stop()
        self.workers.clear()

        # Start Camera Workers / Players based on selected backend
        for ch in self.config.channels:
            is_focused = (self.active_mode == str(ch))
            is_active = (
                ch == self.recording_channel
                or is_focused
                or (
                    self.active_mode == "ALL"
                    and ch in self.selected_channels
                )
            )
            worker = create_capture_backend(
                self.backend_mode,
                ch,
                self.config,
                self,
                http_backend=CameraWorker,
                rtsp_backend=RTSPCameraPlayer,
                hikvision_backend=HikvisionCameraPlayer,
            )
            worker.set_active(is_active)
            worker.set_focused(is_focused)
            worker.set_target_fps(
                target_fps
                if supports_selectable_fps(self.backend_mode)
                else 5
            )
            worker.set_resolution_mode(res_mode)

            worker.frame_ready.connect(self._on_frame_ready)
            worker.status_changed.connect(self._on_worker_status)
            worker.fps_updated.connect(self._on_worker_fps)
            worker.log_event.connect(self._on_worker_log_event)
            self.workers[ch] = worker
            worker.start()

        if self.btn_toggle_log.isChecked():
            self._start_alert_worker()
        else:
            self._stop_alert_worker()

    def _on_backend_changed(self, index: int):
        self.backend_mode = self.combo_backend.itemData(index)
        self.status_bar.showMessage(f"Switching video engine to {self.backend_mode}...", 3000)
        self._start_threads()

    def _start_alert_worker(self):
        if hasattr(self, "alert_worker") and self.alert_worker.isRunning():
            return
        self.alert_worker = AlertStreamWorker(self.config, self)
        self.alert_worker.motion_event.connect(self._on_motion_detected)
        self.alert_worker.alert_status.connect(self._on_alert_status)
        self.alert_worker.start()

    def _stop_alert_worker(self):
        if hasattr(self, "alert_worker") and self.alert_worker.isRunning():
            self.alert_worker.stop()
        self.lbl_status_alert.setText("AlertStream: Paused (events hidden)")

    # ==========================================================================
    # Slot Handlers
    # ==========================================================================
    @Slot(int, QImage)
    def _on_frame_ready(self, channel: int, image: QImage):
        if self.recorder and channel == self.recording_channel:
            self.recorder.add_frame(image)

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
        if not self.btn_toggle_log.isChecked() or self.sender() is not self.alert_worker:
            return

        # Trigger visual indicator on camera tile
        if channel in self.tiles:
            self.tiles[channel].trigger_motion()
        if self.active_mode == str(channel):
            self.single_tile.trigger_motion()

        # Add to event log list
        item = QListWidgetItem(f"[{time_str}] Motion on Camera {channel}")
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

    def _select_grid_cameras(self):
        dialog = CameraSelectionDialog(
            self.config.channels, self.selected_channels, self
        )
        if dialog.exec() != QDialog.Accepted:
            return
        self.selected_channels = dialog.get_selected_channels()
        self._update_camera_grid()
        if self.active_mode == "ALL":
            self._sync_worker_activity()

    def _on_quality_changed(self, index: int):
        q_mode = self.combo_quality.itemData(index)
        for w in self.workers.values():
            w.set_resolution_mode(q_mode)

    def _sync_worker_activity(self):
        visible_channels = set(self.selected_channels)
        for channel, worker in self.workers.items():
            is_focused = self.active_mode == str(channel)
            worker.set_focused(is_focused)
            worker.set_active(
                channel == self.recording_channel
                or is_focused
                or (self.active_mode == "ALL" and channel in visible_channels)
            )

    def switch_mode(self, mode: str):
        self.active_mode = mode
        if mode == "ALL":
            self.stacked_view.setCurrentIndex(0)
            # Re-sync combo box if switched via double click
            idx = self.combo_cam.findData("ALL")
            if idx >= 0 and self.combo_cam.currentIndex() != idx:
                self.combo_cam.setCurrentIndex(idx)
        else:
            ch = int(mode)
            self.gamepad_selected_channel = ch
            self.single_tile.channel = ch
            self.single_tile.lbl_title.setText(f"Camera {ch} (Enlarged)")
            self.stacked_view.setCurrentIndex(1)
            # Re-sync combo box
            idx = self.combo_cam.findData(mode)
            if idx >= 0 and self.combo_cam.currentIndex() != idx:
                self.combo_cam.setCurrentIndex(idx)
        self._update_gamepad_tile_highlight()
        self._sync_worker_activity()

    def _start_gamepad_reader(self):
        self.gamepad_reader = LinuxGamepadReader(parent=self)
        self.gamepad_reader.action_triggered.connect(self.handle_gamepad_action)
        self.gamepad_reader.controller_connected.connect(
            self._on_gamepad_connected
        )
        self.gamepad_reader.start()

    @Slot(str)
    def _on_gamepad_connected(self, device_name: str):
        self.lbl_status_deck.setText(
            f"Controller ({device_name}): A Zoom • B Back • X Snap • Y Recordings • L1/R1 Cam"
        )
        self.lbl_status_deck.setVisible(True)

    def _cycle_camera_selection(self, step: int):
        visible = [
            ch for ch in self.config.channels if ch in self.selected_channels
        ]
        if not visible:
            return
        if self.active_mode == "ALL":
            current = (
                self.gamepad_selected_channel
                if self.gamepad_selected_channel in visible
                else visible[0]
            )
            idx = (visible.index(current) + step) % len(visible)
            self.gamepad_selected_channel = visible[idx]
            self._update_gamepad_tile_highlight()
            self.status_bar.showMessage(
                f"Selected Camera {self.gamepad_selected_channel} (Press A to zoom)",
                2000,
            )
        else:
            current = int(self.active_mode)
            order = visible if current in visible else list(self.config.channels)
            idx = (order.index(current) + step) % len(order)
            self.switch_mode(str(order[idx]))

    def _move_grid_selection_2d(self, d_row: int, d_col: int):
        visible = [
            ch for ch in self.config.channels if ch in self.selected_channels
        ]
        if not visible:
            return
        if self.active_mode != "ALL":
            self._cycle_camera_selection(d_col if d_col != 0 else d_row)
            return
        _rows, columns = camera_grid_dimensions(len(visible))
        current = (
            self.gamepad_selected_channel
            if self.gamepad_selected_channel in visible
            else visible[0]
        )
        index = visible.index(current)
        row, col = divmod(index, columns)
        new_index = min(
            len(visible) - 1,
            max(0, (row + d_row) * columns + (col + d_col)),
        )
        self.gamepad_selected_channel = visible[new_index]
        self._update_gamepad_tile_highlight()

    @Slot(str)
    def handle_gamepad_action(self, action: str) -> bool:
        """Process a physical Steam Deck / Linux gamepad action."""
        if (
            self.active_recordings_dialog is not None
            and self.active_recordings_dialog.isVisible()
        ):
            return self.active_recordings_dialog.handle_gamepad_action(action)

        if action == "dpad_left":
            self._move_grid_selection_2d(0, -1)
            return True
        if action == "dpad_right":
            self._move_grid_selection_2d(0, 1)
            return True
        if action == "dpad_up":
            self._move_grid_selection_2d(-1, 0)
            return True
        if action == "dpad_down":
            self._move_grid_selection_2d(1, 0)
            return True
        if action == "prev_camera":
            self._cycle_camera_selection(-1)
            return True
        if action == "next_camera":
            self._cycle_camera_selection(1)
            return True
        if action == "activate":
            if self.active_mode == "ALL":
                target = (
                    self.gamepad_selected_channel
                    if self.gamepad_selected_channel in self.selected_channels
                    else (
                        self.selected_channels[0]
                        if self.selected_channels
                        else self.config.channels[0]
                    )
                )
                self.switch_mode(str(target))
            else:
                self.switch_mode("ALL")
            return True
        if action == "back":
            if self.active_mode != "ALL":
                self.switch_mode("ALL")
            elif self.isFullScreen() and not is_steam_gaming_mode():
                self._toggle_fullscreen()
            return True
        if action == "snapshot":
            self._take_snapshot()
            return True
        if action == "recordings":
            self._open_recordings_dialog()
            return True
        if action == "pause":
            self.btn_pause.click()
            return True
        if action == "toggle_events":
            self.btn_toggle_log.click()
            return True
        if action == "fullscreen":
            self._toggle_fullscreen()
            return True
        if action == "record":
            self._toggle_recording()
            return True
        return False

    def _toggle_pause(self):
        self.is_paused = self.btn_pause.isChecked()
        self.btn_pause.setText("Resume" if self.is_paused else "Pause")
        self.btn_pause.setIcon(_make_icon("play" if self.is_paused else "pause"))
        for w in self.workers.values():
            w.set_paused(self.is_paused)

    def _on_fps_changed(self, index: int):
        if not supports_selectable_fps(self.backend_mode):
            return
        fps = self.combo_fps.currentData()
        for w in self.workers.values():
            w.set_target_fps(fps)

    def _toggle_event_log(self):
        visible = self.btn_toggle_log.isChecked()
        self.log_panel.setVisible(visible)
        if visible:
            self._start_alert_worker()
        else:
            self._stop_alert_worker()

    @Slot(str)
    def _on_alert_status(self, text: str):
        if self.btn_toggle_log.isChecked() and self.sender() is self.alert_worker:
            self.lbl_status_alert.setText(text)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.btn_fullscreen.setText("Fullscreen")
        else:
            self.showFullScreen()
            self.btn_fullscreen.setText("Exit Fullscreen")

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
        item = QListWidgetItem(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {fname.name}")
        item.setForeground(QtGui.QBrush(QColor("#38bdf8")))
        self.event_list.insertItem(0, item)

    def _take_snapshot(self):
        if self.active_mode == "ALL":
            for ch in self.selected_channels:
                self._save_camera_snapshot(ch)
            noun = "camera" if len(self.selected_channels) == 1 else "cameras"
            self.status_bar.showMessage(
                f"Saved snapshots for {len(self.selected_channels)} displayed {noun}!",
                4000,
            )
        else:
            self._save_camera_snapshot(int(self.active_mode))

    def _toggle_recording(self):
        if self.recorder is not None:
            if self.recorder.isRunning():
                self._stop_recording()
            return

        self._start_recording()

    def _start_recording(self):
        if self.is_paused:
            QMessageBox.information(self, "Recording", "Resume the video stream before recording.")
            return

        if self.active_mode == "ALL":
            channels_to_record = self.selected_channels
            selected_channel, accepted = QInputDialog.getItem(
                self,
                "Record Video",
                "Camera to record:",
                [str(channel) for channel in channels_to_record],
                0,
                False,
            )
            if not accepted:
                return
            channel = int(selected_channel)
        else:
            channel = int(self.active_mode)

        image = self.tiles[channel].last_image
        if image is None or image.isNull():
            QMessageBox.information(
                self,
                "Recording",
                f"Wait for Camera {channel} to show a frame before recording.",
            )
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = self.snapshot_dir / f"cam{channel}_{timestamp}.mp4"
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Video Recording",
            str(default_path),
            "MP4 Video (*.mp4)",
        )
        if not selected_path:
            return

        output_path = Path(selected_path)
        if output_path.suffix.lower() != ".mp4":
            output_path = output_path.with_suffix(".mp4")
        fps_limit = (
            self.combo_fps.currentData()
            if supports_selectable_fps(self.backend_mode)
            else 5
        )
        measured_fps = self.tiles[channel].fps
        fps = (
            min(fps_limit, max(1, round(measured_fps)))
            if measured_fps > 0 else fps_limit
        )

        self.recording_channel = channel
        self.recorder = VideoRecorder(output_path, fps, image.size(), self)
        self.recorder.recording_started.connect(self._on_recording_started)
        self.recorder.recording_saved.connect(self._on_recording_saved)
        self.recorder.recording_error.connect(self._on_recording_error)
        self.recorder.finished.connect(self._on_recorder_finished)

        self.btn_record.setText("Preparing...")
        self.btn_record.setIcon(_make_icon("record"))
        self.btn_record.setEnabled(False)
        self.btn_pause.setEnabled(False)
        self.btn_settings.setEnabled(False)
        self.combo_backend.setEnabled(False)
        self.combo_fps.setEnabled(False)
        self.recorder.start()

    def _stop_recording(self):
        if self.recorder is None:
            return
        self.btn_record.setEnabled(False)
        self.recorder.stop()

    @Slot()
    def _on_recording_started(self):
        self.btn_record.setText("Stop Recording")
        self.btn_record.setIcon(_make_icon("stop"))
        self.btn_record.setEnabled(True)

    @Slot(str, int)
    def _on_recording_saved(self, path: str, dropped_frames: int):
        message = f"Recording saved: {Path(path).name}"
        if dropped_frames:
            message += f" ({dropped_frames} frames skipped because the encoder was busy)"
        self.status_bar.showMessage(message, 6000)
        item = QListWidgetItem(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        item.setForeground(QtGui.QBrush(QColor("#38bdf8")))
        self.event_list.insertItem(0, item)

    @Slot(str)
    def _on_recording_error(self, message: str):
        QMessageBox.warning(self, "Recording Error", message)

    @Slot()
    def _on_recorder_finished(self):
        if self.sender() is not self.recorder:
            return
        self.recorder = None
        self.recording_channel = None
        self.btn_record.setText("Record")
        self.btn_record.setIcon(_make_icon("record"))
        self.btn_record.setEnabled(True)
        self.btn_pause.setEnabled(True)
        self.btn_settings.setEnabled(True)
        self.combo_backend.setEnabled(True)
        self.combo_fps.setEnabled(supports_selectable_fps(self.backend_mode))
        self._sync_worker_activity()

    def _launch_rtsp(self):
        # Check if active is single or all
        ch = (
            self.config.channels[0]
            if self.active_mode == "ALL"
            else int(self.active_mode)
        )
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

    def _open_recordings_dialog(self):
        default_channel = (
            (
                self.gamepad_selected_channel
                if self.gamepad_selected_channel in self.selected_channels
                else self.selected_channels[0]
            )
            if self.active_mode == "ALL"
            else int(self.active_mode)
        )
        dialog = RecordingsDialog(
            self.config,
            self.snapshot_dir,
            default_channel=default_channel,
            parent=self,
        )
        if self.steam_deck_mode:
            dialog.resize(STEAM_DECK_WIDTH, STEAM_DECK_HEIGHT)
        self.active_recordings_dialog = dialog
        try:
            dialog.exec()
        finally:
            self.active_recordings_dialog = None

    def _open_settings(self):
        dialog = SettingsDialog(self.config, self.snapshot_dir, self)
        if dialog.exec() == QDialog.Accepted:
            try:
                new_config = dialog.get_updated_config()
                new_artifact_directory = dialog.get_artifact_directory()
                new_artifact_directory.mkdir(parents=True, exist_ok=True)
                self.settings.setValue(
                    "viewer/artifact_directory", str(new_artifact_directory)
                )
                save_dvr_config(self.settings, new_config)
            except (OSError, ValueError) as exc:
                QMessageBox.critical(
                    self, "Settings Error", f"Could not save settings:\n{exc}"
                )
                return

            previous_channels = list(self.config.channels)
            channels_changed = new_config.channels != previous_channels
            for w in self.workers.values():
                w.stop()
            self._stop_alert_worker()
            self.workers.clear()
            self.config = new_config
            self.snapshot_dir = new_artifact_directory
            self.lbl_status_dvr.setText(f"DVR: {self.config.ip} | User: {self.config.username}")
            if channels_changed:
                self._rebuild_camera_views(previous_channels)
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
        elif key == Qt.Key_R:
            self._toggle_recording()
        elif key == Qt.Key_P:
            self._open_recordings_dialog()
        elif key == Qt.Key_Space:
            self.btn_pause.click()
        elif key in (Qt.Key_F, Qt.Key_F11):
            self._toggle_fullscreen()
        elif key == Qt.Key_Left:
            self.handle_gamepad_action("dpad_left")
        elif key == Qt.Key_Right:
            self.handle_gamepad_action("dpad_right")
        elif key == Qt.Key_Up:
            self.handle_gamepad_action("dpad_up")
        elif key == Qt.Key_Down:
            self.handle_gamepad_action("dpad_down")
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self.handle_gamepad_action("activate")
        elif key == Qt.Key_PageUp:
            self.handle_gamepad_action("prev_camera")
        elif key == Qt.Key_PageDown:
            self.handle_gamepad_action("next_camera")
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        state = ViewerState(
            backend_mode=self.backend_mode,
            fps=int(self.combo_fps.currentData()),
            quality_mode=str(self.combo_quality.currentData()),
            active_mode=self.active_mode,
            visible_channels=list(self.selected_channels),
            events_visible=self.btn_toggle_log.isChecked(),
            auto_save_motion=self.chk_auto_motion.isChecked(),
            artifact_directory=str(self.snapshot_dir),
        )
        try:
            save_viewer_state(
                self.settings,
                state,
                self.saveGeometry(),
                self.splitter.saveState(),
            )
        except OSError as exc:
            QMessageBox.warning(
                self, "Viewer State Error", f"Could not save viewer state:\n{exc}"
            )

        if self.gamepad_reader is not None:
            self.gamepad_reader.stop()
        if self.recorder is not None:
            self.recorder.stop()
        for w in self.workers.values():
            w.stop()
        if hasattr(self, 'alert_worker'):
            self.alert_worker.stop()
        event.accept()


# ==============================================================================
# Entry Point
# ==============================================================================
def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="HikLens — DVR & CCTV Stream Viewer (Desktop & Steam Deck)"
    )
    parser.add_argument(
        "--steam-deck",
        action="store_true",
        help="Enable Steam Deck 1280x800 UI & gamepad mode",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Start in fullscreen mode (automatic in Steam Gaming Mode)",
    )
    parser.add_argument(
        "--add-to-steam",
        action="store_true",
        help="Register HikLens as a Non-Steam shortcut in Steam and exit",
    )
    args, qt_args = parser.parse_known_args(
        sys.argv[1:] if argv is None else argv
    )

    if args.add_to_steam:
        try:
            updated = register_steam_shortcut()
        except Exception as exc:
            print(f"Could not add shortcut to Steam: {exc}", file=sys.stderr)
            return 1
        for path in updated:
            print(f"Registered Non-Steam shortcut in: {path}")
        return 0

    # Enable High DPI scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName("HikLens")
    app.setDesktopFileName("io.github.rwnicholas.HikLens")
    _configure_dark_theme(app)
    font = QFont("Sans-Serif", 10)
    app.setFont(font)

    deck_mode = args.steam_deck or is_steam_deck_hardware() or is_steam_gaming_mode()
    window = MainWindow(steam_deck_mode=deck_mode)
    if args.fullscreen or is_steam_gaming_mode():
        window.showFullScreen()
        window.btn_fullscreen.setText("Exit Fullscreen")
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
