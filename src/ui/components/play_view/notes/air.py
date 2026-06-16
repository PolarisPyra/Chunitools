from __future__ import annotations

# ruff: noqa: PLR0912, PLR0913, PLR0915
import math
from dataclasses import replace

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from src.core.const import NoteType
from src.notes import AirSlideStart, Note
from src.ui.components.play_view.geometry import (
    AIR_ARROW_ANCHOR_OFFSET,
    AIR_ARROW_HEIGHT_SCALE,
    AIR_ARROW_WIDTH_SCALE,
    DRAW_DEPTH_MAX,
    _air_arrow_screen_span,
    _air_path_screen_span,
    _air_path_width_factor,
    _air_path_world_y,
    _air_trace_width_factor_from_world_y,
    _air_trace_world_y_from_g0,
    _chart_air_height_to_g0,
    _clip_air_path_segment,
    _compact_depth_to_z,
    _depth_in_draw_range,
    _lerp,
    _project_point,
    _projected_polygon_is_bounded,
    _projection_for_depth,
    _scaled_span_width,
    _sustain_draw_depths,
)
from src.ui.theme.notes import get_note_color

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
AIR_ANCHOR_FLOOR_TYPES = {
    NoteType.HLD,
    NoteType.HXD,
    NoteType.SLD,
    NoteType.SLC,
    NoteType.SXD,
    NoteType.SXC,
}
AIR_LIFT_STEM_WIDTH_FACTOR = 0.42


class PlayViewAirNotesMixin:
    def _air_path_screen_y(self, note: Note, depth: float, *, end: bool = False) -> float | None:
        world_y = _air_path_world_y(note, end=end)
        if world_y is None:
            return None
        _, screen_y = _project_point(
            0.0,
            world_y,
            _compact_depth_to_z(depth),
            self.width(),
            self.height(),
        )
        return screen_y
    def _air_path_screen_span_at(
        self,
        cell: float,
        width: float,
        depth: float,
        world_y: float | None,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> tuple[float, float, float, float]:
        scale, screen_y, _ = self._world_z_to_screen(depth, vanish_y, judge_y)
        if world_y is not None:
            _, screen_y = _project_point(
                0.0,
                world_y,
                _compact_depth_to_z(depth),
                self.width(),
                self.height(),
            )
        screen_x, screen_w = _air_path_screen_span(cell, width, vanish_x, scale)
        return screen_x, screen_y, screen_w, scale
    def _air_trace_screen_span_at(
        self,
        cell: float,
        width: float,
        depth: float,
        world_y: float | None,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> tuple[float, float, float, float]:
        screen_x, screen_y, screen_w, scale = self._air_path_screen_span_at(
            cell, width, depth, world_y, vanish_x, vanish_y, judge_y
        )
        trace_x, trace_w = _scaled_span_width(
            screen_x, screen_w, _air_trace_width_factor_from_world_y(world_y)
        )
        return trace_x, screen_y, trace_w, scale
    def _air_arrow_screen_span_at_anchor(
        self,
        note: Note,
        vanish_x: float,
        scale: float,
    ) -> tuple[float, float]:
        anchor = getattr(note, "parent", None)
        timeline = self.chart.timeline if self.chart else None
        if anchor is None or not timeline:
            return _air_arrow_screen_span(note.cell, note.width, vanish_x, scale)

        tick = timeline.note_tick(note)
        anchor_end_tick = timeline.note_end_tick(anchor)
        if tick == anchor_end_tick and anchor_end_tick != timeline.note_tick(anchor):
            cell = getattr(anchor, "end_cell", anchor.cell)
            width = getattr(anchor, "end_width", anchor.width)
        else:
            span = timeline.span_at(anchor, tick)
            if span is None:
                cell, width = anchor.cell, anchor.width
            else:
                cell, width = span

        return _air_arrow_screen_span(cell, width, vanish_x, scale)

    def _air_anchor_span_for_note(self, note: Note, *, end: bool = False) -> tuple[float, float]:
        anchor = getattr(note, "parent", None)
        timeline = self.chart.timeline if self.chart else None
        if anchor is None or not timeline:
            return float(note.cell), float(note.width)

        tick = timeline.note_end_tick(note) if end else timeline.note_tick(note)
        anchor_end_tick = timeline.note_end_tick(anchor)
        if tick == anchor_end_tick and anchor_end_tick != timeline.note_tick(anchor):
            return float(getattr(anchor, "end_cell", anchor.cell)), float(
                getattr(anchor, "end_width", anchor.width)
            )

        span = timeline.span_at(anchor, tick)
        if span is not None:
            return float(span[0]), float(span[1])
        return float(anchor.cell), float(anchor.width)

    def _air_anchor_for_note(self, note: Note) -> tuple[Note, bool] | None:
        timeline = self.chart.timeline if self.chart else None
        anchor = getattr(note, "parent", None)
        if anchor is None:
            return None

        end = False
        if timeline:
            tick = timeline.note_tick(note)
            anchor_start = timeline.note_tick(anchor)
            anchor_end = timeline.note_end_tick(anchor)
            end = tick == anchor_end and anchor_end != anchor_start

        return anchor, end
    def _air_anchor_draws_separately(self, note: Note) -> bool:
        anchor_info = self._air_anchor_for_note(note)
        if anchor_info is None:
            return False
        anchor, _end = anchor_info
        return anchor in self._notes and self.visible_note_types.get(anchor.note_type.value, True)
    def _air_has_floor_anchor(self, note: Note) -> bool:
        anchor_info = self._air_anchor_for_note(note)
        if anchor_info is None:
            return False
        anchor, _end = anchor_info
        return anchor.note_type in AIR_ANCHOR_FLOOR_TYPES
    def _air_wrapped_start_world_y(self, note: Note) -> float | None:
        return _air_path_world_y(note)
    def _air_anchor_world_y(self, note: Note) -> float | None:
        anchor_info = self._air_anchor_for_note(note)
        if anchor_info is None:
            if note.note_type == NoteType.AHX:
                return 0.0
            return None
        anchor, end = anchor_info
        anchor_world_y = _air_path_world_y(anchor, end=end)
        if anchor_world_y is None:
            return 0.0
        return anchor_world_y
    def _air_anchor_screen_y(
        self,
        note: Note,
        depth: float,
        vanish_y: float,
        judge_y: float,
    ) -> float | None:
        anchor_info = self._air_anchor_for_note(note)
        if anchor_info is None:
            world_y = self._air_anchor_world_y(note)
            if world_y is None or world_y == 0.0:
                return None
        else:
            anchor, end = anchor_info
            world_y = _air_path_world_y(anchor, end=end)
            if world_y is None:
                # anchor is ground-level — don't override the arrow's elevated Y
                return None

        _, screen_y = _project_point(
            0.0,
            world_y,
            _compact_depth_to_z(depth),
            self.width(),
            self.height(),
        )
        return screen_y
    def _draw_air_lift_if_needed(
        self,
        painter: QPainter,
        note: Note,
        cell: float,
        width: float,
        depth: float,
        path_world_y: float | None,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
        color: QColor,
        alpha: int,
    ) -> None:
        if not _depth_in_draw_range(depth) or path_world_y is None:
            return
        anchor_world_y = self._air_anchor_world_y(note)
        if anchor_world_y is None or abs(anchor_world_y - path_world_y) < 1.0:
            return

        x, y_top, w, scale = self._air_path_screen_span_at(
            cell, width, depth, path_world_y, vanish_x, vanish_y, judge_y
        )
        stem_w = max(3.0, w * AIR_LIFT_STEM_WIDTH_FACTOR)
        stem_x = x + (w - stem_w) / 2.0
        _, y_bottom, _, _ = self._air_path_screen_span_at(
            cell, width, depth, anchor_world_y, vanish_x, vanish_y, judge_y
        )
        overlap = max(3.0, scale * 6.0)
        y_top_overlapped = y_top - overlap if y_bottom > y_top else y_top + overlap
        self._draw_air_lift_connector(
            painter, stem_x, y_bottom, y_top_overlapped, stem_w, scale, color, alpha
        )
    def _draw_air_lift_connector(
        self,
        painter: QPainter,
        x: float,
        y_bottom: float,
        y_top: float,
        w: float,
        scale: float,
        color: QColor,
        alpha: int,
    ) -> None:
        if painter is None:
            return
        if not all(math.isfinite(value) for value in (x, y_bottom, y_top, w, scale)):
            return
        if w <= 0.0 or abs(y_bottom - y_top) < 1.0:
            return
        top = min(y_bottom, y_top)
        bottom = max(y_bottom, y_top)
        body_points = [
            QPointF(x, bottom),
            QPointF(x + w, bottom),
            QPointF(x + w, top),
            QPointF(x, top),
        ]
        if not _projected_polygon_is_bounded(body_points, self.width(), self.height()):
            return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), alpha // 3)))
        painter.drawPolygon(QPolygonF(body_points))

        center_x = x + w / 2.0
        edge_color = QColor(color.red(), color.green(), color.blue(), max(40, alpha // 2))
        painter.setPen(QPen(edge_color, max(1, int(scale * 2))))
        painter.drawLine(QPointF(x, bottom), QPointF(x, top))
        painter.drawLine(QPointF(x + w, bottom), QPointF(x + w, top))

        center_color = QColor(color.red(), color.green(), color.blue(), alpha)
        painter.setPen(QPen(center_color, max(2, int(scale * 4))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(center_x, y_bottom), QPointF(center_x, y_top))
    def _draw_air_arrow(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        scale: float,
        color: QColor,
        alpha: int,
        nt: NoteType,
    ) -> None:
        sw = w * AIR_ARROW_WIDTH_SCALE
        sh = max(6.0, AIR_ARROW_HEIGHT_SCALE * scale)
        is_down = nt in {NoteType.ADW, NoteType.ADR, NoteType.ADL}

        painter.save()
        painter.translate(x + w / 2, y - AIR_ARROW_ANCHOR_OFFSET * scale)

        if is_down:
            painter.scale(1, -1)
            painter.translate(0, sh)

        if nt in {NoteType.AUL, NoteType.ADL}:
            painter.shear(0.5, 0)
        elif nt in {NoteType.AUR, NoteType.ADR}:
            painter.shear(-0.5, 0)

        points = [
            QPointF(-sw / 2, 0),
            QPointF(-sw / 2, -sh * 2 / 3),
            QPointF(0, -sh),
            QPointF(sw / 2, -sh * 2 / 3),
            QPointF(sw / 2, 0),
            QPointF(0, -sh * 1 / 3),
        ]
        polygon = QPolygonF(points)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), alpha)))
        painter.drawPolygon(polygon)

        border_width = max(1.5, sh * 0.12)
        border_color = QColor(220, 220, 220, alpha)
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(polygon)

        painter.restore()
    def _draw_or_defer_air_arrow(
        self,
        painter: QPainter,
        note: Note,
        x: float,
        y: float,
        w: float,
        scale: float,
        alpha: int,
        nt: NoteType,
        depth: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> None:
        if self._defer_air_arrows and (
            self._air_anchor_for_note(note) is not None or note.note_type == NoteType.AHX
        ):
            self._deferred_air_arrows.append(
                (note, x, y, w, scale, alpha, nt, depth, vanish_x, vanish_y, judge_y)
            )
            return

        self._draw_air_arrow_for_note(
            painter, note, x, y, w, scale, alpha, nt, depth, vanish_x, vanish_y, judge_y
        )
    def _draw_air_arrow_for_note(
        self,
        painter: QPainter,
        note: Note,
        x: float,
        y: float,
        w: float,
        scale: float,
        alpha: int,
        nt: NoteType,
        depth: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> None:
        anchor_info = self._air_anchor_for_note(note)
        if anchor_info is not None or note.note_type == NoteType.AHX:
            # Anchor gives us the correct lane span (X, W). Only override Y when
            # the anchor itself is at air height (not ground-level).
            anchored_y = self._air_anchor_screen_y(note, depth, vanish_y, judge_y)
            x, w = self._air_arrow_screen_span_at_anchor(note, vanish_x, scale)
            # anchored_y is None when the anchor has no air height → keep elevated y
            if anchored_y is not None:
                y = anchored_y
            else:
                self._draw_air_ground_step_base_for_anchor(
                    painter,
                    note,
                    depth,
                    alpha,
                )

        arrow_color = get_note_color(nt)
        arrow_color.setAlpha(alpha)
        self._draw_air_arrow(painter, x, y, w, scale, arrow_color, alpha, nt)
    def _draw_air_ground_step_base_for_anchor(
        self,
        painter: QPainter,
        note: Note,
        depth: float,
        alpha: int,
    ) -> None:
        anchor_info = self._air_anchor_for_note(note)
        if anchor_info is None:
            return
        anchor, _end = anchor_info
        if anchor.note_type not in AIR_ANCHOR_FLOOR_TYPES:
            return

        cell, width = self._air_anchor_span_for_note(note)
        color = get_note_color(NoteType.AIR)
        self._draw_air_action_bar_3d(
            painter,
            cell,
            width,
            0.0,
            alpha,
            depth,
            color,
        )
    def _draw_air_start_arrow_if_needed(
        self,
        painter: QPainter,
        note: Note,
        x: float,
        y: float,
        w: float,
        scale: float,
        alpha: int,
        judge_time: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
        depth: float,
    ) -> None:
        target_type = getattr(note, "target_note", None)
        if not target_type:
            return

        arrow_type = None
        if target_type in {"AIR", "AUR", "AUL", "ADW", "ADR", "ADL"}:
            arrow_type = NoteType(target_type)
        elif target_type in {
            "TAP",
            "CHR",
            "HLD",
            "HXD",
            "SLD",
            "SXD",
            "SLC",
            "SXC",
            "AHD",
            "AHX",
            "FLK",
            "MNE",
            "DEF",
        }:
            arrow_type = NoteType.AIR

        if arrow_type is None:
            return

        # When targeting a ground note, the arrow sits on the ground note
        # at ground level, not at the air slide's elevated height.
        is_ground_target = target_type not in {
            "AIR",
            "AUR",
            "AUL",
            "ADW",
            "ADR",
            "ADL",
            "AHD",
            "AHX",
            "ASD",
            "ASC",
            "DEF",
        }
        if is_ground_target:
            _, ground_y, _ = _projection_for_depth(depth, self.width(), self.height())
            y = ground_y

        self._draw_or_defer_air_arrow(
            painter,
            note,
            x,
            y,
            w,
            scale,
            alpha,
            arrow_type,
            depth,
            vanish_x,
            vanish_y,
            judge_y,
        )
    def _draw_air_action_bar_3d(
        self,
        painter: QPainter,
        cell: float,
        width: float,
        world_y: float,
        alpha: int,
        depth: float,
        color: QColor | None = None,
    ) -> None:
        if painter is None:
            return
        corners = self._project_flat_note_corners_at_world_y(cell, width, depth, world_y)
        if not all(math.isfinite(point.x()) and math.isfinite(point.y()) for point in corners):
            return

        scale = _projection_for_depth(depth, self.width(), self.height())[0]
        body = QPolygonF(corners)
        cap_color = color if color is not None else QColor(231, 92, 255)
        fill = QColor(cap_color.red(), cap_color.green(), cap_color.blue(), alpha)
        edge = max(1, int(scale * 2))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawPolygon(body)

        highlight = QColor(
            min(255, cap_color.red() + 80),
            min(255, cap_color.green() + 80),
            min(255, cap_color.blue() + 80),
            min(255, alpha + 30),
        )
        shadow = QColor(
            max(0, cap_color.red() // 3),
            max(0, cap_color.green() // 3),
            max(0, cap_color.blue() // 3),
            max(0, alpha // 2),
        )
        painter.setPen(QPen(highlight, edge))
        painter.drawLine(corners[0], corners[1])
        painter.setPen(QPen(shadow, edge))
        painter.drawLine(corners[3], corners[2])
    def _draw_air_action_stack_3d(
        self,
        painter: QPainter,
        cell: float,
        width: float,
        bottom_world_y: float,
        top_world_y: float,
        alpha: int,
        depth: float,
    ) -> None:
        if abs(top_world_y - bottom_world_y) < 0.5:
            return
        bar_count = 8
        for index in range(1, bar_count + 1):
            progress = index / (bar_count + 1)
            world_y = _lerp(bottom_world_y, top_world_y, progress)
            stack_color = QColor(145, 35, 255, max(45, alpha // 2))
            self._draw_air_action_bar_3d(
                painter,
                cell,
                width,
                world_y,
                max(45, alpha // 2),
                depth,
                stack_color,
            )
    def _draw_air_hold_segment(
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
        is_start: bool,
    ) -> None:
        draw_depths = _sustain_draw_depths(depth, end_depth)
        if draw_depths is None:
            return
        start_world_y = _air_path_world_y(note)
        end_world_y = _air_path_world_y(note, end=True)
        source_start_cell, source_start_width = self._air_anchor_span_for_note(note)
        source_end_cell, source_end_width = self._air_anchor_span_for_note(note, end=True)
        (
            start_cell,
            start_width,
            start_world_y,
            draw_depth,
            end_cell,
            end_width,
            end_world_y,
            draw_end_depth,
        ) = _clip_air_path_segment(
            source_start_cell,
            source_start_width,
            start_world_y,
            depth,
            source_end_cell,
            source_end_width,
            end_world_y,
            end_depth,
        )
        x, y, w, scale = self._air_path_screen_span_at(
            start_cell, start_width, draw_depth, start_world_y, vanish_x, vanish_y, judge_y
        )

        self._draw_air_lift_if_needed(
            painter,
            note,
            source_start_cell,
            source_start_width,
            depth,
            _air_path_world_y(note),
            vanish_x,
            vanish_y,
            judge_y,
            color,
            alpha,
        )

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
            start_world_y=start_world_y,
            end_world_y=end_world_y,
            start_width_factor=_air_path_width_factor(start_width),
            end_width_factor=_air_path_width_factor(end_width),
        )

        if is_start and _depth_in_draw_range(depth):
            self._draw_air_start_arrow_if_needed(
                painter,
                note,
                x,
                y,
                w,
                scale,
                alpha,
                judge_time,
                vanish_x,
                vanish_y,
                judge_y,
                depth,
            )

        if _depth_in_draw_range(end_depth) and end_world_y is not None:
            self._draw_air_action_bar_3d(
                painter,
                source_end_cell,
                source_end_width,
                end_world_y,
                alpha,
                end_depth,
            )
            if note.note_type == NoteType.AHX:
                anchor_world_y = self._air_anchor_world_y(note)
                if anchor_world_y is not None:
                    self._draw_air_action_stack_3d(
                        painter,
                        source_end_cell,
                        source_end_width,
                        anchor_world_y,
                        end_world_y,
                        alpha,
                        end_depth,
                    )

    def _draw_air_slide(
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
        if isinstance(note, AirSlideStart) and note.steps:
            self._draw_air_slide_steps(
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
        else:
            end_cell = getattr(note, "end_cell", note.cell)
            end_width = getattr(note, "end_width", note.width)
            draw_depths = _sustain_draw_depths(depth, end_depth)
            if draw_depths is None:
                return
            start_world_y = self._air_wrapped_start_world_y(note)
            end_world_y = _air_path_world_y(note, end=True)
            source_start_cell, source_start_width = self._air_anchor_span_for_note(note)
            (
                start_cell,
                start_width,
                start_world_y,
                draw_depth,
                draw_end_cell,
                draw_end_width,
                draw_end_world_y,
                draw_end_depth,
            ) = _clip_air_path_segment(
                source_start_cell,
                source_start_width,
                start_world_y,
                depth,
                end_cell,
                end_width,
                end_world_y,
                end_depth,
            )
            x, y, w, scale = self._air_path_screen_span_at(
                start_cell, start_width, draw_depth, start_world_y, vanish_x, vanish_y, judge_y
            )
            self._draw_air_lift_if_needed(
                painter,
                note,
                source_start_cell,
                source_start_width,
                depth,
                _air_path_world_y(note),
                vanish_x,
                vanish_y,
                judge_y,
                color,
                alpha,
            )
            self._draw_projected_sustain_body(
                painter,
                note,
                start_cell,
                start_width,
                draw_depth,
                draw_end_cell,
                draw_end_width,
                draw_end_depth,
                color,
                alpha,
                start_world_y=start_world_y,
                end_world_y=draw_end_world_y,
                start_width_factor=_air_path_width_factor(start_width),
                end_width_factor=_air_path_width_factor(draw_end_width),
            )

            if _depth_in_draw_range(end_depth) and end_world_y is not None:
                self._draw_air_action_bar_3d(
                    painter,
                    end_cell,
                    end_width,
                    end_world_y,
                    alpha,
                    end_depth,
                )
                if start_world_y is not None:
                    self._draw_air_action_stack_3d(
                        painter,
                        end_cell,
                        end_width,
                        start_world_y,
                        end_world_y,
                        alpha,
                        end_depth,
                    )

            if _depth_in_draw_range(depth):
                if not self._air_anchor_draws_separately(note):
                    self._draw_air_wrapped_ground_head(
                        painter,
                        x,
                        y,
                        w,
                        scale,
                        alpha,
                        note,
                        depth,
                        cell=start_cell,
                        width=start_width,
                    )
                self._draw_air_start_arrow_if_needed(
                    painter,
                    note,
                    x,
                    y,
                    w,
                    scale,
                    alpha,
                    judge_time,
                    vanish_x,
                    vanish_y,
                    judge_y,
                    depth,
                )

    def _draw_air_slide_steps(
        self,
        painter: QPainter,
        note: AirSlideStart,
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

        source_start_cell, source_start_width = self._air_anchor_span_for_note(note)
        start_world_y = self._air_wrapped_start_world_y(note)
        start_x, start_y, start_w, start_scale = self._air_path_screen_span_at(
            source_start_cell,
            source_start_width,
            depth,
            start_world_y,
            vanish_x,
            vanish_y,
            judge_y,
        )

        if _depth_in_draw_range(depth):
            if not self._air_anchor_draws_separately(note):
                self._draw_air_wrapped_ground_head(
                    painter,
                    start_x,
                    start_y,
                    start_w,
                    start_scale,
                    alpha,
                    note,
                    depth,
                    cell=source_start_cell,
                    width=source_start_width,
                )
            self._draw_air_start_arrow_if_needed(
                painter,
                note,
                start_x,
                start_y,
                start_w,
                start_scale,
                alpha,
                judge_time,
                vanish_x,
                vanish_y,
                judge_y,
                depth,
            )

        prev_cell, prev_width = source_start_cell, source_start_width
        prev_world_y = start_world_y
        prev_depth = depth

        self._draw_air_lift_if_needed(
            painter,
            note,
            source_start_cell,
            source_start_width,
            depth,
            _air_path_world_y(note),
            vanish_x,
            vanish_y,
            judge_y,
            color,
            alpha,
        )

        for index, step in enumerate(note.steps):
            step_abs = step.measure + step.offset / tl.resolution
            step_end_abs = step_abs + step.duration / tl.resolution
            step_start_time = tl.time_at_measure(step_abs)
            step_start_tick = tl.to_tick(step.measure, step.offset)
            step_start_depth = self._compute_note_depth(
                note,
                step_start_tick,
                step_start_time,
                judge_time,
                cell=float(step.cell),
                width=float(step.width),
            )
            step_time = tl.time_at_measure(step_end_abs)
            step_tick = tl.to_tick(step.measure, step.offset) + step.duration
            step_depth = self._compute_note_depth(
                note,
                step_tick,
                step_time,
                judge_time,
                cell=float(step.end_cell),
                width=float(step.end_width),
            )

            if min(prev_depth, step_depth) >= DRAW_DEPTH_MAX:
                break

            if (
                index > 0
                and not self._air_anchor_draws_separately(step)
                and _depth_in_draw_range(step_start_depth)
            ):
                start_world_y = _air_path_world_y(step)
                head_x, head_y, head_w, head_scale = self._air_path_screen_span_at(
                    step.cell,
                    step.width,
                    step_start_depth,
                    start_world_y,
                    vanish_x,
                    vanish_y,
                    judge_y,
                )
                self._draw_air_wrapped_ground_head(
                    painter,
                    head_x,
                    head_y,
                    head_w,
                    head_scale,
                    alpha,
                    step,
                    step_start_depth,
                    cell=step.cell,
                    width=step.width,
                )

            draw_depths = _sustain_draw_depths(prev_depth, step_depth)
            if draw_depths is None:
                prev_cell = float(step.end_cell)
                prev_width = float(step.end_width)
                prev_world_y = _air_path_world_y(step, end=True)
                prev_depth = step_depth
                continue

            step_world_y = _air_path_world_y(step, end=True)
            (
                start_cell,
                start_width,
                start_world_y,
                draw_start_depth,
                step_cell,
                step_width,
                step_draw_world_y,
                draw_step_depth,
            ) = _clip_air_path_segment(
                prev_cell,
                prev_width,
                prev_world_y,
                prev_depth,
                float(step.end_cell),
                float(step.end_width),
                step_world_y,
                step_depth,
            )

            self._draw_projected_sustain_body(
                painter,
                step,
                start_cell,
                start_width,
                draw_start_depth,
                step_cell,
                step_width,
                draw_step_depth,
                color,
                alpha,
                start_world_y=start_world_y,
                end_world_y=step_draw_world_y,
                start_width_factor=_air_path_width_factor(start_width),
                end_width_factor=_air_path_width_factor(step_width),
            )

            prev_cell = float(step.end_cell)
            prev_width = float(step.end_width)
            prev_world_y = step_world_y
            prev_depth = step_depth

            if index == len(note.steps) - 1 and _depth_in_draw_range(step_depth):
                self._draw_air_action_bar_3d(
                    painter,
                    float(step.end_cell),
                    float(step.end_width),
                    step_world_y if step_world_y is not None else 0.0,
                    alpha,
                    step_depth,
                )
                start_world_y_for_stack = _air_path_world_y(step)
                if start_world_y_for_stack is not None and step_world_y is not None:
                    self._draw_air_action_stack_3d(
                        painter,
                        float(step.end_cell),
                        float(step.end_width),
                        start_world_y_for_stack,
                        step_world_y,
                        alpha,
                        step_depth,
                    )
    def _draw_air_wrapped_ground_head(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        scale: float,
        alpha: int,
        note: Note,
        depth: float,
        *,
        cell: float,
        width: float,
    ) -> None:
        if self._air_has_floor_anchor(note):
            return
        wrapped = self._air_wrapped_ground_type(note)
        if wrapped is None:
            return

        proxy = replace(note, note_type=wrapped)
        color = get_note_color(NoteType.CHR if wrapped in AIR_WRAPPED_EX_HEAD_TYPES else wrapped)

        if wrapped in AIR_WRAPPED_EX_HEAD_TYPES:
            self._draw_extap_quad(painter, x, y, w, scale, color, alpha, proxy, depth, cell, width)
        elif wrapped == NoteType.FLK:
            self._draw_flick(painter, x, y, w, scale, color, alpha, proxy, depth, cell, width)
        elif wrapped == NoteType.MNE:
            self._draw_mine(painter, x, y, w, scale, color, alpha)
        else:
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, proxy, depth, cell, width)
    def _air_wrapped_ground_type(self, note: Note) -> NoteType | None:
        wrapped = getattr(note, "target_note", None)
        if not isinstance(wrapped, str):
            return None
        try:
            wrapped_type = NoteType(wrapped)
        except ValueError:
            return None
        if wrapped_type in AIR_WRAPPED_GROUND_TYPES:
            return wrapped_type
        return None
    def _draw_air_trace(
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
        dur = getattr(note, "duration", 0)
        if dur <= 0:
            self._draw_tap_quad(
                painter,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                note,
                depth,
                cell=note.cell,
                width=note.width,
            )
            return

        end_cell = getattr(note, "end_cell", note.cell)
        end_width = getattr(note, "end_width", note.width)
        draw_depths = _sustain_draw_depths(depth, end_depth)
        if draw_depths is None:
            return
        start_world_y = _air_path_world_y(note)
        end_world_y = _air_path_world_y(note, end=True)
        (
            start_cell,
            start_width,
            start_world_y,
            draw_depth,
            draw_end_cell,
            draw_end_width,
            draw_end_world_y,
            draw_end_depth,
        ) = _clip_air_path_segment(
            note.cell,
            note.width,
            start_world_y,
            depth,
            end_cell,
            end_width,
            end_world_y,
            end_depth,
        )
        x, y, w, scale = self._air_trace_screen_span_at(
            start_cell, start_width, draw_depth, start_world_y, vanish_x, vanish_y, judge_y
        )
        trace_color = QColor(color.red(), color.green(), color.blue(), max(20, alpha // 2))
        trace_edge = QColor(color.red(), color.green(), color.blue(), alpha)
        self._draw_projected_sustain_body(
            painter,
            note,
            start_cell,
            start_width,
            draw_depth,
            draw_end_cell,
            draw_end_width,
            draw_end_depth,
            trace_color,
            alpha,
            start_world_y=start_world_y,
            end_world_y=draw_end_world_y,
            start_width_factor=_air_trace_width_factor_from_world_y(start_world_y),
            end_width_factor=_air_trace_width_factor_from_world_y(draw_end_world_y),
        )
        trace_corners = self._project_sustain_corners(
            note,
            start_cell,
            start_width,
            draw_depth,
            draw_end_cell,
            draw_end_width,
            draw_end_depth,
            start_world_y=start_world_y,
            end_world_y=draw_end_world_y,
            start_width_factor=_air_trace_width_factor_from_world_y(start_world_y),
            end_width_factor=_air_trace_width_factor_from_world_y(draw_end_world_y),
        )
        if not _projected_polygon_is_bounded(trace_corners, self.width(), self.height()):
            return
        painter.setPen(QPen(trace_edge, max(1, int(scale))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(
            (trace_corners[0] + trace_corners[1]) * 0.5, (trace_corners[2] + trace_corners[3]) * 0.5
        )

        crush_interval = getattr(note, "crush_interval", getattr(note, "crush_tick", 0))
        if crush_interval > 0:
            if not self.chart:
                return
            tl = self.chart.timeline
            start_tick = tl.note_tick(note)
            for offset_tick in range(0, dur + 1, crush_interval):
                current_abs_tick = start_tick + offset_tick
                progress = offset_tick / dur if dur > 0 else 0
                curr_cell = note.cell + (end_cell - note.cell) * progress
                curr_width = note.width + (end_width - note.width) * progress
                curr_time = tl.time_at(current_abs_tick)
                curr_depth = self._compute_note_depth(
                    note,
                    current_abs_tick,
                    curr_time,
                    judge_time,
                    cell=curr_cell,
                    width=curr_width,
                )

                if not _depth_in_draw_range(curr_depth):
                    continue

                start_height = float(getattr(note, "starting_height", 1.0))
                target_height = float(getattr(note, "target_height", start_height))
                curr_height = _lerp(start_height, target_height, progress)
                curr_world_y = _air_trace_world_y_from_g0(_chart_air_height_to_g0(curr_height))

                self._draw_air_action_bar_3d(
                    painter,
                    curr_cell,
                    curr_width,
                    curr_world_y,
                    alpha,
                    curr_depth,
                )
