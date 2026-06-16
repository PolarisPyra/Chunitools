from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, Qt, QTimer, Signal
from PySide6.QtWidgets import QScrollBar, QWidget

from src.config import DEFAULT_SCROLL_SPEED
from src.core.const import NoteType
from src.ui import theme
from src.ui.components.note_debug_overlay import NoteDebugOverlay
from src.ui.components.timeline_view.constants import (
    DEFAULT_VIEW_LANE_WIDTH,
    MAX_SCROLL_SPEED,
    MIN_SCROLL_SPEED,
    PIXELS_PER_SCROLL_SPEED,
    SELECTION_EDGE_INTERVAL_MS,
    SELECTION_EDGE_MARGIN,
    SELECTION_EDGE_SPEED,
    TARGET_PLAYBACK_FPS,
)
from src.ui.components.timeline_view.interaction import TimelineInteractionMixin
from src.ui.components.timeline_view.render import TimelineRenderMixin
from src.ui.components.timeline_view.scroll import TimelineScrollMixin
from src.ui.components.timeline_view.selection import TimelineSelectionMixin
from src.ui.view.chart_renderer import ChartRenderer
from src.ui.view.projection import ViewProjection

if TYPE_CHECKING:
    from src.core.models import Chart
    from src.engine.playback import PlaybackController
    from src.notes import Note


class ChartViewport(
    TimelineRenderMixin,
    TimelineInteractionMixin,
    TimelineSelectionMixin,
    TimelineScrollMixin,
    QWidget,
):
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
        self._frame_seq: int = 0

        self._last_pos_update_timer = QElapsedTimer()
        self._last_pos_update_timer.start()
        self._visual_pos: float = 0.0
        self._visual_velocity: float = 0.0  # measures/second

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

        # Track velocity for smooth extrapolation
        dt_update = self._last_pos_update_timer.nsecsElapsed() / 1_000_000_000.0
        if 0.001 < dt_update < 0.1:
            vel = (pos - self._visual_pos) / dt_update
            # Clamp to reasonable BPM-driven scroll speeds (~200 measures/sec max)
            self._visual_velocity = max(-200.0, min(200.0, vel))
        elif dt_update >= 0.1:
            self._visual_velocity = 0.0  # Gap too large — treat as seek
        self._visual_pos = pos
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
        self.painter_engine.debug_active = active
        if hasattr(self.painter_engine, "_delegate") and self.painter_engine._delegate:
            self.painter_engine._delegate.debug_active = active
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
