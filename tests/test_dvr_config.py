import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from cam_viewer import (
        DVRConfig,
        RecordingsDialog,
        SettingsDialog,
        load_dvr_config,
        save_dvr_config,
    )
    from hikvision_sdk import HikvisionRecording, HikvisionSDKError
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 is required for DVR settings tests")
class DVRConfigSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_password_and_stream_verification_code_persist_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "viewer.ini"),
                QSettings.Format.IniFormat,
            )
            config = DVRConfig(
                ip="192.0.2.10",
                username="viewer",
                password="account-password",
                stream_verification_code="stream-code",
                channels=[1],
            )

            save_dvr_config(settings, config)
            loaded = load_dvr_config(settings)

            self.assertEqual(loaded.password, "account-password")
            self.assertEqual(loaded.stream_verification_code, "stream-code")

    def test_settings_dialog_keeps_the_two_secrets_separate_and_masked(self):
        config = DVRConfig(
            ip="192.0.2.10",
            password="account-password",
            stream_verification_code="stream-code",
            channels=[1],
        )
        dialog = SettingsDialog(config, Path(tempfile.gettempdir()))

        updated = dialog.get_updated_config()
        self.assertEqual(updated.password, "account-password")
        self.assertEqual(updated.stream_verification_code, "stream-code")
        self.assertEqual(
            dialog.edit_pass.echoMode(),
            dialog.edit_stream_verification_code.echoMode(),
        )

    def test_get_sdk_button_opens_the_official_download_page(self):
        dialog = SettingsDialog(
            DVRConfig(channels=[1]),
            Path(tempfile.gettempdir()),
        )
        with patch(
            "cam_viewer.QDesktopServices.openUrl", return_value=True
        ) as open_url:
            dialog._open_hikvision_sdk_page()

        self.assertEqual(open_url.call_count, 1)

    def test_helper_setup_builds_and_verifies_selected_sdk_directory(self):
        sdk_directory = Path(tempfile.gettempdir()) / "hikvision-sdk"
        dialog = SettingsDialog(
            DVRConfig(channels=[1]),
            Path(tempfile.gettempdir()),
        )
        dialog.edit_sdk_directory.setText(str(sdk_directory))
        installation = SimpleNamespace(root=sdk_directory.resolve())

        with patch(
            "cam_viewer.build_hikvision_helper",
            return_value=installation,
        ) as build, patch(
            "cam_viewer.QMessageBox.information"
        ):
            dialog._build_hikvision_helper()

        build.assert_called_once_with(str(sdk_directory))
        self.assertEqual(
            dialog.edit_sdk_directory.text(),
            str(sdk_directory.resolve()),
        )
        self.assertTrue(dialog.btn_build_hikvision_helper.isEnabled())

    def test_helper_build_errors_are_shown_to_the_user(self):
        dialog = SettingsDialog(
            DVRConfig(channels=[1]),
            Path(tempfile.gettempdir()),
        )
        dialog.edit_sdk_directory.setText("/missing/sdk")

        with patch(
            "cam_viewer.build_hikvision_helper",
            side_effect=HikvisionSDKError("compiler unavailable"),
        ), patch("cam_viewer.QMessageBox.critical") as show_error:
            dialog._build_hikvision_helper()

        show_error.assert_called_once()
        self.assertIn("compiler unavailable", show_error.call_args.args[2])
        self.assertTrue(dialog.btn_build_hikvision_helper.isEnabled())

    def test_recordings_dialog_searches_and_starts_selected_playback(self):
        config = DVRConfig(ip="192.0.2.10", channels=[1, 2])
        dialog = RecordingsDialog(
            config,
            Path(tempfile.gettempdir()),
            default_channel=2,
        )
        recording = HikvisionRecording(
            name="ch02_clip_01",
            channel=2,
            start_time="2026-11-18 12:00:00",
            end_time="2026-11-18 12:05:00",
            size_bytes=2097152,
            file_type=1,
        )
        with patch(
            "cam_viewer.list_hikvision_recordings",
            return_value=[recording],
        ) as search:
            dialog._search_recordings()

        search.assert_called_once()
        self.assertEqual(dialog.recording_list.count(), 1)

        with patch.object(dialog, "_start_playback") as start_playback:
            dialog._play_selected_recording()

        start_playback.assert_called_once_with(
            channel=2,
            start_time="2026-11-18 12:00:00",
            end_time="2026-11-18 12:05:00",
            recording_name="ch02_clip_01",
            playback_position_percent=0,
            preserve_timeline=True,
        )

    def test_recordings_dialog_timeline_seeks_inside_selected_capture(self):
        config = DVRConfig(ip="192.0.2.10", channels=[1, 2])
        dialog = RecordingsDialog(
            config,
            Path(tempfile.gettempdir()),
            default_channel=2,
        )
        recording = HikvisionRecording(
            name="ch02_clip_01",
            channel=2,
            start_time="2026-11-18 12:00:00",
            end_time="2026-11-18 12:10:00",
            size_bytes=4194304,
            file_type=0,
        )
        with patch(
            "cam_viewer.list_hikvision_recordings",
            return_value=[recording],
        ):
            dialog._search_recordings()

        self.assertEqual(dialog.timeline_widget.duration_seconds, 600)
        self.assertTrue(dialog.timeline_slider.isEnabled())

        with patch.object(dialog, "_start_playback") as start_playback:
            dialog.seek_to_timeline_offset(150)

        self.assertEqual(dialog.timeline_widget.offset_seconds, 150)
        self.assertEqual(dialog.timeline_slider.value(), 150)
        self.assertIn(
            "2026-11-18 12:02:30", dialog.lbl_timeline_current.text()
        )
        start_playback.assert_called_once_with(
            channel=2,
            start_time="2026-11-18 12:02:30",
            end_time="2026-11-18 12:10:00",
            recording_name="ch02_clip_01",
            playback_position_percent=25,
            preserve_timeline=True,
        )

        # OSD timestamp updates from the DVR advance the timeline playhead
        dialog._on_playback_osd_time(2, "2026-11-18 12:04:00")
        self.assertEqual(dialog.timeline_widget.offset_seconds, 240)
        self.assertEqual(dialog.timeline_slider.value(), 240)

        # Playback speed selector provides 0.25x, 0.5x, 1x, 2x, 4x
        speeds = [
            dialog.combo_speed.itemData(i)
            for i in range(dialog.combo_speed.count())
        ]
        self.assertEqual(speeds, [0.25, 0.5, 1.0, 2.0, 4.0])
        self.assertEqual(dialog.selected_playback_speed(), 1.0)
        dialog.combo_speed.setCurrentIndex(4)  # 4x
        self.assertEqual(dialog.selected_playback_speed(), 4.0)


if __name__ == "__main__":
    unittest.main()
