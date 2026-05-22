"""Writers for editable CHUNITHM chart artifacts."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.editor_metadata import save_editor_metadata
from src.core.models import BpmEntry, Chart, ChartMetadata, TimeSignatureEntry
from src.notes.geometry import note_get_steps, note_has_steps

if TYPE_CHECKING:
    from src.notes import Note

DIFFICULTY_NAME_TO_ID = {
    "BASIC": 0,
    "ADVANCED": 1,
    "EXPERT": 2,
    "MASTER": 3,
    "ULTIMA": 4,
    "WORLD'S END": 5,
}

DIFFICULTY_ID_TO_MUSIC_TYPE = {
    0: ("Basic", "BASIC"),
    1: ("Advanced", "ADVANCED"),
    2: ("Expert", "EXPERT"),
    3: ("Master", "MASTER"),
    4: ("Ultima", "ULTIMA"),
    5: ("WorldsEnd", "WORLD'S END"),
}


class IChartSerializer(ABC):
    """Abstract interface for chart serialization strategies."""

    @abstractmethod
    def serialize(self, chart: Chart) -> str:
        """Serialize a Chart to a .c2s document string."""


class C2sSerializer(IChartSerializer):
    """Tab-delimited .c2s document serializer."""

    def serialize(self, chart: Chart) -> str:
        return self._serialize_c2s(chart)

    def serialize_music_xml(
        self, chart: Chart, chart_filename: str, jacket_filename: str = ""
    ) -> str:
        """Serialize arcade-style Music.xml for custom chart metadata."""
        return _serialize_music_xml(chart.metadata, chart_filename, jacket_filename)

    # -- Private helpers -----------------------------------------------------

    @staticmethod
    def _serialize_c2s(chart: Chart) -> str:
        meta = chart.metadata
        lines = _header_lines(meta)
        lines.append("")
        lines.extend(_bpm_lines(chart.bpms))
        lines.extend(_signature_lines(chart.signatures))
        lines.extend(_soflan_lines(chart))
        if chart.notes:
            lines.append("")
            lines.extend(_note_lines(chart.notes))
        return "\n".join(lines).rstrip() + "\n"


def create_blank_chart() -> Chart:
    """Create a valid empty .c2s chart with sensible metadata defaults."""
    metadata = ChartMetadata(
        version="1.13.00",
        music_id="0000",
        title="Untitled",
        artist="Unknown Artist",
        sequence_id="0000_03",
        difficulty="MASTER",
        difficulty_id=3,
        level="1",
        creator="",
        bpm_def=["120.000", "120.000", "120.000", "120.000"],
        met_def=(4, 4),
        resolution=384,
        clk_def=384,
        progjudge_bpm=240.0,
        progjudge_aer=0.999,
    )
    return Chart(
        metadata=metadata,
        bpms=[{"measure": 0, "offset": 0, "bpm": 120.0}],
        signatures=[{"measure": 0, "numerator": 4, "denominator": 4}],
    )


def serialize_c2s(chart: Chart) -> str:
    """Serialize a chart to a tab-delimited .c2s document."""
    return C2sSerializer().serialize(chart)


def save_chart_file(
    chart: Chart,
    path: str | Path,
    source_chart_path: str | Path | None = None,
) -> None:
    """Write a chart to disk as UTF-8 .c2s text."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialize_c2s(chart), encoding="utf-8")
    save_editor_metadata(chart, output_path, source_chart_path)


def serialize_music_xml(chart: Chart, chart_filename: str, jacket_filename: str = "") -> str:
    """Serialize arcade-style Music.xml for custom chart metadata."""
    return _serialize_music_xml(chart.metadata, chart_filename, jacket_filename)


def save_music_xml(chart: Chart, path: str | Path, chart_filename: str) -> None:
    """Write Music.xml next to a custom chart."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jacket_filename = Path(chart.metadata.jacket_path).name if chart.metadata.jacket_path else ""
    output_path.write_text(
        serialize_music_xml(chart, chart_filename, jacket_filename),
        encoding="utf-8",
    )


# -- Module-level helpers (shared by serializer and public API) --------------


def _line(command: str, *values: object) -> str:
    return "\t".join([command, *(str(value) for value in values)])


def _format_float(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def _format_official_float(value: float) -> str:
    return f"{float(value):.3f}"


def _bpm_def(meta: ChartMetadata) -> list[str]:
    if meta.bpm_def:
        return [_format_official_float(float(value)) for value in meta.bpm_def]
    bpm = _format_official_float(meta.progjudge_bpm if meta.progjudge_bpm > 0 else 120.0)
    return [bpm, bpm, bpm, bpm]


def _difficulty_id(meta: ChartMetadata) -> int:
    if meta.difficulty_id:
        return int(meta.difficulty_id)
    return DIFFICULTY_NAME_TO_ID.get((meta.difficulty or "").upper(), 3)


def _default_sequence_id(meta: ChartMetadata) -> str:
    return f"{meta.music_id or '0000'}_{_difficulty_id(meta):02d}"


def _normalized_music_id(meta: ChartMetadata) -> str:
    raw = (meta.music_id or "0").strip()
    if raw.isdecimal():
        return str(int(raw))
    return raw or "0"


def _sorted_bpms(bpms: list[BpmEntry]) -> list[BpmEntry]:
    return sorted(bpms, key=lambda bpm: (bpm["measure"], bpm["offset"], bpm["bpm"]))


def _sorted_signatures(signatures: list[TimeSignatureEntry]) -> list[TimeSignatureEntry]:
    return sorted(
        signatures,
        key=lambda signature: (
            signature["measure"],
            signature["numerator"],
            signature["denominator"],
        ),
    )


def _iter_serializable_notes(notes: list[Note]) -> list[Note]:
    serializable: list[Note] = []
    for note in sorted(notes, key=lambda item: (item.measure, item.offset, item.cell)):
        if note_has_steps(note):
            serializable.extend(note_get_steps(note))
        else:
            serializable.append(note)
    return serializable


def _note_line(note: Note) -> str:
    return note.serialize()


def _text_node(root: ET.Element, path: str, value: str) -> None:
    current = root
    for part in path.split("/"):
        found = current.find(part)
        if found is None:
            found = ET.SubElement(current, part)
        current = found
    current.text = value


def _string_id(root: ET.Element, path: str, value_id: str, value_str: str, data: str) -> None:
    _text_node(root, f"{path}/id", value_id)
    _text_node(root, f"{path}/str", value_str)
    _text_node(root, f"{path}/data", data)


def _split_level(value: str) -> tuple[int, int]:
    raw = (value or "1").strip()
    plus = raw.endswith("+")
    raw = raw.rstrip("+")
    try:
        if "." in raw:
            base_raw, decimal_raw = raw.split(".", 1)
            return max(1, int(base_raw)), max(0, min(99, int(decimal_raw[:2].ljust(2, "0"))))
        return max(1, int(raw)), 50 if plus else 0
    except ValueError:
        return 1, 0


# -- .c2s line-building helpers ---------------------------------------------


def _header_lines(meta: ChartMetadata) -> list[str]:
    lines = [
        _line("VERSION", meta.version or "1.13.00", meta.version or "1.13.00"),
        _line("MUSIC", _normalized_music_id(meta)),
        _line("SEQUENCEID", meta.sequence_id or _default_sequence_id(meta)),
        _line("DIFFICULT", f"{_difficulty_id(meta):02d}"),
        _line("LEVEL", meta.level or "1"),
        _line("CREATOR", meta.creator),
        _line("BPM_DEF", *_bpm_def(meta)),
        _line("MET_DEF", meta.met_def[0], meta.met_def[1]),
        _line("RESOLUTION", meta.resolution),
        _line("CLK_DEF", meta.clk_def),
        _line("PROGJUDGE_BPM", _format_official_float(meta.progjudge_bpm)),
        _line("PROGJUDGE_AER", _format_official_float(meta.progjudge_aer)),
        _line("TUTORIAL", 1 if meta.tutorial else 0),
    ]
    if meta.we_name:
        lines.append(_line("WENAME", meta.we_name))
    if meta.we_level:
        lines.append(_line("WELEVEL", meta.we_level))
    return lines


def _bpm_lines(bpms: list[BpmEntry]) -> list[str]:
    return [
        _line("BPM", bpm["measure"], bpm["offset"], _format_official_float(bpm["bpm"]))
        for bpm in _sorted_bpms(bpms)
    ]


def _signature_lines(signatures: list[TimeSignatureEntry]) -> list[str]:
    return [
        _line("MET", sig["measure"], 0, sig["numerator"], sig["denominator"])
        for sig in _sorted_signatures(signatures)
    ]


def _soflan_lines(chart: Chart) -> list[str]:
    lines: list[str] = []
    if chart.soflan_areas:
        lines.append("")
        for area in chart.soflan_areas:
            lines.append(_line("SLA", area.measure, area.tick, area.cell, area.width, area.duration, area.area_id))
    if chart.soflan_patterns:
        for pat in chart.soflan_patterns:
            lines.append(_line("SLP", pat.measure, pat.tick, pat.duration, _format_official_float(pat.speed), pat.pattern_id))
    if chart.scroll_speeds:
        for spd in chart.scroll_speeds:
            lines.append(_line("SFL", spd.measure, spd.tick, spd.duration, _format_official_float(spd.multiplier)))
    if chart.stops:
        for stop in chart.stops:
            lines.append(_line("STP", stop.measure, stop.tick, stop.duration))
    if chart.decelerations:
        for dec in chart.decelerations:
            lines.append(_line("DCM", dec.measure, dec.tick, dec.duration, _format_official_float(dec.rate)))
    if chart.clicks:
        for click in chart.clicks:
            lines.append(_line("CLK", click.measure, click.tick))
    return lines


def _note_lines(notes: list[Note]) -> list[str]:
    return [_note_line(n) for n in _iter_serializable_notes(notes)]


def _serialize_music_xml(
    meta: ChartMetadata, chart_filename: str, jacket_filename: str = ""
) -> str:
    if not jacket_filename and meta.jacket_path:
        jacket_filename = Path(meta.jacket_path).name
    music_id = _normalized_music_id(meta)
    root = ET.Element(
        "MusicData",
        {
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        },
    )
    _text_node(root, "dataName", f"music{music_id}")
    _string_id(root, "releaseTagName", "0", "Invalid", "")
    _string_id(root, "netOpenName", "0", "Invalid", "")
    _text_node(root, "disableFlag", "false")
    _text_node(root, "exType", "0")
    _text_node(root, "name/id", meta.music_id or "0")
    _text_node(root, "name/str", meta.title or "Untitled")
    _text_node(root, "name/data", "")
    _text_node(root, "sortName", meta.title or "Untitled")
    _text_node(root, "artistName/id", "0")
    _text_node(root, "artistName/str", meta.artist or "Unknown Artist")
    _text_node(root, "artistName/data", "")
    _string_id(root, "genreNames/list/StringID", "0", "ORIGINAL", "")
    _string_id(root, "worksName", "-1", "Invalid", "")
    _string_id(root, "labelName", "-1", "Invalid", "")
    if jacket_filename:
        _text_node(root, "jaketFile/path", jacket_filename)
    else:
        _text_node(root, "jaketFile/path", "")
    _text_node(root, "firstLock", "false")
    _text_node(root, "enableUltima", "true" if _difficulty_id(meta) == 4 else "false")
    _text_node(root, "isGiftMusic", "false")
    _text_node(root, "releaseDate", "20260101")
    _text_node(root, "priority", "0")
    _string_id(root, "cueFileName", music_id, f"music{music_id}", "")
    _string_id(root, "worldsEndTagName", "-1", "Invalid", "")
    _text_node(root, "starDifType", "1")
    _string_id(root, "stageName", "-1", "Invalid", "")

    fumens = ET.SubElement(root, "fumens")
    selected_diff_id = _difficulty_id(meta)
    for diff_id, (type_str, type_data) in DIFFICULTY_ID_TO_MUSIC_TYPE.items():
        fumen = ET.SubElement(fumens, "MusicFumenData")
        _text_node(fumen, "type/id", str(diff_id))
        _text_node(fumen, "type/str", type_str)
        _text_node(fumen, "type/data", type_data)
        enabled = diff_id == selected_diff_id
        _text_node(fumen, "enable", "true" if enabled else "false")
        _text_node(fumen, "file/path", chart_filename if enabled else "")
        if enabled:
            level, decimal = _split_level(meta.level)
        else:
            level, decimal = 0, 0
        _text_node(fumen, "level", str(level))
        _text_node(fumen, "levelDecimal", str(decimal))
        _text_node(fumen, "notesDesigner", meta.creator if enabled else "")
        _text_node(fumen, "defaultBpm", "0")

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(
        root,
        encoding="unicode",
        short_empty_elements=False,
    )
