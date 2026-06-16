from __future__ import annotations

# ruff: noqa: PLR0912, PLR0913, PLR0915
from PySide6.QtGui import QColor, QPainter

from src.core.const import NoteType, RenderRole
from src.notes import Note, Slide, SlideTo
from src.ui.components.play_view.geometry import (
    DRAW_DEPTH_MAX,
    _clip_sustain_segment,
    _depth_in_draw_range,
    _note_screen_span,
    _sustain_draw_depths,
)


class PlayViewSlideNotesMixin:
    def _draw_slide(
        self,
        painter: QPainter,
        note: Note,
        x: float,
        y: float,
        w: float,
        scale: float,
        color: QColor,
        alpha: int,
        judge_time: float,
        depth: float,
        end_depth: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> None:
        if isinstance(note, Slide) and note.steps:
            self._draw_slide_steps(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        elif isinstance(note, SlideTo):
            draw_depths = _sustain_draw_depths(depth, end_depth)
            if draw_depths is None:
                return
            (
                start_cell,
                start_width,
                draw_depth,
                end_cell,
                end_width,
                draw_end_depth,
            ) = _clip_sustain_segment(
                note.cell,
                note.width,
                depth,
                note.end_cell,
                note.end_width,
                end_depth,
            )
            if draw_depth != depth:
                scale, y, _ = self._world_z_to_screen(draw_depth, vanish_y, judge_y)
                x, w = _note_screen_span(start_cell, start_width, vanish_x, scale)

            end_scale, end_y, _ = self._world_z_to_screen(draw_end_depth, vanish_y, judge_y)
            end_x, end_w = _note_screen_span(end_cell, end_width, vanish_x, end_scale)

            self._draw_projected_sustain_body(
                painter,
                note,
                start_cell,
                start_width,
                draw_depth,
                end_cell,
                end_width,
                draw_end_depth,
                color,
                alpha,
            )

            if _depth_in_draw_range(depth):
                self._draw_tap_quad(
                    painter,
                    x,
                    y,
                    w,
                    scale,
                    color,
                    alpha,
                    note,
                    draw_depth,
                    cell=start_cell,
                    width=start_width,
                )
            if _depth_in_draw_range(draw_end_depth):
                end_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
                self._draw_tap_quad(
                    painter,
                    end_x,
                    end_y,
                    end_w,
                    end_scale,
                    end_color,
                    alpha // 2,
                    note,
                    draw_end_depth,
                    cell=end_cell,
                    width=end_width,
                )
    def _draw_slide_steps(
        self,
        painter: QPainter,
        note: Slide,
        x: float,
        y: float,
        w: float,
        scale: float,
        color: QColor,
        alpha: int,
        judge_time: float,
        depth: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> None:
        tl = self.chart.timeline if self.chart else None
        if not tl or not note.steps:
            return

        if _depth_in_draw_range(depth) and self._should_draw_slide_head(note):
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, depth)

        prev_x, prev_y, prev_w, prev_scale = x, y, w, scale
        prev_cell, prev_width = float(note.cell), float(note.width)
        current_tick = tl.note_tick(note)
        prev_depth = depth
        last_depth = depth

        step_count = len(note.steps)
        for index, step in enumerate(note.steps):
            current_tick += step.duration
            step_time = tl.time_at(current_tick)
            step_depth = self._compute_note_depth(
                note,
                current_tick,
                step_time,
                judge_time,
                cell=float(step.end_cell),
                width=float(step.end_width),
            )
            last_depth = step_depth

            if min(prev_depth, step_depth) >= DRAW_DEPTH_MAX:
                break

            draw_depths = _sustain_draw_depths(prev_depth, step_depth)
            if draw_depths is None:
                step_scale, step_y, _ = self._world_z_to_screen(step_depth, vanish_y, judge_y)
                step_x, step_w = _note_screen_span(
                    step.end_cell, step.end_width, vanish_x, step_scale
                )
                prev_x, prev_y, prev_w, prev_scale = step_x, step_y, step_w, step_scale
                prev_cell, prev_width = float(step.end_cell), float(step.end_width)
                prev_depth = step_depth
                continue

            (
                start_cell,
                start_width,
                draw_start_depth,
                step_cell,
                step_width,
                draw_step_depth,
            ) = _clip_sustain_segment(
                prev_cell,
                prev_width,
                prev_depth,
                float(step.end_cell),
                float(step.end_width),
                step_depth,
            )
            prev_scale, prev_y, _ = self._world_z_to_screen(draw_start_depth, vanish_y, judge_y)
            prev_x, prev_w = _note_screen_span(start_cell, start_width, vanish_x, prev_scale)
            step_scale, step_y, _ = self._world_z_to_screen(draw_step_depth, vanish_y, judge_y)
            step_x, step_w = _note_screen_span(step_cell, step_width, vanish_x, step_scale)

            self._draw_projected_sustain_body(
                painter,
                note,
                start_cell,
                start_width,
                draw_start_depth,
                step_cell,
                step_width,
                draw_step_depth,
                color,
                alpha,
            )

            step_color = QColor(color.red(), color.green(), color.blue(), alpha * 3 // 4)
            if (
                self._should_draw_slide_step_head(index, step_count, step)
                and _depth_in_draw_range(step_depth)
                and self.visible_note_types.get(step.note_type.value, True)
            ):
                self._draw_tap_quad(
                    painter,
                    step_x,
                    step_y,
                    step_w,
                    step_scale,
                    step_color,
                    alpha,
                    note,
                    step_depth,
                    cell=step.end_cell,
                    width=step.end_width,
                )

            prev_x, prev_y, prev_w, prev_scale = step_x, step_y, step_w, step_scale
            prev_cell, prev_width = float(step.end_cell), float(step.end_width)
            prev_depth = step_depth

        if _depth_in_draw_range(last_depth):
            end_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
            self._draw_tap_quad(
                painter,
                prev_x,
                prev_y,
                prev_w,
                prev_scale,
                end_color,
                alpha // 2,
                note,
                prev_depth,
                cell=prev_cell,
                width=prev_width,
            )
    def _should_draw_slide_head(self, note: Note) -> bool:
        timeline = self.chart.timeline if self.chart else None
        if not timeline:
            return True
        if timeline.note_render_role(note) == RenderRole.HEAD:
            return True
        if note.note_type not in (NoteType.SXD, NoteType.SXC):
            return False
        predecessor = timeline.note_chain_predecessor(note)
        return predecessor is not None and predecessor.note_type not in (
            NoteType.SXD,
            NoteType.SXC,
        )
    def _should_draw_slide_step_head(self, index: int, step_count: int, step: SlideTo) -> bool:
        if index == step_count - 1:
            return False
        return step.note_type in {NoteType.SLD, NoteType.SXD}

