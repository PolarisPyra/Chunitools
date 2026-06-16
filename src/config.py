"""User configuration loading and persistence (TOML format with sections)."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import platformdirs

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-untyped]

# Support for PyInstaller bundles
meipass = getattr(sys, "_MEIPASS", None)
if getattr(sys, "frozen", False) and meipass is not None:
    PROJECT_ROOT = Path(meipass)
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
SOUNDS_DIR = DEFAULT_DATA_DIR / "sounds"
USER_CONFIG_DIR = Path(platformdirs.user_config_dir("chunitools"))
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.toml"
LEGACY_USER_CONFIG_PATH = USER_CONFIG_DIR / "config.json"
DEFAULT_SCROLL_SPEED = 9.0
DEFAULT_HITSOUND_VOLUME = 0.75
DEFAULT_MUSIC_VOLUME = 0.45
DEFAULT_VISIBLE_NOTE_TYPES: dict[str, bool] = {
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


# ---------------------------------------------------------------------------
# TOML section map: internal field name → (toml_section, toml_key)
# ---------------------------------------------------------------------------
_TOML_FIELD_MAP: dict[str, tuple[str, str]] = {
    "data_root": ("paths", "data_root"),
    "vgstreamcli_path": ("paths", "vgstreamcli_path"),
    "window_width": ("window", "width"),
    "window_height": ("window", "height"),
    "last_difficulty": ("ui", "last_difficulty"),
    "show_fps": ("ui", "show_fps"),
    "show_radar": ("ui", "show_radar"),
    "show_export_button": ("ui", "show_export_button"),
    "show_warnings": ("ui", "show_warnings"),
    "show_inspector": ("ui", "show_inspector"),
    "show_note_debug_overlay": ("ui", "show_note_debug_overlay"),
    "subdivisions": ("ui", "subdivisions"),
    "scroll_speed": ("ui", "scroll_speed"),
    "hitsound_volume": ("ui", "hitsound_volume"),
    "music_volume": ("ui", "music_volume"),
    "visible_note_types": ("visible_note_types", "__table__"),
    "log_debug_level": ("logger", "debug_level"),
    "log_3d": ("logger", "3D_Log"),
    "log_2d": ("logger", "2D_Log"),
    "log_note_rendering": ("logger", "note_rendering_log"),
}

# Sections whose entire table is the value of a single dict field.
_TABLE_FIELDS: set[str] = {"visible_note_types"}


def _toml_value(val: object) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if val == int(val) and not (abs(val) >= 1e15 or 0 < abs(val) < 1e-10):
            return str(int(val))
        return repr(val)
    if val is None:
        return ""
    raise TypeError(f"unsupported TOML type: {type(val).__name__}")


def _is_toml_bare_key(key: str) -> bool:
    """Return True if *key* is a valid TOML bare key (no quotes needed).

    TOML bare keys allow ``[A-Za-z0-9_-]+`` — digits are fine at the start,
    unlike Python identifiers.
    """
    if not key:
        return False
    return all(c.isalnum() or c in ("_", "-") for c in key)


def _toml_encode(settings: UserSettings) -> str:
    """Serialize *settings* to a TOML string with section headers."""
    data = asdict(settings)

    # Group fields into sections
    sections: dict[str, dict[str, object]] = {}
    for field_name, value in data.items():
        if field_name not in _TOML_FIELD_MAP:
            continue
        section, key = _TOML_FIELD_MAP[field_name]
        if field_name in _TABLE_FIELDS and isinstance(value, dict):
            # Whole-table field: the section gets every dict entry
            sections[section] = value  # type: ignore[assignment]
        else:
            sections.setdefault(section, {})[key] = value

    lines: list[str] = []
    # Ensure a stable output order
    section_order = [
        "paths", "window", "ui", "visible_note_types", "logger",
    ]
    for section_name in section_order:
        table = sections.get(section_name)
        if table is None:
            continue
        if section_name in _TABLE_FIELDS:
            # Whole-table section
            assert isinstance(table, dict)
            lines.append(f"[{section_name}]")
            for k, v in table.items():
                qualified = f'"{k}"' if not _is_toml_bare_key(k) else k
                lines.append(f"{qualified} = {_toml_value(v)}")
        else:
            assert isinstance(table, dict)
            lines.append(f"[{section_name}]")
            for key, value in table.items():
                qualified = f'"{key}"' if not _is_toml_bare_key(key) else key
                lines.append(f"{qualified} = {_toml_value(value)}")
        lines.append("")

    return "\n".join(lines)


def _toml_decode(content: str) -> dict[str, object]:
    """Parse TOML content into a flat dict of field_name → value."""
    parsed = tomllib.loads(content)

    # Build reverse map: (section, key) → field_name (for non-table fields)
    reverse: dict[tuple[str, str], str] = {}
    for field_name, (section, key) in _TOML_FIELD_MAP.items():
        if field_name not in _TABLE_FIELDS:
            reverse[(section, key)] = field_name

    flat: dict[str, object] = {}
    for section_name, table in parsed.items():
        if not isinstance(table, dict):
            continue
        if section_name in _TABLE_FIELDS:
            # Find the matching field name for this whole-table section
            for field_name, (sec, _key) in _TOML_FIELD_MAP.items():
                if sec == section_name and field_name in _TABLE_FIELDS:
                    flat[field_name] = table
                    break
        else:
            for key, value in table.items():
                field_name = reverse.get((section_name, key))
                if field_name is not None:
                    flat[field_name] = value

    return flat


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------


@dataclass
class UserSettings:
    """User-mutable settings that persist in config.toml."""

    # ── [paths] ──
    data_root: str = ""
    vgstreamcli_path: str = ""

    # ── [window] ──
    window_width: int = 1920
    window_height: int = 1080

    # ── [ui] ──
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

    # ── [visible_note_types] ──
    visible_note_types: dict[str, bool] = field(
        default_factory=lambda: dict(DEFAULT_VISIBLE_NOTE_TYPES)
    )

    # ── [logger] ──
    log_debug_level: str = "info"
    log_3d: bool = False
    log_2d: bool = False
    log_note_rendering: bool = False

    def save(self) -> None:
        """Persist settings to disk as a TOML file."""
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with USER_CONFIG_PATH.open("w", encoding="utf-8") as fh:
            fh.write(_toml_encode(self))


@dataclass(frozen=True)
class StartupDataRoot:
    """Resolved startup data directory."""

    path: str
    from_config: bool


def resolve_startup_data_root(
    user_settings: UserSettings,
    default_data_dir: Path = DEFAULT_DATA_DIR,
) -> StartupDataRoot:
    """Resolve the startup data root from config, with legacy fallback."""
    configured_root = user_settings.data_root.strip()
    if configured_root and Path(configured_root).expanduser().exists():
        return StartupDataRoot(path=configured_root, from_config=True)

    legacy_root = _load_legacy_data_root()
    if legacy_root:
        user_settings.data_root = legacy_root
        user_settings.save()
        return StartupDataRoot(path=legacy_root, from_config=True)

    default_path = str(default_data_dir)
    return StartupDataRoot(path=default_path, from_config=False)


def _load_legacy_data_root() -> str:
    """Return a usable data root from the old JSON config format, if present."""
    if not LEGACY_USER_CONFIG_PATH.exists():
        return ""
    try:
        with LEGACY_USER_CONFIG_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
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
    """Build a UserSettings from a flat dict (used by tests / TOML decode)."""
    if not isinstance(data, dict):
        return UserSettings()

    valid_fields = {field_info.name for field_info in fields(UserSettings)}
    filtered_data = {
        key: value for key, value in data.items() if isinstance(key, str) and key in valid_fields
    }
    return UserSettings(**filtered_data)


def _migrate_yaml_to_toml() -> UserSettings | None:
    """Migrate settings from old ``config.yaml`` to ``config.toml``, return them or ``None``."""
    yaml_path = USER_CONFIG_DIR / "config.yaml"
    if not yaml_path.exists():
        return None
    try:
        import yaml  # noqa: PLC0415

        with yaml_path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        if not isinstance(raw, dict):
            return None
        settings = _settings_from_mapping(raw)
        settings.save()
        LOGGER.info("Migrated settings from config.yaml to config.toml")
        # Archive the old YAML so we don't re-migrate
        yaml_path.rename(yaml_path.with_suffix(".yaml.bak"))
        return settings
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Failed to migrate config.yaml: %s", exc)
        return None


def load_settings() -> UserSettings:
    """Load settings from disk or return defaults (and persist them)."""
    if not USER_CONFIG_PATH.exists():
        migrated = _migrate_yaml_to_toml()
        if migrated is not None:
            return migrated
        defaults = UserSettings()
        defaults.save()
        return defaults

    try:
        raw = USER_CONFIG_PATH.read_text(encoding="utf-8")
        flat = _toml_decode(raw)
        return _settings_from_mapping(flat)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        LOGGER.warning("Failed to load settings from %s: %s", USER_CONFIG_PATH, exc)
        return UserSettings()


APP_NAME = "Chunitools"
VERSION = "0.2.10"
settings = load_settings()
