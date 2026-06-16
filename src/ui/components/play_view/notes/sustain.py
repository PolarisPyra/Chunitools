from __future__ import annotations

# ruff: noqa: PLR0912, PLR0913, PLR0915
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF

from src.core.const import NoteType, RenderRole
from src.notes import Note, Slide, SlideTo
from src.ui.components.play_view.geometry import (
    DRAW_DEPTH_MAX,
    FIELD_HALF,
    LANE_WIDTH,
    NOTE_WIDTH_FRAC,
    RENDER_BIG_NOTE_DEPTH,
    RENDER_NOTE_DEPTH,
    _clip_sustain_segment,
    _compact_depth_to_z,
    _depth_in_draw_range,
    _note_screen_span,
    _project_point,
    _projected_polygon_is_bounded,
    _projection_for_depth,
    _sustain_draw_depths,
)

AIR_WRAPPED_GROUND_TYPES = {
    NoteType.TAP,
    NoteType.CHR,
    NoteType.FLK,
    NoteType.MNE,
    NoteType.HLD,
    NoteType.HXD,
    NoteType.SLD,
    NoteType.SLC,
    NoteType.SXD,
    NoteType.SXC,
}
AIR_WRAPPED_EX_HEAD_TYPES = {NoteType.CHR, NoteType.HXD, NoteType.SXD, NoteType.SXC}


class PlayViewSustainNotesMixin:
    def _project_flat_note_corners(
        self, note: Note, cell: float, width: float, depth: float
    ) -> list[QPointF]:
        is_big = note.note_type in {NoteType.HLD, NoteType.HXD, NoteType.SLD, NoteType.SXD}
        return self._project_flat_note_corners_at_world_y(
            cell,
            width,
            depth,
            self._get_world_y(note),
            is_big=is_big,
        )
    def _project_flat_note_corners_at_world_y(
        self,
        cell: float,
        width: float,
        depth: float,
        world_y: float,
        *,
        is_big: bool = False,
    ) -> list[QPointF]:
        w, h = self.width(), self.height()
        w_x0 = cell * LANE_WIDTH - FIELD_HALF
        w_x1 = (cell + width) * LANE_WIDTH - FIELD_HALF
        z = _compact_depth_to_z(depth)
        half_depth = (RENDER_BIG_NOTE_DEPTH if is_big else RENDER_NOTE_DEPTH) / 2.0
        z_far = z - half_depth
        z_near = z + half_depth
        pt0 = _project_point(w_x0, world_y, z_far, w, h)
        pt1 = _project_point(w_x1, world_y, z_far, w, h)
        pt2 = _project_point(w_x1, world_y, z_near, w, h)
        pt3 = _project_point(w_x0, world_y, z_near, w, h)
        return [QPointF(*pt0), QPointF(*pt1), QPointF(*pt2), QPointF(*pt3)]
    def _project_sustain_corners(
        self,
        note: Note,
        start_cell: float,
        start_width: float,
        start_depth: float,
        end_cell: float,
        end_width: float,
        end_depth: float,
        *,
        start_world_y: float | None = None,
        end_world_y: float | None = None,
        start_width_factor: float = NOTE_WIDTH_FRAC,
        end_width_factor: float = NOTE_WIDTH_FRAC,
    ) -> list[QPointF]:
        viewport_w, viewport_h = self.width(), self.height()
        start_y = self._get_world_y(note) if start_world_y is None else start_world_y
        end_y = self._get_world_y(note) if end_world_y is None else end_world_y
        start_center = (start_cell + start_width / 2.0) * LANE_WIDTH - FIELD_HALF
        end_center = (end_cell + end_width / 2.0) * LANE_WIDTH - FIELD_HALF
        start_visual_width = start_width * LANE_WIDTH * start_width_factor
        end_visual_width = end_width * LANE_WIDTH * end_width_factor
        start_x0 = start_center - start_visual_width / 2.0
        start_x1 = start_center + start_visual_width / 2.0
        end_x0 = end_center - end_visual_width / 2.0
        end_x1 = end_center + end_visual_width / 2.0
        start_z = _compact_depth_to_z(start_depth)
        end_z = _compact_depth_to_z(end_depth)
        return [
            QPointF(*_project_point(start_x0, start_y, start_z, viewport_w, viewport_h)),
            QPointF(*_project_point(start_x1, start_y, start_z, viewport_w, viewport_h)),
            QPointF(*_project_point(end_x1, end_y, end_z, viewport_w, viewport_h)),
            QPointF(*_project_point(end_x0, end_y, end_z, viewport_w, viewport_h)),
        ]
    def _draw_projected_sustain_body(
        self,
        painter: QPainter,
        note: Note,
        start_cell: float,
        start_width: float,
        start_depth: float,
        end_cell: float,
        end_width: float,
        end_depth: float,
        color: QColor,
        alpha: int,
        *,
        start_world_y: float | None = None,
        end_world_y: float | None = None,
        start_width_factor: float = NOTE_WIDTH_FRAC,
        end_width_factor: float = NOTE_WIDTH_FRAC,
    ) -> None:
        if painter is None:
            return
        corners = self._project_sustain_corners(
            note,
            start_cell,
            start_width,
            start_depth,
            end_cell,
            end_width,
            end_depth,
            start_world_y=start_world_y,
            end_world_y=end_world_y,
            start_width_factor=start_width_factor,
            end_width_factor=end_width_factor,
        )
        if not _projected_polygon_is_bounded(corners, self.width(), self.height()):
            return

        body_color = QColor(color.red(), color.green(), color.blue(), alpha // 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body_color)
        painter.drawPolygon(QPolygonF(corners))

        start_mid = (corners[0] + corners[1]) * 0.5
        end_mid = (corners[2] + corners[3]) * 0.5
        start_scale = _projection_for_depth(start_depth, self.width(), self.height())[0]
        end_scale = _projection_for_depth(end_depth, self.width(), self.height())[0]
        pen_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
        painter.setPen(QPen(pen_color, max(1, int(min(start_scale, end_scale) * 2))))
        painter.drawLine(start_mid, end_mid)
    def _draw_hold(
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
        draw_depths = _sustain_draw_depths(depth, end_depth)
        if draw_depths is None:
            return
        draw_depth, draw_end_depth = draw_depths
        if draw_depth != depth:
            scale, y, _ = self._world_z_to_screen(draw_depth, vanish_y, judge_y)
            x, w = _note_screen_span(note.cell, note.width, vanish_x, scale)

        end_scale, end_y, _ = self._world_z_to_screen(draw_end_depth, vanish_y, judge_y)
        end_x, end_w = _note_screen_span(note.cell, note.width, vanish_x, end_scale)

        self._draw_projected_sustain_body(
            painter,
            note,
            note.cell,
            note.width,
            draw_depth,
            note.cell,
            note.width,
            draw_end_depth,
            color,
            alpha,
        )

        if _depth_in_draw_range(depth):
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, draw_depth)
        if _depth_in_draw_range(draw_end_depth):
            end_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
            self._draw_tap_quad(
                painter, end_x, end_y, end_w, end_scale, end_color, alpha // 2, note, draw_end_depth
            )
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

