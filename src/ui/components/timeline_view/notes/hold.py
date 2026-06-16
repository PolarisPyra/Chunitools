from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QLinearGradient, QPainter

from src.core.const import NoteType
from src.ui.components.timeline_view.notes.support import RendererMixinSupport


class HoldRendererMixin(RendererMixinSupport):
    def _draw_hold_foreground(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        start_color = self.colors.hold if note.note_type == NoteType.HLD else self.colors.ex_tap
        self._draw_tap(painter, note, current_position, timeline, start_color)
        y_end, (x_pos, width) = (
            self.projection.y(timeline.note_abs_end_pos(note), current_position),
            (self.projection.x(note.cell), self.projection.w(note.width)),
        )
        rect = QRectF(
            x_pos, y_end - self.constants.HEAD_HEIGHT / 2, width, self.constants.HEAD_HEIGHT
        )
        if self._has_explicit_air_endpoint_parent(note, timeline.note_end_tick(note), timeline):
            return
        self._draw_rounded_rect(painter, rect, self.colors.hold)
        self._draw_tap_symbol(painter, rect)

    def _draw_hold_background(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        master_type = NoteType.HLD if note.note_type == NoteType.HXD else note.note_type
        if not self.visible_note_types.get(master_type.value, True):
            return
        ys = self.projection.y(timeline.note_abs_pos(note), current_position)
        ye = self.projection.y(timeline.note_abs_end_pos(note), current_position)
        x = self.projection.x(note.cell)
        w = self.projection.w(note.width)
        rect = QRectF(x, min(ys, ye), w, abs(ys - ye))
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        bg = self.colors.hold_background
        gradient.setColorAt(0, bg.dark)
        gradient.setColorAt(0.3, bg.light)
        gradient.setColorAt(0.7, bg.light)
        gradient.setColorAt(1, bg.dark)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRect(rect)
