from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen

from src.core.const import NoteType, RenderRole
from src.notes.slide import Slide, SlideTo
from src.ui.view.renderer.notes.support import RendererMixinSupport, SlidePathPoint

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

        # Build all path points — body must go through ALL points
        # (including invisible SLC control points) to follow the curve.
        points = self._slide_path_points_with_visibility(note, current_position, timeline)
        if len(points) < 2:
            return

        color = self.colors.slide_line

        # Build bezier body path matching game's SpkInterpolationBezierAD3
        body_path = self._build_slide_body_path(points)

        # Fill the slide body with semi-transparent gradient
        body_color = QColor(color)
        body_color.setAlpha(95)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(body_color))
        painter.drawPath(body_path)

        # Draw left/right outline edges as bezier curves
        if len(points) >= 2:
            left_points = [point.left for point in points]
            right_points = [point.right for point in points]
            left_path = self._build_bezier_path(left_points)
            right_path = self._build_bezier_path(right_points)

            edge_color = QColor(color)
            edge_color.setAlpha(170)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(
                    edge_color,
                    2.0,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(left_path)
            painter.drawPath(right_path)

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

        # Draw each step. Visible steps (SLD/SXD) get a colored tap;
        # invisible steps (SLC/SXC) get a grey control point.
        # Matches Rust: draw_slide → for step { if is_visible { draw_tap } else { draw_control_point } }
        current_tick = timeline.note_tick(note)
        for step in note.steps:
            current_tick += step.duration
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

    def _slide_endpoint_color(self, note: Any) -> Any:
        nt = getattr(note, "note_type", None)
        return self.colors.ex_tap if nt in (NoteType.SXD, NoteType.SXC) else self.colors.slide

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
