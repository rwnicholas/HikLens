import importlib
import io
import os
import sys
import threading
import types
import unittest
from unittest.mock import patch


def _install_qt_test_stubs():
    if "PySide6.QtCore" in sys.modules:
        return False

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
            self.slots = []

        def emit(self, *args):
            self.events.append(args)
            for slot in self.slots:
                slot(*args)

        def connect(self, slot):
            self.slots.append(slot)

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
    return True


USING_QT_STUBS = _install_qt_test_stubs()
if not USING_QT_STUBS:
    from PySide6.QtCore import QCoreApplication

hikvision_backend = importlib.import_module("hikvision_backend")


class SignalEvents:
    def __init__(self, worker):
        self.events = {}
        for name in (
            "frame_ready",
            "status_changed",
            "fps_updated",
            "log_event",
            "diagnostics_updated",
            "playback_finished",
            "progress_updated",
            "osd_time_updated",
        ):
            if hasattr(worker, name):
                events = []
                getattr(worker, name).connect(
                    lambda *args, target=events: target.append(args)
                )
                self.events[name] = events

    def __getattr__(self, name):
        return self.events[name]


class HikvisionBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not USING_QT_STUBS:
            cls.application = QCoreApplication.instance() or QCoreApplication([])

    def make_worker(self):
        from types import SimpleNamespace

        config = SimpleNamespace(
            ip="127.0.0.1",
            sdk_port=8000,
            username="user",
            password="secret",
            stream_verification_code="stream-code",
            sdk_directory="/missing/sdk",
        )
        worker = hikvision_backend.HikvisionCameraPlayer(1, config)
        worker.test_events = SignalEvents(worker)
        return worker

    @staticmethod
    def wait_for_worker(worker, timeout=2):
        if USING_QT_STUBS:
            worker.join(timeout=timeout)
        else:
            worker.wait(int(timeout * 1000))
            QCoreApplication.instance().processEvents()

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
            self.wait_for_worker(worker)

        self.assertFalse(worker.isRunning())
        self.assertEqual(
            worker.test_events.status_changed[-1],
            (1, "Hikvision SDK unavailable", False),
        )
        self.assertEqual(
            worker.test_events.log_event[-1][1:],
            ("error", "SDK missing"),
        )

    def test_inactive_channel_does_not_initialize_the_sdk(self):
        worker = self.make_worker()
        worker.set_active(False)
        with patch.object(hikvision_backend, "discover_hikvision_sdk") as discover:
            worker.start()
            if not USING_QT_STUBS:
                import time

                time.sleep(0.05)
            worker.stop()
            if not USING_QT_STUBS:
                QCoreApplication.instance().processEvents()

        discover.assert_not_called()
        self.assertEqual(
            worker.test_events.status_changed[-1],
            (1, "Inactive", False),
        )

    def test_selected_fps_caps_sdk_frames_in_the_shared_pipeline(self):
        worker = self.make_worker()
        worker.set_target_fps(5)
        with patch.object(
            hikvision_backend.time,
            "monotonic",
            side_effect=(1.0, 1.05, 1.21),
        ):
            worker._emit_frame(b"\0" * 4, 1, 1)
            worker._emit_frame(b"\0" * 4, 1, 1)
            worker._emit_frame(b"\0" * 4, 1, 1)

        self.assertEqual(len(worker.test_events.frame_ready), 2)

    def test_quality_and_focus_select_main_or_substream(self):
        worker = self.make_worker()
        self.assertEqual(worker._stream_type(), 1)

        worker.set_focused(True)
        self.assertEqual(worker._stream_type(), 0)

        worker.set_resolution_mode("standard")
        self.assertEqual(worker._stream_type(), 1)

        worker.set_resolution_mode("max")
        self.assertEqual(worker._stream_type(), 0)

    def test_quality_change_requests_preview_restart(self):
        worker = self.make_worker()
        with patch.object(worker, "_terminate_process") as terminate:
            worker.set_resolution_mode("max")

        self.assertTrue(worker._configuration_changed.is_set())
        terminate.assert_called_once()

    def test_login_connection_error_has_actionable_diagnostic(self):
        worker = self.make_worker()
        worker._diagnostics = {"login": "failed", "sdk_error_code": 7}

        message = worker._diagnostic_summary("helper exited")

        self.assertIn("NET_DVR_NETWORK_FAIL_CONNECT", message)
        self.assertIn("configured IP address, SDK port, and network path", message)

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
            worker.test_events.status_changed[-1],
            (1, "Hikvision decode error", False),
        )
        self.assertFalse(worker.test_events.frame_ready)
        self.assertIn(
            "encrypted video could not be decoded",
            worker.test_events.log_event[-1][2],
        )

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

        self.assertEqual(worker.test_events.diagnostics_updated[-1][0], 1)
        diagnostic = worker.test_events.diagnostics_updated[-1][1]
        self.assertEqual(diagnostic["stream_bytes"], 2048)
        self.assertEqual(diagnostic["encryption_type"], 2)
        self.assertTrue(
            any(
                "AES key retrieval: failed" in event[2]
                for event in worker.test_events.log_event
            )
        )
        self.assertTrue(
            any(
                "No decoded frames received" in event[2]
                for event in worker.test_events.log_event
            )
        )
        diagnostic = worker.test_events.diagnostics_updated[-1][1]
        self.assertTrue(diagnostic["stream_verification_code_configured"])
        self.assertFalse(diagnostic["stream_verification_code_applied"])
        self.assertTrue(
            any(
                "not accepted" in event[2]
                for event in worker.test_events.log_event
            )
        )

    def test_verification_code_is_forwarded_to_the_playctrl_helper(self):
        worker = self.make_worker()
        process = types.SimpleNamespace(
            stderr=io.BytesIO(),
            poll=lambda: 0,
            wait=lambda timeout=None: 0,
        )
        installation = types.SimpleNamespace(
            stream_helper="/external/helper",
            library_directory="/external/sdk/lib",
            component_directory="/external/sdk/lib/HCNetSDKCom",
        )
        with patch.dict(
            os.environ,
            {"HIKVISION_STREAM_VERIFICATION_CODE": "never-forward-this"},
        ), patch.object(
            hikvision_backend.subprocess, "Popen", return_value=process
        ) as popen:
            worker._run_helper(installation)

        child_environment = popen.call_args.kwargs["env"]
        self.assertEqual(
            child_environment["HIKVISION_STREAM_VERIFICATION_CODE"],
            "stream-code",
        )
        self.assertTrue(
            child_environment["LD_LIBRARY_PATH"].startswith(
                "/external/sdk/lib:/external/sdk/lib/HCNetSDKCom"
            )
        )
        self.assertNotIn("never-forward-this", child_environment.values())

    def test_helper_success_is_required_before_code_is_reported_as_applied(self):
        worker = self.make_worker()
        worker._apply_diagnostics(
            {
                "stream_verification_code_applied": True,
                "decoder_key_configuration": "ok",
            }
        )

        diagnostic = worker.test_events.diagnostics_updated[-1][1]
        self.assertTrue(diagnostic["stream_verification_code_configured"])
        self.assertTrue(diagnostic["stream_verification_code_applied"])
        self.assertFalse(
            any("not accepted" in event[2] for event in worker.test_events.log_event)
        )

    def test_decoded_frames_use_the_shared_qimage_signal(self):
        worker = self.make_worker()
        worker._emit_frame(bytes(2 * 2 * 4), 2, 2)

        self.assertEqual(len(worker.test_events.frame_ready), 1)
        channel, image = worker.test_events.frame_ready[0]
        self.assertEqual(channel, 1)
        self.assertFalse(image.isNull())
        self.assertEqual(
            worker.test_events.status_changed[-1],
            (1, "Online (Hikvision SDK)", True),
        )

    def test_playback_worker_runs_once_and_emits_progress_and_completion(self):
        from types import SimpleNamespace

        config = SimpleNamespace(
            ip="127.0.0.1",
            sdk_port=8000,
            username="user",
            password="secret",
            stream_verification_code="stream-code",
            sdk_directory="/external/sdk",
        )
        player = hikvision_backend.HikvisionPlaybackPlayer(
            channel=2,
            config=config,
            start_time="2026-11-18 10:07:30",
            end_time="2026-11-18 10:15:00",
            recording_name="ch02_0001",
            stream_type=0,
            playback_position_percent=50,
        )
        player.test_events = SignalEvents(player)
        process = types.SimpleNamespace(
            stderr=io.BytesIO(
                b'HIKVISION_DIAGNOSTIC {"playback_progress":45,"playback_osd_time":"2026-11-18 10:08:12","preview":"ok"}\n'
            ),
            poll=lambda: 0,
            wait=lambda timeout=None: 0,
        )
        installation = types.SimpleNamespace(
            stream_helper="/external/helper",
            library_directory="/external/sdk/lib",
            component_directory="/external/sdk/lib/HCNetSDKCom",
        )
        with patch.object(
            hikvision_backend,
            "discover_hikvision_sdk",
            return_value=installation,
        ), patch.object(
            hikvision_backend.subprocess, "Popen", return_value=process
        ) as popen:
            player.start()
            self.wait_for_worker(player)

        self.assertEqual(
            popen.call_args.args[0],
            ["/external/helper", "--playback"],
        )
        child_env = popen.call_args.kwargs["env"]
        self.assertEqual(child_env["HIKVISION_PLAYBACK"], "1")
        self.assertEqual(child_env["HIKVISION_PLAYBACK_FILE"], "ch02_0001")
        self.assertEqual(child_env["HIKVISION_START_TIME"], "2026-11-18 10:07:30")
        self.assertEqual(child_env["HIKVISION_END_TIME"], "2026-11-18 10:15:00")
        self.assertEqual(child_env["HIKVISION_PLAYBACK_POS"], "50")
        self.assertIn((2, 45), player.test_events.progress_updated)
        self.assertIn(
            (2, "2026-11-18 10:08:12"), player.test_events.osd_time_updated
        )
        self.assertEqual(player.test_events.progress_updated[-1], (2, 100))
        self.assertEqual(
            player.test_events.playback_finished[-1],
            (2, True, "Playback finished."),
        )


if __name__ == "__main__":
    unittest.main()
