"""Sidecar storage for chart-editor metadata.

Official .c2s files should only contain chart data. Paths and export hints used
by the editor live next to the chart in a same-stem ``.json`` file instead.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.core.models import Chart

EDITOR_METADATA_KEYS = (
    "audio_path",
    "jacket_path",
    "option_folder",
    "atomcraft_project",
    "hca_key",
)


def editor_metadata_path(chart_path: str | Path) -> Path:
    """Return the sidecar path for a chart file."""
    return Path(chart_path).with_suffix(".json")


def load_editor_metadata(chart: Chart, chart_path: str | Path) -> None:
    """Populate runtime editor metadata from the chart's sidecar, if present."""
    metadata_path = editor_metadata_path(chart_path)
    if not metadata_path.exists():
        return

    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    entry = _entry_for_chart(data, Path(chart_path).name)
    if not isinstance(entry, dict):
        return

    audio_path = _clean_string(entry.get("audio_path"))
    if audio_path:
        chart.metadata.audio_path = audio_path
    jacket_path = _clean_string(entry.get("jacket_path"))
    if jacket_path:
        chart.metadata.jacket_path = jacket_path

    for key in ("option_folder", "atomcraft_project", "hca_key"):
        value = _clean_string(entry.get(key))
        if value:
            chart.editor[key] = value


def save_editor_metadata(
    chart: Chart,
    chart_path: str | Path,
    source_chart_path: str | Path | None = None,
) -> None:
    """Write editor-only metadata to a per-chart JSON sidecar."""
    metadata_path = editor_metadata_path(chart_path)
    entry = _chart_entry(chart, Path(chart_path), source_chart_path)

    if entry:
        metadata_path.write_text(
            json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return

    if metadata_path.exists():
        metadata_path.unlink()


def _entry_for_chart(data: Any, chart_name: str) -> Any:
    if not isinstance(data, dict):
        return None
    charts = data.get("charts")
    if isinstance(charts, dict) and isinstance(charts.get(chart_name), dict):
        return charts[chart_name]
    return data


def _chart_entry(
    chart: Chart,
    chart_path: Path,
    source_chart_path: str | Path | None,
) -> dict[str, str]:
    audio_path = _local_chart_asset_path(chart.metadata.audio_path, chart_path, source_chart_path)
    jacket_path = _local_chart_asset_path(chart.metadata.jacket_path, chart_path, source_chart_path)
    if audio_path:
        chart.metadata.audio_path = audio_path
    if jacket_path:
        chart.metadata.jacket_path = jacket_path

    values = {
        "audio_path": audio_path,
        "jacket_path": jacket_path,
        **chart.editor,
    }
    return {
        key: value.strip()
        for key, value in values.items()
        if key in EDITOR_METADATA_KEYS and isinstance(value, str) and value.strip()
    }


def _clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _local_chart_asset_path(
    value: str,
    chart_path: Path,
    source_chart_path: str | Path | None,
) -> str:
    raw_path = _clean_string(value)
    if not raw_path:
        return ""

    source_path = _resolve_asset_source(raw_path, chart_path, source_chart_path)
    if source_path is None:
        return raw_path

    destination = chart_path.parent / source_path.name
    if not _same_file(source_path, destination):
        chart_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
    return destination.name


def _resolve_asset_source(
    value: str,
    chart_path: Path,
    source_chart_path: str | Path | None,
) -> Path | None:
    asset_path = Path(value).expanduser()
    candidates: list[Path]
    if asset_path.is_absolute():
        candidates = [asset_path]
    else:
        candidates = []
        if source_chart_path is not None:
            candidates.append(Path(source_chart_path).expanduser().parent / asset_path)
        candidates.append(chart_path.parent / asset_path)
        candidates.append(Path.cwd() / asset_path)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _same_file(source_path: Path, destination: Path) -> bool:
    try:
        return source_path.samefile(destination)
    except OSError:
        return False
