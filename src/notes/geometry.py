"""Geometry queries for notes, consolidating isinstance/hasattr checks.

Provides a single dispatch point for note geometry queries so that consumer
code never needs to import concrete note classes or use ``isinstance`` /
``hasattr`` directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.const import AIR_ARROW_NOTES, AIR_NOTE_TYPES
from src.notes.air import Air, AirHold, AirHoldStart, AirSlide, AirSlideStart, CrashSlide
from src.notes.hold import Hold
from src.notes.slide import Slide, SlideTo

if TYPE_CHECKING:
    from src.notes import Note

_LONG_NOTE_CLASSES = (
    Hold,
    Slide,
    AirHoldStart,
    AirHold,
    CrashSlide,
    AirSlideStart,
    AirSlide,
    SlideTo,
)

_MOVING_NOTE_CLASSES = (
    Slide,
    SlideTo,
    CrashSlide,
    AirSlideStart,
    AirSlide,
    AirHold,
)

_AIR_TARGET_CLASSES = (
    Air,
    AirHoldStart,
    AirHold,
    AirSlideStart,
    AirSlide,
)

_COMPOSITE_NOTE_CLASSES = (Slide, AirSlideStart)


def note_duration(note: Note) -> int:
    """Get the duration of a note in ticks, or 0 for instant notes."""
    if isinstance(note, _COMPOSITE_NOTE_CLASSES):
        try:
            return sum(s.duration for s in note.steps)
        except (AttributeError, TypeError):
            pass
        return 0
    if isinstance(note, _LONG_NOTE_CLASSES):
        return int(getattr(note, "duration", 0))
    return 0


def note_end_cell(note: Note) -> int:
    """Get the ending lane cell for a moving note, or start cell for static notes."""
    if isinstance(note, _COMPOSITE_NOTE_CLASSES):
        try:
            return int(getattr(note.steps[-1], "end_cell", note.cell))
        except (AttributeError, TypeError, IndexError):
            pass
        return note.cell
    if isinstance(note, _MOVING_NOTE_CLASSES):
        return int(getattr(note, "end_cell", note.cell))
    return note.cell


def note_end_width(note: Note) -> int:
    """Get the ending lane width for a moving note, or start width for static notes."""
    if isinstance(note, _COMPOSITE_NOTE_CLASSES):
        try:
            return int(getattr(note.steps[-1], "end_width", note.width))
        except (AttributeError, TypeError, IndexError):
            pass
        return note.width
    if isinstance(note, _MOVING_NOTE_CLASSES):
        return int(getattr(note, "end_width", note.width))
    return note.width


def note_target_note(note: Note) -> str:
    """Get the target note type token for air notes, or empty string."""
    if isinstance(note, _AIR_TARGET_CLASSES):
        return str(getattr(note, "target_note", ""))
    return ""


def note_is_air_arrow(note: Note) -> bool:
    """Check if note is an air arrow (AIR, AUR, AUL, ADW, ADR, ADL)."""
    return note.note_type in AIR_ARROW_NOTES


def note_is_air_type(note: Note) -> bool:
    """Check if note is any air-related type."""
    return note.note_type in AIR_NOTE_TYPES


def note_has_steps(note: Note) -> bool:
    """Check if note contains sub-steps (Slide, AirSlideStart)."""
    return isinstance(note, _COMPOSITE_NOTE_CLASSES)


def note_get_steps(note: Note) -> tuple[Note, ...]:
    """Get the steps of a composite note, or an empty tuple."""
    try:
        return tuple(getattr(note, "steps", ()))
    except (TypeError, AttributeError):
        return ()


def note_tick_span(note: Note, resolution: int) -> tuple[int, int]:
    """Return (start_tick, end_tick) for a note."""
    start = note.measure * resolution + note.offset
    end = start + note_duration(note)
    return start, end
