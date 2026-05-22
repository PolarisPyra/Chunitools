"""Resolve CHUNITHM cue audio assets from parsed chart metadata."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from src.core.models import Chart

__all__ = ["resolve_chart_audio_path", "resolve_chart_awb_path"]

CUE_FILE_DIR_TEMPLATE = "cueFile{music_id:06d}"
CUE_FILE_XML_NAME = "CueFile.xml"
AWB_FILE_NODE = "awbFile/path"
SUPPORTED_CUSTOM_AUDIO_SUFFIXES = {".awb", ".flac", ".mp3", ".wav"}


def _parse_music_id(value: str) -> int | None:
    if not value:
        return None
    try:
        music_id = int(value)
    except ValueError:
        return None
    if music_id < 0:
        return None
    return music_id


def _read_awb_name(cue_file_xml: Path) -> str | None:
    try:
        root = ET.parse(cue_file_xml).getroot()
    except (ET.ParseError, OSError):
        return None

    node = root.find(AWB_FILE_NODE)
    if node is None or node.text is None:
        return None

    awb_name = node.text.strip()
    if not awb_name:
        return None
    return awb_name


def resolve_chart_awb_path(chart: Chart, data_root: str | Path) -> Path | None:
    """Find the AWB music bank for a chart when CHUNITHM cue metadata exists."""
    music_id = _parse_music_id(chart.metadata.music_id)
    if music_id is None:
        return None

    root = Path(data_root)
    cue_dir_name = CUE_FILE_DIR_TEMPLATE.format(music_id=music_id)
    cue_pattern = f"A*/cueFile/{cue_dir_name}/{CUE_FILE_XML_NAME}"
    cue_xml_candidates = sorted(root.glob(cue_pattern))
    for cue_file_xml in cue_xml_candidates:
        awb_name = _read_awb_name(cue_file_xml)
        if awb_name is None:
            continue

        awb_path = cue_file_xml.parent / awb_name
        if awb_path.exists():
            return awb_path

    return None


def resolve_chart_audio_path(
    chart: Chart,
    data_root: str | Path,
    chart_path: str | Path | None = None,
) -> Path | None:
    """Find custom editor audio first, then fall back to arcade AWB metadata."""
    custom_path = _resolve_custom_audio_path(chart.metadata.audio_path, data_root, chart_path)
    if custom_path is not None:
        return custom_path
    return resolve_chart_awb_path(chart, data_root)


def _resolve_custom_audio_path(
    audio_path_value: str,
    data_root: str | Path,
    chart_path: str | Path | None,
) -> Path | None:
    if not audio_path_value:
        return None

    audio_path = Path(audio_path_value).expanduser()
    candidates: list[Path] = []
    if audio_path.is_absolute():
        candidates.append(audio_path)
    else:
        if chart_path is not None:
            candidates.append(Path(chart_path).expanduser().parent / audio_path)
        candidates.append(Path(data_root).expanduser() / audio_path)
        candidates.append(Path.cwd() / audio_path)

    for candidate in candidates:
        if (
            candidate.exists()
            and candidate.is_file()
            and candidate.suffix.lower() in SUPPORTED_CUSTOM_AUDIO_SUFFIXES
        ):
            return candidate
    return None
