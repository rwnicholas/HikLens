import os
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
