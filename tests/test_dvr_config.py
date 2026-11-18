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
        SettingsDialog,
        load_dvr_config,
        save_dvr_config,
    )
    from hikvision_sdk import HikvisionSDKError
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


if __name__ == "__main__":
    unittest.main()
