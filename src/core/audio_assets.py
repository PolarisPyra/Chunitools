"""Resolve CHUNITHM cue audio assets from parsed chart metadata."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.models import Chart

__all__ = ["resolve_chart_audio_path", "resolve_chart_awb_path"]

LOGGER = logging.getLogger(__name__)

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
    """Find the AWB music bank for a chart when CHUNITHM cue metadata exists.

    Searches recursively under *data_root* so the game data can be nested
    (e.g. under ``App/data/``) rather than at the root.
    """
    music_id = _parse_music_id(chart.metadata.music_id)
    if music_id is None:
        return None

    root = Path(data_root)
    cue_dir_name = CUE_FILE_DIR_TEMPLATE.format(music_id=music_id)
    # Recursive glob catches nested layouts like App/data/A*/cueFile/...
    cue_pattern = f"**/A*/cueFile/{cue_dir_name}/{CUE_FILE_XML_NAME}"
    cue_xml_candidates = sorted(root.glob(cue_pattern))
    LOGGER.debug(
        "resolve_chart_awb_path: searching %s for music_id=%s",
        root / cue_pattern,
        music_id,
    )
    for cue_file_xml in cue_xml_candidates:
        awb_name = _read_awb_name(cue_file_xml)
        if awb_name is None:
            LOGGER.debug("  found %s but no awbFile/path node", cue_file_xml)
            continue

        awb_path = cue_file_xml.parent / awb_name
        if awb_path.exists():
            LOGGER.debug("  resolved AWB path: %s", awb_path)
            return awb_path
        LOGGER.debug("  AWB path %s does not exist", awb_path)

    LOGGER.debug("  no AWB found for music_id=%s", music_id)
    return None


def resolve_chart_audio_path(
    chart: Chart,
    data_root: str | Path,
    chart_path: str | Path | None = None,
) -> Path | None:
    """Find custom editor audio first, then fall back to arcade AWB metadata."""
    custom_path = _resolve_custom_audio_path(chart.metadata.audio_path, data_root, chart_path)
    if custom_path is not None:
        LOGGER.debug("resolve_chart_audio_path: custom audio at %s", custom_path)
        return custom_path
    LOGGER.debug(
        "resolve_chart_audio_path: no custom audio, trying AWB (music_id=%s)",
        chart.metadata.music_id,
    )
    awb_path = resolve_chart_awb_path(chart, data_root)
    if awb_path is not None:
        LOGGER.debug("resolve_chart_audio_path: found AWB at %s", awb_path)
    else:
        LOGGER.debug("resolve_chart_audio_path: no AWB found for music_id=%s", chart.metadata.music_id)
    return awb_path


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
