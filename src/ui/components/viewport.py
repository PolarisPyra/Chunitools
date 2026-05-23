from __future__ import annotations

import bisect
from typing import TYPE_CHECKING

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QScrollBar, QWidget

from src.core.config import DEFAULT_SCROLL_SPEED
from src.core.const import AIR_NOTE_TYPES, NoteType
from src.ui import theme
from src.ui.components.note_debug_overlay import NoteDebugOverlay
from src.ui.theme.notes import get_note_color
from src.ui.view import timeline_compat
from src.ui.view.chart_renderer import ChartRenderer
from src.ui.view.export import (
    export_to_image as export_chart_to_image,
    render_segment as render_chart_segment,
)
from src.ui.view.projection import ViewProjection

if TYPE_CHECKING:
    from src.core.models import Chart
    from src.engine.playback import PlaybackController
    from src.notes import Note


SCROLLBAR_WIDTH = 10
SCROLLBAR_MARGIN = 6
SCROLL_UNITS_PER_MEASURE = 1000
SELECTION_EDGE_MARGIN = 36
SELECTION_EDGE_INTERVAL_MS = 16
SELECTION_EDGE_SPEED = 0.04
MAX_VISIBLE_LOOKBACK_MEASURES = 32.0
TARGET_PLAYBACK_FPS = 120
PLAYBACK_REPAINT_INTERVAL_MS = max(1, round(1000 / TARGET_PLAYBACK_FPS))
MIN_SCROLL_SPEED = 1.0
MAX_SCROLL_SPEED = 20.0
PIXELS_PER_SCROLL_SPEED = timeline_compat.MEASURE_HEIGHT
DEFAULT_VIEW_LANE_WIDTH = 24.0
RIGHT_DRAG_THRESHOLD_PX = 4.0


class ChartViewport(QWidget):
    """The main drawing surface for the chart visualizer."""

    chart_loaded = Signal(object)
    current_pos_changed = Signal(float)
    user_seeked = Signal(float)
    frame_rendered = Signal(float)
    resized = Signal()
    zoom_changed = Signal()
    note_selected = Signal(object)
    notes_selected = Signal(object)
    note_context_requested = Signal(object, object)
    note_place_requested = Signal(float, int)
    note_size_drag_place_requested = Signal(float, int, int)
    note_drag_place_requested = Signal(float, int, float, int)

    def __init__(  # noqa: PLR0915
        self, parent: QWidget | None = None, playback_controller: PlaybackController | None = None
    ) -> None:
        super().__init__(parent)
        self.playback_controller = playback_controller
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        self.chart: Chart | None = None
        self.current_pos: float = 0.0
        self.projection = ViewProjection(
            lane_width=DEFAULT_VIEW_LANE_WIDTH,
            base_scroll_scale=PIXELS_PER_SCROLL_SPEED,
            scroll_speed=DEFAULT_SCROLL_SPEED,
        )
        self.total_lanes: int = 16
        self.judgment_offset: int = 100
        self.show_judgment: bool = True
        self.visible_note_types: dict[str, bool] = {}
        self.scroll_speed: float = DEFAULT_SCROLL_SPEED

        self.column_mode: bool = False
        self.measures_per_column: int = 4
        self.column_spacing: int = 100
        self.subdivisions: int = 4

        self.notes_by_measure: dict[int, list[Note]] = {}
        self._visible_notes_cache: tuple[int, int, list[Note]] | None = None
        self._scrollbar_state: tuple[int, int, int] | None = None
        self._notes_by_start_pos: list[Note] = []
        self._note_start_positions: list[float] = []
        self._note_end_positions: dict[Note, float] = {}
        self._pending_playback_update = False
        self._last_playback_update_request = QElapsedTimer()
        self._last_playback_update_request.start()
        self._max_scroll_measure: float = 0.0

        self._drag_last_pos: float | None = None

        self.selected_note: Note | None = None
        self.selected_notes: list[Note] = []
        self.editor_place_mode = False
        self.editor_place_width = 1
        self.editor_place_note_type = NoteType.TAP
        self._placement_drag_origin: tuple[float, int] | None = None
        self._placement_drag_current: tuple[float, int] | None = None
        self._placement_drag_kind: str | None = None
        self._selection_drag_origin: QPointF | None = None
        self._selection_drag_current: QPointF | None = None
        self._selection_drag_viewport_pos: QPointF | None = None
        self._right_press_pos: QPointF | None = None
        self._right_press_global_pos: QPoint | None = None
        self._right_press_note: Note | None = None
        self._right_press_note_was_selected = False
        self._selection_edge_margin = SELECTION_EDGE_MARGIN
        self._selection_edge_velocity = 0.0
        self._selection_edge_fixed_speed = SELECTION_EDGE_SPEED

        self._selection_drag_autoscroll = QTimer(self)
        self._selection_drag_autoscroll.setInterval(SELECTION_EDGE_INTERVAL_MS)
        self._selection_drag_autoscroll.timeout.connect(self._tick_selection_drag_autoscroll)

        self._frame_timer = QElapsedTimer()
        self._frame_timer.start()

        self._last_pos_update_timer = QElapsedTimer()
        self._last_pos_update_timer.start()
        self._visual_pos: float = 0.0

        self.scrollbar = QScrollBar(Qt.Orientation.Vertical, self)
        self._init_scrollbar_style()
        self.scrollbar.hide()

        self.painter_engine = ChartRenderer(
            projection=self.projection,
            total_lanes=self.total_lanes,
            visible_note_types=self.visible_note_types,
            subdivisions=self.subdivisions,
        )

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(max(1, round(1000 / TARGET_PLAYBACK_FPS)))
        self._refresh_timer.timeout.connect(self.update)

        self.scrollbar.valueChanged.connect(self._on_scrollbar_changed)
        self.scrollbar.raise_()

        self.note_debug_overlay = NoteDebugOverlay(self)
        self.note_debug_overlay.raise_()

    @property
    def lane_width(self) -> float:
        return self.projection.lane_width

    @property
    def measure_height(self) -> float:
        return self.projection.measure_height

    def _init_scrollbar_style(self) -> None:
        self.scrollbar.setStyleSheet(
            f"QScrollBar:vertical {{ background: {theme.SURFACE_SCROLLBAR}; "
            "width: 10px; margin: 0; border: none; }"
            f"QScrollBar::handle:vertical {{ background: {theme.SURFACE_SCROLLBAR_HANDLE}; "
            "border-radius: 5px; min-height: 40px; }"
            f"QScrollBar::handle:vertical:hover {{ background: "
            f"{theme.SURFACE_SCROLLBAR_HANDLE_HOVER}; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: {theme.TRANSPARENT}; }}"
        )

    # --- Public API ---

    def set_playback_active(self, active: bool) -> None:
        """Start or stop the dedicated high-precision refresh timer."""
        if active:
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        else:
            self._refresh_timer.stop()
            self.update()

    def set_current_pos(self, pos: float) -> None:
        min_pos, max_pos = self._scroll_bounds()
        pos = max(min_pos, min(max_pos, pos))
        if abs(self.current_pos - pos) < 1e-6:
            return
        self.current_pos = pos
        self._last_pos_update_timer.restart()

        # Optimization: only sync scrollbar if not playing or at lower frequency
        is_playing = self._is_playback_active()
        if not is_playing:
            self._sync_scrollbar()
            self.update()
        elif int(pos * 5) % 2 == 0:  # Even tighter throttle (approx 2.5Hz at 1.0x speed)
            self._sync_scrollbar()

        self.current_pos_changed.emit(self.current_pos)

    def draw_chart(self, chart: Chart) -> None:
        self.prepare_chart(chart)
        self.chart_loaded.emit(chart)
        self._layout_scrollbar()
        self._sync_scrollbar()
        self.update()

    def prepare_chart(self, chart: Chart) -> None:
        self.chart = chart
        self.notes_by_measure = {}
        self._visible_notes_cache = None
        self._scrollbar_state = None
        self._notes_by_start_pos = []
        self._note_start_positions = []
        self._note_end_positions = {}
        self.selected_note = None
        self.selected_notes = []

        timeline = chart.timeline
        self.projection.timeline_engine = timeline  # Inject engine for Note logic

        for note in chart.notes:
            duration = getattr(note, "duration", 0)
            total_ticks = timeline.note_tick(note) + duration
            end_measure = total_ticks // timeline.resolution
            self._note_end_positions[note] = timeline.note_abs_end_pos(note)
            for measure in range(note.measure, end_measure + 1):
                self.notes_by_measure.setdefault(measure, []).append(note)

        self._notes_by_start_pos = list(chart.notes)
        self._note_start_positions = [
            timeline.note_abs_pos(note) for note in self._notes_by_start_pos
        ]
        self.current_pos = 0.0
        self._max_scroll_measure = float(timeline.calculate_max_measure() + 3)
        self._update_painter_config()

    def _update_painter_config(self) -> None:
        self.painter_engine.projection = self.projection
        self.painter_engine.total_lanes = self.total_lanes
        self.painter_engine.visible_note_types = self.visible_note_types
        self.painter_engine.subdivisions = self.subdivisions
        # Clear cache as projection parameters (like lane_width) have changed
        self.painter_engine.cache.clear()
        if hasattr(self.painter_engine, "_delegate") and self.painter_engine._delegate:
            self.painter_engine._delegate.projection = self.projection
            self.painter_engine._delegate.total_lanes = self.total_lanes
            self.painter_engine._delegate.visible_note_types = self.visible_note_types
            self.painter_engine._delegate.subdivisions = self.subdivisions
            self.painter_engine._delegate.cache.clear()

    def set_visible_note_types(self, note_types: dict[str, bool]) -> None:
        self.visible_note_types = note_types
        self.painter_engine.visible_note_types = note_types
        if hasattr(self.painter_engine, "_delegate") and self.painter_engine._delegate:
            self.painter_engine._delegate.visible_note_types = note_types
            self.painter_engine._delegate.cache.clear()
        self.painter_engine.cache.clear()
        self.update()

    def set_note_debug_overlay_active(self, active: bool) -> None:
        self.note_debug_overlay.set_active(active)
        if active:
            self.note_debug_overlay.setGeometry(self.rect())

    def set_subdivisions(self, subdivisions: int) -> None:
        self.subdivisions = subdivisions
        self.painter_engine.subdivisions = subdivisions
        if hasattr(self.painter_engine, "_delegate") and self.painter_engine._delegate:
            self.painter_engine._delegate.subdivisions = subdivisions
            self.painter_engine._delegate.cache.clear()
        self.update()

    def set_scroll_speed(self, multiplier: float, speed_factor: float = 1.0) -> None:
        """Apply XMod scroll speed formula."""
        clamped_multiplier = max(MIN_SCROLL_SPEED, min(MAX_SCROLL_SPEED, float(multiplier)))
        self.scroll_speed = clamped_multiplier
        self.projection.scroll_speed = clamped_multiplier
        self.projection.speed_factor = float(speed_factor)
        self._sync_scrollbar()
        self.zoom_changed.emit()
        # Clear renderer cache on zoom change
        self.painter_engine.cache.clear()
        if hasattr(self.painter_engine, "_delegate") and self.painter_engine._delegate:
            self.painter_engine._delegate.cache.clear()
        self.update()

    def set_total_measures(self, value: float | None) -> None:
        if value is None:
            if self.chart is not None:
                self._max_scroll_measure = float(self.chart.timeline.calculate_max_measure() + 3)
        else:
            self._max_scroll_measure = max(
                self._max_scroll_measure,
                float(value) + 3.0,
            )
        self._sync_scrollbar()

    def set_editor_place_mode(
        self,
        active: bool,
        width: int = 1,
        note_type: NoteType | None = None,
    ) -> None:
        self.editor_place_mode = active
        self.editor_place_width = max(1, min(16, int(width)))
        if note_type is not None:
            self.editor_place_note_type = note_type
        self.setCursor(Qt.CursorShape.CrossCursor if active else Qt.CursorShape.ArrowCursor)

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

    def paintEvent(self, event: QPaintEvent) -> None:
        elapsed_ns = self._frame_timer.nsecsElapsed()
        self._frame_timer.start()
        if elapsed_ns > 0:
            self.frame_rendered.emit(elapsed_ns / 1_000_000_000.0)

        painter = QPainter(self)
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

        if self.show_judgment:
            painter.setPen(QPen(theme.qt(theme.ACCENT), 4))  # Increased width for better visibility
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
        """Return the highest-precision position for rendering."""
        if self.playback_controller:
            return self.playback_controller.get_clock_pos()
        return self.current_pos

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

        current_pos = self.current_pos
        baseline_y = self.height() - self.judgment_offset
        top_abs_pos = projection.pos_at(-baseline_y, current_pos)
        bottom_abs_pos = projection.pos_at(self.judgment_offset, current_pos)

        visible_notes = self._get_visible_notes(
            min(top_abs_pos, bottom_abs_pos), max(top_abs_pos, bottom_abs_pos)
        )

        best_note: Note | None = None
        best_distance: float | None = None
        for note in reversed(visible_notes):
            note_x = projection.x(note.cell)
            note_w = projection.w(note.width)
            note_y = projection.y(self.chart.timeline.note_abs_pos(note), current_pos)

            top_off, bot_off = self._get_note_bounds(note)
            rect = QRectF(note_x - 4, note_y - top_off - 4, note_w + 8, (top_off - bot_off) + 8)

            if not rect.contains(local_x, local_y):
                continue
            distance = abs((note_x + note_w / 2) - local_x) + abs(note_y - local_y)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_note = note
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
        current_pos = self.current_pos
        chart_width = projection.x(self.total_lanes)
        offset_x = (self.width() - chart_width) / 2
        baseline_y = self.height() - self.judgment_offset

        # Origin/Current are (local_x, abs_pos)
        x1 = self._selection_drag_origin.x() + offset_x
        x2 = self._selection_drag_current.x() + offset_x

        # Map absolute positions back to screen Y for the selection rectangle
        y1 = projection.y(self._selection_drag_origin.y(), current_pos) + baseline_y
        y2 = projection.y(self._selection_drag_current.y(), current_pos) + baseline_y

        return QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

    def _pick_notes_in_rect(self, viewport_rect: QRectF) -> list[Note]:
        if not self.chart:
            return []

        projection = self.projection
        current_pos = self.current_pos
        chart_width = projection.x(self.total_lanes)
        offset_x = (self.width() - chart_width) / 2
        baseline_y = self.height() - self.judgment_offset

        matches: list[Note] = []
        for note in self.chart.notes:
            x_pos = projection.x(note.cell) + offset_x
            y_pos = projection.y(self.chart.timeline.note_abs_pos(note), current_pos) + baseline_y
            width = projection.w(note.width)

            top_off, bot_off = self._get_note_bounds(note)
            rect = QRectF(x_pos - 4, y_pos - top_off - 4, width + 8, (top_off - bot_off) + 8)

            if viewport_rect.intersects(rect):
                matches.append(note)
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

        x_pos = projection.x(note.cell)
        y_pos = projection.y(self.chart.timeline.note_abs_pos(note), current_pos)
        width = projection.w(note.width)

        top_off, bot_off = self._get_note_bounds(note)
        rect = QRectF(x_pos - 4, y_pos - top_off - 4, width + 8, (top_off - bot_off) + 8)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(theme.qt(theme.SELECTION_OUTLINE), 2, Qt.PenStyle.DashLine))
        painter.drawRect(rect)

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
            NoteType.ASO,
            NoteType.HHD,
            NoteType.HHX,
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

        start_abs, start_cell = self._placement_drag_origin
        end_abs, end_cell = self._placement_drag_current
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
            NoteType.ASO,
            NoteType.HHD,
            NoteType.HHX,
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
