"""Mutation helpers for chart editing workflows."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

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

# ── Builder registry ────────────────────────────────────────────────────

_Base = dict[str, Any]


def _build_tap(b: _Base, **extras: Any) -> Note:
    return Tap(**b)


def _build_extap(b: _Base, **extras: Any) -> Note:
    return ExTap(**b, unknown="0")


def _build_flick(b: _Base, **extras: Any) -> Note:
    return Flick(**b, unknown="L")


def _build_mine(b: _Base, **extras: Any) -> Note:
    return Mine(**b)


def _build_air_solid(b: _Base, duration: int, **extras: Any) -> Note:
    ec, ew = _end_geom(b["cell"], b["width"], extras.get("end_cell"), extras.get("end_width"))
    return AirSolid(**b, starting_height=1.0, starting_depth=1.0,
                    duration=duration, end_cell=ec, end_width=ew,
                    target_height=1.0, target_depth=1.0, color="DEF")


def _build_heaven_hold(b: _Base, duration: int, **extras: Any) -> Note:
    ec, ew = _end_geom(b["cell"], b["width"], extras.get("end_cell"), extras.get("end_width"))
    return HeavenHold(**b, starting_height=1.0, duration=duration,
                      end_cell=ec, end_width=ew, target_height=1.0,
                      heaven_id=0,
                      animation="UP" if b["note_type"] == NoteType.HHX else None)


def _build_hold(b: _Base, duration: int, **extras: Any) -> Note:
    return Hold(**b, duration=duration)


def _build_slide(b: _Base, duration: int, **extras: Any) -> Note:
    ec, ew = _end_geom(b["cell"], b["width"], extras.get("end_cell"), extras.get("end_width"))
    step = SlideTo(**b, duration=duration, end_cell=ec, end_width=ew,
                   target_id="", animation=None,
                   is_visible=b["note_type"] in {NoteType.SLD, NoteType.SXD})
    return Slide(**b, steps=(step,))


def _build_air(b: _Base, **extras: Any) -> Note:
    return Air(**b, target_note=extras.get("target_note", "DEF"))


def _build_air_hold_start(b: _Base, duration: int, **extras: Any) -> Note:
    return AirHoldStart(**b, target_note=extras.get("target_note", "DEF"), duration=duration)


def _build_air_hold(b: _Base, duration: int, **extras: Any) -> Note:
    return AirHold(**b, target_note=extras.get("target_note", "DEF"), duration=duration, color="DEF")


def _build_air_trace(b: _Base, duration: int, **extras: Any) -> Note:
    ec, ew = _end_geom(b["cell"], b["width"], extras.get("end_cell"), extras.get("end_width"))
    return CrashSlide(**b, crush_interval=0, starting_height=1.0,
                      duration=duration, end_cell=ec, end_width=ew,
                      target_height=1.0, color="NON")


def _build_air_slide(b: _Base, duration: int, **extras: Any) -> Note:
    ec, ew = _end_geom(b["cell"], b["width"], extras.get("end_cell"), extras.get("end_width"))
    step = AirSlide(**b, target_note=extras.get("target_note", "DEF"),
                    starting_height=1.0, duration=duration,
                    end_cell=ec, end_width=ew, target_height=1.0, color="DEF")
    return AirSlideStart(**b, steps=(step,))


_NOTE_BUILDERS: dict[NoteType, Any] = {
    NoteType.TAP: _build_tap,
    NoteType.CHR: _build_extap,
    NoteType.FLK: _build_flick,
    NoteType.MNE: _build_mine,
    NoteType.ASO: _build_air_solid,
    NoteType.HHD: _build_heaven_hold,
    NoteType.HHX: _build_heaven_hold,
    NoteType.HLD: _build_hold,
    NoteType.HXD: _build_hold,
    NoteType.SLD: _build_slide,
    NoteType.SXD: _build_slide,
    NoteType.SLC: _build_slide,
    NoteType.SXC: _build_slide,
    NoteType.AIR: _build_air,
    NoteType.AUR: _build_air,
    NoteType.AUL: _build_air,
    NoteType.ADW: _build_air,
    NoteType.ADR: _build_air,
    NoteType.ADL: _build_air,
    NoteType.AHD: _build_air_hold_start,
    NoteType.AHX: _build_air_hold,
    NoteType.ALD: _build_air_trace,
    NoteType.ASD: _build_air_slide,
    NoteType.ASC: _build_air_slide,
}


def _end_geom(cell: int, width: int, end_cell: Any, end_width: Any) -> tuple[int, int]:
    return clamp_note_geometry(
        cell if end_cell is None else end_cell,
        width if end_width is None else end_width,
    )

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
    builder = _NOTE_BUILDERS.get(note_type)
    if builder is None:
        raise ValueError(f"Unsupported note type: {note_type.value}")
    return builder(
        {"note_type": note_type, "measure": max(0, int(measure)),
         "offset": max(0, int(offset)), "cell": cell, "width": width,
         "parent": parent},
        duration=duration,
        end_cell=end_cell,
        end_width=end_width,
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
