from __future__ import annotations

# ruff: noqa: PLR0913
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QElapsedTimer, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from src.engine.soflan import SoflanProjector
from src.ui.components.note_debug_overlay_3d import NoteDebugOverlay3D
from src.ui.components.play_view.notes import PlayViewNotesMixin
from src.ui.components.play_view.playfield import PlayViewPlayfieldMixin

LOGGER = logging.getLogger("ui.3dview")

if TYPE_CHECKING:
    from src.core.const import NoteType
    from src.core.models import Chart
    from src.engine.playback import PlaybackController
    from src.notes import Note

from src.ui.components.play_view.geometry import (
    DEFAULT_SCROLL_SPEED,
    JUDGE_OFFSET,
    PIXELS_PER_SCROLL_SPEED,
    REPAINT_INTERVAL_MS,
    VISIBLE_DEPTH,
    _scrubber_target_measure,
    _visible_window,
    _world_depth,
)


class PlayView3D(PlayViewNotesMixin, PlayViewPlayfieldMixin, QWidget):
    """3D perspective chart play view using recovered field geometry.

    World-space: 16 lanes x 2 units = 32 total width.
    Screen projection uses a recovered 45-degree camera and lookAt setup.
    Screen mapping keeps 64 units per lane over a -512..512 field.

    Renders notes in a perspective 3D viewport with:
    - Converging lane lines
    - Notes scaling from small (far) to large (judge line)
    - Air notes floating above the playfield
    - Derived lane width, note span, speed window, and visibility bounds
    """

    current_pos_changed = Signal(float)
    user_seeked = Signal(float)

    def __init__(
        self,
        parent: QWidget | None = None,
        playback_controller: PlaybackController | None = None,
    ) -> None:
        super().__init__(parent)
        self.playback_controller = playback_controller
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        self.chart: Chart | None = None
        self.current_pos: float = 0.0
        self.scroll_speed: float = DEFAULT_SCROLL_SPEED
        self._max_scroll_measure: float = 0.0
        self.judge_offset: float = JUDGE_OFFSET
        self.total_lanes: int = 16
        self.show_judgment: bool = True
        self._notes: list[Note] = []
        self._note_times: dict[int, float] = {}
        self._note_end_times: dict[int, float] = {}
        self._note_abs_pos: dict[int, float] = {}
        self._soflan_projector: SoflanProjector | None = None
        self._defer_air_arrows: bool = False
        self._deferred_air_arrows: list[
            tuple[Note, float, float, float, float, int, NoteType, float, float, float, float]
        ] = []
        self.visible_note_types: dict[str, bool] = {}

        self._frame_timer = QElapsedTimer()
        self._frame_timer.start()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(REPAINT_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self.update)

        self._debug_overlay = NoteDebugOverlay3D(self)
        self._debug_overlay.set_play_view(self)

    def set_note_debug_overlay_active(self, active: bool) -> None:
        self._debug_overlay.set_active(active)
        self.update()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._debug_overlay.setGeometry(self.rect())

    def draw_chart(self, chart: Chart) -> None:
        self.chart = chart
        self._soflan_projector = SoflanProjector(chart)
        self._notes = list(chart.notes)
        self._cache_note_times()
        self._max_scroll_measure = float(chart.timeline.calculate_max_measure() + 3)
        self.set_current_pos(self.current_pos)
        LOGGER.debug("3D view loaded chart: %s notes", len(self._notes))
        self.update()

    def set_visible_note_types(self, note_types: dict[str, bool]) -> None:
        self.visible_note_types = note_types
        self.update()

    def _cache_note_times(self) -> None:
        if not self.chart:
            return
        tl = self.chart.timeline
        self._note_times.clear()
        self._note_end_times.clear()
        self._note_abs_pos.clear()
        for note in self._notes:
            abs_pos = tl.note_abs_pos(note)
            self._note_abs_pos[id(note)] = abs_pos
            self._note_times[id(note)] = tl.time_at_measure(abs_pos)
            end_pos = tl.note_abs_end_pos(note)
            self._note_end_times[id(note)] = tl.time_at_measure(end_pos)

    def set_current_pos(self, pos: float) -> None:
        min_pos, max_pos = self._scroll_bounds()
        pos = max(min_pos, min(max_pos, pos))
        if abs(self.current_pos - pos) < 1e-6:
            return
        self.current_pos = pos
        self.update()
        self.current_pos_changed.emit(self.current_pos)

    def set_scroll_speed(self, speed: float) -> None:
        self.scroll_speed = max(0.1, float(speed))
        self.update()

    def set_total_measures(self, total: float | None) -> None:
        if total is None:
            if self.chart is not None:
                self._max_scroll_measure = float(self.chart.timeline.calculate_max_measure() + 3)
        else:
            self._max_scroll_measure = max(
                self._max_scroll_measure,
                float(total) + 3.0,
            )
        self.set_current_pos(self.current_pos)

    @property
    def measure_height(self) -> float:
        return PIXELS_PER_SCROLL_SPEED * self.scroll_speed

    def _scroll_bounds(self) -> tuple[float, float]:
        return 0.0, self._max_scroll_measure

    def _scroll_by_delta(self, delta: float, pixel_delta: float = 0.0) -> None:
        scroll_delta = pixel_delta if pixel_delta else (delta / 120.0) * 100.0
        pos_delta = scroll_delta / self.measure_height
        self.set_current_pos(self.current_pos + pos_delta)
        self.user_seeked.emit(self.current_pos)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt override.
        self._scroll_by_delta(event.angleDelta().y(), event.pixelDelta().y())
        event.accept()

    def set_playback_active(self, active: bool) -> None:
        if active:
            if not self._refresh_timer.isActive():
                self._refresh_timer.start()
        else:
            self._refresh_timer.stop()
            self.update()

    def _get_judge_time(self) -> float:
        if not self.chart:
            return 0.0
        tl = self.chart.timeline
        return tl.time_at_measure(self.current_pos) + self.judge_offset

    def _compute_depth(self, note_time_s: float, judge_time_s: float) -> float:
        window = _visible_window(self.scroll_speed)
        return _world_depth(note_time_s, judge_time_s, window)

    def _compute_note_depth(
        self,
        note: Note,
        tick: int,
        note_time_s: float,
        judge_time_s: float,
        *,
        cell: float | None = None,
        width: float | None = None,
    ) -> float:
        window = _visible_window(self.scroll_speed)
        projector = self._soflan_projector
        if projector is None or not projector.has_scroll_effects():
            return _world_depth(note_time_s, judge_time_s, window)
        return (
            projector.depth_for_note_tick(
                note,
                tick,
                note_time_s,
                judge_time_s,
                window,
                cell=cell,
                width=width,
            )
            * VISIBLE_DEPTH
        )

    def _get_render_pos(self) -> float:
        if self.playback_controller:
            return self.playback_controller.get_clock_pos()
        return self.current_pos

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt override.
        _ = event
        self._frame_timer.start()

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.fillRect(self.rect(), QColor(10, 10, 14))

            if not self.chart:
                self._draw_empty_state(painter)
                return

            render_pos = self._get_render_pos()
            self.current_pos = render_pos
            if self.chart:
                tl = self.chart.timeline
                self.current_pos = render_pos
                judge_time = tl.time_at_measure(render_pos) + self.judge_offset

            self._draw_playfield(painter)
            self._draw_lane_lines(painter, judge_time)
            if self.show_judgment:
                self._draw_judge_line(painter)

            self._draw_notes(painter, judge_time)
            self._draw_scrubber(painter)

        except Exception:
            LOGGER.exception("Unhandled exception during 3D view paintEvent")
            painter.fillRect(self.rect(), QColor(20, 20, 24))
            painter.setPen(QColor(255, 100, 100))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "3D view error occurred. See 3dview.log.",
            )
        finally:
            painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override.
        if not self.chart:
            return
        w = self.width()
        margin = 8
        scrubber_x = margin
        scrubber_w = w - 2 * margin
        scrubber_h = 16
        scrubber_y = self.height() - scrubber_h - 4

        if scrubber_y - 10 <= event.position().y() <= scrubber_y + scrubber_h + 10:
            ratio = max(0.0, min(1.0, (event.position().x() - scrubber_x) / max(1.0, scrubber_w)))
            tl = self.chart.timeline
            target_pos = _scrubber_target_measure(ratio, tl)
            if self.playback_controller:
                self.playback_controller.seek(target_pos)
            else:
                self.current_pos = target_pos
            self.update()
            return
        super().mousePressEvent(event)

    def render_segment(
        self,
        painter: QPainter,
        x_left: int,
        segment_height: int,
        start_measure: int,
        chunk: int = 4,
    ) -> None:
        pass

    def export_to_image(
        self,
        file_path: str,
        measures_per_column: int = 8,
        png_quality: int | None = None,
        antialias: bool = True,
    ) -> bool:
        return False
