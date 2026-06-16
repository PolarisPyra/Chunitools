from __future__ import annotations

# ruff: noqa: PLR0911, PLR0912, PLR0913, PLR0915
import logging
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QElapsedTimer
from PySide6.QtGui import QPainter, QPaintEvent, QPen

from src.ui import theme
from src.ui.view.export import (
    export_to_image as export_chart_to_image,
    render_segment as render_chart_segment,
)

PERF_LOGGER = logging.getLogger("ui.timelineview")
_PERF_SAMPLE_MOD = 60

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class TimelineRenderMixin:
    def render_segment(
        self,
        painter: QPainter,
        x_left: int,
        segment_height: int,
        start_measure: int,
        chunk: int = 4,
    ) -> None:
        if not self.chart:
            return
        render_chart_segment(
            painter,
            self.chart,
            self.painter_engine,
            x_left,
            segment_height,
            start_measure,
            chunk,
        )
    def export_to_image(
        self,
        file_path: str,
        measures_per_column: int = 8,
        png_quality: int | None = None,
        antialias: bool = True,
    ) -> bool:
        if not self.chart:
            return False
        return export_chart_to_image(
            self.chart,
            self.painter_engine,
            file_path,
            measures_per_column,
            png_quality,
            antialias,
        )

    # --- Event Overrides ---
    def paintEvent(self, event: QPaintEvent) -> None:
        self._frame_seq += 1
        t_total = QElapsedTimer()
        t_total.start()

        elapsed_ns = self._frame_timer.nsecsElapsed()
        self._frame_timer.start()
        if elapsed_ns > 0:
            self.frame_rendered.emit(elapsed_ns / 1_000_000_000.0)

        painter = QPainter(cast("QWidget", self))
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.fillRect(self.rect(), theme.qt(theme.APP_BACKGROUND))
            if not self.chart:
                return

            view_height, view_width = self.height(), self.width()
            chart_width = self.projection.x(self.total_lanes)

            # Use extrapolated position for smooth rendering
            render_pos = self._get_render_pos()

            if self.column_mode:
                self._paint_column_mode(painter, view_width, view_height, chart_width, render_pos)
            else:
                self._paint_scrolling_mode(
                    painter, view_width, view_height, chart_width, render_pos
                )

            if self._frame_seq % _PERF_SAMPLE_MOD == 0:
                total_ms = t_total.nsecsElapsed() / 1_000_000.0
                wall_ms = elapsed_ns / 1_000_000.0
                PERF_LOGGER.debug(
                    "frame=%d dt=%.3fms wall=%.2fms",
                    self._frame_seq, total_ms, wall_ms,
                )

        finally:
            painter.end()
    def _paint_scrolling_mode(
        self,
        painter: QPainter,
        view_width: int,
        view_height: int,
        chart_width: float,
        render_pos: float,
    ) -> None:
        offset_x = (view_width - chart_width) / 2.0
        painter.translate(offset_x, float(view_height - self.judgment_offset))

        # Absolute mapping: Y goes up from judgment line
        top_abs_pos = self.projection.pos_at(-(view_height - self.judgment_offset), render_pos)
        bottom_abs_pos = self.projection.pos_at(self.judgment_offset, render_pos)

        self.painter_engine.draw_lane_lines(painter, render_pos, top_abs_pos, bottom_abs_pos)

        start_m = max(0, int(bottom_abs_pos))
        end_m = int(top_abs_pos) + 1
        self.painter_engine.draw_measure_lines(painter, start_m, end_m, render_pos, chart_width)

        visible_notes = (
            self._get_visible_notes(top_abs_pos, bottom_abs_pos)
            if top_abs_pos < bottom_abs_pos
            else self._get_visible_notes(bottom_abs_pos, top_abs_pos)
        )
        self.painter_engine.draw_notes(painter, visible_notes, render_pos)

        if self._frame_seq % _PERF_SAMPLE_MOD == 0:
            PERF_LOGGER.debug("  notes_drawn=%d", len(visible_notes))

        if self.show_judgment:
            painter.setPen(QPen(theme.qt(theme.ACCENT), 4))
            painter.drawLine(0, 0, int(chart_width), 0)

        if self._placement_drag_origin and self._placement_drag_current:
            self._draw_placement_drag_preview(painter, render_pos)

        if self._selection_drag_origin and self._selection_drag_current:
            self._draw_selection_box(painter, offset_x, view_height)

        for note in self.selected_notes:
            self._draw_note_selection_outline(painter, note, self.projection, render_pos)
    def _paint_column_mode(
        self,
        painter: QPainter,
        view_width: int,
        view_height: int,
        chart_width: float,
        render_pos: float,
    ) -> None:
        col_full_width = chart_width + self.column_spacing
        num_cols = int(max(1, view_width // col_full_width))

        # In column mode, render_pos represents the position we are viewing
        start_measure = int(render_pos)

        for i in range(num_cols):
            painter.save()
            # Calculate column X position (center the block of columns)
            total_cols_width = num_cols * col_full_width - self.column_spacing
            block_offset_x = (view_width - total_cols_width) // 2
            col_x = block_offset_x + i * col_full_width

            painter.translate(col_x, view_height - 50)  # Bottom margin

            m_start = start_measure + i * self.measures_per_column
            m_end = m_start + self.measures_per_column

            # Draw column
            self.painter_engine.draw_lane_lines(
                painter, float(m_start), float(m_end), float(m_start)
            )
            self.painter_engine.draw_measure_lines(
                painter, m_start, m_end, float(m_start), chart_width
            )

            # Get notes for these measures
            col_notes = []
            for m in range(int(m_start), int(m_end) + 1):
                col_notes.extend(self.notes_by_measure.get(m, []))

            self.painter_engine.draw_notes(painter, col_notes, float(m_start))
            painter.restore()
    def _get_render_pos(self) -> float:
        """Return the highest-precision position for rendering.

        During playback, extrapolates from the last known position using the
        tracked velocity so that every paint frame lands at exactly the right
        visual position regardless of the playback timer alignment.
        """
        if self._is_playback_active():
            dt = self._last_pos_update_timer.nsecsElapsed() / 1_000_000_000.0
            return self._visual_pos + self._visual_velocity * dt
        if self.playback_controller:
            return self.playback_controller.get_clock_pos()
        return self.current_pos
