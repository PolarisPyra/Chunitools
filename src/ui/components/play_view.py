from __future__ import annotations

# ruff: noqa: PLR0913
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QElapsedTimer, QPointF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from src.core.const import AIR_NOTE_TYPES, NoteType
from src.engine.soflan import SoflanProjector
from src.ui.components.play_view_notes import PlayViewNotesMixin

LOGGER = logging.getLogger("ui.3dview")

if TYPE_CHECKING:
    from src.core.models import Chart
    from src.engine.playback import PlaybackController
    from src.notes import Note

from src.ui.components.util.play_view_geometry import (
    DEFAULT_SCROLL_SPEED,
    FIELD_FAR_Z,
    FIELD_HALF,
    FIELD_NEAR_Z,
    FONT_FAMILY,
    JUDGE_LINE_FAR_Z,
    JUDGE_LINE_NEAR_Z,
    JUDGE_OFFSET,
    LANE_LINE_FAR_Z,
    LANE_LINE_NEAR_Z,
    LANE_WIDTH,
    PIXELS_PER_SCROLL_SPEED,
    RENDER_CHART_AIR_HEIGHT_STEPS,
    REPAINT_INTERVAL_MS,
    VISIBLE_DEPTH,
    _air_trace_world_y_from_g0,
    _format_time,
    _project_point,
    _projection_for_depth,
    _scrubber_progress,
    _scrubber_target_measure,
    _visible_window,
    _world_depth,
)


class PlayView3D(PlayViewNotesMixin, QWidget):
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

        from src.ui.components.note_debug_overlay_3d import NoteDebugOverlay3D  # noqa: PLC0415

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

    def _draw_empty_state(self, painter: QPainter) -> None:
        painter.setPen(QColor(80, 80, 90))
        f = QFont(FONT_FAMILY, 14)
        painter.setFont(f)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "No chart loaded",
        )

    def _draw_playfield(self, painter: QPainter) -> None:
        w, h = self.width(), self.height()

        far_left = _project_point(-FIELD_HALF, 0.0, FIELD_FAR_Z, w, h)
        far_right = _project_point(FIELD_HALF, 0.0, FIELD_FAR_Z, w, h)
        near_left = _project_point(-FIELD_HALF, 0.0, FIELD_NEAR_Z, w, h)
        near_right = _project_point(FIELD_HALF, 0.0, FIELD_NEAR_Z, w, h)

        grad = QLinearGradient(0, far_left[1], 0, near_left[1])
        grad.setColorAt(0.0, QColor(16, 16, 22))
        grad.setColorAt(0.25, QColor(20, 22, 32))
        grad.setColorAt(0.7, QColor(26, 28, 38))
        grad.setColorAt(1.0, QColor(12, 14, 20))
        painter.fillRect(self.rect(), QBrush(grad))

        field_path = QColor(22, 24, 34, 140)
        painter.setBrush(field_path)
        painter.setPen(QPen(QColor(42, 44, 58), 1))
        poly = QPolygonF(
            [
                QPointF(*far_left),
                QPointF(*far_right),
                QPointF(*near_right),
                QPointF(*near_left),
            ]
        )
        painter.drawPolygon(poly)

    def _world_z_to_screen(
        self,
        world_z: float,
        vanish_y: float,
        judge_y: float,
    ) -> tuple[float, float, float]:
        """Project compact render depth through the recovered camera."""
        _ = vanish_y, judge_y
        return _projection_for_depth(world_z, self.width(), self.height())

    def _draw_lane_lines(self, painter: QPainter, judge_time: float) -> None:
        w, h = self.width(), self.height()
        _ = judge_time

        for lane in range(self.total_lanes + 1):
            line_x = -FIELD_HALF + LANE_WIDTH * lane
            x_near, y_near = _project_point(line_x, 0.0, LANE_LINE_NEAR_Z, w, h)
            x_far, y_far = _project_point(line_x, 0.0, LANE_LINE_FAR_Z, w, h)
            alpha = 50 if lane in (0, self.total_lanes) else 24
            painter.setPen(QPen(QColor(130, 140, 170, alpha), 1))
            painter.drawLine(
                int(x_far),
                int(y_far),
                int(x_near),
                int(y_near),
            )

        tick_count = 4
        for lane in range(0, self.total_lanes + 1, tick_count):
            line_x = -FIELD_HALF + LANE_WIDTH * lane
            x_near, y_near = _project_point(line_x, 0.0, LANE_LINE_NEAR_Z, w, h)
            x_far, y_far = _project_point(line_x, 0.0, LANE_LINE_FAR_Z, w, h)
            painter.setPen(QPen(QColor(170, 180, 210, 70), 1))
            painter.drawLine(
                int(x_far),
                int(y_far),
                int(x_near),
                int(y_near),
            )

        sub_count = 16
        for lane in range(0, self.total_lanes + 1, sub_count):
            line_x = -FIELD_HALF + LANE_WIDTH * lane
            x_near, y_near = _project_point(line_x, 0.0, LANE_LINE_NEAR_Z, w, h)
            x_far, y_far = _project_point(line_x, 0.0, LANE_LINE_FAR_Z, w, h)
            painter.setPen(QPen(QColor(210, 220, 250, 90), 1))
            painter.drawLine(
                int(x_far) - 1,
                int(y_far),
                int(x_near) + 1,
                int(y_near),
            )

    def _has_air_judge_line_notes(self) -> bool:
        return any(
            note.note_type in AIR_NOTE_TYPES
            and self.visible_note_types.get(note.note_type.value, True)
            for note in self._notes
        )

    def _draw_projected_judge_line(
        self,
        painter: QPainter,
        world_y: float,
        color: QColor,
        line_width: int = 1,
    ) -> None:
        w, h = self.width(), self.height()
        left_front = _project_point(-FIELD_HALF, world_y, JUDGE_LINE_NEAR_Z, w, h)
        right_front = _project_point(FIELD_HALF, world_y, JUDGE_LINE_NEAR_Z, w, h)
        left_back = _project_point(-FIELD_HALF, world_y, JUDGE_LINE_FAR_Z, w, h)
        judge_y = (left_front[1] + left_back[1]) / 2.0

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, line_width))
        painter.drawLine(
            QPointF(left_front[0], judge_y),
            QPointF(right_front[0], judge_y),
        )

    def _draw_judge_line(self, painter: QPainter) -> None:
        self._draw_projected_judge_line(
            painter,
            0.0,
            QColor(255, 215, 48, 235),
        )
        if self._has_air_judge_line_notes():
            self._draw_projected_judge_line(
                painter,
                _air_trace_world_y_from_g0(RENDER_CHART_AIR_HEIGHT_STEPS),
                QColor(64, 255, 96, 230),
            )

    def _draw_scrubber(self, painter: QPainter) -> None:
        if not self.chart:
            return

        w, h = self.width(), self.height()
        scrubber_h = 16
        scrubber_y = h - scrubber_h - 4
        margin = 8
        scrubber_x = margin
        scrubber_w = w - 2 * margin

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(30, 32, 44, 180))
        painter.drawRoundedRect(scrubber_x, scrubber_y, scrubber_w, scrubber_h, 4, 4)

        tl = self.chart.timeline
        progress, current_seconds, total_seconds = _scrubber_progress(self.current_pos, tl)
        if total_seconds <= 0:
            return

        fill_w = int(scrubber_w * progress)

        grad = QLinearGradient(scrubber_x, 0, scrubber_x + scrubber_w, 0)
        grad.setColorAt(0.0, QColor(80, 160, 220, 200))
        grad.setColorAt(1.0, QColor(100, 180, 240, 200))
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(scrubber_x, scrubber_y, fill_w, scrubber_h, 4, 4)

        painter.setPen(QPen(QColor(60, 64, 80), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(scrubber_x, scrubber_y, scrubber_w, scrubber_h, 4, 4)

        playhead_x = scrubber_x + fill_w
        painter.setPen(QPen(QColor(200, 230, 255, 220), 2))
        painter.drawLine(
            int(playhead_x),
            int(scrubber_y) - 2,
            int(playhead_x),
            int(scrubber_y) + scrubber_h + 2,
        )

        time_text = f"{_format_time(current_seconds)} / {_format_time(total_seconds)}"
        painter.setPen(QColor(160, 170, 190))
        f = QFont(FONT_FAMILY, 8)
        painter.setFont(f)
        painter.drawText(
            int(scrubber_x + 4),
            int(scrubber_y) + 12,
            time_text,
        )

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
