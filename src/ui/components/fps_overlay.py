"""Small FPS overlay widget for the chart viewport."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from src.ui import theme


class FpsOverlay(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples: deque[float] = deque(maxlen=30)
        self._fps: float = 0.0
        self._max_fps: float = 120.0
        self._active = False
        self._skip_next_sample = False
        self.setFixedSize(110, 56)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(f"background: {theme.TRANSPARENT}; border: none;")
        self.hide()

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._skip_next_sample = active
        self.reset()

    def record_frame(self, dt_seconds: float) -> None:
        if not self._active or dt_seconds <= 0:
            return
        if self._skip_next_sample:
            self._skip_next_sample = False
            return
        self._samples.append(dt_seconds)
        avg = sum(self._samples) / len(self._samples)
        self._fps = 0.0 if avg <= 0 else min(self._max_fps, 1.0 / avg)
        self.update()

    def reset(self) -> None:
        self._samples.clear()
        self._fps = 0.0
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bounds = self.rect().adjusted(4, 4, -4, -4)
        panel = QPainterPath()
        panel.addRoundedRect(QRectF(bounds), 6, 6)
        painter.fillPath(panel, theme.qt(theme.OVERLAY_PANEL_FILL))
        painter.setPen(QPen(theme.qt(theme.OVERLAY_PANEL_BORDER), 1.2))
        painter.drawPath(panel)

        painter.setFont(QFont(theme.FONT_UI, 8, QFont.Weight.DemiBold))
        painter.setPen(theme.qt(theme.ACCENT))
        painter.drawText(bounds.adjusted(0, 6, 0, 0), Qt.AlignmentFlag.AlignHCenter, "FPS")

        painter.setFont(QFont(theme.FONT_MONO, 18, QFont.Weight.Normal))
        painter.setPen(theme.qt(theme.TEXT_EDITOR))
        painter.drawText(
            bounds.adjusted(0, 12, 0, -2), Qt.AlignmentFlag.AlignCenter, f"{self._fps:.0f}"
        )
