from __future__ import annotations

# ruff: noqa: PLR0911, PLR0912, PLR0913, PLR0915
import bisect
import logging
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPen

from src.core.const import AIR_NOTE_TYPES, NoteType
from src.ui import theme
from src.ui.components.timeline_view.constants import (
    MAX_VISIBLE_LOOKBACK_MEASURES,
)
from src.ui.theme.notes import get_note_color

if TYPE_CHECKING:
    from src.notes import Note
    from src.ui.view.projection import ViewProjection

PERF_LOGGER = logging.getLogger("ui.timelineview")
_PERF_SAMPLE_MOD = 60


class TimelineSelectionMixin:
    def _get_note_bounds(self, note: Note) -> tuple[float, float]:
        """Return (top_offset, bottom_offset) relative to note._abs_pos in pixels."""
        timeline = self.chart.timeline if self.chart else None
        if not timeline:
            return (7, -7)

        abs_pos = timeline.note_abs_pos(note)
        abs_end_pos = timeline.note_abs_end_pos(note)

        if abs_end_pos > abs_pos:
            height = (abs_end_pos - abs_pos) * self.projection.measure_height
            return (height, 0)  # Sustain body goes from y-height to y

        # TAP, CHR, FLK, MNE have a head of height 10 centered at y_pos
        if note.note_type in {NoteType.TAP, NoteType.CHR, NoteType.FLK, NoteType.MNE}:
            return (5, -5)

        # AIR modifiers have triangles offset from the ground position
        # Air sustains (AHD, ALD, ASD, ASC) should use sustain body bounds
        if note.note_type in AIR_NOTE_TYPES and not hasattr(note, "duration"):
            is_down = any(s in note.note_type.value for s in ("DW", "DR", "DL"))
            if is_down:
                # base_y = y-35, tip_y = y-15 -> range [-40, -10]
                return (40, 10)
            # base_y = y-8, tip_y = y-28 -> range [-32, 2]
            return (32, -2)

        # Default fallback
        return (7, -7)
    def _pick_note(self, viewport_x: float, viewport_y: float) -> Note | None:
        if not self.chart:
            return None

        projection = self.projection
        chart_width = projection.x(self.total_lanes)
        offset_x = int((self.width() - chart_width) / 2)
        local_x = viewport_x - offset_x
        local_y = viewport_y - (self.height() - self.judgment_offset)
        if local_x < 0 or local_x > chart_width:
            return None

        current_pos = self._get_render_pos()
        baseline_y = self.height() - self.judgment_offset
        top_abs_pos = projection.pos_at(-baseline_y, current_pos)
        bottom_abs_pos = projection.pos_at(self.judgment_offset, current_pos)

        visible_notes = self._get_visible_notes(
            min(top_abs_pos, bottom_abs_pos), max(top_abs_pos, bottom_abs_pos)
        )

        timeline = self.chart.timeline
        best_note: Note | None = None
        best_distance: float | None = None

        from src.notes import AirSlideStart, Slide

        def _test_note(n: Note, abs_pos_override: float | None = None) -> None:
            nonlocal best_distance, best_note
            # Slide steps render at end_cell; the wrapper itself renders at cell
            if abs_pos_override is not None:
                cell_attr = getattr(n, "end_cell", n.cell)
                width_attr = getattr(n, "end_width", n.width)
            else:
                cell_attr = n.cell
                width_attr = n.width
            note_x = projection.x(cell_attr)
            note_w = projection.w(width_attr)
            abs_pos = abs_pos_override or timeline.note_abs_pos(n)
            note_y = projection.y(abs_pos, current_pos)
            rect = QRectF(note_x - 4, note_y - 4, note_w + 8, 14)
            if not rect.contains(local_x, local_y):
                return
            distance = abs((note_x + note_w / 2) - local_x) + abs(note_y - local_y)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_note = n

        for note in reversed(visible_notes):
            # Test the top-level wrapper first
            _test_note(note)
            # Also test individual slide/air-slide steps
            if isinstance(note, (Slide, AirSlideStart)):
                base_tick = timeline.note_tick(note)
                current_tick = base_tick
                for step in note.steps:
                    current_tick += step.duration
                    step_abs = current_tick / timeline.resolution
                    _test_note(step, abs_pos_override=step_abs)

        return best_note
    def _selection_drag_point(self, viewport_point: QPointF) -> QPointF:
        """Convert a viewport mouse point to a virtual coordinate (local_x, abs_pos)."""
        projection = self.projection
        chart_width = projection.x(self.total_lanes)
        offset_x = (self.width() - chart_width) / 2
        local_x = viewport_point.x() - offset_x
        local_y = viewport_point.y() - (self.height() - self.judgment_offset)

        abs_pos = projection.pos_at(local_y, self.current_pos)
        return QPointF(local_x, abs_pos)
    def _placement_target(
        self,
        viewport_point: QPointF,
        placement_width: int | None = None,
    ) -> tuple[float, int] | None:
        """Convert a viewport click to an absolute chart position and lane cell."""
        projection = self.projection
        chart_width = projection.x(self.total_lanes)
        offset_x = (self.width() - chart_width) / 2
        local_x = viewport_point.x() - offset_x
        if local_x < 0 or local_x > chart_width:
            return None
        local_y = viewport_point.y() - (self.height() - self.judgment_offset)
        abs_pos = max(0.0, projection.pos_at(local_y, self.current_pos))
        width = self.editor_place_width if placement_width is None else placement_width
        max_cell = max(0, self.total_lanes - max(1, min(16, int(width))))
        cell = max(0, min(max_cell, int(projection.cell_at(local_x))))
        return abs_pos, cell
    def _selection_rect(self) -> QRectF:
        if self._selection_drag_origin is None or self._selection_drag_current is None:
            return QRectF()

        projection = self.projection
        current_pos = self._get_render_pos()
        chart_width = projection.x(self.total_lanes)
        offset_x = (self.width() - chart_width) / 2
        baseline_y = self.height() - self.judgment_offset
        x1 = self._selection_drag_origin.x() + offset_x
        x2 = self._selection_drag_current.x() + offset_x

        # Map absolute positions back to screen Y for the selection rectangle
        y1 = projection.y(self._selection_drag_origin.y(), current_pos) + baseline_y
        y2 = projection.y(self._selection_drag_current.y(), current_pos) + baseline_y

        return QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
    def _pick_notes_in_rect(self, viewport_rect: QRectF) -> list[Note]:
        if not self.chart:
            return []

        from src.notes import AirSlideStart, Slide

        projection = self.projection
        current_pos = self._get_render_pos()
        chart_width = projection.x(self.total_lanes)
        offset_x = (self.width() - chart_width) / 2
        baseline_y = self.height() - self.judgment_offset

        timeline = self.chart.timeline
        matches: list[Note] = []

        def _test_rect(n, note_y: float) -> None:
            from src.notes import SlideTo as _SlideTo
            if isinstance(n, _SlideTo):
                cell_attr = n.end_cell
                width_attr = n.end_width
            else:
                cell_attr = n.cell
                width_attr = n.width
            x_pos = projection.x(cell_attr) + offset_x
            y_pos = note_y + baseline_y
            width = projection.w(width_attr)
            rect = QRectF(x_pos - 4, y_pos - 4, width + 8, 14)
            if viewport_rect.intersects(rect):
                matches.append(n)

        for note in self.chart.notes:
            note_y = projection.y(timeline.note_abs_pos(note), current_pos)
            _test_rect(note, note_y)

            # Also test slide steps
            if isinstance(note, (Slide, AirSlideStart)):
                base_tick = timeline.note_tick(note)
                current_tick = base_tick
                for step in note.steps:
                    current_tick += step.duration
                    step_y = projection.y(current_tick / timeline.resolution, current_pos)
                    _test_rect(step, step_y)

        return matches
    def _draw_note_selection_outline(
        self,
        painter: QPainter,
        note: Note,
        projection: ViewProjection,
        current_pos: float,
    ) -> None:
        if self.chart is None:
            return

        from src.notes import SlideTo

        timeline = self.chart.timeline

        def _draw_rect(n, n_abs_pos: float) -> None:
            if isinstance(n, SlideTo):
                cell_attr = n.end_cell
                width_attr = n.end_width
            else:
                cell_attr = n.cell
                width_attr = n.width
            x_pos = projection.x(cell_attr)
            y_pos = projection.y(n_abs_pos, current_pos)
            width = projection.w(width_attr)
            rect = QRectF(x_pos - 4, y_pos - 4, width + 8, 14)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.qt(theme.SELECTION_OUTLINE), 2, Qt.PenStyle.DashLine))
            painter.drawRect(rect)

        if isinstance(note, SlideTo):
            # Slide step — need to find its parent and compute position
            for parent_note in self.chart.notes:
                if hasattr(parent_note, "steps") and note in parent_note.steps:
                    base_tick = timeline.note_tick(parent_note)
                    current_tick = base_tick
                    for step in parent_note.steps:
                        current_tick += step.duration
                        if step is note:
                            _draw_rect(note, current_tick / timeline.resolution)
                            return
            return

        _draw_rect(note, timeline.note_abs_pos(note))

    # --- Helpers ---
    def _reset_selection_drag_state(self) -> None:
        self._selection_drag_origin = None
        self._selection_drag_current = None
        self._selection_drag_viewport_pos = None
        self._selection_edge_velocity = 0.0
        self._selection_drag_autoscroll.stop()
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.ArrowCursor)
    def _reset_placement_drag_state(self) -> None:
        self._placement_drag_origin = None
        self._placement_drag_current = None
        self._placement_drag_kind = None
        self.setMouseTracking(False)
        cursor = (
            Qt.CursorShape.CrossCursor if self.editor_place_mode else Qt.CursorShape.ArrowCursor
        )
        self.setCursor(cursor)
    def _editor_uses_timed_drag_placement(self) -> bool:
        return self.editor_place_note_type in {
            NoteType.HLD,
            NoteType.HXD,
            NoteType.AHD,
            NoteType.AHX,
            NoteType.ALD,
            NoteType.SLD,
            NoteType.SLC,
            NoteType.SXD,
            NoteType.SXC,
            NoteType.ASD,
            NoteType.ASC,
        }
    def _editor_uses_size_drag_placement(self) -> bool:
        return not self._editor_uses_timed_drag_placement()
    def _collect_notes_in_range(
        self, notes: list[Note], start_pos: float, end_pos: float
    ) -> list[Note]:
        """Collect notes that intersect the visible measure range."""
        idx_end = bisect.bisect_right(self._note_start_positions, end_pos)
        visible: list[Note] = []
        for i in range(idx_end - 1, -1, -1):
            note = notes[i]
            note_start_pos = self._note_start_positions[i]
            note_end_pos = self._note_end_positions[note]
            if note_end_pos >= start_pos:
                visible.append(note)
            elif start_pos - note_start_pos > MAX_VISIBLE_LOOKBACK_MEASURES:
                break

        return visible
    def _get_visible_notes(self, start_pos: float, end_pos: float) -> list[Note]:
        if not self.chart:
            return []
        return self._collect_notes_in_range(self._notes_by_start_pos, start_pos, end_pos)
    def _collect_visible_notes(
        self,
        notes_by_measure: dict[int, list[Note]],
        start_measure: int,
        end_measure: int,
    ) -> list[Note]:
        """Return deduplicated notes visible in [start_measure, end_measure]."""
        visible: list[Note] = []
        seen: set[int] = set()
        for measure in range(start_measure, end_measure + 1):
            for note in notes_by_measure.get(measure, []):
                note_id = id(note)
                if note_id in seen:
                    continue
                visible.append(note)
                seen.add(note_id)
        return visible
    def _draw_selection_box(self, painter: QPainter, offset_x: float, view_height: int) -> None:
        rect = self._selection_rect()
        painter.save()
        painter.resetTransform()
        painter.setBrush(theme.qt(theme.SELECTION_FILL))
        painter.setPen(QPen(theme.qt(theme.SELECTION_OUTLINE), 1, Qt.PenStyle.DashLine))
        painter.drawRect(rect)
        painter.restore()
    def _draw_placement_drag_preview(self, painter: QPainter, current_pos: float) -> None:
        if self._placement_drag_origin is None or self._placement_drag_current is None:
            return

        drag_origin = cast("tuple[float, int]", self._placement_drag_origin)
        drag_current = cast("tuple[float, int]", self._placement_drag_current)
        start_abs, start_cell = drag_origin
        end_abs, end_cell = drag_current
        start_y = self.projection.y(start_abs, current_pos)
        end_y = self.projection.y(end_abs, current_pos)
        start_x = self.projection.x(start_cell)
        end_x = self.projection.x(end_cell)
        if self._placement_drag_kind == "size":
            cell = min(start_cell, end_cell)
            width_cells = abs(end_cell - start_cell) + 1
            start_x = self.projection.x(cell)
            end_x = start_x
            width = self.projection.w(width_cells)
        else:
            width = self.projection.w(self.editor_place_width)

        color = get_note_color(self.editor_place_note_type)
        fill = theme.with_alpha(color, 70)
        outline = QPen(theme.with_alpha(color, 220), 2)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(outline)
        painter.setBrush(fill)

        if self._placement_drag_kind == "size":
            painter.drawRoundedRect(
                QRectF(start_x, start_y - 5, width, 10),
                3,
                3,
            )
        elif self.editor_place_note_type in {
            NoteType.SLD,
            NoteType.SLC,
            NoteType.SXD,
            NoteType.SXC,
            NoteType.ASD,
            NoteType.ASC,
            NoteType.ALD,
        }:
            painter.drawLine(
                QPointF(start_x + width / 2, start_y),
                QPointF(end_x + width / 2, end_y),
            )
            head_height = 10.0
            painter.drawRoundedRect(
                QRectF(start_x, start_y - head_height / 2, width, head_height),
                3,
                3,
            )
            painter.drawRoundedRect(
                QRectF(end_x, end_y - head_height / 2, width, head_height),
                3,
                3,
            )
        else:
            top = min(start_y, end_y)
            height = max(10.0, abs(end_y - start_y))
            painter.drawRoundedRect(QRectF(start_x, top, width, height), 3, 3)
        painter.restore()
    def _apply_selection_rect(self) -> None:
        rect = self._selection_rect()
        if rect.width() < 4 and rect.height() < 4:
            pos = self._selection_drag_viewport_pos
            if pos is None:
                self.notes_selected.emit([])
                return

            note = self._pick_note(pos.x(), pos.y())
            self.selected_notes = [note] if note else []
            self.selected_note = note
            if note:
                self.note_selected.emit(note)
            else:
                self.notes_selected.emit([])
        else:
            self.selected_notes = self._pick_notes_in_rect(rect)
            self.selected_note = self.selected_notes[0] if self.selected_notes else None
            self.notes_selected.emit(list(self.selected_notes))
    def _clear_selection(self) -> None:
        self.selected_notes = []
        self.selected_note = None
        self._selection_drag_origin = None
        self.notes_selected.emit([])
        self.setCursor(Qt.CursorShape.ArrowCursor)
