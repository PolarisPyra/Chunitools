from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from src.core.const import NoteType, RenderRole
from src.notes.slide import Slide, SlideTo

if TYPE_CHECKING:
    from src.ui.view.renderer.base import SlidePathPoint

NOTE_ROLE_START = "ST"
NOTE_ROLE_LINE_CONTROL = "LC"
NOTE_ROLE_END = "EN"


class SlideRendererMixin:
    def _draw_slide_background(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not isinstance(note, Slide):
            return

        master_type = (
            NoteType.SLD
            if note.note_type == NoteType.SLC
            else (NoteType.SXD if note.note_type == NoteType.SXC else note.note_type)
        )
        if not self.visible_note_types.get(master_type.value, True):
            return

        points = self._slide_path_points(note, current_position, timeline)
        if len(points) < 2:
            return

        color = self.colors.slide_line

        for a, b in zip(points, points[1:]):
            self._draw_slide_segment_ribbon(painter, a, b, color)

        centers = [point.center for point in points]
        core_path = self._build_polyline_path(centers)

        core_color = QColor(color)
        core_color.setAlpha(210)
        painter.setPen(
            QPen(
                core_color,
                3.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(core_path)

    def _draw_slide_segment_ribbon(
        self,
        painter: QPainter,
        a: SlidePathPoint,
        b: SlidePathPoint,
        color: QColor,
    ) -> None:
        quad = QPolygonF([a.left, b.left, b.right, a.right])

        body = QColor(color)
        body.setAlpha(95)

        edge = QColor(color)
        edge.setAlpha(170)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(body))
        painter.drawPolygon(quad)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                edge,
                2.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawLine(a.left, b.left)
        painter.drawLine(a.right, b.right)

    def _draw_slide_foreground(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if self._should_draw_slide_head(note, timeline):
            master_type = (
                NoteType.SLD
                if note.note_type == NoteType.SLC
                else (
                    NoteType.SXD
                    if note.note_type == NoteType.SXC
                    else note.note_type
                )
            )
            if self.visible_note_types.get(master_type.value, True):
                self._draw_tap(
                    painter,
                    note,
                    current_position,
                    timeline,
                    self._slide_start_color(note),
                )
        current_tick = timeline.note_tick(note)
        step_count = len(note.steps)
        for index, step in enumerate(note.steps):
            current_tick += step.duration
            if (
                self.visible_note_types.get(step.note_type.value, True)
                and self._slide_step_role(index, step_count, step) == NOTE_ROLE_START
            ):
                self._draw_step_tap(
                    painter, step, current_tick, current_position, timeline
                )
        if not timeline.note_has_successor(note):
            last_step = note.steps[-1] if note.steps else note
            end_tick = timeline.note_end_tick(note)
            end_cell = getattr(last_step, "end_cell", note.cell)
            end_width = getattr(last_step, "end_width", note.width)
            # Don't draw slide tail if an air arrow replaces it
            if hasattr(self, "_has_air_reference_at") and self._has_air_reference_at(
                end_tick, end_cell, end_width, "SLD", timeline
            ):
                return
            master_type = (
                NoteType.SLD
                if note.note_type == NoteType.SLC
                else (
                    NoteType.SXD
                    if note.note_type == NoteType.SXC
                    else note.note_type
                )
            )
            if self.visible_note_types.get(master_type.value, True):
                y_end, (x_pos, width) = self.projection.y(
                    end_tick / timeline.resolution,
                    current_position,
                ), (
                    self.projection.x(end_cell),
                    self.projection.w(end_width),
                )
                rect = QRectF(
                    x_pos,
                    y_end - self.constants.HEAD_HEIGHT / 2,
                    width,
                    self.constants.HEAD_HEIGHT,
                )
                self._draw_rounded_rect(
                    painter, rect, self._slide_endpoint_color(last_step)
                )

    def _draw_slide_foreground_orphan(
        self,
        painter: QPainter,
        note: SlideTo,
        current_position: float,
        timeline: Any,
    ) -> None:
        master = (
            NoteType.SLD
            if note.note_type == NoteType.SLC
            else (
                NoteType.SXD
                if note.note_type == NoteType.SXC
                else note.note_type
            )
        )
        if not self.visible_note_types.get(master.value, True):
            return
        color = self._slide_start_color(note)
        self._draw_tap(painter, note, current_position, timeline, color)
        if not timeline.note_has_successor(note):
            y_end, (x_pos, width) = self.projection.y(
                timeline.note_end_tick(note) / timeline.resolution,
                current_position,
            ), (
                self.projection.x(note.end_cell),
                self.projection.w(note.end_width),
            )
            rect = QRectF(
                x_pos,
                y_end - self.constants.HEAD_HEIGHT / 2,
                width,
                self.constants.HEAD_HEIGHT,
            )
            self._draw_rounded_rect(painter, rect, self._slide_endpoint_color(note))

    def _draw_step_tap(
        self,
        painter: QPainter,
        step: Any,
        absolute_tick: int,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(step.note_type.value, True):
            return
        y, x, w = self.projection.y(
            absolute_tick / timeline.resolution, current_position
        ), self.projection.x(step.end_cell), self.projection.w(step.end_width)
        rect = QRectF(
            x, y - self.constants.HEAD_HEIGHT / 2, w, self.constants.HEAD_HEIGHT
        )

        if timeline.note_render_role(step) == RenderRole.CONTROL:
            pixmap_key = ("control_point", "#808080", w)
            pixmap = self.cache.get_pixmap(
                pixmap_key,
                lambda p, r: (
                    p.setPen(self.cache.get_pen(QColor("#808080"), 1)),
                    p.setBrush(
                        self.cache.get_brush(
                            QColor("#808080"), self.constants.CONTROL_POINT_ALPHA
                        )
                    ),
                    p.drawRoundedRect(
                        r,
                        r.height() * self.constants.CORNER_RADIUS_RATIO,
                        r.height() * self.constants.CORNER_RADIUS_RATIO,
                    ),
                ),
                w,
                self.constants.HEAD_HEIGHT,
            )
            painter.drawPixmap(rect.topLeft().toPoint(), pixmap)
            return

        color = self._slide_endpoint_color(step)
        pixmap_key = self._tap_pixmap_key(color, w, "tap")
        pixmap = self.cache.get_pixmap(
            pixmap_key,
            lambda p, r: (
                self._draw_rounded_rect(p, r, color),
                self._draw_tap_symbol(p, r),
            ),
            w,
            self.constants.HEAD_HEIGHT,
        )
        painter.drawPixmap(rect.topLeft().toPoint(), pixmap)

    def _slide_step_role(
        self, index: int, step_count: int, step: Any
    ) -> str:
        if index == step_count - 1:
            return NOTE_ROLE_END
        if step.note_type == NoteType.SLD:
            return NOTE_ROLE_START
        return NOTE_ROLE_LINE_CONTROL

    def _slide_start_color(self, note: Any) -> Any:
        return (
            self.colors.ex_tap
            if note.note_type in (NoteType.SXD, NoteType.SXC)
            else self.colors.slide
        )

    def _slide_endpoint_color(self, note: Any) -> Any:
        return self.colors.slide

    def _slide_head_color(self, note: Any) -> Any:
        return self._slide_start_color(note)

    def _should_draw_slide_head(self, note: Any, timeline: Any) -> bool:
        if timeline.note_render_role(note) == RenderRole.HEAD:
            return True
        if note.note_type not in (NoteType.SXD, NoteType.SXC):
            return False
        predecessor = timeline.note_chain_predecessor(note)
        return predecessor is not None and predecessor.note_type not in (
            NoteType.SXD,
            NoteType.SXC,
        )

    def _slide_path_points(
        self,
        note: Slide,
        current_position: float,
        timeline: Any,
    ) -> list[SlidePathPoint]:
        res = timeline.resolution
        current_tick = timeline.note_tick(note)
        points = [
            self._slide_path_point(
                note.cell,
                note.width,
                self.projection.y(current_tick / res, current_position),
            )
        ]
        for step in note.steps:
            current_tick += step.duration
            points.append(
                self._slide_path_point(
                    step.end_cell,
                    step.end_width,
                    self.projection.y(current_tick / res, current_position),
                )
            )
        return points

    def _slide_path_points_orphan(
        self,
        note: SlideTo,
        current_position: float,
        timeline: Any,
    ) -> list[SlidePathPoint]:
        res = timeline.resolution
        start_tick = timeline.note_tick(note)
        end_tick = start_tick + note.duration
        return [
            self._slide_path_point(
                note.cell,
                note.width,
                self.projection.y(start_tick / res, current_position),
            ),
            self._slide_path_point(
                note.end_cell,
                note.end_width,
                self.projection.y(end_tick / res, current_position),
            ),
        ]

    def _slide_path_point(
        self, cell: int, width: int, y: float
    ) -> SlidePathPoint:
        from src.ui.view.renderer.base import SlidePathPoint

        x = self.projection.x(float(cell))
        w = self.projection.w(float(width))
        return SlidePathPoint(
            center=QPointF(x + w / 2, y),
            left=QPointF(x, y),
            right=QPointF(x + w, y),
        )
