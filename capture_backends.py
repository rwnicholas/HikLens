"""Shared worker contract and selector for camera capture implementations."""

from __future__ import annotations

from typing import Any, Protocol


class CaptureBackend(Protocol):
    """Worker interface consumed by the camera UI and frame pipeline."""

    frame_ready: Any
    status_changed: Any
    fps_updated: Any
    log_event: Any

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def set_active(self, active: bool) -> None: ...

    def set_focused(self, focused: bool) -> None: ...

    def set_paused(self, paused: bool) -> None: ...

    def set_target_fps(self, fps: int) -> None: ...

    def set_resolution_mode(self, mode: str) -> None: ...


def create_capture_backend(
    backend_mode: str,
    channel: int,
    config,
    parent,
    *,
    http_backend,
    rtsp_backend,
    hikvision_backend,
) -> CaptureBackend:
    """Create one backend implementing the shared QImage frame pipeline."""
    backend_types = {
        "HTTP": http_backend,
        "RTSP": rtsp_backend,
        "HIKVISION": hikvision_backend,
    }
    try:
        backend_type = backend_types[backend_mode]
    except KeyError as exc:
        raise ValueError(f"Unknown capture backend: {backend_mode}") from exc
    return backend_type(channel, config, parent)
