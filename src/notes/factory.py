"""Shared construction rules for parsed and editor-created notes.

Every note type has two construction paths:

1. **Parse** — reconstruct a ``Note`` from raw ``.c2s`` tab-separated fields.
2. **Build** — create an editor-default ``Note`` with sensible defaults for
   the chart editor UI.

All construction functions use **explicit named keyword arguments only** — no
``**kwargs``, ``**base``, or ``**extras`` dict splatting.  Every argument is
visible at the call site.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, TypedDict

from src.core.const import NoteType
from src.notes.air import Air, AirHold, AirHoldStart, AirSlide, AirSlideStart, CrashSlide
from src.notes.effects import AirSolid, HeavenHold
from src.notes.flick import Flick
from src.notes.hold import Hold
from src.notes.schema import NOTE_SCHEMAS, parse_schema_fields
from src.notes.slide import Slide, SlideTo
from src.notes.tap import ExTap, Mine, Tap

if TYPE_CHECKING:
    from src.notes.base import Note


DEFAULT_NOTE_DURATION = 384


# ── Game-accurate note categories ──────────────────────────────────────────


class NoteCategory(str, Enum):
    """Categories matching the CHUNITHM engine classification."""

    GROUND = "ground"  # TAP, MNE
    CRUSH = "crush"  # CHR (ExTap / double-hit mechanic)
    FLICK = "flick"  # FLK
    HOLD = "hold"  # HLD, HXD
    SLIDE = "slide"  # SLD, SLC, SXD, SXC
    AIR_ARROW = "air_arrow"  # AIR, AUR, AUL, ADW, ADR, ADL
    AIR_HOLD = "air_hold"  # AHD, AHX
    AIR_SLIDE = "air_slide"  # ASD, ASC, ASX
    AIR_TRACE = "air_trace"  # ALD
    AIR_SOLID = "air_solid"  # ASO
    HEAVEN = "heaven"  # HHD, HHX


_NOTE_CATEGORIES: dict[NoteType, NoteCategory] = {
    NoteType.TAP: NoteCategory.GROUND,
    NoteType.CHR: NoteCategory.CRUSH,
    NoteType.FLK: NoteCategory.FLICK,
    NoteType.MNE: NoteCategory.GROUND,
    NoteType.HLD: NoteCategory.HOLD,
    NoteType.HXD: NoteCategory.HOLD,
    NoteType.SLD: NoteCategory.SLIDE,
    NoteType.SXD: NoteCategory.SLIDE,
    NoteType.SLC: NoteCategory.SLIDE,
    NoteType.SXC: NoteCategory.SLIDE,
    NoteType.AIR: NoteCategory.AIR_ARROW,
    NoteType.AUR: NoteCategory.AIR_ARROW,
    NoteType.AUL: NoteCategory.AIR_ARROW,
    NoteType.ADW: NoteCategory.AIR_ARROW,
    NoteType.ADR: NoteCategory.AIR_ARROW,
    NoteType.ADL: NoteCategory.AIR_ARROW,
    NoteType.AHD: NoteCategory.AIR_HOLD,
    NoteType.AHX: NoteCategory.AIR_HOLD,
    NoteType.ALD: NoteCategory.AIR_TRACE,
    NoteType.ASD: NoteCategory.AIR_SLIDE,
    NoteType.ASC: NoteCategory.AIR_SLIDE,
    NoteType.ASX: NoteCategory.AIR_SLIDE,
    NoteType.ASO: NoteCategory.AIR_SOLID,
    NoteType.HHD: NoteCategory.HEAVEN,
    NoteType.HHX: NoteCategory.HEAVEN,
}


# ── Utility ────────────────────────────────────────────────────────────────


def int_from_float(value: str) -> int:
    """Parse ``.c2s`` integer fields that may be emitted with a decimal point."""
    return int(float(value))


def _valid_note_geometry(cell: int, width: int) -> bool:
    return 0 <= cell <= 15 and 1 <= width <= 16 and cell + width <= 16


class NoteHead(TypedDict):
    """The first five columns common to every ``.c2s`` note line."""

    measure: int
    offset: int
    cell: int
    width: int
    data: tuple[str, ...]


def parse_note_head(args: list[str], *, validate_geometry: bool = False) -> NoteHead | None:
    """Parse common ``.c2s`` note columns, preserving parser tolerance by default."""
    if len(args) < 4:
        return None
    try:
        measure = int_from_float(args[0])
        offset = int_from_float(args[1])
        cell = int_from_float(args[2])
        width = int_from_float(args[3])
    except (ValueError, TypeError):
        return None
    if validate_geometry and (measure < 0 or offset < 0 or not _valid_note_geometry(cell, width)):
        return None
    return NoteHead(measure=measure, offset=offset, cell=cell, width=width, data=tuple(args[4:]))


def clamp_note_geometry(cell: int, width: int) -> tuple[int, int]:
    """Clamp note lane geometry to the 16-lane CHUNITHM playfield."""
    c = max(0, min(15, int(cell)))
    w = max(1, min(16 - c, int(width)))
    return c, w


# ── Parse functions (per NoteType, one-to-one with .c2s format) ────────────


def _parse_tap(note_type: NoteType, head: NoteHead) -> Note:
    return Tap(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
    )


def _parse_chr(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return ExTap(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        animation=f["animation"],
    )


def _parse_flick(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return Flick(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        direction=f["direction"],
    )


def _parse_mine(note_type: NoteType, head: NoteHead) -> Note:
    return Mine(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
    )


def _parse_hold(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return Hold(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        duration=f["duration"],
        animation=f.get("animation"),
    )


def _parse_slide(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return SlideTo(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        duration=f["duration"],
        end_cell=f["end_cell"],
        end_width=f["end_width"],
        target_id=f.get("target_id"),
        animation=f.get("animation"),
        is_visible=note_type.value.endswith("D"),
    )


def _parse_air_arrow(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return Air(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        target_note=f["target_note"],
        color=f.get("color", "DEF"),
        color_is_explicit="color" in f,
    )


def _parse_air_hold(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return AirHoldStart(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        target_note=f["target_note"],
        duration=f["duration"],
        color=f.get("color", "DEF"),
        color_is_explicit="color" in f,
    )


def _parse_air_hold_action(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return AirHold(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        target_note=f["target_note"],
        duration=f["duration"],
        color=f["color"],
    )


def _parse_air_trace(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return CrashSlide(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        crush_interval=f["crush_interval"],
        starting_height=f["starting_height"],
        duration=f["duration"],
        end_cell=f["end_cell"],
        end_width=f["end_width"],
        target_height=f["target_height"],
        color=f["color"],
    )


def _parse_air_slide(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return AirSlide(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        target_note=f["target_note"],
        starting_height=f["starting_height"],
        duration=f["duration"],
        end_cell=f["end_cell"],
        end_width=f["end_width"],
        target_height=f["target_height"],
        color=f["color"],
    )


def _parse_air_solid(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return AirSolid(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        starting_height=f["starting_height"],
        starting_depth=f["starting_depth"],
        duration=f["duration"],
        end_cell=f["end_cell"],
        end_width=f["end_width"],
        target_height=f["target_height"],
        target_depth=f["target_depth"],
        color=f["color"],
    )


def _parse_heaven_hold(note_type: NoteType, head: NoteHead) -> Note:
    f = parse_schema_fields(note_type, head["data"])
    return HeavenHold(
        note_type=note_type,
        measure=head["measure"],
        offset=head["offset"],
        cell=head["cell"],
        width=head["width"],
        starting_height=f["starting_height"],
        duration=f["duration"],
        end_cell=f["end_cell"],
        end_width=f["end_width"],
        target_height=f["target_height"],
        heaven_id=f["heaven_id"],
        animation=f.get("animation"),
    )


_NOTE_PARSERS: dict[NoteType, type] = {
    NoteType.TAP: _parse_tap,
    NoteType.CHR: _parse_chr,
    NoteType.FLK: _parse_flick,
    NoteType.MNE: _parse_mine,
    NoteType.HLD: _parse_hold,
    NoteType.HXD: _parse_hold,
    NoteType.SLD: _parse_slide,
    NoteType.SXD: _parse_slide,
    NoteType.SLC: _parse_slide,
    NoteType.SXC: _parse_slide,
    NoteType.AIR: _parse_air_arrow,
    NoteType.AUR: _parse_air_arrow,
    NoteType.AUL: _parse_air_arrow,
    NoteType.ADW: _parse_air_arrow,
    NoteType.ADR: _parse_air_arrow,
    NoteType.ADL: _parse_air_arrow,
    NoteType.AHD: _parse_air_hold,
    NoteType.AHX: _parse_air_hold_action,
    NoteType.ALD: _parse_air_trace,
    NoteType.ASD: _parse_air_slide,
    NoteType.ASC: _parse_air_slide,
    NoteType.ASX: _parse_air_slide,
    NoteType.ASO: _parse_air_solid,
    NoteType.HHD: _parse_heaven_hold,
    NoteType.HHX: _parse_heaven_hold,
}


# ── Complex editor builders (notes that need geometry/step wrapping) ───────


def _build_slide(  # noqa: PLR0913
    note_type: NoteType,
    measure: int,
    offset: int,
    cell: int,
    width: int,
    parent: Note | None = None,
    duration: int = DEFAULT_NOTE_DURATION,
    end_cell: int | None = None,
    end_width: int | None = None,
    **_ignored: object,
) -> Note:
    ec, ew = clamp_note_geometry(
        cell if end_cell is None else end_cell, width if end_width is None else end_width
    )
    step = SlideTo(
        note_type=note_type,
        measure=measure,
        offset=offset,
        cell=cell,
        width=width,
        parent=None,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_id="",
        animation=None,
        is_visible=note_type in {NoteType.SLD, NoteType.SXD},
    )
    return Slide(
        note_type=note_type,
        measure=measure,
        offset=offset,
        cell=cell,
        width=width,
        parent=parent,
        steps=(step,),
    )


def _build_air_trace(  # noqa: PLR0913
    note_type: NoteType,
    measure: int,
    offset: int,
    cell: int,
    width: int,
    parent: Note | None = None,
    duration: int = DEFAULT_NOTE_DURATION,
    end_cell: int | None = None,
    end_width: int | None = None,
    **_ignored: object,
) -> Note:
    ec, ew = clamp_note_geometry(
        cell if end_cell is None else end_cell, width if end_width is None else end_width
    )
    return CrashSlide(
        note_type=note_type,
        measure=measure,
        offset=offset,
        cell=cell,
        width=width,
        parent=parent,
        crush_interval=0,
        starting_height=1.0,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_height=1.0,
        color="NON",
    )


def _build_air_slide(  # noqa: PLR0913
    note_type: NoteType,
    measure: int,
    offset: int,
    cell: int,
    width: int,
    parent: Note | None = None,
    duration: int = DEFAULT_NOTE_DURATION,
    end_cell: int | None = None,
    end_width: int | None = None,
    target_note: str | None = None,
    **_ignored: object,
) -> Note:
    ec, ew = clamp_note_geometry(
        cell if end_cell is None else end_cell, width if end_width is None else end_width
    )
    step = AirSlide(
        note_type=note_type,
        measure=measure,
        offset=offset,
        cell=cell,
        width=width,
        parent=None,
        target_note=target_note or "DEF",
        starting_height=1.0,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_height=1.0,
        color="DEF",
    )
    return AirSlideStart(
        note_type=note_type,
        measure=measure,
        offset=offset,
        cell=cell,
        width=width,
        parent=parent,
        steps=(step,),
    )


def _build_air_solid(  # noqa: PLR0913
    note_type: NoteType,
    measure: int,
    offset: int,
    cell: int,
    width: int,
    parent: Note | None = None,
    duration: int = DEFAULT_NOTE_DURATION,
    end_cell: int | None = None,
    end_width: int | None = None,
    **_ignored: object,
) -> Note:
    ec, ew = clamp_note_geometry(
        cell if end_cell is None else end_cell, width if end_width is None else end_width
    )
    return AirSolid(
        note_type=note_type,
        measure=measure,
        offset=offset,
        cell=cell,
        width=width,
        parent=parent,
        starting_height=1.0,
        starting_depth=1.0,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_height=1.0,
        target_depth=1.0,
        color="DEF",
    )


def _build_heaven_hold(  # noqa: PLR0913
    note_type: NoteType,
    measure: int,
    offset: int,
    cell: int,
    width: int,
    parent: Note | None = None,
    duration: int = DEFAULT_NOTE_DURATION,
    end_cell: int | None = None,
    end_width: int | None = None,
    **_ignored: object,
) -> Note:
    ec, ew = clamp_note_geometry(
        cell if end_cell is None else end_cell, width if end_width is None else end_width
    )
    return HeavenHold(
        note_type=note_type,
        measure=measure,
        offset=offset,
        cell=cell,
        width=width,
        parent=parent,
        starting_height=1.0,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_height=1.0,
        heaven_id=0,
        animation="UP" if note_type == NoteType.HHX else None,
    )


# ── Complex builder dispatch ───────────────────────────────────────────────

_COMPLEX_BUILDERS: dict[NoteType, type] = {
    NoteType.SLD: _build_slide,
    NoteType.SXD: _build_slide,
    NoteType.SLC: _build_slide,
    NoteType.SXC: _build_slide,
    NoteType.ALD: _build_air_trace,
    NoteType.ASD: _build_air_slide,
    NoteType.ASC: _build_air_slide,
    NoteType.ASO: _build_air_solid,
    NoteType.HHD: _build_heaven_hold,
    NoteType.HHX: _build_heaven_hold,
}


# ── Public category frozensets ─────────────────────────────────────────────


def _notes_in_category(cat: NoteCategory) -> frozenset[NoteType]:
    return frozenset(nt for nt, c in _NOTE_CATEGORIES.items() if c == cat)


GROUND_NOTE_TYPES: frozenset[NoteType] = (
    _notes_in_category(NoteCategory.GROUND)
    | _notes_in_category(NoteCategory.HOLD)
    | _notes_in_category(NoteCategory.SLIDE)
    | _notes_in_category(NoteCategory.FLICK)
)
CRUSH_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.CRUSH)
FLICK_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.FLICK)
HOLD_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.HOLD)
SLIDE_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.SLIDE)
AIR_ARROW_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.AIR_ARROW)
AIR_HOLD_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.AIR_HOLD)
AIR_SLIDE_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.AIR_SLIDE)
AIR_TRACE_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.AIR_TRACE)
AIR_SOLID_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.AIR_SOLID)
HEAVEN_NOTE_TYPES: frozenset[NoteType] = _notes_in_category(NoteCategory.HEAVEN)

PARSER_NOTE_TYPES: frozenset[NoteType] = frozenset(_NOTE_PARSERS)
PARSER_NOTE_TYPE_VALUES: frozenset[str] = frozenset(nt.value for nt in _NOTE_PARSERS)
EDITOR_NOTE_TYPES: frozenset[NoteType] = frozenset(_COMPLEX_BUILDERS) | frozenset(
    {
        NoteType.TAP,
        NoteType.CHR,
        NoteType.FLK,
        NoteType.MNE,
        NoteType.HLD,
        NoteType.HXD,
        NoteType.AIR,
        NoteType.AUR,
        NoteType.AUL,
        NoteType.ADW,
        NoteType.ADR,
        NoteType.ADL,
        NoteType.AHD,
        NoteType.AHX,
    }
)
SCHEMA_NOTE_TYPES: frozenset[NoteType] = frozenset(NOTE_SCHEMAS)


# ── Public API ─────────────────────────────────────────────────────────────


def parse_note(note_type: NoteType, args: list[str]) -> Note | None:
    """Create a note from ``.c2s`` fields, returning ``None`` for malformed lines."""
    parser = _NOTE_PARSERS.get(note_type)
    if parser is None:
        return None
    head = parse_note_head(args)
    if head is None:
        return None
    try:
        return parser(note_type, head)
    except (ValueError, TypeError, IndexError):
        return None


def build_editor_note(  # noqa: PLR0913,PLR0911
    note_type: NoteType,
    *,
    measure: int = 0,
    offset: int = 0,
    cell: int = 0,
    width: int = 0,
    duration: int | None = None,
    end_cell: int | None = None,
    end_width: int | None = None,
    parent: Note | None = None,
    target_note: str | None = None,
) -> Note:
    """Create an editor-default note for a supported note type."""
    cell, width = clamp_note_geometry(cell, width)
    note_duration = max(1, int(duration or DEFAULT_NOTE_DURATION))
    m = max(0, int(measure))
    o = max(0, int(offset))

    # Complex builders (geometry / step-wrapping logic)
    builder = _COMPLEX_BUILDERS.get(note_type)
    if builder is not None:
        return builder(
            note_type=note_type,
            measure=m,
            offset=o,
            cell=cell,
            width=width,
            parent=parent,
            duration=note_duration,
            end_cell=end_cell,
            end_width=end_width,
            target_note=target_note,
        )

    # Simple builders — each just creates the note with base fields + 1-2 defaults
    if note_type in {NoteType.TAP, NoteType.MNE}:
        cls = Tap if note_type == NoteType.TAP else Mine
        return cls(note_type=note_type, measure=m, offset=o, cell=cell, width=width, parent=parent)

    if note_type == NoteType.CHR:
        return ExTap(
            note_type=note_type,
            measure=m,
            offset=o,
            cell=cell,
            width=width,
            parent=parent,
            animation="0",
        )

    if note_type == NoteType.FLK:
        return Flick(
            note_type=note_type,
            measure=m,
            offset=o,
            cell=cell,
            width=width,
            parent=parent,
            direction="L",
        )

    if note_type in {NoteType.HLD, NoteType.HXD}:
        return Hold(
            note_type=note_type,
            measure=m,
            offset=o,
            cell=cell,
            width=width,
            parent=parent,
            duration=note_duration,
        )

    if note_type in {
        NoteType.AIR,
        NoteType.AUR,
        NoteType.AUL,
        NoteType.ADW,
        NoteType.ADR,
        NoteType.ADL,
    }:
        return Air(
            note_type=note_type,
            measure=m,
            offset=o,
            cell=cell,
            width=width,
            parent=parent,
            target_note=target_note or "DEF",
        )

    if note_type == NoteType.AHD:
        return AirHoldStart(
            note_type=note_type,
            measure=m,
            offset=o,
            cell=cell,
            width=width,
            parent=parent,
            target_note=target_note or "DEF",
            duration=note_duration,
        )

    if note_type == NoteType.AHX:
        return AirHold(
            note_type=note_type,
            measure=m,
            offset=o,
            cell=cell,
            width=width,
            parent=parent,
            target_note=target_note or "DEF",
            duration=note_duration,
            color="DEF",
        )

    raise ValueError(f"Unsupported note type: {note_type.value}")
