from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-untyped]

from src import config
from src.config import (
    DEFAULT_HITSOUND_VOLUME,
    DEFAULT_MUSIC_VOLUME,
    DEFAULT_VISIBLE_NOTE_TYPES,
    UserSettings,
    _load_legacy_data_root,
    _settings_from_mapping,
    _toml_decode,
    resolve_startup_data_root,
)


def test_settings_from_mapping_ignores_unknown_keys() -> None:
    settings = _settings_from_mapping(
        {
            "window_width": 1280,
            "unknown": "ignored",
            "show_radar": True,
            "scroll_speed": 8.25,
        }
    )

    assert settings.window_width == 1280
    assert settings.show_radar
    assert settings.scroll_speed == 8.25


def test_settings_from_non_mapping_returns_defaults() -> None:
    settings = _settings_from_mapping(["not", "a", "mapping"])

    assert settings == UserSettings()
    assert settings.scroll_speed == 9.0


def test_visible_note_defaults_are_not_shared() -> None:
    first = UserSettings()
    second = UserSettings()

    first.visible_note_types["TAP"] = False

    assert second.visible_note_types == DEFAULT_VISIBLE_NOTE_TYPES


def test_audio_volume_defaults_favor_hitsounds_over_music() -> None:
    settings = UserSettings()

    assert settings.hitsound_volume == DEFAULT_HITSOUND_VOLUME
    assert settings.music_volume == DEFAULT_MUSIC_VOLUME
    assert settings.hitsound_volume > settings.music_volume


def test_audio_volume_settings_save_to_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)

    settings = UserSettings(hitsound_volume=0.82, music_volume=0.31)
    settings.save()

    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert parsed["ui"]["hitsound_volume"] == 0.82
    assert parsed["ui"]["music_volume"] == 0.31


def test_note_debug_overlay_setting_saves_to_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)

    UserSettings(show_note_debug_overlay=True).save()

    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert parsed["ui"]["show_note_debug_overlay"] is True


def test_data_root_setting_saves_to_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    data_root = tmp_path / "game-data"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)

    UserSettings(data_root=str(data_root)).save()

    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert parsed["paths"]["data_root"] == str(data_root)


def test_audio_volume_settings_load_from_config_mapping() -> None:
    settings = _settings_from_mapping(
        {
            "hitsound_volume": 0.67,
            "music_volume": 0.22,
        }
    )

    assert settings.hitsound_volume == 0.67
    assert settings.music_volume == 0.22


def test_note_debug_overlay_setting_loads_from_config_mapping() -> None:
    settings = _settings_from_mapping({"show_note_debug_overlay": True})

    assert settings.show_note_debug_overlay is True


def test_logger_defaults_set_on_UserSettings() -> None:
    settings = UserSettings()

    assert settings.log_debug_level == "info"
    assert settings.log_3d is False
    assert settings.log_2d is False


def test_logger_settings_save_to_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)

    UserSettings(log_debug_level="debug", log_3d=True, log_2d=True).save()

    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert parsed["logger"]["debug_level"] == "debug"
    assert parsed["logger"]["3D_Log"] is True
    assert parsed["logger"]["2D_Log"] is True


def test_logger_settings_load_round_trip(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)

    orig = UserSettings(log_debug_level="debug", log_3d=True, log_2d=True)
    orig.save()

    loaded = config.load_settings()
    assert loaded.log_debug_level == "debug"
    assert loaded.log_3d is True
    assert loaded.log_2d is True


def test_toml_decode_visible_note_types() -> None:
    toml_str = """
[visible_note_types]
TAP = false
FLK = true
"""
    flat = _toml_decode(toml_str)
    assert flat["visible_note_types"] == {"TAP": False, "FLK": True}


def test_toml_decode_logger_section() -> None:
    toml_str = """
[logger]
debug_level = "warn"
"3D_Log" = true
"2D_Log" = false
"""
    flat = _toml_decode(toml_str)
    assert flat["log_debug_level"] == "warn"
    assert flat["log_3d"] is True
    assert flat["log_2d"] is False


def test_toml_encode_visible_note_types() -> None:
    s = UserSettings()
    s.visible_note_types["TAP"] = False
    toml_str = config._toml_encode(s)
    parsed = tomllib.loads(toml_str)
    assert parsed["visible_note_types"]["TAP"] is False
    assert parsed["visible_note_types"]["FLK"] is True


def test_startup_uses_existing_configured_data_root(tmp_path) -> None:
    configured_root = tmp_path / "game-data"
    configured_root.mkdir()

    resolved = resolve_startup_data_root(
        UserSettings(data_root=str(configured_root)),
        tmp_path / "missing-default-data",
    )

    assert resolved.path == str(configured_root)
    assert resolved.from_config


def test_startup_uses_default_when_no_data_root(tmp_path) -> None:
    resolved = resolve_startup_data_root(
        UserSettings(data_root=""),
        tmp_path / "missing-default-data",
    )

    assert resolved.path == str(tmp_path / "missing-default-data")
    assert not resolved.from_config


def test_startup_uses_existing_default_data_root(tmp_path) -> None:
    default_data_root = tmp_path / "data"
    default_data_root.mkdir()

    resolved = resolve_startup_data_root(UserSettings(), default_data_root)

    assert resolved.path == str(default_data_root)
    assert not resolved.from_config


def test_legacy_json_data_root_can_seed_startup_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    legacy_path = tmp_path / "config.json"
    data_root = tmp_path / "legacy-data"
    data_root.mkdir()
    legacy_path.write_text(f'{{"DataRoot": "{data_root}"}}', encoding="utf-8")
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "LEGACY_USER_CONFIG_PATH", legacy_path)
    settings = UserSettings(data_root="")

    resolved = resolve_startup_data_root(settings, tmp_path / "missing-default-data")

    assert resolved.path == str(data_root)
    assert resolved.from_config
    assert settings.data_root == str(data_root)
    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert parsed["paths"]["data_root"] == str(data_root)


def test_missing_toml_data_root_falls_back_to_legacy_json(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    legacy_path = tmp_path / "config.json"
    data_root = tmp_path / "legacy-data"
    data_root.mkdir()
    legacy_path.write_text(f'{{"DataRoot": "{data_root}"}}', encoding="utf-8")
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "LEGACY_USER_CONFIG_PATH", legacy_path)
    settings = UserSettings(data_root=str(tmp_path / "deleted-data-root"))

    resolved = resolve_startup_data_root(settings, tmp_path / "missing-default-data")

    assert resolved.path == str(data_root)
    assert resolved.from_config
    assert settings.data_root == str(data_root)


def test_legacy_data_root_ignores_missing_path(monkeypatch, tmp_path) -> None:
    legacy_path = tmp_path / "config.json"
    legacy_path.write_text('{"DataRoot": "/definitely/missing"}', encoding="utf-8")
    monkeypatch.setattr(config, "LEGACY_USER_CONFIG_PATH", legacy_path)

    assert _load_legacy_data_root() == ""


def test_visible_note_round_trip(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)

    orig = UserSettings()
    orig.visible_note_types["TAP"] = False
    orig.save()

    loaded = config.load_settings()
    assert loaded.visible_note_types["TAP"] is False
    assert loaded.visible_note_types["FLK"] is True
