from __future__ import annotations

# ruff: noqa: PLR0912, PLR0913, PLR0915
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF

from src.ui.components.play_view.geometry import _depth_in_draw_range

if TYPE_CHECKING:
    from src.notes import Note

class PlayViewFlickNotesMixin:
    def _draw_flick(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        scale: float,
        color: QColor,
        alpha: int,
        note: Note,
        depth: float,
        cell: float | None = None,
        width: float | None = None,
    ) -> None:
        if not _depth_in_draw_range(depth):
            return
        if getattr(self, "_defer_note_overlays", False):
            self._deferred_flick_overlays.append(
                (note, x, y, w, scale, color, alpha, depth, cell, width)
            )
            return
        c_val = cell if cell is not None else float(note.cell)
        w_val = width if width is not None else float(note.width)
        corners = self._project_flat_note_corners(note, c_val, w_val, depth)
        poly = QPolygonF(corners)

        painter.setPen(QPen(color.lighter(130), max(1, int(scale * 2))))
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), alpha))
        painter.drawPolygon(poly)

        left_mid = (corners[0] + corners[3]) * 0.5
        right_mid = (corners[1] + corners[2]) * 0.5
        center = (left_mid + right_mid) * 0.5

        painter.setPen(QPen(QColor(255, 255, 255, alpha), max(1, int(scale * 1.5))))
        dx = 3 * scale
        dy = 4 * scale
        painter.drawLine(
            QPointF(center.x() - dx, center.y() - dy),
            QPointF(center.x() + dx, center.y()),
        )
        painter.drawLine(
            QPointF(center.x() - dx, center.y() + dy),
            QPointF(center.x() + dx, center.y()),
        )
