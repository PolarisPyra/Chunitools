from __future__ import annotations

import yaml

import src.core.config as config
from src.core.config import (
    DEFAULT_HITSOUND_VOLUME,
    DEFAULT_MUSIC_VOLUME,
    DEFAULT_VISIBLE_NOTE_TYPES,
    UserSettings,
    _load_legacy_data_root,
    _settings_from_mapping,
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
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)

    settings = UserSettings(hitsound_volume=0.82, music_volume=0.31)
    settings.save()

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["hitsound_volume"] == 0.82
    assert saved["music_volume"] == 0.31


def test_note_debug_overlay_setting_saves_to_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)

    UserSettings(show_note_debug_overlay=True).save()

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["show_note_debug_overlay"] is True


def test_data_root_setting_saves_to_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    data_root = tmp_path / "game-data"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "USER_CONFIG_PATH", config_path)

    UserSettings(data_root=str(data_root)).save()

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["data_root"] == str(data_root)


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


def test_startup_uses_existing_configured_data_root_without_prompting(tmp_path) -> None:
    configured_root = tmp_path / "game-data"
    configured_root.mkdir()

    resolved = resolve_startup_data_root(
        UserSettings(data_root=str(configured_root)),
        tmp_path / "missing-default-data",
    )

    assert resolved.path == str(configured_root)
    assert resolved.from_config
    assert not resolved.should_prompt


def test_startup_prompts_when_configured_data_root_is_missing(tmp_path) -> None:
    missing_configured_root = tmp_path / "deleted-data-root"

    resolved = resolve_startup_data_root(
        UserSettings(data_root=str(missing_configured_root)),
        tmp_path / "missing-default-data",
    )

    assert resolved.path == str(missing_configured_root)
    assert resolved.from_config
    assert resolved.should_prompt


def test_startup_prompts_when_no_configured_data_root_and_default_missing(tmp_path) -> None:
    resolved = resolve_startup_data_root(
        UserSettings(data_root=""),
        tmp_path / "missing-default-data",
    )

    assert resolved.path == str(tmp_path / "missing-default-data")
    assert not resolved.from_config
    assert resolved.should_prompt


def test_startup_uses_existing_default_data_root_without_prompting(tmp_path) -> None:
    default_data_root = tmp_path / "data"
    default_data_root.mkdir()

    resolved = resolve_startup_data_root(UserSettings(), default_data_root)

    assert resolved.path == str(default_data_root)
    assert not resolved.from_config
    assert not resolved.should_prompt


def test_legacy_json_data_root_can_seed_startup_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
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
    assert not resolved.should_prompt
    assert settings.data_root == str(data_root)
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["data_root"] == str(data_root)


def test_missing_yaml_data_root_falls_back_to_legacy_json(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
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
    assert not resolved.should_prompt
    assert settings.data_root == str(data_root)


def test_legacy_data_root_ignores_missing_path(monkeypatch, tmp_path) -> None:
    legacy_path = tmp_path / "config.json"
    legacy_path.write_text('{"DataRoot": "/definitely/missing"}', encoding="utf-8")
    monkeypatch.setattr(config, "LEGACY_USER_CONFIG_PATH", legacy_path)

    assert _load_legacy_data_root() == ""
