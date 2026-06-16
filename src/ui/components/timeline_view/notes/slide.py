from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from src.core.const import NoteType, RenderRole
from src.notes.slide import Slide, SlideTo
from src.ui.components.timeline_view.notes.support import RendererMixinSupport, SlidePathPoint

NOTE_DEBUG = logging.getLogger("note_rendering_debug")

NOTE_ROLE_START = "ST"
NOTE_ROLE_LINE_CONTROL = "LC"
NOTE_ROLE_END = "EN"


class SlideRendererMixin(RendererMixinSupport):
    def _draw_slide_background(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not isinstance(note, Slide):
            return

        # Build all path points — ribbon must go through ALL points
        # (including invisible SLC control points) to follow the curve.
        # The is_visible flag only affects the foreground (tap vs control point).
        points = self._slide_path_points_with_visibility(note, current_position, timeline)
        if len(points) < 2:
            return

        color = self.colors.slide_line

        # Draw ribbon through ALL points
        for a, b in zip(points, points[1:], strict=False):
            self._draw_slide_segment_ribbon(painter, a, b, color)

        # Core path through all points
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
        if not isinstance(note, Slide):
            return

        # Head tap — always drawn at the wrapper's start position
        if self._should_draw_slide_head(note, timeline):
            head_color = self._slide_start_color(note)
            NOTE_DEBUG.debug("  slide_head: %s m=%d:%d c=%d w=%d color=%s",
                             note.note_type.value, note.measure, note.offset,
                             note.cell, note.width, "ex_tap" if head_color == self.colors.ex_tap else "slide")
            self._draw_tap(
                painter, note, current_position, timeline,
                head_color,
            )

        # The final endpoint gets a tap head. Intermediate visible steps are
        # path starts, while invisible SLC/SXC steps are line controls.
        current_tick = timeline.note_tick(note)
        step_count = len(note.steps)
        for index, step in enumerate(note.steps):
            current_tick += step.duration
            if self._slide_step_role(index, step_count, step) == NOTE_ROLE_END:
                self._draw_step_tap(painter, step, current_tick, current_position, timeline)

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
            else (NoteType.SXD if note.note_type == NoteType.SXC else note.note_type)
        )
        if not self.visible_note_types.get(master.value, True):
            return
        color = self._slide_start_color(note)
        self._draw_tap(painter, note, current_position, timeline, color)
        if not timeline.note_has_successor(note):
            y_end, (x_pos, width) = (
                self.projection.y(
                    timeline.note_end_tick(note) / timeline.resolution,
                    current_position,
                ),
                (
                    self.projection.x(note.end_cell),
                    self.projection.w(note.end_width),
                ),
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
        y, x, w = (
            self.projection.y(absolute_tick / timeline.resolution, current_position),
            self.projection.x(step.end_cell),
            self.projection.w(step.end_width),
        )
        rect = QRectF(x, y - self.constants.HEAD_HEIGHT / 2, w, self.constants.HEAD_HEIGHT)

        visible = getattr(step, "is_visible", True)
        color_name = "ctrl_pt" if not visible else ("ex_tap" if step.note_type in (NoteType.SXD, NoteType.SXC) else "slide")
        NOTE_DEBUG.debug("  step_draw: %s m=%d:%d c=%d→%d visible=%s color=%s",
                         step.note_type.value, step.measure, step.offset,
                         step.cell, step.end_cell, visible, color_name)

        if not getattr(step, "is_visible", True):
            # Invisible steps (SLC/SXC) draw as grey control points
            border_color = QColor("#808080")
            border_color.setAlpha(127)  # 50% alpha — matches Rust version
            pixmap_key = ("control_point_v2", "#808080", round(w, 2))
            pixmap = self.cache.get_pixmap(
                pixmap_key,
                lambda p, r: (
                    p.setPen(self.cache.get_pen(border_color, 1)),
                    p.setBrush(
                        self.cache.get_brush(QColor("#808080"), self.constants.CONTROL_POINT_ALPHA)
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

        def draw_cached_step(p: QPainter, r: QRectF) -> None:
            self._draw_rounded_rect(p, r, color)
            self._draw_tap_symbol(p, r)

        pixmap = self.cache.get_pixmap(
            pixmap_key,
            draw_cached_step,
            w,
            self.constants.HEAD_HEIGHT,
        )
        painter.drawPixmap(rect.topLeft().toPoint(), pixmap)

    def _slide_start_color(self, note: Any) -> Any:
        return self.colors.ex_tap if note.note_type in (NoteType.SXD, NoteType.SXC) else self.colors.slide

    def _slide_step_role(self, index: int, step_count: int, step: Any) -> str:
        if index == step_count - 1:
            return NOTE_ROLE_END
        if getattr(step, "is_visible", True):
            return NOTE_ROLE_START
        return NOTE_ROLE_LINE_CONTROL

    def _slide_endpoint_color(self, note: Any) -> Any:
        # Steps within a slide chain always use normal slide blue/cyan.
        # The chain head color (ex_tap vs slide) is handled by _slide_start_color.
        return self.colors.slide

    def _slide_head_color(self, note: Any) -> Any:
        return self._slide_start_color(note)

    def _should_draw_slide_head(self, note: Any, timeline: Any) -> bool:
        # Draw a visible head only when this slide is the chain root (HEAD role)
        # or when it follows a non-slide predecessor (new independent slide start).
        # SLC/SXC control points never draw their own head.
        if timeline.note_render_role(note) == RenderRole.HEAD:
            return True
        if note.note_type in (NoteType.SLC, NoteType.SXC):
            return False
        predecessor = timeline.note_chain_predecessor(note)
        return predecessor is not None and predecessor.note_type not in (
            NoteType.SLD,
            NoteType.SXD,
            NoteType.SLC,
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

    def _slide_path_points_with_visibility(
        self,
        note: Slide,
        current_position: float,
        timeline: Any,
    ) -> list[SlidePathPoint]:
        """Build path points with visibility flags matching Rust's is_visible."""
        res = timeline.resolution
        current_tick = timeline.note_tick(note)
        # The head is always visible (it's the entry point)
        points = [
            self._slide_path_point(
                note.cell,
                note.width,
                self.projection.y(current_tick / res, current_position),
                visible=True,
            )
        ]
        for step in note.steps:
            current_tick += step.duration
            points.append(
                self._slide_path_point(
                    step.end_cell,
                    step.end_width,
                    self.projection.y(current_tick / res, current_position),
                    visible=getattr(step, "is_visible", True),
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

    def _slide_path_point(self, cell: int, width: int, y: float, *, visible: bool = True) -> SlidePathPoint:
        x = self.projection.x(float(cell))
        w = self.projection.w(float(width))
        return SlidePathPoint(
            center=QPointF(x + w / 2, y),
            left=QPointF(x, y),
            right=QPointF(x + w, y),
            visible=visible,
        )
