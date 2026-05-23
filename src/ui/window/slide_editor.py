"""Ground and air slide segment append/insert/find operations."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from src.core.const import NoteType
from src.core.editor import make_note
from src.notes import AirSlide, AirSlideStart, Note, Slide, SlideTo

if TYPE_CHECKING:
    from src.ui.window.window import MainWindow


GROUND_SLIDE_TYPES = {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC}
AIR_SLIDE_TYPES = {NoteType.ASD, NoteType.ASC}


class SlideEditor:
    """Manipulates ground and air slide chains inside a chart."""

    def __init__(self, window: MainWindow) -> None:
        self.w = window

    @property
    def _chart(self):
        return self.w.current_chart

    # ── Ground slides ──

    def append_ground(
        self, start_tick: int, start_cell: int, width: int,
        start_measure: int, start_offset: int, duration: int, end_cell: int,
    ) -> Slide | None:
        chart = self._chart
        if chart is None:
            return None
        tail = self._find_ground_tail(start_tick, start_cell, width)
        if tail is None:
            return self.insert_ground(
                start_tick, start_cell, width,
                start_measure, start_offset, duration, end_cell,
            )
        segment = make_note(
            self.w._editor_note_type,
            measure=start_measure, offset=start_offset,
            cell=start_cell, width=width,
            duration=duration, end_cell=end_cell, end_width=width,
        )
        if not isinstance(segment, Slide):
            return None
        original, _tail_step = tail
        replacement = replace(original, steps=(*original.steps, segment.steps[0]))
        self._replace(original, replacement)
        return replacement

    def insert_ground(
        self, start_tick: int, start_cell: int, width: int,
        start_measure: int, start_offset: int, duration: int, end_cell: int,
    ) -> Slide | None:
        chart = self._chart
        if chart is None:
            return None
        containing = self._find_ground_segment(start_tick, start_cell, width)
        if containing is None:
            return None
        original, split_step, split_index = containing
        seg_start = self._tl.note_tick(split_step)
        seg_end = self._tl.note_end_tick(split_step)
        inserted_end = start_tick + duration
        if inserted_end > seg_end:
            return None
        segment = make_note(
            self.w._editor_note_type,
            measure=start_measure, offset=start_offset,
            cell=start_cell, width=width,
            duration=duration, end_cell=end_cell, end_width=width,
        )
        if not isinstance(segment, Slide):
            return None
        inserted_step = segment.steps[0]
        steps: list[SlideTo] = list(original.steps[:split_index])
        steps.append(replace(split_step, duration=start_tick - seg_start, end_cell=start_cell, end_width=width))
        steps.append(inserted_step)
        if inserted_end < seg_end:
            rem_meas, rem_off = divmod(inserted_end, chart.metadata.resolution)
            steps.append(replace(split_step, measure=rem_meas, offset=rem_off, cell=end_cell, width=width, duration=seg_end - inserted_end))
        steps.extend(original.steps[split_index + 1:])
        replacement = replace(original, steps=tuple(steps))
        self._replace(original, replacement)
        return replacement

    def _find_ground_tail(self, tick: int, cell: int, width: int) -> tuple[Slide, Note] | None:
        chart = self._chart
        if chart is None:
            return None
        tl = chart.timeline
        for note in reversed(chart.notes):
            if not isinstance(note, Slide) or not note.steps:
                continue
            tail = note.steps[-1]
            if tl.note_end_tick(tail) == tick and tail.end_cell == cell and tail.end_width == width:
                return note, tail
        return None

    def _find_ground_segment(self, tick: int, cell: int, width: int) -> tuple[Slide, SlideTo, int] | None:
        chart = self._chart
        if chart is None:
            return None
        tl = chart.timeline
        candidates: list[tuple[int, Slide, SlideTo, int]] = []
        for note in reversed(chart.notes):
            if not isinstance(note, Slide):
                continue
            for idx, step in enumerate(note.steps):
                if not tl.note_tick(step) < tick < tl.note_end_tick(step):
                    continue
                span = tl.span_at(step, tick)
                if span is None:
                    continue
                if span == (cell, width):
                    return note, step, idx
                candidates.append((abs(span[0] - cell) + abs(span[1] - width), note, step, idx))
        if candidates:
            _, note, step, idx = min(candidates, key=lambda x: x[0])
            return note, step, idx
        return None

    # ── Air slides ──

    def append_air(
        self, start_tick: int, start_cell: int, width: int,
        start_measure: int, start_offset: int, duration: int, end_cell: int,
    ) -> AirSlideStart | None:
        chart = self._chart
        if chart is None:
            return None
        tail = self._find_air_tail(start_tick, start_cell, width)
        if tail is None:
            return self.insert_air(
                start_tick, start_cell, width,
                start_measure, start_offset, duration, end_cell,
            )
        original, tail_step = tail
        segment = make_note(
            self.w._editor_note_type,
            measure=start_measure, offset=start_offset,
            cell=start_cell, width=width,
            duration=duration, end_cell=end_cell, end_width=width,
            target_note=tail_step.note_type.value, parent=tail_step,
        )
        if not isinstance(segment, AirSlideStart):
            return None
        replacement = replace(original, steps=(*original.steps, segment.steps[0]))
        self._replace(original, replacement)
        return replacement

    def insert_air(
        self, start_tick: int, start_cell: int, width: int,
        start_measure: int, start_offset: int, duration: int, end_cell: int,
    ) -> AirSlideStart | None:
        chart = self._chart
        if chart is None:
            return None
        containing = self._find_air_segment(start_tick, start_cell, width)
        if containing is None:
            return None
        original, split_step, split_index = containing
        seg_start = self._tl.note_tick(split_step)
        seg_end = self._tl.note_end_tick(split_step)
        inserted_end = start_tick + duration
        if inserted_end > seg_end:
            return None
        segment = make_note(
            self.w._editor_note_type,
            measure=start_measure, offset=start_offset,
            cell=start_cell, width=width,
            duration=duration, end_cell=end_cell, end_width=width,
            target_note=split_step.note_type.value, parent=split_step,
        )
        if not isinstance(segment, AirSlideStart):
            return None
        inserted_step = segment.steps[0]
        steps: list[AirSlide] = list(original.steps[:split_index])
        steps.append(replace(split_step, duration=start_tick - seg_start, end_cell=start_cell, end_width=width))
        steps.append(inserted_step)
        if inserted_end < seg_end:
            rem_meas, rem_off = divmod(inserted_end, chart.metadata.resolution)
            steps.append(replace(split_step, measure=rem_meas, offset=rem_off, cell=end_cell, width=width, duration=seg_end - inserted_end, target_note=inserted_step.note_type.value, parent=inserted_step))
        steps.extend(original.steps[split_index + 1:])
        replacement = replace(original, steps=tuple(steps))
        self._replace(original, replacement)
        return replacement

    def _find_air_tail(self, tick: int, cell: int, width: int) -> tuple[AirSlideStart, Note] | None:
        chart = self._chart
        if chart is None:
            return None
        tl = chart.timeline
        for note in reversed(chart.notes):
            if not isinstance(note, AirSlideStart) or not note.steps:
                continue
            tail = note.steps[-1]
            if tl.note_end_tick(tail) == tick and tail.end_cell == cell and tail.end_width == width:
                return note, tail
        return None

    def _find_air_segment(self, tick: int, cell: int, width: int) -> tuple[AirSlideStart, AirSlide, int] | None:
        chart = self._chart
        if chart is None:
            return None
        tl = chart.timeline
        candidates: list[tuple[int, AirSlideStart, AirSlide, int]] = []
        for note in reversed(chart.notes):
            if not isinstance(note, AirSlideStart):
                continue
            for idx, step in enumerate(note.steps):
                if not tl.note_tick(step) < tick < tl.note_end_tick(step):
                    continue
                span = tl.span_at(step, tick)
                if span is None:
                    continue
                if span == (cell, width):
                    return note, step, idx
                candidates.append((abs(span[0] - cell) + abs(span[1] - width), note, step, idx))
        if candidates:
            _, note, step, idx = min(candidates, key=lambda x: x[0])
            return note, step, idx
        return None

    # ── Utilities ──

    def replace_note(self, original: Note, replacement: Note) -> None:
        chart = self._chart
        if chart is None:
            return
        for i, n in enumerate(chart.notes):
            if n is original:
                chart.notes[i] = replacement
                chart.invalidate_timeline()
                return

    def _replace(self, original: Note, replacement: Note) -> None:
        self.replace_note(original, replacement)

    @property
    def _tl(self):
        chart = self._chart
        return chart.timeline if chart else None
