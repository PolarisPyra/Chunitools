from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QLinearGradient, QPainter, QPainterPath, QPen

from src.ui.components.timeline_view.notes.support import RendererMixinSupport


class DamageRendererMixin(RendererMixinSupport):
    def _draw_damage(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        y, x, w = (
            self.projection.y(timeline.note_abs_pos(note), current_position),
            self.projection.x(note.cell),
            self.projection.w(note.width),
        )
        rect = QRectF(x, y - self.constants.HEAD_HEIGHT / 2, w, self.constants.HEAD_HEIGHT)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, self.colors.damage.light)
        gradient.setColorAt(1, self.colors.damage.dark)
        path = QPainterPath()
        path.moveTo(rect.center().x(), rect.top())
        path.lineTo(rect.right(), rect.center().y())
        path.lineTo(rect.center().x(), rect.bottom())
        path.lineTo(rect.left(), rect.center().y())
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)
        painter.setPen(
            QPen(
                self.colors.border.light,
                rect.height() * self.constants.BORDER_WIDTH_RATIO,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setPen(
            QPen(Qt.GlobalColor.white, rect.height() * self.constants.BORDER_WIDTH_RATIO)
        )
        inset = rect.height() * 0.32
        painter.drawLine(
            rect.topLeft() + QPointF(inset, inset),
            rect.bottomRight() - QPointF(inset, inset),
        )
        painter.drawLine(
            rect.topRight() + QPointF(-inset, inset),
            rect.bottomLeft() + QPointF(inset, -inset),
        )
