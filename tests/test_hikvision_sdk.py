import os
import platform
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import hikvision_sdk
from hikvision_sdk import (
    HikvisionRecording,
    HikvisionSDKError,
    build_hikvision_helper,
    discover_hikvision_sdk,
    list_hikvision_recordings,
)


def _write_elf(path: Path, architecture: tuple[int, int]):
    header = bytearray(20)
    header[:4] = b"\x7fELF"
    header[4] = architecture[0]
    header[5] = 1
    header[6] = 1
    struct.pack_into("<H", header, 18, architecture[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header)


def _sdk_fixture(root: Path, architecture: tuple[int, int]):
    library_directory = root / "lib"
    for name in (
        "libhcnetsdk.so",
        "libPlayCtrl.so",
        "libhpr.so",
        "libHCCore.so",
        "libAudioRender.so",
    ):
        _write_elf(library_directory / name, architecture)
    _write_elf(library_directory / "HCNetSDKCom/libHCPreview.so", architecture)
    helper = root / "app/hikvision_stream_helper"
    _write_elf(helper, architecture)
    helper.chmod(0o755)
    return helper


class HikvisionSDKDiscoveryTests(unittest.TestCase):
    def test_build_helper_uses_selected_sdk_and_verifies_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "vendor sdk"
            root.mkdir()
            source = Path(directory) / "source"
            source.mkdir()
            installation = object()
            with patch.object(
                hikvision_sdk, "_helper_source_directory", return_value=source
            ), patch.object(
                hikvision_sdk.subprocess,
                "run",
                return_value=type(
                    "Result",
                    (),
                    {"returncode": 0, "stderr": "", "stdout": ""},
                )(),
            ) as run, patch.object(
                hikvision_sdk,
                "discover_hikvision_sdk",
                return_value=installation,
            ) as discover:
                result = build_hikvision_helper(root)

            self.assertIs(result, installation)
            self.assertEqual(
                run.call_args.args[0],
                [
                    "make",
                    "-B",
                    "-C",
                    str(source),
                    "helper",
                    f"SDK_ROOT={root.resolve()}",
                ],
            )
            discover.assert_called_once_with(root.resolve())

    def test_helper_build_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(
                hikvision_sdk, "_helper_source_directory", return_value=root
            ), patch.object(
                hikvision_sdk.subprocess,
                "run",
                return_value=type(
                    "Result",
                    (),
                    {
                        "returncode": 2,
                        "stderr": "missing PlayCtrl headers",
                        "stdout": "",
                    },
                )(),
            ):
                with self.assertRaisesRegex(
                    HikvisionSDKError,
                    "missing PlayCtrl headers",
                ):
                    build_hikvision_helper(root)

    def test_reports_missing_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            with patch.dict(os.environ, {"HIKVISION_SDK_DIR": ""}):
                with self.assertRaisesRegex(HikvisionSDKError, "not found"):
                    discover_hikvision_sdk(missing)

    def test_checks_architecture_and_local_helper(self):
        host = hikvision_sdk._ELF_HOSTS[platform.machine().lower()]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sdk"
            helper = _sdk_fixture(root, host)
            with patch.dict(
                os.environ,
                {"HIKVISION_HELPER_PATH": "", "HIKVISION_SDK_DIR": ""},
            ), patch.object(
                hikvision_sdk.Path, "home", return_value=Path(directory)
            ), patch.object(hikvision_sdk, "_verify_helper") as verify:
                installation = discover_hikvision_sdk(root)
            self.assertEqual(installation.root, root.resolve())
            self.assertEqual(installation.stream_helper, helper.resolve())
            verify.assert_called_once_with(
                helper.resolve(),
                (root / "lib").resolve(),
                (root / "lib/HCNetSDKCom").resolve(),
            )

    def test_prefers_the_helper_installed_by_the_documented_make_target(self):
        host = hikvision_sdk._ELF_HOSTS[platform.machine().lower()]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / "sdk"
            _sdk_fixture(root, host)
            local_helper = (
                home / ".local/lib/hiklens/hikvision_stream_helper"
            )
            _write_elf(local_helper, host)
            local_helper.chmod(0o755)
            with patch.dict(
                os.environ,
                {
                    "HIKVISION_HELPER_PATH": "",
                    "HIKVISION_SDK_DIR": "",
                },
            ), patch.object(hikvision_sdk.Path, "home", return_value=home), patch.object(
                hikvision_sdk, "_verify_helper"
            ) as verify:
                installation = discover_hikvision_sdk(root)
            self.assertEqual(installation.stream_helper, local_helper.resolve())
            verify.assert_called_once_with(
                local_helper.resolve(),
                (root / "lib").resolve(),
                (root / "lib/HCNetSDKCom").resolve(),
            )

    def test_build_helper_uses_packaged_helper_when_make_is_unavailable(self):
        host = hikvision_sdk._ELF_HOSTS[platform.machine().lower()]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / "sdk"
            helper = _sdk_fixture(root, host)
            helper.unlink()
            packaged_helper = home / "flatpak/hikvision_stream_helper"
            _write_elf(packaged_helper, host)
            packaged_helper.chmod(0o755)
            with patch.dict(
                os.environ,
                {"HIKVISION_HELPER_PATH": "", "HIKVISION_SDK_DIR": ""},
            ), patch.object(
                hikvision_sdk.Path, "home", return_value=home
            ), patch.object(
                hikvision_sdk, "_helper_source_directory", return_value=home
            ), patch.object(
                hikvision_sdk,
                "_packaged_helpers",
                return_value=[packaged_helper],
            ), patch.object(
                hikvision_sdk.subprocess,
                "run",
                side_effect=FileNotFoundError("make not found"),
            ), patch.object(
                hikvision_sdk, "_verify_helper"
            ) as verify:
                installation = build_hikvision_helper(root)

            self.assertEqual(
                installation.stream_helper,
                packaged_helper.resolve(),
            )
            verify.assert_called_once_with(
                packaged_helper.resolve(),
                (root / "lib").resolve(),
                (root / "lib/HCNetSDKCom").resolve(),
            )

    def test_verify_helper_passes_sdk_library_paths_in_ld_library_path(self):
        host = hikvision_sdk._ELF_HOSTS[platform.machine().lower()]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sdk"
            helper = _sdk_fixture(root, host)
            hikvision_sdk._HELPER_CHECK_CACHE.clear()
            with patch.object(
                hikvision_sdk.subprocess,
                "run",
                return_value=type(
                    "Result",
                    (),
                    {"returncode": 0, "stderr": "", "stdout": ""},
                )(),
            ) as run:
                hikvision_sdk._verify_helper(
                    helper,
                    root / "lib",
                    root / "lib/HCNetSDKCom",
                )

            env = run.call_args.kwargs["env"]
            self.assertTrue(
                env["LD_LIBRARY_PATH"].startswith(
                    f"{root / 'lib'}:{root / 'lib/HCNetSDKCom'}"
                )
            )

    def test_rejects_mismatched_library_architecture(self):
        host = hikvision_sdk._ELF_HOSTS[platform.machine().lower()]
        other = (1, 3) if host[0] == 2 else (2, 62)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sdk"
            _sdk_fixture(root, host)
            _write_elf(root / "lib/libPlayCtrl.so", other)
            with patch.dict(
                os.environ,
                {"HIKVISION_HELPER_PATH": "", "HIKVISION_SDK_DIR": ""},
            ):
                with self.assertRaisesRegex(HikvisionSDKError, "Architecture mismatch"):
                    discover_hikvision_sdk(root)

    def test_reports_missing_required_shared_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sdk"
            (root / "lib/HCNetSDKCom").mkdir(parents=True)
            with patch.dict(
                os.environ,
                {"HIKVISION_HELPER_PATH": "", "HIKVISION_SDK_DIR": ""},
            ):
                with self.assertRaisesRegex(
                    HikvisionSDKError, "missing required libraries/components"
                ):
                    discover_hikvision_sdk(root)

    def test_list_recordings_parses_helper_json_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sdk"
            installation = hikvision_sdk.HikvisionSDKInstallation(
                root=root,
                library_directory=root / "lib",
                component_directory=root / "lib/HCNetSDKCom",
                stream_helper=root / "app/hikvision_stream_helper",
            )
            config = type(
                "Config",
                (),
                {
                    "ip": "192.0.2.10",
                    "sdk_port": 8000,
                    "username": "admin",
                    "password": "secret",
                    "sdk_directory": str(root),
                },
            )()
            stdout = (
                "HIKVISION_RECORDING "
                '{"name":"ch01_0001","channel":1,'
                '"start_time":"2026-11-18 10:00:00",'
                '"end_time":"2026-11-18 10:15:00",'
                '"size_bytes":10485760,"file_type":1,'
                '"locked":false,"stream_type":0}\n'
            )
            with patch.object(
                hikvision_sdk,
                "discover_hikvision_sdk",
                return_value=installation,
            ), patch.object(
                hikvision_sdk.subprocess,
                "run",
                return_value=type(
                    "Result",
                    (),
                    {"returncode": 0, "stdout": stdout, "stderr": ""},
                )(),
            ) as run:
                recordings = list_hikvision_recordings(
                    config,
                    channel=1,
                    start_time="2026-11-18 09:00:00",
                    end_time="2026-11-18 11:00:00",
                )

            self.assertEqual(
                recordings,
                [
                    HikvisionRecording(
                        name="ch01_0001",
                        channel=1,
                        start_time="2026-11-18 10:00:00",
                        end_time="2026-11-18 10:15:00",
                        size_bytes=10485760,
                        file_type=1,
                        locked=False,
                        stream_type=0,
                    )
                ],
            )
            self.assertEqual(
                run.call_args.args[0],
                [str(installation.stream_helper), "--list-recordings"],
            )
            env = run.call_args.kwargs["env"]
            self.assertEqual(env["HIKVISION_CHANNEL"], "1")
            self.assertEqual(env["HIKVISION_START_TIME"], "2026-11-18 09:00:00")
            self.assertEqual(env["HIKVISION_END_TIME"], "2026-11-18 11:00:00")

    def test_list_recordings_rebuilds_outdated_helper_automatically(self):
        host = hikvision_sdk._ELF_HOSTS[platform.machine().lower()]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "sdk"
            outdated_helper = _sdk_fixture(root, host)
            outdated_helper.write_bytes(outdated_helper.read_bytes() + b"\0" * 100)
            updated_helper = root / "app/hikvision_stream_helper_v2"
            _write_elf(updated_helper, host)
            updated_helper.write_bytes(
                updated_helper.read_bytes()
                + b"\0" * 100
                + b"--list-recordings\0--playback\0HIKVISION_PLAYBACK_POS\0HIKVISION_PLAYBACK_SPEED_STEPS\0"
            )
            updated_helper.chmod(0o755)
            old_install = hikvision_sdk.HikvisionSDKInstallation(
                root=root,
                library_directory=root / "lib",
                component_directory=root / "lib/HCNetSDKCom",
                stream_helper=outdated_helper,
            )
            new_install = hikvision_sdk.HikvisionSDKInstallation(
                root=root,
                library_directory=root / "lib",
                component_directory=root / "lib/HCNetSDKCom",
                stream_helper=updated_helper,
            )
            config = type(
                "Config",
                (),
                {
                    "ip": "192.0.2.10",
                    "sdk_port": 8000,
                    "username": "admin",
                    "password": "secret",
                    "sdk_directory": str(root),
                },
            )()
            with patch.object(
                hikvision_sdk,
                "discover_hikvision_sdk",
                return_value=old_install,
            ), patch.object(
                hikvision_sdk,
                "build_hikvision_helper",
                return_value=new_install,
            ) as rebuild, patch.object(
                hikvision_sdk.subprocess,
                "run",
                return_value=type(
                    "Result",
                    (),
                    {"returncode": 0, "stdout": "", "stderr": "Cannot load libcuda.so.1\n"},
                )(),
            ) as run:
                recordings = list_hikvision_recordings(
                    config,
                    channel=1,
                    start_time="2026-11-18 09:00:00",
                    end_time="2026-11-18 11:00:00",
                )

            self.assertEqual(recordings, [])
            rebuild.assert_called_once_with(root)
            self.assertEqual(
                run.call_args.args[0],
                [str(updated_helper), "--list-recordings"],
            )


if __name__ == "__main__":
    unittest.main()
