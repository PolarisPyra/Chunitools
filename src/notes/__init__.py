"""Note models and construction dispatch for the CHUNITHM chart domain.

Each concrete note class (Tap, ExTap, Hold, etc.) owns its own ``parse()``
and ``build()`` classmethods.  This module provides the dispatchers
``parse_note()`` and ``build_editor_note()``, plus game-accurate category
frozensets.
"""

from __future__ import annotations

from enum import Enum

from src.core.const import NoteType
from src.notes.air import (
    Air,
    AirHold,
    AirHoldStart,
    AirSlide,
    AirSlidePattern,
    AirSlideStart,
)
from src.notes.base import (
    DEFAULT_NOTE_DURATION,
    Note,
    clamp_note_geometry,
    parse_note_head,
)
from src.notes.flick import Flick
from src.notes.hold import Hold
from src.notes.schema import NOTE_SCHEMAS
from src.notes.slide import Slide, SlideTo
from src.notes.tap import ExTap, Mine, Tap

# ── Note dispatch registry ──────────────────────────────────────────────────

_NOTE_CLASSES: dict[str, type[Note]] = {
    "TAP": Tap, "CHR": ExTap, "FLK": Flick, "MNE": Mine,
    "HLD": Hold, "HXD": Hold,
    "SLD": SlideTo, "SXD": SlideTo, "SLC": SlideTo, "SXC": SlideTo,
    "AIR": Air, "AUR": Air, "AUL": Air, "ADW": Air, "ADR": Air, "ADL": Air,
    "AHD": AirHoldStart, "AHX": AirHold,
    "ALD": AirSlidePattern,
    "ASD": AirSlide, "ASC": AirSlide,
}

# Buildable note types exposed by the editor.
_BUILDABLE: dict[str, type[Note]] = {
    "TAP": Tap, "CHR": ExTap, "FLK": Flick, "MNE": Mine,
    "HLD": Hold, "HXD": Hold,
    "SLD": Slide, "SXD": Slide, "SLC": Slide, "SXC": Slide,
    "AIR": Air, "AUR": Air, "AUL": Air, "ADW": Air, "ADR": Air, "ADL": Air,
    "AHD": AirHoldStart, "AHX": AirHold,
    "ALD": AirSlidePattern,
    "ASD": AirSlideStart, "ASC": AirSlideStart,
}

PARSER_NOTE_TYPES: frozenset = frozenset(_NOTE_CLASSES)
PARSER_NOTE_TYPE_VALUES: frozenset[str] = frozenset(_NOTE_CLASSES)
EDITOR_NOTE_TYPES: frozenset = frozenset(_BUILDABLE)
SCHEMA_NOTE_TYPES: frozenset = frozenset(NOTE_SCHEMAS)


# ── Game-accurate categories ────────────────────────────────────────────────


class NoteCategory(str, Enum):
    """Categories matching the supported CHUNITHM C2S model."""

    GROUND = "ground"
    EX_TAP = "ex_tap"
    FLICK = "flick"
    HOLD = "hold"
    SLIDE = "slide"
    AIR_ARROW = "air_arrow"
    AIR_HOLD = "air_hold"
    AIR_SLIDE = "air_slide"
    AIR_SLIDE_PATTERN = "air_slide_pattern"


_NOTE_CATEGORIES: dict[str, NoteCategory] = {
    "TAP": NoteCategory.GROUND,
    "CHR": NoteCategory.EX_TAP,
    "FLK": NoteCategory.FLICK,
    "MNE": NoteCategory.GROUND,
    "HLD": NoteCategory.HOLD,
    "HXD": NoteCategory.HOLD,
    "SLD": NoteCategory.SLIDE,
    "SXD": NoteCategory.SLIDE,
    "SLC": NoteCategory.SLIDE,
    "SXC": NoteCategory.SLIDE,
    "AIR": NoteCategory.AIR_ARROW,
    "AUR": NoteCategory.AIR_ARROW,
    "AUL": NoteCategory.AIR_ARROW,
    "ADW": NoteCategory.AIR_ARROW,
    "ADR": NoteCategory.AIR_ARROW,
    "ADL": NoteCategory.AIR_ARROW,
    "AHD": NoteCategory.AIR_HOLD,
    "AHX": NoteCategory.AIR_HOLD,
    "ALD": NoteCategory.AIR_SLIDE_PATTERN,
    "ASD": NoteCategory.AIR_SLIDE,
    "ASC": NoteCategory.AIR_SLIDE,
}


def _notes(cat: NoteCategory) -> frozenset:
    return frozenset(nt for nt, c in _NOTE_CATEGORIES.items() if c == cat)


GROUND_NOTE_TYPES = (
    _notes(NoteCategory.GROUND) | _notes(NoteCategory.HOLD)
    | _notes(NoteCategory.SLIDE) | _notes(NoteCategory.FLICK)
    | _notes(NoteCategory.EX_TAP)
)
EXTAP_NOTE_TYPES = _notes(NoteCategory.EX_TAP)
FLICK_NOTE_TYPES = _notes(NoteCategory.FLICK)
HOLD_NOTE_TYPES = _notes(NoteCategory.HOLD)
SLIDE_NOTE_TYPES = _notes(NoteCategory.SLIDE)
AIR_ARROW_NOTE_TYPES = _notes(NoteCategory.AIR_ARROW)
AIR_HOLD_NOTE_TYPES = _notes(NoteCategory.AIR_HOLD)
AIR_SLIDE_NOTE_TYPES = _notes(NoteCategory.AIR_SLIDE)
AIR_SLIDE_PATTERN_NOTE_TYPES = _notes(NoteCategory.AIR_SLIDE_PATTERN)


# ── Public API ──────────────────────────────────────────────────────────────


def parse_note(note_type: NoteType | str, args: list[str]) -> Note | None:
    """Create a note from ``.c2s`` fields.

    *note_type* can be a ``NoteType`` enum or its string value.
    Returns ``None`` for unknown types or malformed lines.
    """
    key = note_type.value if isinstance(note_type, NoteType) else note_type
    cls = _NOTE_CLASSES.get(key)
    if cls is None:
        return None
    head = parse_note_head(args)
    if head is None:
        return None
    try:
        return cls.parse(NoteType(key), head)
    except (ValueError, TypeError, IndexError):
        return None


def build_editor_note(  # noqa: PLR0913
    note_type: NoteType | str,
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
    """Create an editor-default note."""
    key = note_type.value if isinstance(note_type, NoteType) else note_type
    cls = _BUILDABLE.get(key)
    if cls is None:
        raise ValueError(f"Unsupported note type: {key}")

    cell, width = clamp_note_geometry(cell, width)
    note_duration = max(1, int(duration or DEFAULT_NOTE_DURATION))
    m = max(0, int(measure))
    o = max(0, int(offset))

    return cls.build(
        NoteType(key), measure=m, offset=o, cell=cell, width=width,
        parent=parent, duration=note_duration,
        end_cell=end_cell, end_width=end_width, target_note=target_note,
    )


__all__ = [
    # Note classes
    "Note", "Tap", "ExTap", "Mine", "Hold", "Slide", "SlideTo",
    "Flick",
    "Air", "AirHoldStart", "AirHold", "AirSlidePattern", "AirSlideStart", "AirSlide",
    # Construction
    "parse_note", "build_editor_note", "clamp_note_geometry", "parse_note_head",
    # Categories
    "GROUND_NOTE_TYPES", "EXTAP_NOTE_TYPES", "FLICK_NOTE_TYPES",
    "HOLD_NOTE_TYPES", "SLIDE_NOTE_TYPES",
    "AIR_ARROW_NOTE_TYPES", "AIR_HOLD_NOTE_TYPES", "AIR_SLIDE_NOTE_TYPES",
    "AIR_SLIDE_PATTERN_NOTE_TYPES",
    # Internal
    "PARSER_NOTE_TYPES", "PARSER_NOTE_TYPE_VALUES",
    "EDITOR_NOTE_TYPES", "SCHEMA_NOTE_TYPES",
]
