"""Qt worker that adapts the optional Hikvision helper to the frame pipeline."""

from __future__ import annotations

import json
import os
import select
import signal
import struct
import subprocess
import threading
import time

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from hikvision_sdk import (
    HikvisionSDKError,
    discover_hikvision_sdk,
    helper_runtime_environment,
)


_FRAME_HEADER = struct.Struct("<4sIII")
_MAX_FRAME_BYTES = 128 * 1024 * 1024
_DIAGNOSTIC_PREFIX = "HIKVISION_DIAGNOSTIC "
_STATUS_FIELDS = {
    "sdk_init": "SDK initialization",
    "login": "DVR login",
    "aes_key_retrieval": "AES key retrieval",
    "sdk_secret_key": "SDK secret-key configuration",
    "preview": "Live preview",
    "playctrl_initialization": "PlayCtrl initialization",
    "decoder_key_configuration": "PlayCtrl decoder-key configuration",
}


class HikvisionCameraPlayer(QThread):
    """HCNetSDK/PlayCtrl capture worker conforming to the camera frame API."""

    frame_ready = Signal(int, QImage)
    status_changed = Signal(int, str, bool)
    fps_updated = Signal(int, float)
    log_event = Signal(int, str, str)
    diagnostics_updated = Signal(int, object)

    def __init__(self, channel: int, config, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.config = config
        self._running = True
        self._active = True
        self._paused = False
        self._focused = False
        self._resolution_mode = "auto"
        self._target_fps = 10
        self._reported_inactive = False
        self._stop_event = threading.Event()
        self._configuration_changed = threading.Event()
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._diagnostics_lock = threading.Lock()
        self._diagnostics: dict = {}
        self._verification_code_notice_logged = False
        self._last_logged_status: dict[str, str] = {}
        self._last_logged_error = ""
        self._frames_counted = 0
        self._last_fps_time = time.monotonic()
        self._last_frame_time = 0.0
        self._error_logged = False

    def start(self):
        if not self.isRunning():
            super().start()

    def stop(self):
        self._running = False
        self._stop_event.set()
        self._terminate_process()
        self.wait()

    def set_active(self, active: bool):
        self._active = bool(active)
        if self._active:
            self._stop_event.set()
        else:
            self._stop_event.clear()
            self._terminate_process()
            if self.isRunning():
                self.status_changed.emit(self.channel, "Inactive", False)
                self._reported_inactive = True

    def set_focused(self, focused: bool):
        focused = bool(focused)
        if self._focused != focused:
            self._focused = focused
            self._restart_for_stream_change()

    def set_paused(self, paused: bool):
        self._paused = bool(paused)

    def set_target_fps(self, fps: int):
        self._target_fps = max(1, min(int(fps), 30))

    def set_resolution_mode(self, mode: str):
        if self._resolution_mode != mode:
            self._resolution_mode = mode
            self._restart_for_stream_change()

    def _restart_for_stream_change(self):
        self._configuration_changed.set()
        self._stop_event.set()
        self._terminate_process()

    def _stream_type(self) -> int:
        if self._resolution_mode == "max":
            return 0
        if self._resolution_mode == "standard":
            return 1
        return 0 if self._focused else 1

    def run(self):
        installation = None
        while self._running:
            if not self._active:
                if not self._reported_inactive:
                    self.status_changed.emit(self.channel, "Inactive", False)
                    self._reported_inactive = True
                self._stop_event.wait(0.2)
                self._stop_event.clear()
                continue
            self._reported_inactive = False
            self._stop_event.clear()
            self._configuration_changed.clear()

            if installation is None:
                self.status_changed.emit(
                    self.channel, "Checking Hikvision SDK…", False
                )
                try:
                    installation = discover_hikvision_sdk(
                        self.config.sdk_directory
                    )
                except HikvisionSDKError as exc:
                    self.status_changed.emit(
                        self.channel, "Hikvision SDK unavailable", False
                    )
                    self.log_event.emit(self.channel, "error", str(exc))
                    self._stop_event.wait()
                    return

            self.status_changed.emit(
                self.channel,
                "Starting Hikvision "
                f"{'main' if self._stream_type() == 0 else 'sub'}-stream preview…",
                False,
            )
            exit_code, intentional_stop, error = self._run_helper(installation)
            if not self._running:
                break
            if self._configuration_changed.is_set():
                continue
            if not self._active:
                continue
            if intentional_stop:
                continue

            if error:
                self.status_changed.emit(
                    self.channel, "Hikvision decode error", False
                )
                if not self._error_logged or self._frames_counted:
                    self.log_event.emit(
                        self.channel, "error", self._diagnostic_summary(error)
                    )
                self._error_logged = True
            elif exit_code:
                self.status_changed.emit(
                    self.channel, f"Hikvision helper exited ({exit_code})", False
                )
                if not self._error_logged:
                    self.log_event.emit(
                        self.channel,
                        "error",
                        f"Hikvision stream helper exited with status {exit_code}.",
                    )
                self._error_logged = True
            else:
                self._error_logged = False

            if self._running and self._active:
                self._stop_event.wait(5.0)
                self._stop_event.clear()

    def _run_helper(self, installation) -> tuple[int, bool, str]:
        read_fd, write_fd = os.pipe()
        env = helper_runtime_environment(
            getattr(installation, "library_directory", None),
            getattr(installation, "component_directory", None),
        )
        env.update(
            {
                "HIKVISION_HOST": self.config.ip,
                "HIKVISION_PORT": str(self.config.sdk_port),
                "HIKVISION_USERNAME": self.config.username,
                "HIKVISION_PASSWORD": self.config.password,
                "HIKVISION_STREAM_VERIFICATION_CODE": (
                    self.config.stream_verification_code
                ),
                "HIKVISION_CHANNEL": str(self.channel),
                "HIKVISION_STREAM_TYPE": str(self._stream_type()),
                "HIKVISION_RUN_SECONDS": "0",
                "HIKVISION_PLAYM4_KEY_LENGTH": "128",
                # The helper reads this limit at startup; apply the live UI cap
                # in _emit_frame so selector changes take effect immediately.
                "HIKVISION_TARGET_FPS": "30",
                "HIKVISION_FRAME_FD": str(write_fd),
            }
        )

        try:
            process = subprocess.Popen(
                [str(installation.stream_helper)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=env,
                close_fds=True,
                pass_fds=(write_fd,),
            )
        except OSError as exc:
            os.close(read_fd)
            os.close(write_fd)
            return 127, False, f"Could not start Hikvision stream helper: {exc}"
        finally:
            if write_fd >= 0:
                try:
                    os.close(write_fd)
                except OSError:
                    pass

        with self._process_lock:
            self._process = process
        if (
            not self._running
            or not self._active
            or self._configuration_changed.is_set()
        ):
            self._terminate_process()
        diagnostic_thread = threading.Thread(
            target=self._read_diagnostics,
            args=(process,),
            daemon=True,
        )
        diagnostic_thread.start()

        protocol_error = ""
        try:
            while (
                self._running
                and self._active
                and not self._configuration_changed.is_set()
            ):
                header = self._read_exact(read_fd, _FRAME_HEADER.size, process)
                if header is None:
                    break
                magic, width, height, byte_count = _FRAME_HEADER.unpack(header)
                expected_size = width * height * 4
                if (
                    magic != b"HIKF"
                    or width < 1
                    or height < 1
                    or expected_size != byte_count
                    or byte_count > _MAX_FRAME_BYTES
                ):
                    protocol_error = (
                        "Hikvision helper returned an invalid decoded-frame packet."
                    )
                    self._terminate_process()
                    break

                pixels = self._read_exact(read_fd, byte_count, process)
                if pixels is None:
                    protocol_error = (
                        "Hikvision helper closed during a decoded-frame packet."
                    )
                    break
                self._emit_frame(pixels, width, height)
        except RuntimeError as exc:
            protocol_error = str(exc)
            self._terminate_process()
        finally:
            os.close(read_fd)
            if process.poll() is None:
                self._terminate_process()
            try:
                exit_code = process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                exit_code = process.wait()
            diagnostic_thread.join(timeout=2)
            if process.stderr is not None:
                process.stderr.close()
            with self._process_lock:
                if self._process is process:
                    self._process = None

        with self._diagnostics_lock:
            diagnostics = dict(self._diagnostics)
        intentional_stop = (
            not self._running
            or not self._active
            or self._configuration_changed.is_set()
        )
        error = protocol_error or str(diagnostics.get("decoder_error", ""))
        if exit_code == 9 and not error:
            error = "No decoded frames received; encrypted video could not be decoded."
        elif exit_code not in (0, 9, -signal.SIGTERM) and not error:
            error = (
                f"Hikvision helper failed with exit status {exit_code}; "
                f"diagnostics: {json.dumps(diagnostics, sort_keys=True)}"
            )
        return exit_code, intentional_stop, error

    def _read_exact(
        self, fd: int, size: int, process: subprocess.Popen
    ) -> bytes | None:
        result = bytearray()
        while len(result) < size and self._running and self._active:
            try:
                readable, _, _ = select.select([fd], [], [], 0.25)
            except OSError as exc:
                raise RuntimeError(f"Could not read Hikvision frame pipe: {exc}") from exc
            if not readable:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(fd, size - len(result))
            except OSError as exc:
                raise RuntimeError(f"Could not read Hikvision frame pipe: {exc}") from exc
            if not chunk:
                break
            result.extend(chunk)
        if not result:
            return None
        if len(result) != size:
            raise RuntimeError("Hikvision helper sent a truncated frame packet.")
        return bytes(result)

    def _emit_frame(self, pixels: bytes, width: int, height: int):
        now = time.monotonic()
        minimum_interval = 1.0 / self._target_fps
        if self._paused or now - self._last_frame_time < minimum_interval:
            return
        image = QImage(
            pixels,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGB32,
        ).copy()
        if image.isNull():
            self.log_event.emit(
                self.channel, "error", "Could not construct a QImage from PlayCtrl RGB32 data."
            )
            return

        self._last_frame_time = now
        self._frames_counted += 1
        self._error_logged = False
        self.frame_ready.emit(self.channel, image)
        self.status_changed.emit(self.channel, "Online (Hikvision SDK)", True)
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self.fps_updated.emit(
                self.channel, round(self._frames_counted / elapsed, 1)
            )
            self._frames_counted = 0
            self._last_fps_time = now

    def _read_diagnostics(self, process: subprocess.Popen):
        if process.stderr is None:
            return
        try:
            for raw_line in process.stderr:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith(_DIAGNOSTIC_PREFIX):
                    continue
                try:
                    diagnostic = json.loads(line[len(_DIAGNOSTIC_PREFIX) :])
                except json.JSONDecodeError:
                    self.log_event.emit(
                        self.channel,
                        "warn",
                        "Hikvision helper emitted malformed diagnostic data.",
                    )
                    continue
                if not isinstance(diagnostic, dict):
                    continue
                self._apply_diagnostics(diagnostic)
        except OSError as exc:
            if self._running:
                self.log_event.emit(
                    self.channel,
                    "warn",
                    f"Could not read Hikvision diagnostics ({type(exc).__name__}).",
                )

    def _apply_diagnostics(self, diagnostic: dict):
        diagnostic = dict(diagnostic)
        code_configured = bool(self.config.stream_verification_code)
        diagnostic["stream_verification_code_configured"] = code_configured
        code_applied = bool(
            diagnostic.get("stream_verification_code_applied", False)
        )
        diagnostic["stream_verification_code_applied"] = code_applied
        with self._diagnostics_lock:
            self._diagnostics.update(diagnostic)
            snapshot = dict(self._diagnostics)

        self.diagnostics_updated.emit(self.channel, snapshot)
        if not code_applied and not self._verification_code_notice_logged:
            if code_configured:
                message = (
                    "The Streaming Verification Code is configured but PlayCtrl "
                    "has not accepted it for decoder setup."
                )
            else:
                message = (
                    "The Hikvision encrypted preview requires a Streaming "
                    "Verification Code; configure it separately from the DVR "
                    "password."
                )
            self.log_event.emit(
                self.channel,
                "warn",
                message,
            )
            self._verification_code_notice_logged = True
        for field, label in _STATUS_FIELDS.items():
            status = str(diagnostic.get(field, "pending"))
            if status in ("pending", self._last_logged_status.get(field)):
                continue
            self._last_logged_status[field] = status
            level = "error" if status == "failed" else "info"
            self.log_event.emit(
                self.channel, level, f"Hikvision {label}: {status}."
            )

        error = str(diagnostic.get("decoder_error", ""))
        if error and error != self._last_logged_error:
            self._last_logged_error = error
            self.log_event.emit(self.channel, "error", f"Hikvision decoder: {error}.")

    def _diagnostic_summary(self, error: str) -> str:
        with self._diagnostics_lock:
            diagnostics = dict(self._diagnostics)
        if (
            diagnostics.get("login") == "failed"
            and diagnostics.get("sdk_error_code") == 7
        ):
            diagnostics["sdk_error_message"] = (
                "NET_DVR_NETWORK_FAIL_CONNECT: HCNetSDK could not connect to the "
                "DVR. Check its configured IP address, SDK port, and network path."
            )
        diagnostics["decoder_error"] = error
        return "Hikvision capture failed: " + json.dumps(
            diagnostics, sort_keys=True
        )

    def _terminate_process(self):
        with self._process_lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        except ProcessLookupError:
            pass
