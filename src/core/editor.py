"""Mutation helpers for chart editing workflows."""

from __future__ import annotations

from dataclasses import replace

from src.core.const import NoteType
from src.core.models import Chart
from src.notes import (
    Air,
    AirHold,
    AirHoldStart,
    AirSlide,
    AirSlideStart,
    AirSolid,
    CrashSlide,
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

DEFAULT_NOTE_DURATION = 384


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
    clamped_cell = max(0, min(15, int(cell)))
    clamped_width = max(1, min(16 - clamped_cell, int(width)))
    return clamped_cell, clamped_width


def make_note(
    note_type: NoteType,
    *,
    measure: int,
    offset: int,
    cell: int,
    width: int,
    duration: int = DEFAULT_NOTE_DURATION,
    end_cell: int | None = None,
    end_width: int | None = None,
    target_note: str = "DEF",
    parent: Note | None = None,
) -> Note:
    """Create a note with valid default extra fields for the requested type."""
    cell, width = clamp_note_geometry(cell, width)
    duration = max(1, int(duration))
    base = {
        "note_type": note_type,
        "measure": max(0, int(measure)),
        "offset": max(0, int(offset)),
        "cell": cell,
        "width": width,
        "parent": parent,
    }

    if note_type == NoteType.TAP:
        return Tap(**base)
    if note_type == NoteType.CHR:
        return ExTap(**base, unknown="0")
    if note_type == NoteType.FLK:
        return Flick(**base, unknown="L")
    if note_type == NoteType.MNE:
        return Mine(**base)
    if note_type == NoteType.ASO:
        end_cell, end_width = clamp_note_geometry(
            cell if end_cell is None else end_cell,
            width if end_width is None else end_width,
        )
        return AirSolid(
            **base,
            starting_height=1.0,
            starting_depth=1.0,
            duration=duration,
            end_cell=end_cell,
            end_width=end_width,
            target_height=1.0,
            target_depth=1.0,
            color="DEF",
        )
    if note_type in {NoteType.HHD, NoteType.HHX}:
        end_cell, end_width = clamp_note_geometry(
            cell if end_cell is None else end_cell,
            width if end_width is None else end_width,
        )
        return HeavenHold(
            **base,
            starting_height=1.0,
            duration=duration,
            end_cell=end_cell,
            end_width=end_width,
            target_height=1.0,
            heaven_id=0,
            animation="UP" if note_type == NoteType.HHX else None,
        )
    if note_type in {NoteType.HLD, NoteType.HXD}:
        return Hold(**base, duration=duration)
    if note_type in {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC}:
        end_cell, end_width = clamp_note_geometry(
            cell if end_cell is None else end_cell,
            width if end_width is None else end_width,
        )
        step = SlideTo(
            **base,
            duration=duration,
            end_cell=end_cell,
            end_width=end_width,
            target_id="",
            animation=None,
            is_visible=note_type in {NoteType.SLD, NoteType.SXD},
        )
        return Slide(**base, steps=(step,))
    if note_type in {
        NoteType.AIR,
        NoteType.AUR,
        NoteType.AUL,
        NoteType.ADW,
        NoteType.ADR,
        NoteType.ADL,
    }:
        return Air(**base, target_note=target_note)
    if note_type == NoteType.AHD:
        return AirHoldStart(**base, target_note=target_note, duration=duration)
    if note_type == NoteType.AHX:
        return AirHold(**base, target_note=target_note, duration=duration, color="DEF")
    if note_type == NoteType.ALD:
        end_cell, end_width = clamp_note_geometry(
            cell if end_cell is None else end_cell,
            width if end_width is None else end_width,
        )
        return CrashSlide(
            **base,
            crush_tick=0,
            starting_height=1.0,
            duration=duration,
            end_cell=end_cell,
            end_width=end_width,
            target_height=1.0,
            color="NON",
        )
    if note_type in {NoteType.ASD, NoteType.ASC}:
        end_cell, end_width = clamp_note_geometry(
            cell if end_cell is None else end_cell,
            width if end_width is None else end_width,
        )
        step = AirSlide(
            **base,
            target_note=target_note,
            starting_height=1.0,
            duration=duration,
            end_cell=end_cell,
            end_width=end_width,
            target_height=1.0,
            color="DEF",
        )
        return AirSlideStart(**base, steps=(step,))

    raise ValueError(f"Unsupported note type: {note_type.value}")


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
