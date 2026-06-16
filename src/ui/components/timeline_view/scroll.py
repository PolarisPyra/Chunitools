from __future__ import annotations

# ruff: noqa: PLR0911, PLR0912, PLR0913, PLR0915
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QRect

from src.ui.components.timeline_view.constants import (
    SCROLL_UNITS_PER_MEASURE,
    SCROLLBAR_MARGIN,
    SCROLLBAR_WIDTH,
)

if TYPE_CHECKING:
    from src.notes import Note

PERF_LOGGER = logging.getLogger("ui.timelineview")
_PERF_SAMPLE_MOD = 60


class TimelineScrollMixin:
    def _handle_zoom(self, delta: int) -> None:
        factor = 1.15 if delta > 0 else 0.85
        new_h = self.projection.measure_height * factor
        new_w = self.projection.lane_width * factor
        if 200 <= new_h <= 8000 and 10 <= new_w <= 300:
            self.projection.measure_height = new_h
            self.projection.lane_width = new_w
            self.zoom_changed.emit()
            self.update()
    def _scroll_bounds(self) -> tuple[float, float]:
        return 0.0, self._max_scroll_measure
    def _layout_scrollbar(self) -> None:
        self.scrollbar.setGeometry(
            QRect(
                self.width() - SCROLLBAR_WIDTH - SCROLLBAR_MARGIN,
                SCROLLBAR_MARGIN,
                SCROLLBAR_WIDTH,
                max(0, self.height() - SCROLLBAR_MARGIN * 2),
            )
        )
    def _sync_scrollbar(self) -> None:
        min_p, max_p = self._scroll_bounds()
        total_pos = max_p - min_p

        # INVERSION: max_p is top (value 0), 0 is bottom (value range_max)
        val = int(round((max_p - self.current_pos) * SCROLL_UNITS_PER_MEASURE))
        range_max = int(round(total_pos * SCROLL_UNITS_PER_MEASURE))
        page = int(round((self.height() / self.measure_height) * SCROLL_UNITS_PER_MEASURE))

        self.scrollbar.blockSignals(True)
        self.scrollbar.setRange(0, max(0, range_max))
        self.scrollbar.setPageStep(page)
        self.scrollbar.setValue(val)
        self.scrollbar.blockSignals(False)
        if not self.scrollbar.isVisible():
            self.scrollbar.show()
            self.scrollbar.raise_()
    def _on_scrollbar_changed(self, value: int) -> None:
        min_p, max_p = self._scroll_bounds()
        # INVERSION: pos = max_p - (value / UNIT)
        self.set_current_pos(max_p - (value / SCROLL_UNITS_PER_MEASURE))
        self.user_seeked.emit(self.current_pos)
    def _tick_selection_drag_autoscroll(self) -> None:
        if not self._selection_drag_origin or not self._selection_drag_viewport_pos:
            self._selection_drag_autoscroll.stop()
            return
        self.set_current_pos(self.current_pos + self._selection_edge_velocity)
        self.user_seeked.emit(self.current_pos)
        self._selection_drag_current = self._selection_drag_point(self._selection_drag_viewport_pos)
        self.update()
    def jump_to_measure(self, measure: int, offset: int = 0) -> None:
        if not self.chart:
            return
        res = max(1, int(self.chart.metadata.resolution))
        self.set_current_pos(measure + offset / res)
    def select_measure(self, measure: int) -> list[Note]:
        if not self.chart:
            return []
        notes = [n for n in self.chart.notes if n.measure == measure]
        self.selected_notes = notes
        self.selected_note = notes[0] if notes else None
        self.notes_selected.emit(list(notes))
        self.update()
        return notes
    def _is_playback_active(self) -> bool:
        playback = getattr(self.parent(), "playback", None)
        return bool(playback and playback.is_playing)
    def _request_viewport_update(self, is_playing: bool) -> None:
        """Request a redraw of the viewport, with special handling for playback."""
        self._pending_playback_update = False
        self.update()
