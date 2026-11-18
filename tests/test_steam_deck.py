import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from steam_deck import (
    LinuxGamepadReader,
    compute_steam_shortcut_appid,
    dump_shortcuts_vdf,
    is_steam_deck_hardware,
    is_steam_gaming_mode,
    parse_shortcuts_vdf,
    register_steam_shortcut,
    trigger_steam_osk,
)

try:
    from PySide6.QtWidgets import QApplication
    from cam_viewer import DVRConfig, MainWindow, RecordingsDialog
except ImportError:
    QApplication = None


class SteamDeckIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QApplication is not None:
            cls.application = QApplication.instance() or QApplication([])

    def test_detects_steam_deck_hardware_from_dmi_or_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            dmi_file = Path(tmp) / "product_name"
            dmi_file.write_text("Jupiter\n", encoding="utf-8")
            self.assertTrue(
                is_steam_deck_hardware(env={}, dmi_paths=(dmi_file,))
            )

            dmi_file.write_text("Galileo\n", encoding="utf-8")
            self.assertTrue(
                is_steam_deck_hardware(env={}, dmi_paths=(dmi_file,))
            )

            dmi_file.write_text("Standard PC\n", encoding="utf-8")
            self.assertFalse(
                is_steam_deck_hardware(env={}, dmi_paths=(dmi_file,))
            )
            self.assertTrue(
                is_steam_deck_hardware(
                    env={"SteamDeck": "1"}, dmi_paths=(dmi_file,)
                )
            )

    def test_detects_steam_gaming_mode_environment(self):
        self.assertFalse(is_steam_gaming_mode(env={}))
        self.assertTrue(is_steam_gaming_mode(env={"STEAM_GAMEPADUI": "1"}))
        self.assertTrue(
            is_steam_gaming_mode(env={"GAMESCOPE_WAYLAND_DISPLAY": "gamescope-0"})
        )
        self.assertTrue(
            is_steam_gaming_mode(env={"XDG_CURRENT_DESKTOP": "gamescope"})
        )

    def test_binary_shortcuts_vdf_round_trip_and_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            config_dir = home / ".local/share/Steam/userdata/12345678/config"
            config_dir.mkdir(parents=True)

            # Seed an existing shortcut to verify preservation
            seed = [
                {
                    "appid": compute_steam_shortcut_appid('"/usr/bin/foo"', "FooApp"),
                    "AppName": "FooApp",
                    "Exe": '"/usr/bin/foo"',
                    "StartDir": '"/usr/bin"',
                    "LaunchOptions": "",
                    "IsHidden": 0,
                    "tags": {"0": "Favorite"},
                }
            ]
            vdf_file = config_dir / "shortcuts.vdf"
            vdf_file.write_bytes(dump_shortcuts_vdf(seed))

            updated = register_steam_shortcut(
                home_dir=home,
                env={"FLATPAK_ID": "io.github.rwnicholas.HikvisionLinux"},
            )
            self.assertEqual(updated, [vdf_file.resolve()])

            parsed = parse_shortcuts_vdf(vdf_file.read_bytes())
            self.assertEqual(len(parsed), 2)
            self.assertEqual(parsed[0]["AppName"], "FooApp")
            self.assertEqual(parsed[1]["AppName"], "Hikvision Camera Viewer")
            self.assertEqual(parsed[1]["Exe"], '"/usr/bin/flatpak"')
            self.assertIn(
                "run io.github.rwnicholas.HikvisionLinux --steam-deck",
                str(parsed[1]["LaunchOptions"]),
            )

            # Re-registering updates in place instead of duplicating
            register_steam_shortcut(
                home_dir=home,
                env={"FLATPAK_ID": "io.github.rwnicholas.HikvisionLinux"},
            )
            parsed_again = parse_shortcuts_vdf(vdf_file.read_bytes())
            self.assertEqual(len(parsed_again), 2)

            # Also supports an explicit steam_dir path (e.g. chosen via portal file dialog in Flatpak)
            explicit_updated = register_steam_shortcut(
                steam_dir=home / ".local/share/Steam",
                env={"FLATPAK_ID": "io.github.rwnicholas.HikvisionLinux"},
            )
            self.assertEqual(explicit_updated, [vdf_file.resolve()])

    def test_gamepad_event_decoder_maps_buttons_and_axes(self):
        reader = LinuxGamepadReader()
        # Button A pressed (type=1, number=0, value=1)
        btn_a = struct.pack("IhBB", 100, 1, 0x01, LinuxGamepadReader.BTN_A)
        self.assertEqual(reader.decode_event(btn_a), "activate")

        # Button Y pressed -> open recordings
        btn_y = struct.pack("IhBB", 101, 1, 0x01, LinuxGamepadReader.BTN_Y)
        self.assertEqual(reader.decode_event(btn_y), "recordings")

        # Init event is ignored
        init_ev = struct.pack("IhBB", 102, 1, 0x81, LinuxGamepadReader.BTN_A)
        self.assertIsNone(reader.decode_event(init_ev))

        # D-Pad hat horizontal axis 6 right (+32767)
        axis_right = struct.pack("IhBB", 103, 32767, 0x02, 6)
        self.assertEqual(reader.decode_event(axis_right), "dpad_right")

    def test_trigger_steam_osk_uses_steam_protocol(self):
        opened = []
        self.assertTrue(
            trigger_steam_osk(open_fn=lambda url: (opened.append(url), True)[1])
        )
        self.assertEqual(opened, ["steam://open/keyboard"])

    @unittest.skipIf(QApplication is None, "PySide6 is required for UI gamepad tests")
    def test_main_window_and_recordings_dialog_handle_gamepad_navigation(self):
        with patch.object(MainWindow, "_start_threads"), patch.object(
            MainWindow, "_restore_viewer_state"
        ):
            window = MainWindow(steam_deck_mode=True, enable_gamepad=False)

        self.assertTrue(window.steam_deck_mode)
        self.assertEqual(window.active_mode, "ALL")
        self.assertEqual(window.gamepad_selected_channel, 1)

        # D-Pad right moves highlight to Camera 2
        window.handle_gamepad_action("dpad_right")
        self.assertEqual(window.gamepad_selected_channel, 2)
        self.assertTrue(window.tiles[2].is_gamepad_selected)

        # Button A zooms into Camera 2
        window.handle_gamepad_action("activate")
        self.assertEqual(window.active_mode, "2")

        # R1 bumper switches to Camera 3 while zoomed in
        window.handle_gamepad_action("next_camera")
        self.assertEqual(window.active_mode, "3")

        # Button B returns to Grid View
        window.handle_gamepad_action("back")
        self.assertEqual(window.active_mode, "ALL")

        # RecordingsDialog gamepad controls: L1/R1 change speed, D-Pad Left/Right seek
        dialog = RecordingsDialog(
            DVRConfig(channels=[1, 2]),
            Path(tempfile.gettempdir()),
            default_channel=1,
        )
        self.assertEqual(dialog.selected_playback_speed(), 1.0)
        dialog.handle_gamepad_action("next_camera")
        self.assertEqual(dialog.selected_playback_speed(), 2.0)
        dialog.handle_gamepad_action("prev_camera")
        self.assertEqual(dialog.selected_playback_speed(), 1.0)


if __name__ == "__main__":
    unittest.main()
