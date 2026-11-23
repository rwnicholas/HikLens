"""Steam Deck hardware detection, Steam Input / Linux gamepad polling, and Non-Steam shortcut integration."""

from __future__ import annotations

import binascii
import os
from pathlib import Path
import struct
from typing import Callable

try:
    from PySide6.QtCore import QThread, Signal
except ImportError:
    import threading

    class Signal:  # type: ignore[no-redef]
        def __init__(self, *types):
            del types

    class QThread(threading.Thread):  # type: ignore[no-redef]
        def __init__(self, parent=None):
            super().__init__(daemon=True)
            self.parent = parent

        def wait(self, _ms=None):
            if self.is_alive():
                self.join(timeout=1.5)


STEAM_DECK_WIDTH = 1280
STEAM_DECK_HEIGHT = 800

_DMI_PATHS = (
    Path("/sys/devices/virtual/dmi/id/product_name"),
    Path("/sys/devices/virtual/dmi/id/board_name"),
)
_STEAM_DECK_PRODUCTS = {"jupiter", "galileo"}

# Linux /dev/input/js* event constants
_JS_EVENT_BUTTON = 0x01
_JS_EVENT_AXIS = 0x02
_JS_EVENT_INIT = 0x80
_JS_STRUCT = struct.Struct("IhBB")


def is_steam_deck_hardware(
    env: dict[str, str] | None = None,
    dmi_paths: tuple[Path, ...] = _DMI_PATHS,
) -> bool:
    """Return True when running on a Steam Deck (LCD 'Jupiter' or OLED 'Galileo') or when forced."""
    environment = os.environ if env is None else env
    forced = environment.get("HIKVISION_STEAM_DECK", "").strip().lower()
    if forced in {"1", "true", "yes", "on"}:
        return True
    if forced in {"0", "false", "no", "off"}:
        return False

    if environment.get("SteamDeck", "").strip() == "1":
        return True
    if environment.get("STEAM_DECK", "").strip() == "1":
        return True

    for dmi_path in dmi_paths:
        try:
            value = dmi_path.read_text(encoding="utf-8", errors="ignore").strip().lower()
        except OSError:
            continue
        if any(token in value for token in _STEAM_DECK_PRODUCTS):
            return True
    return False


def is_steam_gaming_mode(env: dict[str, str] | None = None) -> bool:
    """Return True when running inside Steam Gaming Mode / Gamescope."""
    environment = os.environ if env is None else env
    forced = environment.get("HIKVISION_STEAM_GAMING_MODE", "").strip().lower()
    if forced in {"1", "true", "yes", "on"}:
        return True
    if forced in {"0", "false", "no", "off"}:
        return False

    if environment.get("STEAM_GAMEPADUI", "").strip() == "1":
        return True
    if environment.get("GAMESCOPE_WAYLAND_DISPLAY", "").strip():
        return True
    desktop = environment.get("XDG_CURRENT_DESKTOP", "").strip().lower()
    return "gamescope" in desktop


def trigger_steam_osk(open_fn: Callable[[str], bool] | None = None) -> bool:
    """Request the Steam On-Screen Keyboard via the steam://open/keyboard protocol."""
    uri = "steam://open/keyboard"
    if open_fn is not None:
        return bool(open_fn(uri))
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        return bool(QDesktopServices.openUrl(QUrl(uri)))
    except Exception:
        return False


class LinuxGamepadReader(QThread):
    """Background reader for Linux /dev/input/js* gamepad devices (Steam Deck / Xbox / XInput).

    Emits high-level semantic actions so both the live camera viewer and DVR recordings
    playback dialog can be controlled with physical Steam Deck controls.
    """

    action_triggered = Signal(str)
    controller_connected = Signal(str)

    # Standard Linux xpad / Steam Virtual Gamepad button numbers
    BTN_A = 0
    BTN_B = 1
    BTN_X = 2
    BTN_Y = 3
    BTN_LB = 4
    BTN_RB = 5
    BTN_BACK = 6
    BTN_START = 7
    BTN_GUIDE = 8
    BTN_LSTICK = 9
    BTN_RSTICK = 10
    BTN_DPAD_UP = 11
    BTN_DPAD_DOWN = 12
    BTN_DPAD_LEFT = 13
    BTN_DPAD_RIGHT = 14

    _BUTTON_ACTIONS = {
        BTN_A: "activate",
        BTN_B: "back",
        BTN_X: "snapshot",
        BTN_Y: "recordings",
        BTN_LB: "prev_camera",
        BTN_RB: "next_camera",
        BTN_BACK: "toggle_events",
        BTN_START: "pause",
        BTN_LSTICK: "fullscreen",
        BTN_RSTICK: "record",
        BTN_DPAD_UP: "dpad_up",
        BTN_DPAD_DOWN: "dpad_down",
        BTN_DPAD_LEFT: "dpad_left",
        BTN_DPAD_RIGHT: "dpad_right",
    }

    def __init__(self, device_dir: Path = Path("/dev/input"), parent=None):
        super().__init__(parent)
        self.device_dir = Path(device_dir)
        self._running = True
        self._axis_states: dict[int, int] = {}

    def stop(self):
        self._running = False
        self.wait(1500)

    def decode_event(self, event_bytes: bytes) -> str | None:
        """Decode a single 8-byte Linux js_event struct into a semantic action name."""
        if len(event_bytes) != _JS_STRUCT.size:
            return None
        _time_ms, value, event_type, number = _JS_STRUCT.unpack(event_bytes)
        if event_type & _JS_EVENT_INIT:
            return None

        base_type = event_type & ~_JS_EVENT_INIT
        if base_type == _JS_EVENT_BUTTON:
            if value == 1:
                return self._BUTTON_ACTIONS.get(number)
            return None

        if base_type == _JS_EVENT_AXIS:
            # D-Pad hats (axes 6/7) or Left Analog Stick (axes 0/1)
            threshold = 16000
            direction = -1 if value < -threshold else (1 if value > threshold else 0)
            previous = self._axis_states.get(number, 0)
            self._axis_states[number] = direction
            if direction == 0 or direction == previous:
                return None
            if number in (0, 6):
                return "dpad_left" if direction < 0 else "dpad_right"
            if number in (1, 7):
                return "dpad_up" if direction < 0 else "dpad_down"
            # L2 / R2 analog triggers (axes 2/5)
            if number == 2 and direction > 0 and previous <= 0:
                return "seek_back"
            if number == 5 and direction > 0 and previous <= 0:
                return "seek_forward"
        return None

    def _find_joystick_device(self) -> Path | None:
        if not self.device_dir.is_dir():
            return None
        candidates = sorted(self.device_dir.glob("js*"))
        for candidate in candidates:
            if os.access(candidate, os.R_OK):
                return candidate
        return None

    def run(self):
        import select
        import time

        while self._running:
            device = self._find_joystick_device()
            if device is None:
                for _ in range(10):
                    if not self._running:
                        return
                    time.sleep(0.2)
                continue

            fd = -1
            try:
                fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
                self.controller_connected.emit(device.name)
                while self._running:
                    ready, _, _ = select.select([fd], [], [], 0.2)
                    if not ready:
                        continue
                    data = os.read(fd, _JS_STRUCT.size)
                    if not data:
                        break
                    action = self.decode_event(data)
                    if action:
                        self.action_triggered.emit(action)
            except OSError:
                time.sleep(0.5)
            finally:
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass


# ==============================================================================
# Binary VDF (shortcuts.vdf) Parser & Builder for Non-Steam Game Registration
# ==============================================================================
_VDF_TYPE_MAP = 0x00
_VDF_TYPE_STR = 0x01
_VDF_TYPE_INT = 0x02
_VDF_END = 0x08


def compute_steam_shortcut_appid(exe: str, appname: str) -> int:
    """Compute the 32-bit unsigned shortcut AppID used by Steam for Non-Steam shortcuts."""
    raw = (exe + appname).encode("utf-8")
    crc = binascii.crc32(raw) & 0xFFFFFFFF
    return (crc | 0x80000000) & 0xFFFFFFFF


def _read_cstring(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\x00", offset)
    if end < 0:
        raise ValueError("Unterminated string in binary VDF.")
    return data[offset:end].decode("utf-8", errors="replace"), end + 1


def _parse_vdf_map(data: bytes, offset: int = 0) -> tuple[dict[str, object], int]:
    result: dict[str, object] = {}
    length = len(data)
    while offset < length:
        value_type = data[offset]
        offset += 1
        if value_type == _VDF_END:
            return result, offset
        key, offset = _read_cstring(data, offset)
        if value_type == _VDF_TYPE_MAP:
            nested, offset = _parse_vdf_map(data, offset)
            result[key] = nested
        elif value_type == _VDF_TYPE_STR:
            val, offset = _read_cstring(data, offset)
            result[key] = val
        elif value_type == _VDF_TYPE_INT:
            if offset + 4 > length:
                raise ValueError("Truncated int32 in binary VDF.")
            (val,) = struct.unpack_from("<I", data, offset)
            offset += 4
            result[key] = int(val)
        else:
            raise ValueError(f"Unsupported binary VDF field type: 0x{value_type:02x}")
    return result, offset


def _encode_vdf_map(mapping: dict[str, object]) -> bytes:
    out = bytearray()
    for key, value in mapping.items():
        key_bytes = str(key).encode("utf-8") + b"\x00"
        if isinstance(value, dict):
            out.append(_VDF_TYPE_MAP)
            out.extend(key_bytes)
            out.extend(_encode_vdf_map(value))
            out.append(_VDF_END)
        elif isinstance(value, int):
            out.append(_VDF_TYPE_INT)
            out.extend(key_bytes)
            out.extend(struct.pack("<I", value & 0xFFFFFFFF))
        else:
            out.append(_VDF_TYPE_STR)
            out.extend(key_bytes)
            out.extend(str(value).encode("utf-8") + b"\x00")
    return bytes(out)


def parse_shortcuts_vdf(data: bytes) -> list[dict[str, object]]:
    """Parse Steam's binary config/shortcuts.vdf into a list of shortcut dicts."""
    if not data:
        return []
    root, _ = _parse_vdf_map(data, 0)
    shortcuts_map = None
    for key, value in root.items():
        if key.lower() == "shortcuts" and isinstance(value, dict):
            shortcuts_map = value
            break
    if not shortcuts_map:
        return []
    entries: list[tuple[int, dict[str, object]]] = []
    for key, value in shortcuts_map.items():
        if isinstance(value, dict):
            idx = int(key) if str(key).isdigit() else len(entries)
            entries.append((idx, dict(value)))
    entries.sort(key=lambda item: item[0])
    return [entry for _, entry in entries]


def dump_shortcuts_vdf(shortcuts: list[dict[str, object]]) -> bytes:
    """Serialize a list of shortcut dicts into Steam's binary shortcuts.vdf format."""
    numbered = {str(index): entry for index, entry in enumerate(shortcuts)}
    return _encode_vdf_map({"shortcuts": numbered}) + bytes([_VDF_END])


def resolve_steam_launch_command(
    project_root: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, str, str, str]:
    """Determine (exe, start_dir, launch_options, icon_path) for adding this app to Steam."""
    environment = os.environ if env is None else env
    root = (project_root or Path(__file__).resolve().parent).resolve()
    icon_candidates = [
        root / "packaging/flatpak/io.github.rwnicholas.HikLens.svg",
        Path("/app/share/icons/hicolor/scalable/apps/io.github.rwnicholas.HikLens.svg"),
    ]
    icon_path = next((str(p) for p in icon_candidates if p.is_file()), "")

    flatpak_id = environment.get("FLATPAK_ID", "").strip()
    if flatpak_id:
        return (
            '"/usr/bin/flatpak"',
            f'"{Path.home()}"',
            f"run {flatpak_id} --steam-deck",
            flatpak_id,
        )

    appimage = environment.get("APPIMAGE", "").strip()
    if appimage:
        appimage_path = Path(appimage).resolve()
        return (
            f'"{appimage_path}"',
            f'"{appimage_path.parent}"',
            "--steam-deck",
            icon_path,
        )

    start_script = root / "start_viewer.sh"
    if start_script.is_file():
        return (
            f'"{start_script}"',
            f'"{root}"',
            "--steam-deck",
            icon_path,
        )

    viewer_py = root / "cam_viewer.py"
    return (
        '"/usr/bin/python3"',
        f'"{root}"',
        f'"{viewer_py}" --steam-deck',
        icon_path,
    )


def _collect_userdata_config_dirs(userdata: Path, seen: set[Path], config_dirs: list[Path]):
    try:
        children = sorted(userdata.iterdir())
    except OSError:
        return
    for user_dir in children:
        if not user_dir.is_dir() or not user_dir.name.isdigit() or user_dir.name == "0":
            continue
        resolved = (user_dir / "config").resolve()
        if resolved not in seen:
            seen.add(resolved)
            config_dirs.append(resolved)


def find_steam_userdata_dirs(
    home_dir: Path | None = None,
    steam_dir: str | os.PathLike[str] | None = None,
) -> list[Path]:
    """Find Steam userdata/<id>/config directories on Linux / SteamOS."""
    seen: set[Path] = set()
    config_dirs: list[Path] = []

    if steam_dir:
        custom = Path(steam_dir).expanduser()
        if custom.name == "config" and custom.parent.name.isdigit():
            resolved = custom.resolve()
            return [resolved]
        if custom.name == "userdata" and custom.is_dir():
            _collect_userdata_config_dirs(custom, seen, config_dirs)
            if config_dirs:
                return config_dirs
        if (custom / "userdata").is_dir():
            _collect_userdata_config_dirs(custom / "userdata", seen, config_dirs)
            if config_dirs:
                return config_dirs
        if custom.name.isdigit() and custom.parent.name == "userdata":
            return [(custom / "config").resolve()]

    home = (home_dir or Path.home()).expanduser()
    candidate_homes = [home]
    if home_dir is None:
        for deck_home in (Path("/home/deck"), Path("/var/home/deck")):
            if deck_home not in candidate_homes and deck_home.is_dir():
                candidate_homes.append(deck_home)

    steam_roots: list[Path] = []
    env_steam = os.environ.get("STEAM_DIR", "").strip()
    if env_steam:
        steam_roots.append(Path(env_steam).expanduser())
    if home_dir is None:
        xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
        if xdg_data_home:
            steam_roots.append(Path(xdg_data_home).expanduser() / "Steam")

    for base_home in candidate_homes:
        steam_roots.extend(
            [
                base_home / ".local/share/Steam",
                base_home / ".steam/steam",
                base_home / ".steam/root",
                base_home / ".steam/debian-installation",
                base_home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
                base_home / ".var/app/com.valvesoftware.Steam/.steam/steam",
            ]
        )

    for steam_root in steam_roots:
        userdata = steam_root / "userdata"
        if userdata.is_dir():
            _collect_userdata_config_dirs(userdata, seen, config_dirs)
    return config_dirs


def register_steam_shortcut(
    appname: str = "HikLens",
    project_root: Path | None = None,
    home_dir: Path | None = None,
    steam_dir: str | os.PathLike[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[Path]:
    """Add or update HikLens in Steam's Non-Steam shortcuts.vdf for all local Steam users.

    Returns the list of modified shortcuts.vdf paths.
    """
    environment = os.environ if env is None else env
    config_dirs = find_steam_userdata_dirs(
        home_dir=home_dir,
        steam_dir=steam_dir,
    )
    if not config_dirs:
        flatpak_id = environment.get("FLATPAK_ID", "").strip()
        if flatpak_id:
            raise FileNotFoundError(
                "Steam's userdata directory is not accessible inside the Flatpak sandbox.\n\n"
                "Choose your ~/.local/share/Steam directory in the file dialog, or grant access with:\n"
                f"flatpak override --user --filesystem=xdg-data/Steam:rw {flatpak_id}"
            )
        raise FileNotFoundError(
            "No Steam userdata directory was found (~/.local/share/Steam/userdata). "
            "Select your Steam folder (e.g. ~/.local/share/Steam) to register the shortcut."
        )

    exe, start_dir, launch_options, icon_path = resolve_steam_launch_command(
        project_root=project_root,
        env=env,
    )
    appid = compute_steam_shortcut_appid(exe, appname)

    shortcut_entry: dict[str, object] = {
        "appid": appid,
        "AppName": appname,
        "Exe": exe,
        "StartDir": start_dir,
        "icon": icon_path,
        "ShortcutPath": "",
        "LaunchOptions": launch_options,
        "IsHidden": 0,
        "AllowDesktopConfig": 1,
        "AllowOverlay": 1,
        "OpenVR": 0,
        "Devkit": 0,
        "DevkitGameID": "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime": 0,
        "FlatpakAppID": "",
        "tags": {"0": "Security", "1": "CCTV"},
    }

    updated_files: list[Path] = []
    for config_dir in config_dirs:
        config_dir.mkdir(parents=True, exist_ok=True)
        vdf_path = config_dir / "shortcuts.vdf"
        existing: list[dict[str, object]] = []
        if vdf_path.is_file():
            try:
                existing = parse_shortcuts_vdf(vdf_path.read_bytes())
            except Exception:
                existing = []

        replaced = False
        for idx, item in enumerate(existing):
            existing_name = str(item.get("AppName") or item.get("appname") or "").strip()
            if existing_name.lower() == appname.lower():
                existing[idx] = shortcut_entry
                replaced = True
                break
        if not replaced:
            existing.append(shortcut_entry)

        vdf_path.write_bytes(dump_shortcuts_vdf(existing))
        updated_files.append(vdf_path)

    return updated_files
