"""Mutation helpers for chart editing workflows."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from src.core.const import NoteType  # noqa: TC001
from src.notes import (  # noqa: TC001
    DEFAULT_NOTE_DURATION as _DEFAULT_NOTE_DURATION,
    Air,
    AirHold,
    AirHoldStart,
    AirSlide,
    AirSlideStart,
    CrashSlide,
    ExTap,
    Flick,
    Hold,
    Mine,
    Note,
    Slide,
    SlideTo,
    Tap,
    build_editor_note,
    clamp_note_geometry as _clamp_note_geometry,
)

if TYPE_CHECKING:
    from src.core.models import Chart

DEFAULT_NOTE_DURATION = _DEFAULT_NOTE_DURATION

__all__ = [
    "DEFAULT_NOTE_DURATION",
    "Air",
    "AirHold",
    "AirHoldStart",
    "AirSlide",
    "AirSlideStart",
    "CrashSlide",
    "ExTap",
    "Flick",
    "Hold",
    "Mine",
    "Note",
    "NoteType",
    "Slide",
    "SlideTo",
    "Tap",
    "add_note",
    "clamp_note_geometry",
    "make_note",
    "move_note",
    "remove_notes",
    "snap_abs_pos",
]


# ── Public API ──────────────────────────────────────────────────────────


def snap_abs_pos(abs_pos: float, resolution: int, subdivisions: int) -> tuple[int, int]:
    """Snap an absolute measure position to the active editor grid."""
    resolution = max(1, int(resolution))
    subdivisions = max(1, int(subdivisions))
    tick_step = max(1, round(resolution / subdivisions))
    raw_tick = max(0, round(abs_pos * resolution))
    snapped_tick = round(raw_tick / tick_step) * tick_step
    return snapped_tick // resolution, snapped_tick % resolution


def clamp_note_geometry(cell: int, width: int) -> tuple[int, int]:
    """Clamp note lane geometry to the 16-lane CHUNITHM playfield."""
    return _clamp_note_geometry(cell, width)


def make_note(  # noqa: PLR0913
    note_type: NoteType,
    *,
    measure: int = 0,
    offset: int = 0,
    cell: int = 0,
    width: int = 0,
    duration: int | None = None,
    end_cell: int | None = None,
    end_width: int | None = None,
    target: str | None = None,
    animation: str | None = None,
    color: int | None = None,
    is_visible: bool = True,
    crush_interval: int | None = None,
    height: int | None = None,
    end_height: int | None = None,
    end_offset: int | None = None,
    steps: list[dict[str, Any]] | None = None,
    unknown: int | None = None,
    parent: Note | None = None,
    target_note: str | None = None,
) -> Note:
    """Create a note with valid default extra fields for the requested type."""
    return build_editor_note(
        note_type,
        measure=measure,
        offset=offset,
        cell=cell,
        width=width,
        duration=duration,
        end_cell=end_cell,
        end_width=end_width,
        parent=parent,
        target_note=target_note,
    )


def add_note(chart: Chart, note: Note) -> None:
    """Append a note and refresh cached timeline/index state."""
    chart.notes.append(note)
    chart.notes.sort(key=lambda n: (n.measure, n.offset, n.cell, n.width, n.note_type.value))
    chart.invalidate_timeline()


def remove_notes(chart: Chart, notes: list[Note]) -> int:
    """Remove selected top-level notes from a chart."""
    selected = set(notes)
    original_count = len(chart.notes)
    chart.notes = [note for note in chart.notes if note not in selected]
    removed = original_count - len(chart.notes)
    if removed:
        chart.invalidate_timeline()
    return removed


def move_note(chart: Chart, note: Note, *, measure: int, offset: int, cell: int) -> Note:
    """Return a moved copy of a note and replace it in the chart."""
    cell, width = clamp_note_geometry(cell, note.width)
    moved = replace(note, measure=max(0, measure), offset=max(0, offset), cell=cell, width=width)
    for index, existing in enumerate(chart.notes):
        if existing is note:
            chart.notes[index] = moved
            chart.invalidate_timeline()
            return moved
    raise ValueError("Note does not belong to chart")
