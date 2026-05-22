from __future__ import annotations

from pathlib import Path

from src.core import config
from src.ui.window import export as export_module


class DummyWindow:
    pass


def test_open_logs_folder_uses_user_config_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "USER_CONFIG_DIR", tmp_path)

    opened_url = None

    def fake_open_url(url):
        nonlocal opened_url
        opened_url = url.toLocalFile()

    monkeypatch.setattr(export_module.QDesktopServices, "openUrl", fake_open_url)

    export_module.open_logs_folder(DummyWindow())

    expected_path = tmp_path / "logs"
    assert expected_path.exists()
    assert opened_url == str(expected_path)
