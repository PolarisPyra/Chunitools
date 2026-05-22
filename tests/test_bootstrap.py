from __future__ import annotations

import logging
from pathlib import Path

from src.app import bootstrap
from src.bootstrap import (
    BOOTSTRAP_ONLY_ENV,
    BOOTSTRAP_ONLY_VALUE,
    _is_bootstrap_only,
)
from src.core.read import load_chart_file


def test_bootstrap_only_env_is_parsed_explicitly(monkeypatch) -> None:
    monkeypatch.setenv(BOOTSTRAP_ONLY_ENV, BOOTSTRAP_ONLY_VALUE)

    assert _is_bootstrap_only()


def test_config_log_dir_is_used_for_logging(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bootstrap, "USER_CONFIG_DIR", tmp_path)

    bootstrap._configure_logging()

    log_dir = tmp_path / "logs"
    assert (log_dir / "debug.log").exists()
    assert (log_dir / "chartloading.log").exists()


def test_chart_loading_surfaces_diagnostics_when_warnings_exist(tmp_path: Path) -> None:
    chart_path = tmp_path / "missing_target.c2s"
    chart_path.write_text(
        "MUSICID\t0000\n"
        "TITLE\tDiagnostic Test\n"
        "ARTIST\tUnit Test\n"
        "DIFFICULT\t1\n"
        "LEVEL\t10\n"
        "HLD\t0\t0\t0\t1\t384\n"
        "AIR\t0\t0\t0\t1\tXXX\n",
        encoding="utf-8",
    )

    chart = load_chart_file(chart_path)

    assert chart.warnings
    assert any("has unresolved target" in warning for warning in chart.warnings)


def test_bootstrap_only_rejects_other_values(monkeypatch) -> None:
    monkeypatch.setenv(BOOTSTRAP_ONLY_ENV, "true")

    assert not _is_bootstrap_only()
