"""Runtime discovery and compatibility checks for the optional Hikvision SDK."""

from __future__ import annotations

import os
import platform
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
_HELPER_CHECK_CACHE: dict[tuple[str, int, int], str | None] = {}
HIKVISION_SDK_DOWNLOAD_URL = (
    "https://www.hikvision.com/en/support/tools/hitools/clf4633a00e385d6ea/"
)


def _helper_source_directory() -> Path:
    candidates = [
        Path(__file__).resolve().parent / "hikvision-sdk",
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
        raise HikvisionSDKError(
            "Cannot build the Hikvision helper because 'make' is not installed."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HikvisionSDKError(
            "Building the Hikvision helper timed out after 180 seconds."
        ) from exc
    except OSError as exc:
        raise HikvisionSDKError(f"Could not run make to build the helper: {exc}") from exc

    if result.returncode:
        details = (result.stderr or result.stdout).strip()
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


def _verify_helper(helper: Path) -> None:
    stat = helper.stat()
    cache_key = (str(helper), stat.st_mtime_ns, stat.st_size)
    with _HELPER_CHECK_LOCK:
        if cache_key in _HELPER_CHECK_CACHE:
            error = _HELPER_CHECK_CACHE[cache_key]
            if error:
                raise HikvisionSDKError(error)
            return

        try:
            helper_environment = os.environ.copy()
            helper_environment["EGL_PLATFORM"] = "surfaceless"
            helper_environment.pop("DISPLAY", None)
            helper_environment.pop("WAYLAND_DISPLAY", None)
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
            detail = (result.stderr or result.stdout).strip()
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


def _candidate_helpers(root: Path):
    configured_helper = os.environ.get("HIKVISION_HELPER_PATH", "").strip()
    if configured_helper:
        yield Path(configured_helper).expanduser()
    yield Path.home() / ".local/lib/hikvision-camera-viewer/hikvision_stream_helper"
    yield root / "app" / "hikvision_stream_helper"


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

    helper = next(
        (
            candidate.resolve()
            for candidate in _candidate_helpers(root)
            if candidate.is_file() and os.access(candidate, os.X_OK)
        ),
        None,
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
    _verify_helper(helper)

    return HikvisionSDKInstallation(
        root=root,
        library_directory=library_directory,
        component_directory=component_directory,
        stream_helper=helper,
    )
