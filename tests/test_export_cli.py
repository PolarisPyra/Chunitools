from __future__ import annotations

from src.cli.export_chart import _default_output_path


def test_default_output_path_uses_title_and_difficulty() -> None:
    assert _default_output_path("charts/example.c2s", "Song/Name", "MASTER") == (
        "Song_Name_MASTER.png"
    )


def test_default_output_path_falls_back_to_chart_stem() -> None:
    assert _default_output_path("charts/example.c2s", "", "") == "example.png"
