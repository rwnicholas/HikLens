import importlib
import sys
import threading
import types
import unittest
from unittest.mock import patch


def _install_qt_test_stubs():
    if "PySide6.QtCore" in sys.modules:
        return

    class Signal:
        def __init__(self, *types):
            del types

        def __set_name__(self, owner, name):
            del owner
            self.name = f"_test_signal_{name}"

        def __get__(self, instance, owner):
            del owner
            if instance is None:
                return self
            return instance.__dict__.setdefault(self.name, _BoundSignal())

    class _BoundSignal:
        def __init__(self):
            self.events = []

        def emit(self, *args):
            self.events.append(args)

    class QThread(threading.Thread):
        def __init__(self, parent=None):
            super().__init__(daemon=True)
            self.parent = parent

        def isRunning(self):
            return self.is_alive()

        def wait(self, milliseconds=None):
            self.join(None if milliseconds is None else milliseconds / 1000)
            return not self.is_alive()

    class QImage:
        class Format:
            Format_RGB32 = 1

        def __init__(self, *args):
            self.args = args

        def copy(self):
            return self

        def isNull(self):
            return False

    pyside = types.ModuleType("PySide6")
    core = types.ModuleType("PySide6.QtCore")
    gui = types.ModuleType("PySide6.QtGui")
    core.QThread = QThread
    core.Signal = Signal
    gui.QImage = QImage
    pyside.QtCore = core
    pyside.QtGui = gui
    sys.modules["PySide6"] = pyside
    sys.modules["PySide6.QtCore"] = core
    sys.modules["PySide6.QtGui"] = gui


_install_qt_test_stubs()
hikvision_backend = importlib.import_module("hikvision_backend")


class HikvisionBackendTests(unittest.TestCase):
    def make_worker(self):
        from types import SimpleNamespace

        config = SimpleNamespace(
            ip="127.0.0.1",
            sdk_port=8000,
            username="user",
            password="secret",
            sdk_directory="/missing/sdk",
        )
        return hikvision_backend.HikvisionCameraPlayer(1, config)

    def test_missing_sdk_is_reported_without_backend_fallback(self):
        worker = self.make_worker()
        with patch.object(
            hikvision_backend,
            "discover_hikvision_sdk",
            side_effect=hikvision_backend.HikvisionSDKError("SDK missing"),
        ):
            def stop_wait(_timeout=None):
                del _timeout
                worker._running = False

            worker._stop_event.wait = stop_wait
            worker.start()
            worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(
            worker.status_changed.events[-1],
            (1, "Hikvision SDK unavailable", False),
        )
        self.assertEqual(worker.log_event.events[-1][1:], ("error", "SDK missing"))

    def test_inactive_channel_does_not_initialize_the_sdk(self):
        worker = self.make_worker()
        worker.set_active(False)
        with patch.object(hikvision_backend, "discover_hikvision_sdk") as discover:
            worker.start()
            worker.stop()

        discover.assert_not_called()
        self.assertEqual(
            worker.status_changed.events[-1],
            (1, "Inactive", False),
        )

    def test_no_decoded_frames_is_an_error_not_an_online_black_frame(self):
        worker = self.make_worker()
        worker._running = True
        worker._active = True
        def fail_to_decode(_installation):
            del _installation
            return (
                9,
                False,
                "No decoded frames received; encrypted video could not be decoded.",
            )

        worker._run_helper = fail_to_decode

        def stop_after_error(_timeout):
            del _timeout
            worker._running = False

        worker._stop_event.wait = stop_after_error

        with patch.object(hikvision_backend, "discover_hikvision_sdk", return_value=object()):
            worker.run()

        self.assertEqual(
            worker.status_changed.events[-1],
            (1, "Hikvision decode error", False),
        )
        self.assertFalse(worker.frame_ready.events)
        self.assertIn("encrypted video could not be decoded", worker.log_event.events[-1][2])

    def test_diagnostics_are_emitted_and_logged_as_structured_fields(self):
        worker = self.make_worker()
        worker._apply_diagnostics(
            {
                "sdk_init": "ok",
                "login": "ok",
                "aes_key_retrieval": "failed",
                "stream_chunks": 4,
                "stream_bytes": 2048,
                "encryption_type": 2,
                "frames_decoded": 0,
                "decoder_error": "No decoded frames received",
            }
        )

        self.assertEqual(worker.diagnostics_updated.events[-1][0], 1)
        diagnostic = worker.diagnostics_updated.events[-1][1]
        self.assertEqual(diagnostic["stream_bytes"], 2048)
        self.assertEqual(diagnostic["encryption_type"], 2)
        self.assertTrue(
            any(
                "AES key retrieval: failed" in event[2]
                for event in worker.log_event.events
            )
        )
        self.assertTrue(
            any(
                "No decoded frames received" in event[2]
                for event in worker.log_event.events
            )
        )

    def test_decoded_frames_use_the_shared_qimage_signal(self):
        worker = self.make_worker()
        worker._emit_frame(bytes(2 * 2 * 4), 2, 2)

        self.assertEqual(len(worker.frame_ready.events), 1)
        channel, image = worker.frame_ready.events[0]
        self.assertEqual(channel, 1)
        self.assertFalse(image.isNull())
        self.assertEqual(
            worker.status_changed.events[-1],
            (1, "Online (Hikvision SDK)", True),
        )


if __name__ == "__main__":
    unittest.main()
