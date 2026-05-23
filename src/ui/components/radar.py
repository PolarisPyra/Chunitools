"""Radar chart widget for per-note-type density stats."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from src.core.const import NoteType

if TYPE_CHECKING:
    from src.core.models import Chart
    from src.notes import Note
from src.ui import theme

_MAX_VALUE_FALLBACK = 1.0


@dataclass(frozen=True)
class RadarAxis:
    label: str
    note_types: tuple[str, ...]
    color: QColor


_AXES: tuple[RadarAxis, ...] = (
    RadarAxis("TAP", (NoteType.TAP,), theme.qt(theme.NOTE_TAP)),
    RadarAxis("EX TAP", (NoteType.CHR,), theme.qt(theme.NOTE_CHR)),
    RadarAxis("HOLD", (NoteType.HLD, NoteType.HXD), theme.qt(theme.NOTE_HOLD)),
    RadarAxis(
        "SLIDE",
        (NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC, NoteType.ASC, NoteType.ASD),
        theme.qt(theme.NOTE_SLIDE),
    ),
    RadarAxis(
        "AIR",
        (
            NoteType.AIR,
            NoteType.AUR,
            NoteType.AUL,
            NoteType.AHD,
            NoteType.ADW,
            NoteType.ADR,
            NoteType.ADL,
            NoteType.ALD,
        ),
        theme.qt(theme.NOTE_AIR_TRACE),
    ),
    RadarAxis("FLICK", (NoteType.FLK,), theme.qt(theme.NOTE_FLICK)),
)


class NoteDensityRadar(QWidget):
    """Game-style radar chart for note composition."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chart: Chart | None = None
        self.values: list[float] = [0.0] * len(_AXES)
        self._cached_rings: list[list[QPointF]] | None = None
        self._cached_radius: float = 0.0
        self._cached_center: QPointF = QPointF(0, 0)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(f"background: {theme.TRANSPARENT}; border: none;")

    def update_chart(self, chart: Chart | None) -> None:
        self.chart = chart
        self.values = self._calculate_values(chart)
        self.update()

    def _calculate_values(self, chart: Chart | None) -> list[float]:
        if not chart or not chart.notes:
            return [0.0] * len(_AXES)

        counts = [self._count_axis_notes(chart.notes, axis) for axis in _AXES]
        max_count = max(*counts, _MAX_VALUE_FALLBACK)
        return [count / max_count for count in counts]

    @staticmethod
    def _count_axis_notes(notes: list[Note], axis: RadarAxis) -> int:
        note_types = set(axis.note_types)
        return sum(1 for note in notes if note.note_type in note_types)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bounds = self.rect().adjusted(10, 10, -10, -10)
        center = QPointF(bounds.center())
        radius = min(bounds.width(), bounds.height()) * 0.25
        if radius <= 0:
            return

        # Optimization: Use drawRoundedRect directly
        painter.setPen(QPen(theme.qt(theme.OVERLAY_PANEL_BORDER), 1.2))
        painter.setBrush(theme.qt(theme.OVERLAY_PANEL_FILL))
        painter.drawRoundedRect(bounds, 6, 6)

        if (
            radius != self._cached_radius
            or center != self._cached_center
            or self._cached_rings is None
        ):
            self._cached_rings = self._ring_points(center, radius)
            self._cached_radius = radius
            self._cached_center = center

        points_by_ring = self._cached_rings
        self._draw_grid(painter, center, points_by_ring)
        self._draw_data_polygon(painter, center, radius)
        self._draw_labels(painter, center, radius)

    def _ring_points(self, center: QPointF, radius: float) -> list[list[QPointF]]:
        rings: list[list[QPointF]] = []
        sides = len(_AXES)
        for step in range(1, 5):
            ring_radius = radius * (step / 4)
            ring: list[QPointF] = []
            for i in range(sides):
                angle = -math.pi / 2 + (2 * math.pi * i / sides)
                ring.append(
                    QPointF(
                        center.x() + math.cos(angle) * ring_radius,
                        center.y() + math.sin(angle) * ring_radius,
                    )
                )
            rings.append(ring)
        return rings

    def _draw_grid(
        self, painter: QPainter, center: QPointF, points_by_ring: list[list[QPointF]]
    ) -> None:
        painter.setPen(QPen(theme.qt(theme.RADAR_GRID_OUTLINE), 2))
        painter.setBrush(theme.qt(theme.RADAR_GRID_FILL))
        painter.drawPolygon(QPolygonF(points_by_ring[-1]))

        painter.setPen(QPen(theme.qt(theme.RADAR_GRID_LINE), 1))
        for ring in points_by_ring[:-1]:
            painter.drawPolygon(QPolygonF(ring))

        for i, outer in enumerate(points_by_ring[-1]):
            painter.setPen(QPen(theme.qt(theme.RADAR_GRID_SPOKE), 1.2))
            painter.drawLine(center, outer)

            for tick in range(1, 4):
                tick_point = points_by_ring[tick - 1][i]
                dx = tick_point.x() - center.x()
                dy = tick_point.y() - center.y()
                length = math.hypot(dx, dy) or 1.0
                nx = -dy / length
                ny = dx / length
                tick_size = 4
                painter.drawLine(
                    QPointF(tick_point.x() - nx * tick_size, tick_point.y() - ny * tick_size),
                    QPointF(tick_point.x() + nx * tick_size, tick_point.y() + ny * tick_size),
                )

    def _draw_data_polygon(self, painter: QPainter, center: QPointF, radius: float) -> None:
        sides = len(_AXES)
        points: list[QPointF] = []
        for i, value in enumerate(self.values):
            angle = -math.pi / 2 + (2 * math.pi * i / sides)
            dist = radius * max(0.0, value)
            points.append(
                QPointF(center.x() + math.cos(angle) * dist, center.y() + math.sin(angle) * dist)
            )

        polygon = QPolygonF(points)
        painter.setPen(QPen(theme.qt(theme.RADAR_DATA_STROKE), 1.5))
        painter.setBrush(theme.qt(theme.RADAR_DATA_FILL))
        painter.drawPolygon(polygon)

    def _draw_labels(self, painter: QPainter, center: QPointF, radius: float) -> None:
        font = QFont(theme.FONT_UI, 8, QFont.Weight.DemiBold)
        painter.setFont(font)
        sides = len(_AXES)

        for i, axis in enumerate(_AXES):
            angle = -math.pi / 2 + (2 * math.pi * i / sides)
            label_dist = radius + 16
            point = QPointF(
                center.x() + math.cos(angle) * label_dist,
                center.y() + math.sin(angle) * label_dist,
            )
            rect = QRectF(point.x() - 36, point.y() - 12, 72, 24)
            painter.setPen(QPen(theme.qt(theme.RADAR_LABEL_SHADOW), 4))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, axis.label)
            painter.setPen(QPen(axis.color, 1.5))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, axis.label)
