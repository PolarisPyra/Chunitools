"""Shared construction rules for parsed and editor-created notes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from src.core.const import NoteType
from src.notes.air import Air, AirHold, AirHoldStart, AirSlide, AirSlideStart, CrashSlide
from src.notes.effects import AirSolid, HeavenHold
from src.notes.flick import Flick
from src.notes.hold import Hold
from src.notes.schema import NOTE_SCHEMAS, parse_schema_fields
from src.notes.slide import Slide, SlideTo
from src.notes.tap import ExTap, Mine, Tap

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from src.notes.base import Note

DEFAULT_NOTE_DURATION = 384

ParserNoteGroup = Literal["ground", "slide", "air_slide", "air_modifier", "air_sustain"]


class NoteHead(TypedDict):
    measure: int
    offset: int
    cell: int
    width: int
    data: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NoteFactorySpec:
    parse: Callable[[NoteType, NoteHead], Note] | None
    build_editor: Callable[[dict[str, Any], int, dict[str, Any]], Note] | None
    parser_group: ParserNoteGroup


def int_from_float(value: str) -> int:
    """Parse .c2s integer fields that may be emitted with a decimal point."""
    return int(float(value))


def valid_note_geometry(cell: int, width: int) -> bool:
    """Return whether lane geometry fits inside the 16-lane playfield."""
    return 0 <= cell <= 15 and 1 <= width <= 16 and cell + width <= 16


def parse_note_head(args: list[str], *, validate_geometry: bool = False) -> NoteHead | None:
    """Parse common .c2s note columns, preserving parser tolerance by default."""
    if len(args) < 4:
        return None

    try:
        measure = int_from_float(args[0])
        offset = int_from_float(args[1])
        cell = int_from_float(args[2])
        width = int_from_float(args[3])
    except (ValueError, TypeError):
        return None

    if validate_geometry and (measure < 0 or offset < 0 or not valid_note_geometry(cell, width)):
        return None

    return {
        "measure": measure,
        "offset": offset,
        "cell": cell,
        "width": width,
        "data": tuple(args[4:]),
    }


def clamp_note_geometry(cell: int, width: int) -> tuple[int, int]:
    """Clamp note lane geometry to the 16-lane CHUNITHM playfield."""
    clamped_cell = max(0, min(15, int(cell)))
    clamped_width = max(1, min(16 - clamped_cell, int(width)))
    return clamped_cell, clamped_width


def _base_kwargs(note_type: NoteType, head: NoteHead) -> dict[str, Any]:
    return {
        "note_type": note_type,
        "measure": head["measure"],
        "offset": head["offset"],
        "cell": head["cell"],
        "width": head["width"],
    }


def _parse_tap(note_type: NoteType, head: NoteHead) -> Note:
    return Tap(**_base_kwargs(note_type, head))


def _parse_mine(note_type: NoteType, head: NoteHead) -> Note:
    return Mine(**_base_kwargs(note_type, head))


def _parse_extap(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return ExTap(**_base_kwargs(note_type, head), animation=fields["animation"])


def _parse_flick(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return Flick(**_base_kwargs(note_type, head), direction=fields["direction"])


def _parse_hold(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return Hold(
        **_base_kwargs(note_type, head),
        duration=fields["duration"],
        animation=fields.get("animation"),
    )


def _parse_slide(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return SlideTo(
        **_base_kwargs(note_type, head),
        duration=fields["duration"],
        end_cell=fields["end_cell"],
        end_width=fields["end_width"],
        target_id=fields.get("target_id"),
        animation=fields.get("animation"),
        is_visible=note_type.value.endswith("D"),
    )


def _parse_air(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return Air(
        **_base_kwargs(note_type, head),
        target_note=fields["target_note"],
        color=fields.get("color", "DEF"),
        color_is_explicit="color" in fields,
    )


def _parse_air_hold_start(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return AirHoldStart(
        **_base_kwargs(note_type, head),
        target_note=fields["target_note"],
        duration=fields["duration"],
        color=fields.get("color", "DEF"),
        color_is_explicit="color" in fields,
    )


def _parse_air_hold(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return AirHold(
        **_base_kwargs(note_type, head),
        target_note=fields["target_note"],
        duration=fields["duration"],
        color=fields.get("color", "DEF"),
    )


def _parse_crash_slide(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return CrashSlide(
        **_base_kwargs(note_type, head),
        crush_interval=fields["crush_interval"],
        starting_height=fields["starting_height"],
        duration=fields["duration"],
        end_cell=fields["end_cell"],
        end_width=fields["end_width"],
        target_height=fields["target_height"],
        color=fields["color"],
    )


def _parse_air_slide(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return AirSlide(
        **_base_kwargs(note_type, head),
        target_note=fields["target_note"],
        starting_height=fields["starting_height"],
        duration=fields["duration"],
        end_cell=fields["end_cell"],
        end_width=fields["end_width"],
        target_height=fields["target_height"],
        color=fields["color"],
    )


def _parse_air_solid(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return AirSolid(
        **_base_kwargs(note_type, head),
        starting_height=fields["starting_height"],
        starting_depth=fields["starting_depth"],
        duration=fields["duration"],
        end_cell=fields["end_cell"],
        end_width=fields["end_width"],
        target_height=fields["target_height"],
        target_depth=fields["target_depth"],
        color=fields["color"],
    )


def _parse_heaven_hold(note_type: NoteType, head: NoteHead) -> Note:
    fields = parse_schema_fields(note_type, head["data"])
    return HeavenHold(
        **_base_kwargs(note_type, head),
        starting_height=fields["starting_height"],
        duration=fields["duration"],
        end_cell=fields["end_cell"],
        end_width=fields["end_width"],
        target_height=fields["target_height"],
        heaven_id=fields["heaven_id"],
        animation=fields.get("animation"),
    )


def _end_geom(cell: int, width: int, end_cell: Any, end_width: Any) -> tuple[int, int]:
    return clamp_note_geometry(
        cell if end_cell is None else end_cell,
        width if end_width is None else end_width,
    )


def _build_tap(base: dict[str, Any], _duration: int, _extras: dict[str, Any]) -> Note:
    return Tap(**base)


def _build_extap(base: dict[str, Any], _duration: int, _extras: dict[str, Any]) -> Note:
    return ExTap(**base, animation="0")


def _build_flick(base: dict[str, Any], _duration: int, _extras: dict[str, Any]) -> Note:
    return Flick(**base, direction="L")


def _build_mine(base: dict[str, Any], _duration: int, _extras: dict[str, Any]) -> Note:
    return Mine(**base)


def _build_air_solid(base: dict[str, Any], duration: int, extras: dict[str, Any]) -> Note:
    ec, ew = _end_geom(base["cell"], base["width"], extras.get("end_cell"), extras.get("end_width"))
    return AirSolid(
        **base,
        starting_height=1.0,
        starting_depth=1.0,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_height=1.0,
        target_depth=1.0,
        color="DEF",
    )


def _build_heaven_hold(base: dict[str, Any], duration: int, extras: dict[str, Any]) -> Note:
    ec, ew = _end_geom(base["cell"], base["width"], extras.get("end_cell"), extras.get("end_width"))
    return HeavenHold(
        **base,
        starting_height=1.0,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_height=1.0,
        heaven_id=0,
        animation="UP" if base["note_type"] == NoteType.HHX else None,
    )


def _build_hold(base: dict[str, Any], duration: int, _extras: dict[str, Any]) -> Note:
    return Hold(**base, duration=duration)


def _build_slide(base: dict[str, Any], duration: int, extras: dict[str, Any]) -> Note:
    ec, ew = _end_geom(base["cell"], base["width"], extras.get("end_cell"), extras.get("end_width"))
    step = SlideTo(
        **base,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_id="",
        animation=None,
        is_visible=base["note_type"] in {NoteType.SLD, NoteType.SXD},
    )
    return Slide(**base, steps=(step,))


def _build_air(base: dict[str, Any], _duration: int, extras: dict[str, Any]) -> Note:
    return Air(**base, target_note=extras.get("target_note", "DEF"))


def _build_air_hold_start(base: dict[str, Any], duration: int, extras: dict[str, Any]) -> Note:
    return AirHoldStart(**base, target_note=extras.get("target_note", "DEF"), duration=duration)


def _build_air_hold(base: dict[str, Any], duration: int, extras: dict[str, Any]) -> Note:
    return AirHold(
        **base,
        target_note=extras.get("target_note", "DEF"),
        duration=duration,
        color="DEF",
    )


def _build_air_trace(base: dict[str, Any], duration: int, extras: dict[str, Any]) -> Note:
    ec, ew = _end_geom(base["cell"], base["width"], extras.get("end_cell"), extras.get("end_width"))
    return CrashSlide(
        **base,
        crush_interval=0,
        starting_height=1.0,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_height=1.0,
        color="NON",
    )


def _build_air_slide(base: dict[str, Any], duration: int, extras: dict[str, Any]) -> Note:
    ec, ew = _end_geom(base["cell"], base["width"], extras.get("end_cell"), extras.get("end_width"))
    step = AirSlide(
        **base,
        target_note=extras.get("target_note", "DEF"),
        starting_height=1.0,
        duration=duration,
        end_cell=ec,
        end_width=ew,
        target_height=1.0,
        color="DEF",
    )
    return AirSlideStart(**base, steps=(step,))


_NOTE_FACTORIES: dict[NoteType, NoteFactorySpec] = {
    NoteType.TAP: NoteFactorySpec(_parse_tap, _build_tap, "ground"),
    NoteType.CHR: NoteFactorySpec(_parse_extap, _build_extap, "ground"),
    NoteType.FLK: NoteFactorySpec(_parse_flick, _build_flick, "ground"),
    NoteType.MNE: NoteFactorySpec(_parse_mine, _build_mine, "ground"),
    NoteType.HLD: NoteFactorySpec(_parse_hold, _build_hold, "ground"),
    NoteType.HXD: NoteFactorySpec(_parse_hold, _build_hold, "ground"),
    NoteType.SLD: NoteFactorySpec(_parse_slide, _build_slide, "slide"),
    NoteType.SXD: NoteFactorySpec(_parse_slide, _build_slide, "slide"),
    NoteType.SLC: NoteFactorySpec(_parse_slide, _build_slide, "slide"),
    NoteType.SXC: NoteFactorySpec(_parse_slide, _build_slide, "slide"),
    NoteType.AIR: NoteFactorySpec(_parse_air, _build_air, "air_modifier"),
    NoteType.AUR: NoteFactorySpec(_parse_air, _build_air, "air_modifier"),
    NoteType.AUL: NoteFactorySpec(_parse_air, _build_air, "air_modifier"),
    NoteType.ADW: NoteFactorySpec(_parse_air, _build_air, "air_modifier"),
    NoteType.ADR: NoteFactorySpec(_parse_air, _build_air, "air_modifier"),
    NoteType.ADL: NoteFactorySpec(_parse_air, _build_air, "air_modifier"),
    NoteType.AHD: NoteFactorySpec(_parse_air_hold_start, _build_air_hold_start, "air_sustain"),
    NoteType.AHX: NoteFactorySpec(_parse_air_hold, _build_air_hold, "air_sustain"),
    NoteType.ALD: NoteFactorySpec(_parse_crash_slide, _build_air_trace, "air_sustain"),
    NoteType.ASD: NoteFactorySpec(_parse_air_slide, _build_air_slide, "air_slide"),
    NoteType.ASC: NoteFactorySpec(_parse_air_slide, _build_air_slide, "air_slide"),
    NoteType.ASX: NoteFactorySpec(_parse_air_slide, None, "air_slide"),
    NoteType.ASO: NoteFactorySpec(_parse_air_solid, _build_air_solid, "ground"),
    NoteType.HHD: NoteFactorySpec(_parse_heaven_hold, _build_heaven_hold, "ground"),
    NoteType.HHX: NoteFactorySpec(_parse_heaven_hold, _build_heaven_hold, "ground"),
}

NOTE_FACTORIES: Mapping[NoteType, NoteFactorySpec] = _NOTE_FACTORIES

PARSER_NOTE_TYPES: frozenset[NoteType] = frozenset(
    note_type for note_type, spec in _NOTE_FACTORIES.items() if spec.parse is not None
)
PARSER_NOTE_TYPE_VALUES: frozenset[str] = frozenset(
    note_type.value for note_type in PARSER_NOTE_TYPES
)
EDITOR_NOTE_TYPES: frozenset[NoteType] = frozenset(
    note_type for note_type, spec in _NOTE_FACTORIES.items() if spec.build_editor is not None
)
SLIDE_NOTE_TYPES: frozenset[NoteType] = frozenset(
    note_type for note_type, spec in _NOTE_FACTORIES.items() if spec.parser_group == "slide"
)
AIR_SLIDE_NOTE_TYPES: frozenset[NoteType] = frozenset(
    note_type for note_type, spec in _NOTE_FACTORIES.items() if spec.parser_group == "air_slide"
)
AIR_MODIFIER_NOTE_TYPES: frozenset[NoteType] = frozenset(
    note_type for note_type, spec in _NOTE_FACTORIES.items() if spec.parser_group == "air_modifier"
)
AIR_SUSTAIN_NOTE_TYPES: frozenset[NoteType] = frozenset(
    note_type for note_type, spec in _NOTE_FACTORIES.items() if spec.parser_group == "air_sustain"
)

SCHEMA_NOTE_TYPES: frozenset[NoteType] = frozenset(NOTE_SCHEMAS)


def parse_note(note_type: NoteType, args: list[str]) -> Note | None:
    """Create a note from .c2s fields, returning ``None`` for malformed lines."""
    spec = _NOTE_FACTORIES.get(note_type)
    if spec is None or spec.parse is None:
        return None
    head = parse_note_head(args)
    if head is None:
        return None
    try:
        return spec.parse(note_type, head)
    except (ValueError, TypeError, IndexError):
        return None


def build_editor_note(  # noqa: PLR0913
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
    spec = _NOTE_FACTORIES.get(note_type)
    if spec is None or spec.build_editor is None:
        raise ValueError(f"Unsupported note type: {note_type.value}")

    cell, width = clamp_note_geometry(cell, width)
    base = {
        "note_type": note_type,
        "measure": max(0, int(measure)),
        "offset": max(0, int(offset)),
        "cell": cell,
        "width": width,
        "parent": parent,
    }
    extras = {
        "end_cell": end_cell,
        "end_width": end_width,
        "target_note": target_note,
    }
    note_duration = max(1, int(duration or DEFAULT_NOTE_DURATION))
    return spec.build_editor(base, note_duration, extras)
