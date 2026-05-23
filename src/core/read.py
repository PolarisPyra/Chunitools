"""
Core metadata discovery and chart loading logic.

This module provides the primary entry points for scanning local directories for
Chunithm charts and parsing their .c2s contents into internal models.
"""

from __future__ import annotations

import contextlib
import logging
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import replace
from pathlib import Path

logger = logging.getLogger("chartloading")

from src.core.const import Command, NoteType
from src.core.editor_metadata import load_editor_metadata
from src.core.library_models import (
    DirectoryParseResult,
    FumenInfo,
    MetadataPreview,
    SongInfo,
)
from src.core.library_scanner import DataScanner
from src.core.metadata import fast_get_metadata
from src.core.models import (
    Chart,
    Click,
    Deceleration,
    ScrollSpeed,
    SofLanArea,
    SofLanPattern,
    Stop,
)
from src.notes import (
    AirSlide,
    AirSlideStart,
    Note,
    Slide,
    SlideTo,
)
from src.notes.factory import (
    AIR_MODIFIER_NOTE_TYPES,
    AIR_SLIDE_NOTE_TYPES,
    AIR_SUSTAIN_NOTE_TYPES,
    PARSER_NOTE_TYPE_VALUES,
    SLIDE_NOTE_TYPES,
    parse_note,
)
from src.notes.geometry import (
    note_duration,
    note_end_cell,
    note_end_width,
    note_get_steps,
    note_has_steps,
)

__all__ = [
    "FumenInfo",
    "SongInfo",
    "DirectoryParseResult",
    "MetadataPreview",
    "DataScanner",
    "IChartParser",
    "C2sParser",
    "fast_get_metadata",
    "discover_chart_files",
    "parse_c2s",
    "load_chart_file",
    "parse_chart_directory",
]

DEFAULT_CHART_SUFFIXES = (".c2s",)
CUSTOM_AUDIO_COMMAND = "AUDIO"


_SYSTEM_CMD_VALUES: frozenset[str] = frozenset(
    {
        "SLP",
        "SFL",
        "SFE",
        "SLA",
        "STP",
        "DCM",
        "CLK",
    }
)


def _node_text(parent: ET.Element, path: str, default: str = "") -> str:
    node = parent.find(path)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _node_int(parent: ET.Element, path: str, default: int = 0) -> int:
    value = _node_text(parent, path)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_note(note_type: NoteType, args: list[str]) -> Note | None:  # noqa: PLR0911, PLR0912
    """Dispatch note parsing exactly as implemented in nai-rs."""
    return parse_note(note_type, args)


class IChartParser(ABC):
    """Abstract interface for chart parsing strategies.

    Implementations parse chart file content into a :class:`Chart` model,
    encapsulating format-version quirks within concrete subclasses.
    """

    @abstractmethod
    def parse(self, content: str) -> Chart:
        """Parse chart content into a Chart model."""


class C2sParser(IChartParser):
    """Multi-pass .c2s chart parser.

    Encapsulates the complex hierarchical parsing logic:
      1. Tokenization and metadata extraction
      2. Note parsing and slide-segment chaining
      3. Air-note anchor resolution
    """

    def __init__(self) -> None:
        self._chart: Chart | None = None
        self._raw_notes: list[tuple[NoteType, tuple[str, ...]]] = []
        self._seen_raw_notes: set[tuple[NoteType, tuple[str, ...]]] = set()

    def parse(self, content: str) -> Chart:
        self._chart = Chart()
        self._raw_notes.clear()
        self._seen_raw_notes.clear()
        self._tokenize(content)
        self._pass1_parse_notes()
        self._pass2_join_slides()
        self._pass3_anchor_air_notes()
        self._chart.notes.sort(key=lambda n: (n.measure, n.offset, n.cell))
        return self._chart

    @property
    def _active_chart(self) -> Chart:
        if self._chart is None:
            raise RuntimeError("Parser chart is not initialized")
        return self._chart

    # -- Convenience accessors ------------------------------------------------

    @property
    def _resolution(self) -> int:
        return int(self._active_chart.metadata.resolution)

    def _get_tick(self, n: Note) -> int:
        return n.measure * self._resolution + n.offset

    def _get_end_tick(self, n: Note) -> int:
        if note_has_steps(n):
            steps = note_get_steps(n)
            if steps:
                return self._get_end_tick(steps[-1])
        dur = note_duration(n)
        if dur > 0:
            return self._get_tick(n) + dur
        return self._get_tick(n)

    # -- Tokenization (Pass 0) -----------------------------------------------

    def _tokenize(self, content: str) -> None:
        metadata_map = {
            Command.MUSICID.value: "music_id",
            Command.TITLE.value: "title",
            Command.ARTIST.value: "artist",
            Command.VERSION.value: "version",
            Command.VERS.value: "version",
            Command.MUSIC.value: "music_id",
            Command.SEQUENCEID.value: "sequence_id",
            Command.DIFFICULT.value: "difficulty",
            Command.LEVEL.value: "level",
            Command.CREATOR.value: "creator",
            Command.RESOLUTION.value: "resolution",
            Command.CLK_DEF.value: "clk_def",
            Command.PROGJUDGE_BPM.value: "progjudge_bpm",
            Command.PROGJUDGE_AER.value: "progjudge_aer",
            Command.TUTORIAL.value: "tutorial",
            Command.WENAME.value: "we_name",
            Command.WELEVEL.value: "we_level",
        }

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            command_str, args = parts[0], parts[1:]

            if command_str in metadata_map:
                _handle_metadata_command(self._active_chart, command_str, args, metadata_map)
            elif command_str == Command.BPM_DEF.value:
                self._active_chart.metadata.bpm_def = args
            elif command_str == Command.MET_DEF.value:
                _handle_met_def_command(self._active_chart, args)
            elif command_str == Command.BPM.value:
                _handle_bpm_command(self._active_chart, args)
            elif command_str == Command.MET.value:
                _handle_met_command(self._active_chart, args)
            elif command_str == CUSTOM_AUDIO_COMMAND and args:
                self._active_chart.metadata.audio_path = " ".join(args).strip()
            elif command_str in _SYSTEM_CMD_VALUES:
                _handle_system_command(self._active_chart, command_str, args)
            elif command_str in PARSER_NOTE_TYPE_VALUES:
                try:
                    nt = NoteType(command_str)
                    raw_note = (nt, tuple(args))
                    if raw_note not in self._seen_raw_notes:
                        self._seen_raw_notes.add(raw_note)
                        self._raw_notes.append(raw_note)
                except ValueError:
                    continue

    # -- Pass 1: Initial note parsing -----------------------------------------

    def _pass1_parse_notes(self) -> None:
        self._ground_notes: list[Note] = []
        self._slide_segments: list[SlideTo] = []
        self._air_slide_segments: list[AirSlide] = []
        self._air_modifiers: list[tuple[NoteType, tuple[str, ...]]] = []
        self._air_sustains: list[Note] = []

        for nt, args_tuple in self._raw_notes:
            args = list(args_tuple)
            if nt in SLIDE_NOTE_TYPES:
                note = _parse_note(nt, args)
                if isinstance(note, SlideTo):
                    self._slide_segments.append(note)
            elif nt in AIR_SLIDE_NOTE_TYPES:
                note = _parse_note(nt, args)
                if isinstance(note, AirSlide):
                    self._air_slide_segments.append(note)
            elif nt in AIR_MODIFIER_NOTE_TYPES:
                self._air_modifiers.append((nt, args_tuple))
            else:
                note = _parse_note(nt, args)
                if note:
                    if nt in AIR_SUSTAIN_NOTE_TYPES:
                        self._air_sustains.append(note)
                    else:
                        self._ground_notes.append(note)

    # -- Pass 2: Slide-segment chaining ---------------------------------------

    def _pass2_join_slides(self) -> None:
        self._target_note_families = {
            NoteType.HLD: frozenset({NoteType.HLD, NoteType.HXD}),
            NoteType.SLD: frozenset({NoteType.SLD, NoteType.SXD, NoteType.SLC, NoteType.SXC}),
            NoteType.ASD: frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX}),
            NoteType.ASC: frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX}),
            NoteType.ASX: frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX}),
        }
        self._used_slide_segments: set[SlideTo] = set()
        self._used_air_slide_segments: set[AirSlide] = set()
        self._joined_slides = self._join_slide_segments()
        self._joined_air_slides = self._join_air_slide_segments()

    def _matches_target_note(self, candidate: Note, target_type: str) -> bool:
        try:
            required_type = NoteType(target_type)
        except ValueError:
            return False
        return candidate.note_type in self._target_note_families.get(
            required_type, frozenset({required_type})
        )

    def _join_slide_segments(self) -> list[Slide]:
        self._slide_segments.sort(key=lambda s: (self._get_tick(s), s.cell, s.width))
        joined: list[Slide] = []
        used = self._used_slide_segments

        for i, start_seg in enumerate(self._slide_segments):
            if start_seg in used:
                continue
            chain = [start_seg]
            used.add(start_seg)
            current = start_seg

            while True:
                end_tick = self._get_end_tick(current)
                end_cell = current.end_cell
                end_width = current.end_width
                found = False
                for j in range(i + 1, len(self._slide_segments)):
                    nxt = self._slide_segments[j]
                    if nxt in used:
                        continue
                    if (
                        self._get_tick(nxt) == end_tick
                        and nxt.cell == end_cell
                        and nxt.width == end_width
                    ):
                        chain.append(nxt)
                        used.add(nxt)
                        current = nxt
                        found = True
                        break
                    if self._get_tick(nxt) > end_tick:
                        break
                if not found:
                    break

            joined.append(
                Slide(
                    note_type=start_seg.note_type,
                    measure=start_seg.measure,
                    offset=start_seg.offset,
                    cell=start_seg.cell,
                    width=start_seg.width,
                    steps=tuple(chain),
                )
            )

        orphan_slides = [s for s in self._slide_segments if s not in used]
        if orphan_slides:
            self._active_chart._warnings.append(
                f"{len(orphan_slides)} slide segment(s) could not be chained "
                f"(no matching successor at end position)"
            )
        return joined

    def _join_air_slide_segments(self) -> list[AirSlideStart]:  # noqa: PLR0912
        self._air_slide_segments.sort(key=lambda s: (self._get_tick(s), s.cell, s.width))
        joined: list[AirSlideStart] = []
        used = self._used_air_slide_segments

        for i, start_seg in enumerate(self._air_slide_segments):
            if start_seg in used:
                continue
            chain: list[AirSlide] = [start_seg]
            used.add(start_seg)
            current = start_seg

            while True:
                end_tick = self._get_end_tick(current)
                end_cell = current.end_cell
                end_width = current.end_width
                candidates: list[AirSlide] = []
                for j in range(i + 1, len(self._air_slide_segments)):
                    nxt = self._air_slide_segments[j]
                    if nxt in used:
                        continue
                    if (
                        self._get_tick(nxt) == end_tick
                        and abs(float(nxt.cell) - end_cell) < 0.1
                        and abs(float(nxt.width) - end_width) < 0.1
                    ):
                        candidates.append(nxt)
                    if self._get_tick(nxt) > end_tick:
                        break
                if not candidates:
                    break
                best: AirSlide | None = None
                for cand in candidates:
                    if cand.target_note == current.note_type.value:
                        best = cand
                        break
                if not best:
                    best = candidates[0]
                chain.append(best)
                used.add(best)
                current = best

            joined.append(
                AirSlideStart(
                    note_type=start_seg.note_type,
                    measure=start_seg.measure,
                    offset=start_seg.offset,
                    cell=start_seg.cell,
                    width=start_seg.width,
                    steps=tuple(chain),
                )
            )

        orphan_air = [s for s in self._air_slide_segments if s not in used]
        if orphan_air:
            self._active_chart._warnings.append(
                f"{len(orphan_air)} air slide segment(s) could not be chained "
                f"(no matching successor at end position)"
            )
        return joined

    # -- Pass 3: Air-note anchoring -------------------------------------------

    def _pass3_anchor_air_notes(self) -> None:  # noqa: PLR0912, PLR0915
        remaining: list[AirSlide] = [
            s for s in self._air_slide_segments if s not in self._used_air_slide_segments
        ]
        all_potential_anchors: list[Note] = [
            *self._ground_notes,
            *self._joined_slides,
            *(n for n in self._air_sustains if n.note_type != NoteType.ALD),
            *self._joined_air_slides,
            *remaining,
        ]

        anchor_lookup: dict[tuple[int, int, int], list[Note]] = {}

        def add_anchor(tick: int, cell: int, width: int, n: Note) -> None:
            k = (tick, cell, width)
            anchor_lookup.setdefault(k, []).append(n)

        for n in all_potential_anchors:
            add_anchor(self._get_tick(n), n.cell, n.width, n)
            if note_has_steps(n):
                for step in note_get_steps(n):
                    add_anchor(
                        self._get_end_tick(step),
                        note_end_cell(step),
                        note_end_width(step),
                        step,
                    )
            else:
                dur = note_duration(n)
                if dur > 0:
                    ec = note_end_cell(n)
                    ew = note_end_width(n)
                    add_anchor(self._get_end_tick(n), ec, ew, n)

        final_notes: list[Note] = []

        # 3.1 Anchor joined air slides
        for note in self._joined_air_slides:
            tick = self._get_tick(note)
            k = (tick, note.cell, note.width)
            candidates = anchor_lookup.get(k, [])
            anchor = None
            target_type = getattr(note, "target_note", "DEF")
            if target_type == "DEF":
                if candidates:
                    anchor = candidates[0]
            else:
                for cand in candidates:
                    if self._matches_target_note(cand, target_type):
                        anchor = cand
                        break
            if anchor:
                note_obj = replace(note, parent=anchor)
            else:
                note_obj = note
            final_notes.append(note_obj)

        # 3.2 Anchor individual remaining segments
        for seg in remaining:
            tick = self._get_tick(seg)
            k = (tick, seg.cell, seg.width)
            candidates = anchor_lookup.get(k, [])
            anchor = None
            target_type = seg.target_note
            if target_type == "DEF":
                filtered = [c for c in candidates if c is not seg]
                if filtered:
                    anchor = filtered[0]
            else:
                for cand in candidates:
                    if cand is not seg and self._matches_target_note(cand, target_type):
                        anchor = cand
                        break
            if anchor:
                seg_obj = replace(seg, parent=anchor)
            else:
                seg_obj = seg
            final_notes.append(seg_obj)

        # 3.3 Add non-air notes
        final_notes.extend(self._ground_notes)
        final_notes.extend(self._joined_slides)
        final_notes.extend(self._air_sustains)

        # 3.4 Anchor air modifiers
        for nt, args_tuple in self._air_modifiers:
            args = list(args_tuple)
            note = _parse_note(nt, args)
            if not note:
                continue
            tick = self._get_tick(note)
            k = (tick, note.cell, note.width)
            candidates = anchor_lookup.get(k, [])
            anchor = None
            target_type = getattr(note, "target_note", "DEF")
            if target_type == "DEF":
                if candidates:
                    anchor = candidates[0]
            else:
                for cand in candidates:
                    if self._matches_target_note(cand, target_type):
                        anchor = cand
                        break
            if anchor:
                note = replace(note, parent=anchor)
            final_notes.append(note)

        self._active_chart.notes = final_notes


def parse_c2s(content: str) -> Chart:
    """Parse a complete .c2s file using a hierarchical multi-pass approach."""
    return C2sParser().parse(content)


def discover_chart_files(
    root: str | Path, suffixes: tuple[str, ...] = DEFAULT_CHART_SUFFIXES
) -> list[Path]:
    base = Path(root)
    if not base.exists():
        return []
    files = [path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in suffixes]
    files.sort()
    return files


DIFFICULTY_NAMES: dict[int, str] = {
    0: "BASIC",
    1: "ADVANCED",
    2: "EXPERT",
    3: "MASTER",
    4: "WORLD'S END",
    5: "ULTIMA",
}


def _handle_metadata_command(
    chart: Chart, command: str, args: list[str], metadata_map: dict[str, str]
) -> None:
    if command not in metadata_map or not args:
        return

    attribute_name = metadata_map[command]
    if attribute_name in ("creator", "title", "artist"):
        setattr(chart.metadata, attribute_name, " ".join(args))
    elif attribute_name in ("resolution", "clk_def"):
        with contextlib.suppress(ValueError, TypeError):
            setattr(chart.metadata, attribute_name, int(float(args[0])))
    elif attribute_name in ("progjudge_bpm", "progjudge_aer"):
        with contextlib.suppress(ValueError, TypeError):
            setattr(chart.metadata, attribute_name, float(args[0]))
    elif attribute_name == "difficulty":
        try:
            diff_id = int(float(args[0]))
            chart.metadata.difficulty_id = diff_id
            chart.metadata.difficulty = DIFFICULTY_NAMES.get(diff_id, str(diff_id))
        except (ValueError, TypeError):
            chart.metadata.difficulty = args[0]
    elif attribute_name == "we_level":
        with contextlib.suppress(ValueError, TypeError):
            chart.metadata.we_level = int(float(args[0]))
    elif attribute_name == "tutorial":
        chart.metadata.tutorial = args[0] == "1"
    else:
        setattr(chart.metadata, attribute_name, args[0])


def _handle_bpm_command(chart: Chart, args: list[str]) -> None:
    if len(args) < 3:
        return

    try:
        measure = int(float(args[0]))
        offset = int(float(args[1]))
        bpm_value = float(args[2])
    except ValueError:
        return

    if measure >= 0 and offset >= 0 and bpm_value > 0:
        chart.bpms.append({"measure": measure, "offset": offset, "bpm": bpm_value})


def _handle_met_def_command(chart: Chart, args: list[str]) -> None:
    if len(args) < 2:
        return
    try:
        num = int(float(args[0]))
        den = int(float(args[1]))
        chart.metadata.met_def = (num, den)
    except (ValueError, TypeError):
        pass


def _handle_met_command(chart: Chart, args: list[str]) -> None:
    if len(args) < 3:
        return
    try:
        measure = int(float(args[0]))
        if len(args) >= 4:
            num = int(float(args[2]))
            den = int(float(args[3]))
        else:
            num = int(float(args[1]))
            den = int(float(args[2]))
        chart.signatures.append({"measure": measure, "numerator": num, "denominator": den})
    except (ValueError, TypeError):
        pass


def _handle_note_command(chart: Chart, command_str: str, args: list[str]) -> None:
    try:
        note_type_enum = NoteType(command_str)
    except ValueError:
        return

    note = _parse_note(note_type_enum, args)
    if note is not None:
        chart.notes.append(note)


def _handle_system_command(chart: Chart, command_str: str, args: list[str]) -> None:
    try:
        if command_str == "SLA":
            chart.soflan_areas.append(
                SofLanArea(
                    measure=int(float(args[0])),
                    tick=int(float(args[1])),
                    cell=int(float(args[2])),
                    width=int(float(args[3])),
                    duration=int(float(args[4])),
                    area_id=int(float(args[5])),
                )
            )
        elif command_str == "SLP":
            chart.soflan_patterns.append(
                SofLanPattern(
                    measure=int(float(args[0])),
                    tick=int(float(args[1])),
                    duration=int(float(args[2])),
                    speed=float(args[3]),
                    pattern_id=int(float(args[4])),
                )
            )
        elif command_str in ("SFL", "SFE"):
            chart.scroll_speeds.append(
                ScrollSpeed(
                    measure=int(float(args[0])),
                    tick=int(float(args[1])),
                    duration=int(float(args[2])),
                    multiplier=float(args[3]),
                )
            )
        elif command_str == "STP":
            chart.stops.append(
                Stop(
                    measure=int(float(args[0])),
                    tick=int(float(args[1])),
                    duration=int(float(args[2])),
                )
            )
        elif command_str == "DCM":
            chart.decelerations.append(
                Deceleration(
                    measure=int(float(args[0])),
                    tick=int(float(args[1])),
                    duration=int(float(args[2])),
                    rate=float(args[3]),
                )
            )
        elif command_str == "CLK":
            chart.clicks.append(
                Click(
                    measure=int(float(args[0])),
                    tick=int(float(args[1])),
                )
            )
    except (ValueError, IndexError, TypeError):
        pass


# (parse_c2s is now delegated to C2sParser above)


def load_chart_file(path: str | Path) -> Chart:
    source_path = Path(path)
    try:
        text = source_path.read_text(encoding="utf-8")
        chart = parse_c2s(text)
        _apply_music_id_from_filename(chart, source_path)
        _resolve_metadata_from_xml(chart, source_path)
        load_editor_metadata(chart, source_path)
        _resolve_custom_audio_path(chart, source_path)
        if not chart.metadata.jacket_path:
            chart.metadata.jacket_path = _find_jacket_art(chart, source_path)
    except Exception:
        logger.exception("Failed to load chart file: %s", source_path)
        raise

    _log_chart_diagnostics(chart, source_path)
    return chart


def _log_chart_diagnostics(chart: Chart, source_path: Path) -> None:
    try:
        timeline = chart.timeline
    except Exception:
        logger.exception("Failed to build chart timeline for %s", source_path)
        return

    warnings = chart.warnings
    if not warnings:
        return

    logger.warning(
        "Chart diagnostics for %s: %d warning(s), %d notes, max_measure=%d",
        source_path,
        len(warnings),
        len(chart.notes),
        timeline.calculate_max_measure(),
    )
    for warning in warnings:
        logger.warning("%s", warning)


def _resolve_custom_audio_path(chart: Chart, source_path: Path) -> None:
    if not chart.metadata.audio_path:
        return
    audio_path = Path(chart.metadata.audio_path)
    if audio_path.is_absolute():
        return
    resolved = source_path.parent / audio_path
    if resolved.exists():
        chart.metadata.audio_path = str(resolved)


def _resolve_metadata_from_xml(chart: Chart, source_path: Path) -> None:  # noqa: PLR0912
    """Attempt to fill missing metadata (title, artist) from Music.xml."""
    xml_path = source_path.parent / "Music.xml"
    if not xml_path.exists():
        return

    try:
        root = ET.parse(xml_path).getroot()

        # Resolve Title if missing or placeholder
        if chart.metadata.title in {"", "Untitled"}:
            name_str = root.findtext("name/str")
            if name_str:
                chart.metadata.title = name_str.strip()

        # Resolve Artist if missing
        if not chart.metadata.artist:
            artist_str = root.findtext("artistName/str")
            if artist_str:
                chart.metadata.artist = artist_str.strip()

        # Resolve Music ID if missing
        if chart.metadata.music_id in {"", "0"}:
            music_id = root.findtext("name/id")
            if music_id:
                chart.metadata.music_id = music_id.strip()

        # Resolve Level & Difficulty by matching filename in <fumens>
        fumens_node = root.find("fumens")
        if fumens_node is not None:
            current_filename = source_path.name
            for fumen_node in fumens_node.findall("MusicFumenData"):
                fumen_file = fumen_node.findtext("file/path")
                if fumen_file and fumen_file.strip() == current_filename:
                    # Match found!
                    diff_name = fumen_node.findtext("type/str")
                    if diff_name:
                        chart.metadata.difficulty = diff_name.strip()

                    level = fumen_node.findtext("level")
                    decimal = fumen_node.findtext("levelDecimal")
                    if level:
                        level_str = level.strip()
                        try:
                            if decimal and int(decimal.strip()) >= 50:
                                level_str += "+"
                        except (ValueError, TypeError):
                            pass
                        chart.metadata.level = level_str
                    break

    except (ET.ParseError, OSError):
        pass


def _find_jacket_art(chart: Chart, source_path: Path) -> str:
    """Find arcade-style jacket art (.dds) for the given chart."""
    # Pattern: .../music/music{id}/CHU_UI_Jacket_{id}.dds
    music_id = chart.metadata.music_id
    if not music_id:
        return ""

    # Check same directory as chart
    parent_dir = source_path.parent
    jacket_name = f"CHU_UI_Jacket_{music_id}.dds"
    jacket_path = parent_dir / jacket_name

    if jacket_path.exists():
        return str(jacket_path)

    # Fallback: check if the parent directory matches music{id} pattern and search there
    # This handles cases where the chart might be in a subdirectory or named differently
    match = re.search(r"music(\d+)", str(parent_dir))
    if match:
        dir_id = match.group(1)
        fallback_name = f"CHU_UI_Jacket_{dir_id}.dds"
        fallback_path = parent_dir / fallback_name
        if fallback_path.exists():
            return str(fallback_path)

    return ""


def _apply_music_id_from_filename(chart: Chart, source_path: Path) -> None:
    if chart.metadata.music_id not in {"", "0"}:
        return

    music_id = source_path.stem.split("_", maxsplit=1)[0]
    if music_id.isdecimal():
        chart.metadata.music_id = music_id


def parse_chart_directory(
    root: str | Path, suffixes: tuple[str, ...] = DEFAULT_CHART_SUFFIXES
) -> DirectoryParseResult:
    result = DirectoryParseResult()
    files = discover_chart_files(root, suffixes=suffixes)
    result.total_files = len(files)
    for file_path in files:
        try:
            chart = load_chart_file(file_path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            result.failed_files.append((file_path, str(exc)))
            continue
        result.parsed_files += 1
        result.total_notes += len(chart.notes)
        result.total_warnings += len(chart.warnings)
    return result
