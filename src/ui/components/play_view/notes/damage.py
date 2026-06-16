from __future__ import annotations

# ruff: noqa: PLR0912, PLR0913, PLR0915
import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF

from src.ui.components.play_view.geometry import (
    _depth_in_draw_range,
    _projection_for_depth,
)

if TYPE_CHECKING:
    from src.notes import Note

class PlayViewDamageNotesMixin:
    def _draw_flat_note_quad(
        self,
        painter: QPainter,
        cell: float,
        width: float,
        depth: float,
        color: QColor,
        alpha: int,
        note: Note,
        is_extap: bool = False,
    ) -> list[QPointF]:
        corners = self._project_flat_note_corners(note, cell, width, depth)
        if not all(math.isfinite(pt.x()) and math.isfinite(pt.y()) for pt in corners):
            return corners
        poly = QPolygonF(corners)
        scale = _projection_for_depth(depth, self.width(), self.height())[0]

        if is_extap:
            gold = QColor(255, 215, 0, alpha)
            painter.setPen(QPen(QColor(255, 240, 150, alpha), max(1, int(scale * 2))))
            painter.setBrush(gold)
            painter.drawPolygon(poly)

            left_mid = (corners[0] + corners[3]) * 0.5
            right_mid = (corners[1] + corners[2]) * 0.5
            painter.setPen(QPen(QColor(255, 255, 200, alpha // 2), 1))
            painter.drawLine(left_mid, right_mid)
        else:
            paint_alpha = QColor(color.red(), color.green(), color.blue(), alpha)
            painter.setPen(QPen(color.darker(130), max(1, int(scale * 2))))
            painter.setBrush(paint_alpha)
            painter.drawPolygon(poly)

            glow = QColor(color.red(), color.green(), color.blue(), alpha // 4)
            painter.setPen(QPen(glow, max(2, int(scale * 3))))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(poly)

        return corners
    def _draw_tap_quad(
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
        c_val = cell if cell is not None else float(note.cell)
        w_val = width if width is not None else float(note.width)
        self._draw_flat_note_quad(painter, c_val, w_val, depth, color, alpha, note, is_extap=False)
    def _draw_extap_quad(
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
        c_val = cell if cell is not None else float(note.cell)
        w_val = width if width is not None else float(note.width)
        self._draw_flat_note_quad(painter, c_val, w_val, depth, color, alpha, note, is_extap=True)
    def _draw_mine(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        scale: float,
        color: QColor,
        alpha: int,
    ) -> None:
        r = max(2, int(w * 0.35))
        cx, cy = int(x + w / 2), int(y)
        painter.setPen(QPen(QColor(200, 60, 60, alpha), max(1, int(scale * 2))))
        painter.setBrush(QColor(100, 20, 20, alpha))
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        painter.setPen(QPen(QColor(255, 100, 100, alpha), max(1, int(scale * 1.5))))
        painter.drawLine(cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2)
        painter.drawLine(cx + r // 2, cy - r // 2, cx - r // 2, cy + r // 2)

