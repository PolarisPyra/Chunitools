"""
Core metadata discovery and chart loading logic.

This module provides the primary entry points for scanning local directories for
Chunithm charts and parsing their .c2s contents into internal models.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger("chartloading")

from src.core.editor_metadata import load_editor_metadata
from src.core.models import (
    Chart,
    Click,
    Deceleration,
    SofLanArea,
    SofLanPattern,
    ScrollSpeed,
    Stop,
)
from src.core.const import Command, NoteType
from src.core.library_models import (
    DirectoryParseResult,
    FumenInfo,
    MetadataPreview,
    SongInfo,
)
from src.core.library_scanner import DataScanner
from src.notes import (
    AirHoldStart,
    Air,
    AirHold,
    AirSlideStart,
    CrashSlide,
    AirSlide,
    AirSolid,
    ExTap,
    Flick,
    HeavenHold,
    Hold,
    Mine,
    Note,
    Slide,
    SlideTo,
    Tap,
)
from src.core.metadata import fast_get_metadata

__all__ = [
    "FumenInfo",
    "SongInfo",
    "DirectoryParseResult",
    "MetadataPreview",
    "DataScanner",
    "fast_get_metadata",
    "discover_chart_files",
    "parse_c2s",
    "load_chart_file",
    "parse_chart_directory",
]

DEFAULT_CHART_SUFFIXES = (".c2s",)
CUSTOM_AUDIO_COMMAND = "AUDIO"


# All note-type tokens recognised as playfield objects.
_NOTE_CMDS: frozenset[NoteType] = frozenset(
    [
        NoteType.TAP,
        NoteType.CHR,
        NoteType.HLD,
        NoteType.HXD,
        NoteType.SLD,
        NoteType.SLC,
        NoteType.SXD,
        NoteType.SXC,
        NoteType.FLK,
        NoteType.AIR,
        NoteType.AUR,
        NoteType.AUL,
        NoteType.AHD,
        NoteType.ADW,
        NoteType.ADR,
        NoteType.ADL,
        NoteType.ALD,
        NoteType.ASD,
        NoteType.ASC,
        NoteType.ASX,
        NoteType.AHX,
        NoteType.ASO,
        NoteType.HHD,
        NoteType.HHX,
        NoteType.MNE,
    ]
)
_NOTE_CMD_VALUES: frozenset[str] = frozenset(note_type.value for note_type in _NOTE_CMDS)

_SYSTEM_CMD_VALUES: frozenset[str] = frozenset({
    "SLP",
    "SFL",
    "SFE",
    "SLA",
    "STP",
    "DCM",
    "CLK",
})
SLIDE_NOTE_TYPES: frozenset[NoteType] = frozenset(
    {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC}
)
AIR_SLIDE_NOTE_TYPES: frozenset[NoteType] = frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX})
AIR_MODIFIER_NOTE_TYPES: frozenset[NoteType] = frozenset(
    {NoteType.AIR, NoteType.AUR, NoteType.AUL, NoteType.ADW, NoteType.ADR, NoteType.ADL}
)
AIR_SUSTAIN_NOTE_TYPES: frozenset[NoteType] = frozenset(
    {NoteType.AHD, NoteType.ALD, NoteType.AHX}
)


class _NoteHead(TypedDict):
    measure: int
    offset: int
    cell: int
    width: int
    data: tuple[str, ...]


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


def _parse_int(value: str) -> int:
    return int(float(value))


def _valid_position(cell: int, width: int) -> bool:
    return 0 <= cell <= 15 and 1 <= width <= 16 and cell + width <= 16


def _parse_note_head(args: list[str]) -> _NoteHead | None:
    if len(args) < 4:
        return None

    try:
        measure = _parse_int(args[0])
        offset = _parse_int(args[1])
        cell = _parse_int(args[2])
        width = _parse_int(args[3])
    except ValueError:
        return None

    if measure < 0 or offset < 0 or not _valid_position(cell, width):
        return None

    return {
        "measure": measure,
        "offset": offset,
        "cell": cell,
        "width": width,
        "data": tuple(args[4:]),
    }


def _parse_note(note_type: NoteType, args: list[str]) -> Note | None:
    """Dispatch note parsing exactly as implemented in nai-rs."""
    if len(args) < 4:
        return None

    try:
        measure = int(float(args[0]))
        offset = int(float(args[1]))
        cell = int(float(args[2]))
        width = int(float(args[3]))
        data = args[4:]

        if note_type == NoteType.TAP:
            return Tap(note_type=note_type, measure=measure, offset=offset, cell=cell, width=width)
        
        if note_type == NoteType.MNE:
            return Mine(note_type=note_type, measure=measure, offset=offset, cell=cell, width=width)

        if note_type == NoteType.ASO:
            return AirSolid(
                note_type=note_type,
                measure=measure,
                offset=offset,
                cell=cell,
                width=width,
                starting_height=float(data[0]),
                starting_depth=float(data[1]),
                duration=int(float(data[2])),
                end_cell=int(float(data[3])),
                end_width=int(float(data[4])),
                target_height=float(data[5]),
                target_depth=float(data[6]),
                color=data[7],
            )

        if note_type in (NoteType.HHD, NoteType.HHX):
            return HeavenHold(
                note_type=note_type,
                measure=measure,
                offset=offset,
                cell=cell,
                width=width,
                starting_height=float(data[0]),
                duration=int(float(data[1])),
                end_cell=int(float(data[2])),
                end_width=int(float(data[3])),
                target_height=float(data[4]),
                heaven_id=int(float(data[5])),
                animation=data[6] if len(data) > 6 else None,
            )

        if note_type == NoteType.CHR:
            return ExTap(note_type=note_type, measure=measure, offset=offset, cell=cell, width=width, unknown=data[0])

        if note_type in (NoteType.HLD, NoteType.HXD):
            duration = int(float(data[0]))
            animation = data[1] if len(data) > 1 else None
            return Hold(note_type=note_type, measure=measure, offset=offset, cell=cell, width=width, duration=duration, animation=animation)

        if note_type in (NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC):
            duration = int(float(data[0]))
            end_cell = int(float(data[1]))
            end_width = int(float(data[2]))
            target_id = data[3] if len(data) > 3 else None
            animation = data[4] if len(data) > 4 else None
            is_visible = note_type.endswith("D")
            return SlideTo(
                note_type=note_type,
                measure=measure,
                offset=offset,
                cell=cell,
                width=width,
                duration=duration,
                end_cell=end_cell,
                end_width=end_width,
                target_id=target_id,
                animation=animation,
                is_visible=is_visible,
            )

        if note_type == NoteType.FLK:
            return Flick(note_type=note_type, measure=measure, offset=offset, cell=cell, width=width, unknown=data[0])

        if note_type == NoteType.AIR:
            color = data[1] if len(data) > 1 else "DEF"
            return Air(
                note_type=note_type,
                measure=measure,
                offset=offset,
                cell=cell,
                width=width,
                target_note=data[0],
                color=color,
            )

        if note_type in (NoteType.AUR, NoteType.AUL, NoteType.ADW, NoteType.ADR, NoteType.ADL):
            color = data[1] if len(data) > 1 else "DEF"
            return Air(note_type=note_type, measure=measure, offset=offset, cell=cell, width=width, target_note=data[0], color=color)

        if note_type == NoteType.AHD:
            return AirHoldStart(note_type=note_type, measure=measure, offset=offset, cell=cell, width=width, target_note=data[0], duration=int(float(data[1])))

        if note_type == NoteType.AHX:
            return AirHold(
                note_type=note_type, measure=measure, offset=offset, cell=cell, width=width,
                target_note=data[0], duration=int(float(data[1])), color=data[2] if len(data) > 2 else "DEF"
            )

        if note_type == NoteType.ALD:
            return CrashSlide(
                note_type=note_type, measure=measure, offset=offset, cell=cell, width=width,
                crush_interval=int(float(data[0])),
                starting_height=float(data[1]),
                duration=int(float(data[2])),
                end_cell=int(float(data[3])),
                end_width=int(float(data[4])),
                target_height=float(data[5]),
                color=data[6]
            )

        if note_type in (NoteType.ASD, NoteType.ASC, NoteType.ASX):
            return AirSlide(
                note_type=note_type, measure=measure, offset=offset, cell=cell, width=width,
                target_note=data[0],
                starting_height=float(data[1]),
                duration=int(float(data[2])),
                end_cell=int(float(data[3])),
                end_width=int(float(data[4])),
                target_height=float(data[5]),
                color=data[6]
            )

    except (ValueError, TypeError, IndexError):
        return None

    return None


def discover_chart_files(
    root: str | Path, suffixes: tuple[str, ...] = DEFAULT_CHART_SUFFIXES
) -> list[Path]:
    base = Path(root)
    if not base.exists():
        return []
    files = [
        path for path in base.rglob("*") if path.is_file() and path.suffix.lower() in suffixes
    ]
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
        try:
            setattr(chart.metadata, attribute_name, int(float(args[0])))
        except (ValueError, TypeError):
            pass
    elif attribute_name in ("progjudge_bpm", "progjudge_aer"):
        try:
            setattr(chart.metadata, attribute_name, float(args[0]))
        except (ValueError, TypeError):
            pass
    elif attribute_name == "difficulty":
        try:
            diff_id = int(float(args[0]))
            chart.metadata.difficulty_id = diff_id
            chart.metadata.difficulty = DIFFICULTY_NAMES.get(diff_id, str(diff_id))
        except (ValueError, TypeError):
            chart.metadata.difficulty = args[0]
    elif attribute_name == "we_level":
        try:
            chart.metadata.we_level = int(float(args[0]))
        except (ValueError, TypeError):
            pass
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
            chart.soflan_areas.append(SofLanArea(
                measure=int(float(args[0])),
                tick=int(float(args[1])),
                cell=int(float(args[2])),
                width=int(float(args[3])),
                duration=int(float(args[4])),
                area_id=int(float(args[5])),
            ))
        elif command_str == "SLP":
            chart.soflan_patterns.append(SofLanPattern(
                measure=int(float(args[0])),
                tick=int(float(args[1])),
                duration=int(float(args[2])),
                speed=float(args[3]),
                pattern_id=int(float(args[4])),
            ))
        elif command_str in ("SFL", "SFE"):
            chart.scroll_speeds.append(ScrollSpeed(
                measure=int(float(args[0])),
                tick=int(float(args[1])),
                duration=int(float(args[2])),
                multiplier=float(args[3]),
            ))
        elif command_str == "STP":
            chart.stops.append(Stop(
                measure=int(float(args[0])),
                tick=int(float(args[1])),
                duration=int(float(args[2])),
            ))
        elif command_str == "DCM":
            chart.decelerations.append(Deceleration(
                measure=int(float(args[0])),
                tick=int(float(args[1])),
                duration=int(float(args[2])),
                rate=float(args[3]),
            ))
        elif command_str == "CLK":
            chart.clicks.append(Click(
                measure=int(float(args[0])),
                tick=int(float(args[1])),
            ))
    except (ValueError, IndexError, TypeError):
        pass


def parse_c2s(content: str) -> Chart:
    """Parse a complete .c2s file using a hierarchical multi-pass approach."""
    chart = Chart()
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


    raw_notes: list[tuple[NoteType, tuple[str, ...]]] = []
    seen_raw_notes: set[tuple[NoteType, tuple[str, ...]]] = set()

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split("\t")
        command_str, args = parts[0], parts[1:]

        if command_str in metadata_map:
            _handle_metadata_command(chart, command_str, args, metadata_map)
        elif command_str == Command.BPM_DEF.value:
            chart.metadata.bpm_def = args
        elif command_str == Command.MET_DEF.value:
            _handle_met_def_command(chart, args)
        elif command_str == Command.BPM.value:
            _handle_bpm_command(chart, args)
        elif command_str == Command.MET.value:
            _handle_met_command(chart, args)
        elif command_str == CUSTOM_AUDIO_COMMAND and args:
            chart.metadata.audio_path = " ".join(args).strip()
        elif command_str in _SYSTEM_CMD_VALUES:
            _handle_system_command(chart, command_str, args)
        elif command_str in _NOTE_CMD_VALUES:
            try:
                nt = NoteType(command_str)
                # Deduplicate exact identical lines to avoid extra overlapping notes
                raw_note = (nt, tuple(args))
                if raw_note not in seen_raw_notes:
                    seen_raw_notes.add(raw_note)
                    raw_notes.append(raw_note)
            except ValueError:
                continue

    # Pass 1: Initial Parsing
    ground_notes: list[Note] = []
    slide_segments: list[SlideTo] = []
    air_slide_segments: list[AirSlide] = []
    # Only AIR arrows need anchoring; sustains are potential anchors themselves.
    air_modifiers: list[tuple[NoteType, tuple[str, ...]]] = []
    air_sustains: list[Note] = []

    for nt, args_tuple in raw_notes:
        args = list(args_tuple)
        if nt in SLIDE_NOTE_TYPES:
            note = _parse_note(nt, args)
            if isinstance(note, SlideTo):
                slide_segments.append(note)
        elif nt in AIR_SLIDE_NOTE_TYPES:
            note = _parse_note(nt, args)
            if isinstance(note, AirSlide):
                air_slide_segments.append(note)
        elif nt in AIR_MODIFIER_NOTE_TYPES:
            air_modifiers.append((nt, args_tuple))
        else:
            note = _parse_note(nt, args)
            if note:
                if nt in AIR_SUSTAIN_NOTE_TYPES:
                    air_sustains.append(note)
                else:
                    ground_notes.append(note)

    res = int(chart.metadata.resolution)

    def get_tick(n: Note) -> int:
        return n.measure * res + n.offset

    def get_end_tick(n: Note) -> int:
        if isinstance(n, (Slide, AirSlideStart)):
            return get_end_tick(n.steps[-1])
        if hasattr(n, "duration"):
            return get_tick(n) + getattr(n, "duration")
        return get_tick(n)

    target_note_families = {
        NoteType.HLD: frozenset({NoteType.HLD, NoteType.HXD}),
        NoteType.SLD: frozenset({NoteType.SLD, NoteType.SXD, NoteType.SLC, NoteType.SXC}),
        NoteType.ASD: frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX}),
        NoteType.ASC: frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX}),
        NoteType.ASX: frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX}),
    }

    def matches_target_note(candidate: Note, target_type: str) -> bool:
        try:
            required_type = NoteType(target_type)
        except ValueError:
            return False
        return candidate.note_type in target_note_families.get(
            required_type, frozenset({required_type})
        )

    # Pass 2: Join Slide Segments
    # Sort segments by start tick
    slide_segments.sort(key=lambda s: (get_tick(s), s.cell, s.width))
    
    joined_slides: list[Slide] = []
    used_segments: set[SlideTo] = set()

    for i, slide_start_segment in enumerate(slide_segments):
        if slide_start_segment in used_segments:
            continue
        
        # Start a new slide chain
        slide_chain = [slide_start_segment]
        used_segments.add(slide_start_segment)
        
        current_slide_segment = slide_start_segment
        while True:
            # Look for a segment that starts where curr ends
            end_tick = get_end_tick(current_slide_segment)
            end_cell = current_slide_segment.end_cell
            end_width = current_slide_segment.end_width
            
            found = False
            # Search forward from current position
            for j in range(i + 1, len(slide_segments)):
                next_seg = slide_segments[j]
                if next_seg in used_segments:
                    continue
                
                if (get_tick(next_seg) == end_tick and 
                    next_seg.cell == end_cell and 
                    next_seg.width == end_width):
                    slide_chain.append(next_seg)
                    used_segments.add(next_seg)
                    current_slide_segment = next_seg
                    found = True
                    break
                
                # Since segments are sorted by tick, we can stop early if we've passed end_tick
                if get_tick(next_seg) > end_tick:
                    break
            
            if not found:
                break
        
        # Create a Slide from the chain
        joined_slide = Slide(
            note_type=slide_start_segment.note_type,
            measure=slide_start_segment.measure,
            offset=slide_start_segment.offset,
            cell=slide_start_segment.cell,
            width=slide_start_segment.width,
            steps=tuple(slide_chain)
        )
        joined_slides.append(joined_slide)

    # Pass 2.1: Join Air Slide Segments (Restored to its logical place)
    air_slide_segments.sort(key=lambda s: (get_tick(s), s.cell, s.width))
    joined_air_slides: list[AirSlideStart] = []
    used_air_segments: set[AirSlide] = set()

    for i, air_start_segment in enumerate(air_slide_segments):
        if air_start_segment in used_air_segments:
            continue
        
        air_chain: list[AirSlide] = [air_start_segment]
        used_air_segments.add(air_start_segment)
        
        current_air_segment = air_start_segment
        while True:
            end_tick = get_end_tick(current_air_segment)
            end_cell = current_air_segment.end_cell
            end_width = current_air_segment.end_width
            
            air_candidates: list[AirSlide] = []
            for j in range(i + 1, len(air_slide_segments)):
                next_air_segment = air_slide_segments[j]
                if next_air_segment in used_air_segments:
                    continue
                if get_tick(next_air_segment) == end_tick:
                    if abs(float(next_air_segment.cell) - end_cell) < 0.1 and abs(float(next_air_segment.width) - end_width) < 0.1:
                        air_candidates.append(next_air_segment)
                if get_tick(next_air_segment) > end_tick:
                    break
            
            if air_candidates:
                best_next: AirSlide | None = None
                for cand in air_candidates:
                    if cand.target_note == current_air_segment.note_type.value:
                        best_next = cand
                        break
                
                if not best_next:
                    best_next = air_candidates[0]
                
                air_chain.append(best_next)
                used_air_segments.add(best_next)
                current_air_segment = best_next
                found = True
            else:
                found = False
            
            if not found:
                break
        
        air_slide = AirSlideStart(
            note_type=air_start_segment.note_type,
            measure=air_start_segment.measure,
            offset=air_start_segment.offset,
            cell=air_start_segment.cell,
            width=air_start_segment.width,
            steps=tuple(air_chain)
        )
        joined_air_slides.append(air_slide)

    # Warn about orphan (un-joined) slide segments
    orphan_slides = [s for s in slide_segments if s not in used_segments]
    if orphan_slides:
        chart._warnings.append(
            f"{len(orphan_slides)} slide segment(s) could not be chained "
            f"(no matching successor at end position)"
        )
    orphan_air_slides = [s for s in air_slide_segments if s not in used_air_segments]
    if orphan_air_slides:
        chart._warnings.append(
            f"{len(orphan_air_slides)} air slide segment(s) could not be chained "
            f"(no matching successor at end position)"
        )

    # Pass 3: Anchor ALL Air Notes (Chains, Segments, and Modifiers)
    remaining_segments: list[AirSlide] = [
        segment for segment in air_slide_segments if segment not in used_air_segments
    ]
    all_potential_anchors: list[Note] = [
        *ground_notes,
        *joined_slides,
        *(note for note in air_sustains if note.note_type != NoteType.ALD),
        *joined_air_slides,
        *remaining_segments,
    ]
    
    # Build lookup for all possible anchor points
    anchor_lookup: dict[tuple[int, int, int], list[Note]] = {}
    
    def add_anchor(tick: int, cell: int, width: int, n: Note):
        k = (tick, cell, width)
        if k not in anchor_lookup:
            anchor_lookup[k] = []
        anchor_lookup[k].append(n)

    for n in all_potential_anchors:
        # Start of any note
        add_anchor(get_tick(n), n.cell, n.width, n)
        
        if isinstance(n, (Slide, AirSlideStart)):
            # Each step end can be an anchor
            for step in n.steps:
                add_anchor(get_end_tick(step), step.end_cell, step.end_width, step)
        elif hasattr(n, "duration") and getattr(n, "duration") > 0:
            # End of hold/sustain
            end_cell = getattr(n, "end_cell", n.cell)
            end_width = getattr(n, "end_width", n.width)
            add_anchor(get_end_tick(n), end_cell, end_width, n)

    final_notes: list[Note] = []

    # 3.1 Anchor Joined Air Slides
    for air_slide_note in joined_air_slides:
        tick = get_tick(air_slide_note)
        k = (tick, air_slide_note.cell, air_slide_note.width)
        candidates = anchor_lookup.get(k, [])
        
        anchor = None
        target_type = air_slide_note.steps[0].target_note
        if target_type == "DEF":
            if candidates:
                # Avoid self-anchoring
                filtered = [c for c in candidates if c is not air_slide_note]
                if filtered:
                    anchor = filtered[0]
        else:
            for air_slide_candidate in candidates:
                if air_slide_candidate is air_slide_note: continue
                if matches_target_note(air_slide_candidate, target_type):
                    anchor = air_slide_candidate
                    break
        
        if anchor:
            air_slide_note = replace(air_slide_note, parent=anchor)
        final_notes.append(air_slide_note)

    # 3.2 Anchor Individual segments (orphans)
    for remaining_segment in remaining_segments:
        tick = get_tick(remaining_segment)
        k = (tick, remaining_segment.cell, remaining_segment.width)
        candidates = anchor_lookup.get(k, [])
        
        anchor = None
        target_type = remaining_segment.target_note
        if target_type == "DEF":
            if candidates:
                filtered = [c for c in candidates if c is not remaining_segment]
                if filtered:
                    anchor = filtered[0]
        else:
            for remaining_candidate in candidates:
                if remaining_candidate is remaining_segment: continue
                if matches_target_note(remaining_candidate, target_type):
                    anchor = remaining_candidate
                    break
        
        if anchor:
            remaining_segment = replace(remaining_segment, parent=anchor)
        final_notes.append(remaining_segment)

    # 3.3 Add non-air notes to final list
    final_notes.extend(ground_notes)
    final_notes.extend(joined_slides)
    final_notes.extend(air_sustains)

    # 3.4 Anchor Air Modifiers (Arrows)
    for nt, args_tuple in air_modifiers:
        args = list(args_tuple)
        note = _parse_note(nt, args)
        if not note:
            continue

        tick = get_tick(note)
        k = (tick, note.cell, note.width)
        candidates = anchor_lookup.get(k, [])
        
        anchor = None
        target_type = getattr(note, "target_note", "DEF")
        if target_type == "DEF":
            if candidates:
                anchor = candidates[0]
        else:
            for modifier_candidate in candidates:
                if matches_target_note(modifier_candidate, target_type):
                    anchor = modifier_candidate
                    break
        
        if anchor:
            note = replace(note, parent=anchor)

        final_notes.append(note)

    chart.notes = final_notes
    chart.notes.sort(key=lambda n: (n.measure, n.offset, n.cell))
    return chart


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


def _resolve_metadata_from_xml(chart: Chart, source_path: Path) -> None:
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
