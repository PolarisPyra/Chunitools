"""User configuration loading and persistence."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import platformdirs
import yaml

__all__ = [
    "APP_NAME",
    "DEFAULT_DATA_DIR",
    "DEFAULT_SCROLL_SPEED",
    "SOUNDS_DIR",
    "USER_CONFIG_DIR",
    "LEGACY_USER_CONFIG_PATH",
    "USER_CONFIG_PATH",
    "VERSION",
    "StartupDataRoot",
    "UserSettings",
    "get_sounds_dir",
    "load_settings",
    "resolve_startup_data_root",
    "settings",
]

# Support for PyInstaller bundles
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
SOUNDS_DIR = DEFAULT_DATA_DIR / "sounds"
USER_CONFIG_DIR = Path(platformdirs.user_config_dir("chunitools"))
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.yaml"
LEGACY_USER_CONFIG_PATH = USER_CONFIG_DIR / "config.json"
DEFAULT_SCROLL_SPEED = 9.0
DEFAULT_HITSOUND_VOLUME = 0.75
DEFAULT_MUSIC_VOLUME = 0.45
DEFAULT_VISIBLE_NOTE_TYPES = {
    "TAP": True,
    "CHR": True,
    "FLK": True,
    "MNE": True,
    "HLD": True,
    "HXD": True,
    "SLD": True,
    "SXD": True,
    "SLC": True,
    "SXC": True,
    "AIR": True,
    "AUR": True,
    "AUL": True,
    "AHD": True,
    "ADW": True,
    "ADR": True,
    "ADL": True,
    "ALD": True,
    "ASD": True,
    "ASC": True,
}
LOGGER = logging.getLogger(__name__)


def get_sounds_dir(data_root: str | None = None) -> Path:
    """Resolve the active sounds directory from configured data roots."""
    if data_root:
        candidate = Path(data_root) / "sounds"
        if candidate.exists():
            return candidate
    return SOUNDS_DIR


@dataclass
class UserSettings:
    """User-mutable settings that persist in config.yaml."""
    data_root: str = ""
    window_width: int = 1920
    window_height: int = 1080
    last_difficulty: int = 0
    show_fps: bool = False
    show_radar: bool = False
    show_export_button: bool = True
    show_warnings: bool = False
    show_inspector: bool = False
    show_note_debug_overlay: bool = False
    subdivisions: int = 4
    scroll_speed: float = DEFAULT_SCROLL_SPEED
    hitsound_volume: float = DEFAULT_HITSOUND_VOLUME
    music_volume: float = DEFAULT_MUSIC_VOLUME
    visible_note_types: dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_VISIBLE_NOTE_TYPES)
    )

    def save(self) -> None:
        """Persist settings to disk."""
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with USER_CONFIG_PATH.open("w", encoding="utf-8") as file_handle:
            yaml.dump(asdict(self), file_handle, default_flow_style=False)


@dataclass(frozen=True)
class StartupDataRoot:
    """Resolved startup data directory and whether startup should prompt for it."""

    path: str
    should_prompt: bool
    from_config: bool


def resolve_startup_data_root(
    user_settings: UserSettings,
    default_data_dir: Path = DEFAULT_DATA_DIR,
) -> StartupDataRoot:
    """Choose the startup data root from saved config when it is usable."""
    configured_root = user_settings.data_root.strip()
    if configured_root:
        if Path(configured_root).expanduser().exists():
            return StartupDataRoot(
                path=configured_root,
                should_prompt=False,
                from_config=True,
            )
        legacy_root = _load_legacy_data_root()
        if legacy_root:
            user_settings.data_root = legacy_root
            user_settings.save()
            return StartupDataRoot(
                path=legacy_root,
                should_prompt=False,
                from_config=True,
            )

        LOGGER.warning(
            "Configured data_root does not exist: %s. "
            "Prompting for a replacement data directory.",
            configured_root,
        )
        return StartupDataRoot(
            path=configured_root,
            should_prompt=True,
            from_config=True,
        )

    legacy_root = _load_legacy_data_root()
    if legacy_root:
        user_settings.data_root = legacy_root
        user_settings.save()
        return StartupDataRoot(
            path=legacy_root,
            should_prompt=False,
            from_config=True,
        )

    default_path = str(default_data_dir)
    return StartupDataRoot(
        path=default_path,
        should_prompt=not default_data_dir.exists(),
        from_config=False,
    )


def _load_legacy_data_root() -> str:
    """Return a usable data root from the old JSON config format, if present."""
    if not LEGACY_USER_CONFIG_PATH.exists():
        return ""
    try:
        with LEGACY_USER_CONFIG_PATH.open("r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        LOGGER.warning("Failed to load legacy config from %s: %s", LEGACY_USER_CONFIG_PATH, exc)
        return ""

    if not isinstance(data, dict):
        return ""

    legacy_root = data.get("DataRoot") or data.get("data_root") or ""
    if not isinstance(legacy_root, str):
        return ""

    legacy_root = legacy_root.strip()
    if not legacy_root:
        return ""

    if Path(legacy_root).expanduser().exists():
        return legacy_root

    LOGGER.warning("Legacy data root does not exist: %s", legacy_root)
    return ""


def _settings_from_mapping(data: object) -> UserSettings:
    if not isinstance(data, dict):
        return UserSettings()

    valid_fields = {field_info.name for field_info in fields(UserSettings)}
    filtered_data = {
        key: value
        for key, value in data.items()
        if isinstance(key, str) and key in valid_fields
    }
    return UserSettings(**filtered_data)


def load_settings() -> UserSettings:
    """Load settings from disk or return defaults (and persist them)."""
    if not USER_CONFIG_PATH.exists():
        defaults = UserSettings()
        defaults.save()
        return defaults

    try:
        with USER_CONFIG_PATH.open("r", encoding="utf-8") as file_handle:
            return _settings_from_mapping(yaml.safe_load(file_handle))
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        LOGGER.warning("Failed to load settings from %s: %s", USER_CONFIG_PATH, exc)
        return UserSettings()


APP_NAME = "Chunitools"
VERSION = "0.2.1"
settings = load_settings()
