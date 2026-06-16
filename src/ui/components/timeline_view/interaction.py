from __future__ import annotations

# ruff: noqa: PLR0911, PLR0912, PLR0913, PLR0915
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt

from src.ui.components.timeline_view.constants import (
    RIGHT_DRAG_THRESHOLD_PX,
)

if TYPE_CHECKING:
    from PySide6.QtGui import QMouseEvent, QResizeEvent, QWheelEvent

    from src.notes import Note

PERF_LOGGER = logging.getLogger("ui.timelineview")
_PERF_SAMPLE_MOD = 60


class TimelineInteractionMixin:
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_scrollbar()
        self._sync_scrollbar()
        if self.note_debug_overlay.is_active():
            self.note_debug_overlay.setGeometry(self.rect())
        self.resized.emit()
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: PLR0911, PLR0912, PLR0915
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                note = self._pick_note(event.position().x(), event.position().y())
                if note is not None:
                    if note in self.selected_notes:
                        self.selected_notes = [n for n in self.selected_notes if n is not note]
                    else:
                        self.selected_notes.append(note)
                    self.selected_note = self.selected_notes[0] if self.selected_notes else None
                    if self.selected_notes:
                        self.note_selected.emit(self.selected_notes[-1])
                        self.notes_selected.emit(list(self.selected_notes))
                    else:
                        self.notes_selected.emit([])
                    self.update()
                return
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self._drag_last_pos = self.projection.pos_at(event.position().y(), self.current_pos)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
            if self.editor_place_mode:
                target = self._placement_target(event.position())
                if target is not None:
                    if self._editor_uses_timed_drag_placement():
                        self._placement_drag_origin = target
                        self._placement_drag_current = target
                        self._placement_drag_kind = "timed"
                        self.setMouseTracking(True)
                        self.update()
                        return
                    if self._editor_uses_size_drag_placement():
                        self._placement_drag_origin = target
                        self._placement_drag_current = target
                        self._placement_drag_kind = "size"
                        self.setMouseTracking(True)
                        self.update()
                        return
                    abs_pos, cell = target
                    self.note_place_requested.emit(abs_pos, cell)
                return
            return

        if event.button() == Qt.MouseButton.RightButton:
            self._right_press_pos = event.position()
            self._right_press_global_pos = event.globalPosition().toPoint()
            self._right_press_note = None
            self._right_press_note_was_selected = False
            note = self._pick_note(event.position().x(), event.position().y())
            if note is not None:
                self._right_press_note = note
                self._right_press_note_was_selected = self._is_note_selected(note)
                self.selected_note = note
                self.selected_notes = [note]
                if not self._right_press_note_was_selected:
                    self.note_selected.emit(note)
                    self.notes_selected.emit([note])
            else:
                self._start_selection_drag(event.position())
            self.update()
            return
    def _is_note_selected(self, note: Note) -> bool:
        return self.selected_note is note or any(
            selected is note for selected in self.selected_notes
        )
    def _reset_right_press_state(self) -> None:
        self._right_press_pos = None
        self._right_press_global_pos = None
        self._right_press_note = None
        self._right_press_note_was_selected = False
    def _right_drag_exceeds_threshold(self, position: QPointF) -> bool:
        if self._right_press_pos is None:
            return False
        return (
            abs(position.x() - self._right_press_pos.x())
            + abs(position.y() - self._right_press_pos.y())
            >= RIGHT_DRAG_THRESHOLD_PX
        )
    def _start_selection_drag(self, position: QPointF) -> None:
        self._selection_drag_viewport_pos = position
        self._selection_drag_origin = self._selection_drag_point(position)
        self._selection_drag_current = self._selection_drag_origin
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
    def _calculate_drag_velocity(
        self, viewport_y: float, height: int, margin: int, fixed_speed: float
    ) -> float:
        """Calculate autoscroll velocity based on mouse position relative to viewport edges."""
        if viewport_y < margin:
            # Move up (scrolling positive Y in our coordinate system)
            return fixed_speed * (1.0 - max(0, viewport_y) / margin)
        if viewport_y > height - margin:
            # Move down
            dist = height - viewport_y
            return -fixed_speed * (1.0 - max(0, dist) / margin)
        return 0.0
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._placement_drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            placement_width = 1 if self._placement_drag_kind == "size" else None
            target = self._placement_target(event.position(), placement_width)
            if target is not None:
                self._placement_drag_current = target
                self.update()
            return
        if (
            self._right_press_pos is not None
            and event.buttons() & Qt.MouseButton.RightButton
            and self._selection_drag_origin is None
            and self._right_drag_exceeds_threshold(event.position())
        ):
            self._start_selection_drag(self._right_press_pos)
        if self._selection_drag_origin is not None and event.buttons() & Qt.MouseButton.RightButton:
            self._selection_drag_viewport_pos = event.position()
            self._selection_drag_current = self._selection_drag_point(event.position())
            self._selection_edge_velocity = self._calculate_drag_velocity(
                event.position().y(),
                self.height(),
                self._selection_edge_margin,
                self._selection_edge_fixed_speed,
            )
            if self._selection_edge_velocity != 0:
                self._selection_drag_autoscroll.start()
            else:
                self._selection_drag_autoscroll.stop()
            self.update()
            return
        if self._drag_last_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            new_pos = self.projection.pos_at(event.position().y(), self.current_pos)
            delta = self._drag_last_pos - new_pos
            self.set_current_pos(self.current_pos + delta)
            self.user_seeked.emit(self.current_pos)
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._placement_drag_origin is not None:
                end = self._placement_drag_current or self._placement_drag_origin
                start_abs, start_cell = self._placement_drag_origin
                end_abs, end_cell = end
                if self._placement_drag_kind == "size":
                    if end_cell == start_cell:
                        self.note_place_requested.emit(start_abs, start_cell)
                    else:
                        cell = min(start_cell, end_cell)
                        width = abs(end_cell - start_cell) + 1
                        self.note_size_drag_place_requested.emit(start_abs, cell, width)
                else:
                    self.note_drag_place_requested.emit(start_abs, start_cell, end_abs, end_cell)
                self._reset_placement_drag_state()
                self.update()
                return
            if self._drag_last_pos is not None:
                self._drag_last_pos = None
                self.setMouseTracking(False)
                self.setCursor(Qt.CursorShape.ArrowCursor)
                return
        if event.button() == Qt.MouseButton.RightButton and self._selection_drag_origin is not None:
            self._apply_selection_rect()
            self._reset_selection_drag_state()
            self._reset_right_press_state()
            self.update()
            return
        if event.button() == Qt.MouseButton.RightButton:
            if self._right_press_note is not None and self._right_press_note_was_selected:
                menu_pos = self._right_press_global_pos or event.globalPosition().toPoint()
                self.note_context_requested.emit(self._right_press_note, menu_pos)
            self._reset_right_press_state()
    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._handle_zoom(delta)
            return

        pixel_delta = event.pixelDelta().y()
        scroll_delta = pixel_delta if pixel_delta else (delta / 120.0) * 100.0
        pos_delta = scroll_delta / self.measure_height
        self.set_current_pos(self.current_pos + pos_delta)
        self.user_seeked.emit(self.current_pos)
