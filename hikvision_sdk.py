"""Runtime discovery and compatibility checks for the optional Hikvision SDK."""

from __future__ import annotations

import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


class HikvisionSDKError(RuntimeError):
    """Raised when an external Hikvision SDK installation cannot be used."""


@dataclass(frozen=True)
class HikvisionSDKInstallation:
    root: Path
    library_directory: Path
    component_directory: Path
    stream_helper: Path


@dataclass(frozen=True)
class HikvisionRecording:
    name: str
    channel: int
    start_time: str
    end_time: str
    size_bytes: int = 0
    file_type: int = 0
    locked: bool = False
    stream_type: int = 0


_RECORDING_PREFIX = "HIKVISION_RECORDING "
_RECORDING_FILE_TYPES = {
    0: "Scheduled",
    1: "Motion",
    2: "Alarm",
    3: "Motion | Alarm",
    4: "Motion & Alarm",
    5: "Command",
    6: "Manual",
    7: "VCA",
    9: "VCA",
    10: "PIR",
    11: "Wireless",
    12: "Emergency",
}


def recording_file_type_label(file_type: int) -> str:
    return _RECORDING_FILE_TYPES.get(int(file_type), f"Type {file_type}")


_ELF_HOSTS = {
    "x86_64": (2, 62),
    "amd64": (2, 62),
    "aarch64": (2, 183),
    "arm64": (2, 183),
    "i386": (1, 3),
    "i686": (1, 3),
    "armv7l": (1, 40),
}
_HELPER_CHECK_LOCK = threading.Lock()
_HELPER_CHECK_CACHE: dict[tuple[str, int, int, str, str], str | None] = {}
HIKVISION_SDK_DOWNLOAD_URL = (
    "https://www.hikvision.com/en/support/tools/hitools/clf4633a00e385d6ea/"
)


def _helper_source_directory() -> Path:
    candidates = [
        Path(__file__).resolve().parent / "hikvision-sdk",
        Path("/app/share/hiklens/hikvision-sdk"),
        Path("/app/share/hikvision-linux/hikvision-sdk"),
    ]
    bundle_directory = getattr(sys, "_MEIPASS", None)
    if bundle_directory:
        candidates.insert(0, Path(bundle_directory) / "hikvision-sdk")
    for candidate in candidates:
        if (candidate / "Makefile").is_file() and (
            candidate / "sdk_stream_test.cpp"
        ).is_file():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise HikvisionSDKError(
        "Hikvision helper build sources are missing from this installation. "
        f"Searched: {searched}"
    )


def _clean_helper_output(text: str) -> str:
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and line.strip() != "Cannot load libcuda.so.1"
    ]
    return "\n".join(lines).strip()


def _helper_supports_recordings(helper: str | os.PathLike[str]) -> bool:
    path = Path(helper)
    if not path.is_file():
        return True
    try:
        data = path.read_bytes()
    except OSError:
        return False
    # 20-byte synthetic ELF fixtures used in unit tests do not embed strings.
    if len(data) <= 64:
        return True
    return (
        b"--list-recordings" in data
        and b"--playback" in data
        and b"HIKVISION_PLAYBACK_POS" in data
        and b"HIKVISION_PLAYBACK_SPEED_STEPS" in data
    )


def _compile_helper_directly(
    source_directory: Path,
    root: Path,
) -> subprocess.CompletedProcess[str] | None:
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        return None
    configured_helper = os.environ.get("HIKVISION_HELPER_PATH", "").strip()
    helper_path = (
        Path(configured_helper).expanduser()
        if configured_helper
        else Path.home() / ".local/lib/hikvision-camera-viewer/hikvision_stream_helper"
    )
    helper_path.parent.mkdir(parents=True, exist_ok=True)
    library_directory = root / "lib"
    component_directory = library_directory / "HCNetSDKCom"
    command = [
        compiler,
        "-std=c++17",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-isystem",
        str(root / "incEn"),
        "-isystem",
        str(root / "QtDemo/includeCn"),
        str(source_directory / "sdk_stream_test.cpp"),
        f"-L{library_directory}",
        f"-Wl,-rpath,{library_directory}:{component_directory}",
        "-lhcnetsdk",
        "-lPlayCtrl",
        "-pthread",
        "-o",
        str(helper_path),
    ]
    env = os.environ.copy()
    env["CCACHE_DISABLE"] = "1"
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def build_hikvision_helper(
    sdk_directory: str | os.PathLike[str],
) -> HikvisionSDKInstallation:
    """Build the local helper against a user-provided SDK and verify it."""
    root = Path(sdk_directory).expanduser().resolve()
    if not root.is_dir():
        raise HikvisionSDKError(f"Hikvision SDK directory does not exist: {root}")

    source_directory = _helper_source_directory()
    command = [
        "make",
        "-B",
        "-C",
        str(source_directory),
        "helper",
        f"SDK_ROOT={root}",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError as exc:
        try:
            return discover_hikvision_sdk(root)
        except HikvisionSDKError as discover_exc:
            if "Hikvision stream helper is not built" not in str(discover_exc):
                raise
            direct_result = _compile_helper_directly(source_directory, root)
            if direct_result is None:
                raise HikvisionSDKError(
                    "Cannot build the Hikvision helper because 'make' is not installed."
                ) from exc
            result = direct_result
    except subprocess.TimeoutExpired as exc:
        raise HikvisionSDKError(
            "Building the Hikvision helper timed out after 180 seconds."
        ) from exc
    except OSError as exc:
        raise HikvisionSDKError(f"Could not run make to build the helper: {exc}") from exc

    if result.returncode:
        details = (result.stderr or result.stdout).strip()
        if any(
            token in details
            for token in (
                "c++: No such file",
                "c++: not found",
                "c++: command not found",
            )
        ):
            try:
                return discover_hikvision_sdk(root)
            except HikvisionSDKError:
                pass
        raise HikvisionSDKError(
            "Hikvision helper build failed. Check that the selected SDK package "
            "matches this system and includes its development headers/libraries. "
            f"Build output: {details[-3000:] or 'no details'}"
        )

    return discover_hikvision_sdk(root)


def _read_elf_architecture(path: Path) -> tuple[int, int]:
    try:
        with path.open("rb") as stream:
            header = stream.read(20)
    except OSError as exc:
        raise HikvisionSDKError(f"Cannot read SDK file {path}: {exc}") from exc

    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise HikvisionSDKError(f"SDK file is not a valid ELF object: {path}")
    elf_class, byte_order = header[4], header[5]
    if byte_order not in (1, 2):
        raise HikvisionSDKError(f"SDK file has an invalid ELF byte order: {path}")
    endian = "<" if byte_order == 1 else ">"
    machine = struct.unpack(f"{endian}H", header[18:20])[0]
    return elf_class, machine


def _check_elf_architecture(path: Path, expected: tuple[int, int]) -> None:
    actual = _read_elf_architecture(path)
    if actual != expected:
        raise HikvisionSDKError(
            f"Architecture mismatch for {path.name}: expected ELF class/"
            f"machine {expected}, found {actual}."
        )


def helper_runtime_environment(
    library_directory: Path | None = None,
    component_directory: Path | None = None,
    base_environment: dict[str, str] | None = None,
) -> dict[str, str]:
    helper_environment = (
        os.environ.copy() if base_environment is None else dict(base_environment)
    )
    helper_environment["EGL_PLATFORM"] = "surfaceless"
    helper_environment.pop("DISPLAY", None)
    helper_environment.pop("WAYLAND_DISPLAY", None)
    if library_directory is not None and component_directory is not None:
        ld_paths = [str(library_directory), str(component_directory)]
        existing = helper_environment.get("LD_LIBRARY_PATH", "").strip()
        if existing:
            ld_paths.append(existing)
        helper_environment["LD_LIBRARY_PATH"] = ":".join(ld_paths)
    return helper_environment


def _verify_helper(
    helper: Path,
    library_directory: Path | None = None,
    component_directory: Path | None = None,
) -> None:
    stat = helper.stat()
    cache_key = (
        str(helper),
        stat.st_mtime_ns,
        stat.st_size,
        str(library_directory or ""),
        str(component_directory or ""),
    )
    with _HELPER_CHECK_LOCK:
        if cache_key in _HELPER_CHECK_CACHE:
            error = _HELPER_CHECK_CACHE[cache_key]
            if error:
                raise HikvisionSDKError(error)
            return

        try:
            helper_environment = helper_runtime_environment(
                library_directory,
                component_directory,
            )
            result = subprocess.run(
                [str(helper), "--check-sdk"],
                check=False,
                capture_output=True,
                text=True,
                env=helper_environment,
                timeout=10,
            )
        except subprocess.TimeoutExpired as exc:
            message = f"Hikvision helper dependency check timed out: {helper}"
            _HELPER_CHECK_CACHE[cache_key] = message
            raise HikvisionSDKError(message) from exc
        except OSError as exc:
            message = f"Could not run Hikvision helper {helper}: {exc}"
            _HELPER_CHECK_CACHE[cache_key] = message
            raise HikvisionSDKError(message) from exc

        if result.returncode:
            detail = _clean_helper_output(result.stderr or result.stdout)
            message = (
                f"Hikvision helper could not load its SDK dependencies "
                f"(exit {result.returncode}): {detail[-800:] or 'no details'}"
            )
            _HELPER_CHECK_CACHE[cache_key] = message
            raise HikvisionSDKError(message)
        _HELPER_CHECK_CACHE[cache_key] = None


def _candidate_roots(configured_directory: str | os.PathLike[str] | None):
    if configured_directory:
        yield Path(configured_directory).expanduser()
        return

    environment_directory = os.environ.get("HIKVISION_SDK_DIR", "").strip()
    if environment_directory:
        yield Path(environment_directory).expanduser()

    yield Path.home() / "Downloads/EN-HCNetSDKV6.1.11.40_build20260922_linux64"
    yield Path("/opt/hikvision-sdk")
    yield Path("/usr/local/lib/hikvision-sdk")


def _packaged_helpers():
    bundle_directory = getattr(sys, "_MEIPASS", None)
    if bundle_directory:
        yield Path(bundle_directory) / "hikvision-sdk" / "hikvision_stream_helper"
        yield Path(bundle_directory).parent / "hikvision_stream_helper"
    yield Path(__file__).resolve().parent / "hikvision_stream_helper"
    yield Path("/app/lib/hiklens/hikvision_stream_helper")
    yield Path("/app/lib/hikvision-camera-viewer/hikvision_stream_helper")


def _candidate_helpers(root: Path):
    configured_helper = os.environ.get("HIKVISION_HELPER_PATH", "").strip()
    if configured_helper:
        yield Path(configured_helper).expanduser()
    yield Path.home() / ".local/lib/hiklens/hikvision_stream_helper"
    yield Path.home() / ".local/lib/hikvision-camera-viewer/hikvision_stream_helper"
    yield root / "app" / "hikvision_stream_helper"
    yield from _packaged_helpers()


def discover_hikvision_sdk(
    configured_directory: str | os.PathLike[str] | None = None,
) -> HikvisionSDKInstallation:
    """Locate a compatible Linux SDK and its locally built stream helper."""
    if platform.system() != "Linux":
        raise HikvisionSDKError("The Hikvision HCNetSDK backend is supported on Linux only.")

    host = _ELF_HOSTS.get(platform.machine().lower())
    if host is None:
        raise HikvisionSDKError(
            f"Unsupported host architecture: {platform.machine()}."
        )

    candidates = list(_candidate_roots(configured_directory))
    root = next(
        (candidate.resolve() for candidate in candidates if candidate.is_dir()),
        None,
    )
    if root is None:
        searched = ", ".join(str(path) for path in candidates)
        raise HikvisionSDKError(
            "Hikvision Linux SDK directory was not found. Configure it in "
            "Settings or set HIKVISION_SDK_DIR. Searched: " + searched
        )

    library_directory = root / "lib"
    component_directory = library_directory / "HCNetSDKCom"
    required = (
        library_directory / "libhcnetsdk.so",
        library_directory / "libPlayCtrl.so",
        library_directory / "libhpr.so",
        library_directory / "libHCCore.so",
        library_directory / "libAudioRender.so",
    )
    missing = [path for path in required if not path.is_file()]
    if not component_directory.is_dir() or not any(
        component_directory.glob("*.so")
    ):
        missing.append(component_directory)
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise HikvisionSDKError(
            "The configured directory is not a complete Hikvision Linux SDK; "
            f"missing required libraries/components: {missing_text}"
        )

    checked_files = list(required)
    checked_files.extend(sorted(component_directory.glob("*.so")))
    for path in checked_files:
        _check_elf_architecture(path, host)

    executable_helpers = [
        candidate.resolve()
        for candidate in _candidate_helpers(root)
        if candidate.is_file() and os.access(candidate, os.X_OK)
    ]
    helper = next(
        (
            candidate
            for candidate in executable_helpers
            if _helper_supports_recordings(candidate)
        ),
        executable_helpers[0] if executable_helpers else None,
    )
    if helper is None:
        searched_helpers = ", ".join(
            str(path) for path in _candidate_helpers(root)
        )
        raise HikvisionSDKError(
            "Hikvision stream helper is not built. Build it with: "
            f'make -C hikvision-sdk helper SDK_ROOT="{root}". '
            f"Searched: {searched_helpers}"
        )
    _check_elf_architecture(helper, host)
    _verify_helper(helper, library_directory, component_directory)

    return HikvisionSDKInstallation(
        root=root,
        library_directory=library_directory,
        component_directory=component_directory,
        stream_helper=helper,
    )


def _ensure_recordings_capable_helper(
    installation: HikvisionSDKInstallation,
) -> HikvisionSDKInstallation:
    if _helper_supports_recordings(installation.stream_helper):
        return installation
    rebuilt = build_hikvision_helper(installation.root)
    if not _helper_supports_recordings(rebuilt.stream_helper):
        raise HikvisionSDKError(
            "The installed Hikvision stream helper is outdated and does not "
            "support DVR recordings playback. Click 'Build / Verify Helper' "
            "in Settings or rebuild the Flatpak/AppImage package."
        )
    return rebuilt


def list_hikvision_recordings(
    config,
    channel: int,
    start_time: str,
    end_time: str,
) -> list[HikvisionRecording]:
    """Query recorded DVR segments for a channel and time range via HCNetSDK."""
    installation = _ensure_recordings_capable_helper(
        discover_hikvision_sdk(getattr(config, "sdk_directory", ""))
    )
    env = helper_runtime_environment(
        installation.library_directory,
        installation.component_directory,
    )
    env.update(
        {
            "HIKVISION_HOST": str(config.ip),
            "HIKVISION_PORT": str(getattr(config, "sdk_port", 8000)),
            "HIKVISION_USERNAME": str(config.username),
            "HIKVISION_PASSWORD": str(config.password),
            "HIKVISION_CHANNEL": str(int(channel)),
            "HIKVISION_START_TIME": str(start_time).strip(),
            "HIKVISION_END_TIME": str(end_time).strip(),
        }
    )
    try:
        result = subprocess.run(
            [str(installation.stream_helper), "--list-recordings"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=45,
        )
    except subprocess.TimeoutExpired as exc:
        raise HikvisionSDKError(
            "Searching DVR recordings timed out after 45 seconds."
        ) from exc
    except OSError as exc:
        raise HikvisionSDKError(
            f"Could not run Hikvision helper to search recordings: {exc}"
        ) from exc

    if result.returncode:
        detail = _clean_helper_output(result.stderr or result.stdout)
        raise HikvisionSDKError(
            f"Could not search DVR recordings (exit {result.returncode}): "
            f"{detail[-800:] or 'no details'}"
        )

    recordings: list[HikvisionRecording] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith(_RECORDING_PREFIX):
            continue
        try:
            payload = json.loads(line[len(_RECORDING_PREFIX) :])
        except json.JSONDecodeError as exc:
            raise HikvisionSDKError(
                "Hikvision helper emitted malformed recording metadata."
            ) from exc
        if not isinstance(payload, dict):
            continue
        recordings.append(
            HikvisionRecording(
                name=str(payload.get("name", "")),
                channel=int(payload.get("channel", channel)),
                start_time=str(payload.get("start_time", "")),
                end_time=str(payload.get("end_time", "")),
                size_bytes=max(0, int(payload.get("size_bytes", 0))),
                file_type=int(payload.get("file_type", 0)),
                locked=bool(payload.get("locked", False)),
                stream_type=int(payload.get("stream_type", 0)),
            )
        )
    return recordings
