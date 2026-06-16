"""Debug overlay for 3D play view that displays note type labels above notes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from src.ui.components.util.play_view_geometry import (
    DRAW_DEPTH_MAX,
    DRAW_DEPTH_MIN,
    _note_screen_span,
)
from src.ui.theme import notes as note_theme

if TYPE_CHECKING:
    from src.ui.components.play_view import PlayView3D


class NoteDebugOverlay3D(QWidget):
    """Overlay widget that renders note type labels above each note in 3D view."""

    def __init__(self, parent: PlayView3D | None = None) -> None:
        super().__init__(parent)
        self._play_view = parent
        self._active = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        self.hide()

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self.setVisible(active)
        self.update()

    def is_active(self) -> bool:
        return self._active

    def set_play_view(self, play_view: PlayView3D) -> None:
        self._play_view = play_view

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        _ = event
        if not self._active or not self._play_view or not self._play_view.chart:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        pv = self._play_view
        chart = pv.chart
        assert chart is not None
        timeline = chart.timeline
        judge_time = timeline.time_at_measure(pv.current_pos) + pv.judge_offset

        font = QFont("Consolas, Courier New, monospace", 9, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        for note in pv._notes:
            if not pv.visible_note_types.get(note.note_type.value, True):
                continue

            note_time = pv._note_times.get(id(note), 0.0)
            depth = pv._compute_note_depth(note, timeline.note_tick(note), note_time, judge_time)

            if not _depth_in_draw_range_3d(depth):
                continue

            scale, screen_y, _ = pv._world_z_to_screen(
                depth, pv.height() * 0.10, pv.height() * 0.90
            )

            vanish_x = pv.width() / 2.0
            lane_x, note_w = _note_screen_span(note.cell, note.width, vanish_x, scale)

            if note_w < 4:
                continue

            label = note.note_type.value
            color = note_theme.get_note_color(note.note_type)

            if getattr(note, "duration", 0) > 0:
                label = f"{label}"

            text_width = metrics.horizontalAdvance(label)
            text_height = metrics.height()

            label_x = lane_x + (note_w - text_width) / 2
            label_y = screen_y - 22 * scale

            alpha = 200
            bg_color = color.lighter(150)
            bg_color.setAlpha(50)
            border_color = color
            border_color.setAlpha(alpha)

            padding = 3
            rect = QRectF(
                label_x - padding,
                label_y - text_height + padding,
                text_width + padding * 2,
                text_height + padding * 2,
            )

            path = QPainterPath()
            path.addRoundedRect(rect, 3, 3)
            painter.fillPath(path, bg_color)
            painter.setPen(QPen(border_color, 1))
            painter.drawPath(path)

            painter.setPen(color)
            painter.drawText(
                rect.toRect(),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        painter.end()


def _depth_in_draw_range_3d(depth: float) -> bool:
    return DRAW_DEPTH_MIN < depth < DRAW_DEPTH_MAX
