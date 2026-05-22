"""Timeline ruler widget for chart navigation context."""

from __future__ import annotations

import logging
from math import ceil, floor

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from src.core.models import Chart
from src.engine.timeline import ChartTimeline
from src.ui import theme

LOGGER = logging.getLogger("ui.timelineview")


class TimelineWidget(QWidget):
    seek_requested = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self._chart: Chart | None = None
        self._timeline: ChartTimeline | None = None
        self._playhead_measure: float = 0.0
        self._subdivisions: int = 4
        self._total_measures: float | None = None

    def set_chart(self, chart: Chart | None) -> None:
        self._chart = chart
        if chart:
            self._timeline = chart.timeline
            LOGGER.debug(
                "Timeline chart set: %s measures",
                self._timeline.calculate_max_measure(),
            )
        else:
            self._timeline = None
            LOGGER.debug("Timeline chart cleared")
        self._playhead_measure = 0.0
        self._total_measures = None
        self.update()

    def set_playhead_measure(self, value: float) -> None:
        self._playhead_measure = max(0.0, value)
        LOGGER.debug("Timeline playhead moved to %.3f", self._playhead_measure)
        self.update()

    def set_subdivisions(self, value: int) -> None:
        self._subdivisions = max(1, int(value))
        self.update()

    def set_total_measures(self, value: float | None) -> None:
        self._total_measures = max(1.0, float(value)) if value is not None else None
        self.update()

    def _display_measure_count(self) -> float:
        if self._total_measures is not None:
            return self._total_measures
        if self._timeline:
            return float(self._timeline.calculate_max_measure())
        return 8.0

    def _measure_to_x(self, measure: float, max_measure: float, width: int) -> int:
        if max_measure <= 0:
            return 0
        x = floor((measure / max_measure) * width + 0.5)
        return max(0, min(width, x))

    def _subdivision_tick_positions(
        self,
        max_measure: float,
        width: int,
    ) -> list[tuple[int, int, int]]:
        if self._subdivisions <= 1 or max_measure <= 0:
            return []

        ticks: list[tuple[int, int, int]] = []
        seen_x: set[int] = set()
        for measure in range(ceil(max_measure)):
            for sub_index in range(1, self._subdivisions):
                sub_position = measure + sub_index / self._subdivisions
                if sub_position >= max_measure:
                    continue
                sub_x = self._measure_to_x(sub_position, max_measure, width)
                if sub_x in seen_x:
                    continue
                ticks.append((sub_x, measure, sub_index))
                seen_x.add(sub_x)
        return ticks

    def _active_subdivision_span(
        self,
        max_measure: float,
        width: int,
    ) -> tuple[int, int] | None:
        if self._subdivisions <= 1:
            return None

        clamped_measure = max(0.0, min(float(max_measure), self._playhead_measure))
        measure_index = min(max(0, ceil(max_measure) - 1), int(clamped_measure))
        measure_fraction = clamped_measure - measure_index
        subdivision_index = min(
            self._subdivisions - 1,
            int(measure_fraction * self._subdivisions),
        )
        start_pos = measure_index + subdivision_index / self._subdivisions
        end_pos = measure_index + (subdivision_index + 1) / self._subdivisions
        start_x = max(0, min(width, floor((start_pos / max_measure) * width)))
        end_x = max(start_x + 1, ceil((end_pos / max_measure) * width))
        return start_x, min(width, end_x)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override.
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.fillRect(self.rect(), theme.qt(theme.SURFACE_TIMELINE))

            max_measure = max(1.0, self._display_measure_count())
            last_measure = max(1, ceil(max_measure))

            w = max(1, self.width())
            h = self.height()
            minor_pen = QPen(theme.qt(theme.TIMELINE_LINE), 1)
            minor_pen.setCosmetic(True)
            major_pen = QPen(theme.qt(theme.TIMELINE_LINE), 1)
            major_pen.setCosmetic(True)
            active_pen = QPen(theme.qt(theme.ACCENT), 2)
            active_pen.setCosmetic(True)

            active_span = self._active_subdivision_span(max_measure, w)
            if active_span:
                span_start, span_end = active_span
                painter.fillRect(
                    span_start,
                    0,
                    max(1, span_end - span_start),
                    h,
                    theme.qt(theme.SELECTION_FILL),
                )

            if self._subdivisions > 1:
                painter.setPen(minor_pen)
                clamped_playhead = max(0.0, min(max_measure, self._playhead_measure))
                playhead_measure = min(last_measure - 1, int(clamped_playhead))
                playhead_subdivision = min(
                    self._subdivisions - 1,
                    int((clamped_playhead - playhead_measure) * self._subdivisions),
                )
                for sub_x, measure, sub_index in self._subdivision_tick_positions(max_measure, w):
                    tick_height = 8 if sub_index % max(1, self._subdivisions // 4) == 0 else 4
                    if (
                        measure == playhead_measure
                        and sub_index in {playhead_subdivision, playhead_subdivision + 1}
                    ):
                        painter.setPen(active_pen)
                        tick_height = h - 2
                    else:
                        painter.setPen(minor_pen)
                    painter.drawLine(sub_x, h - tick_height - 1, sub_x, h - 1)

            painter.setPen(major_pen)
            for measure in range(last_measure + 1):
                x = self._measure_to_x(float(measure), max_measure, w)
                y_top = 10 if measure % 4 == 0 else 18
                painter.drawLine(x, y_top, x, h - 1)
                if measure % 4 == 0:
                    painter.setPen(theme.qt(theme.TEXT_TIMELINE))
                    painter.drawText(x + 3, 10, str(measure))
                    painter.setPen(major_pen)

            playhead_x = int((min(self._playhead_measure, max_measure) / max_measure) * w)
            painter.setPen(QPen(theme.qt(theme.ACCENT_TIMELINE_PLAYHEAD), 2))
            painter.drawLine(playhead_x, 0, playhead_x, h)
        except Exception:
            LOGGER.exception("Unhandled exception during timeline paintEvent")
            painter.fillRect(self.rect(), theme.qt(theme.SURFACE_TIMELINE))
            painter.setPen(QPen(theme.qt(theme.ACCENT), 1))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Timeline view error occurred. See timelineview.log.",
            )
        finally:
            painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override.
        if event.button() != Qt.MouseButton.LeftButton:
            return
        max_measure = max(1.0, self._display_measure_count())
        ratio = max(0.0, min(1.0, event.position().x() / max(1.0, self.width())))
        target = ratio * max_measure
        LOGGER.debug("Timeline seek requested to %.3f", target)
        self.set_playhead_measure(target)
        self.seek_requested.emit(target)
