from __future__ import annotations

# ruff: noqa: PLR0913

import logging
import math
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

from src.core.const import AIR_NOTE_TYPES, NoteType, RenderRole
from src.engine.soflan import SoflanProjector
from src.notes import (
    AirSlideStart,
    Note,
    Slide,
    SlideTo,
)
from src.ui.theme.notes import TRACE_COLORS, get_note_color
from src.ui.view import timeline_compat

LOGGER = logging.getLogger("ui.3dview")

if TYPE_CHECKING:
    from src.core.models import Chart
    from src.engine.playback import PlaybackController
    from src.engine.timeline import ChartTimeline


# World-space coordinate system.
# Ghidra ScoreReader evidence accepts chart cells from -16 through 32, and
# the renderer maps the visible 16-lane playfield to -512..512.
WORLD_WIDTH = 32.0      # 16 lanes x 2 units/lane
WORLD_HALF = 16.0
LANE_UNITS = 2.0
PIXELS_PER_UNIT = 32.0  # screen pixels per world unit
FIELD_WIDTH = int(WORLD_WIDTH * PIXELS_PER_UNIT)  # 1024
HALF_WIDTH = int(FIELD_WIDTH / 2)                  # 512
LANE_WIDTH = int(LANE_UNITS * PIXELS_PER_UNIT)     # 64

# Widget depth is a compact equivalent of the normalized render depth.
VISIBLE_DEPTH = 20.0     # world units from judge to vanish plane

# Tap quads are full lane-span quads:
# x0 = 64 * lane - 512; x1 = x0 + 64 * width.
NOTE_WIDTH_FRAC = 1.0
GLOW_FRAC = 0.12
RENDER_NOTE_DEPTH = 108.56
RENDER_BIG_NOTE_DEPTH = 118.0 * 1.13
RENDER_AIR_HEIGHT = 233.0
RENDER_AIR_TRACE_HEIGHT = 466.0
RENDER_CHART_AIR_HEIGHT_MIN = 1.0
RENDER_CHART_AIR_HEIGHT_RANGE = 4.0
RENDER_CHART_AIR_HEIGHT_STEPS = 8.0
RENDER_AIR_TRACE_WIDTH_HEIGHT_SLOPE = -0.25
AIR_ARROW_WIDTH_SCALE = 1.25
AIR_ARROW_HEIGHT_SCALE = 72.0
AIR_ARROW_ANCHOR_OFFSET = 5.0
RENDER_WIDTH_SCALE = (
    0.0, 0.4, 0.5, 0.63, 0.69, 0.7, 0.7, 0.73, 0.75,
    0.765, 0.78, 0.795, 0.81, 0.825, 0.84, 0.855, 0.87,
)
RENDER_MIN_AIR_PATH_WIDTH_SCALE = 0.734375

JUDGE_OFFSET = 0.0
DEFAULT_SCROLL_SPEED = 9.0
VISIBLE_WINDOW_FACTOR = 7.0
PIXELS_PER_SCROLL_SPEED = timeline_compat.MEASURE_HEIGHT

# Normalized visibility ranges converted to this widget's world-depth units.
RENDER_ACTIVE_DEPTH_MIN_FRAC = -0.25
RENDER_ACTIVE_DEPTH_MAX_FRAC = 0.84
RENDER_DRAW_DEPTH_MIN_FRAC = -0.0625
RENDER_DRAW_DEPTH_MAX_FRAC = 0.84
ACTIVE_DEPTH_MIN = VISIBLE_DEPTH * RENDER_ACTIVE_DEPTH_MIN_FRAC
ACTIVE_DEPTH_MAX = VISIBLE_DEPTH * RENDER_ACTIVE_DEPTH_MAX_FRAC
DRAW_DEPTH_MIN = VISIBLE_DEPTH * RENDER_DRAW_DEPTH_MIN_FRAC
DRAW_DEPTH_MAX = VISIBLE_DEPTH * RENDER_DRAW_DEPTH_MAX_FRAC

FIELD_HALF = 512.0
FIELD_DEPTH = 5120.0
FIELD_NEAR_Z = 200.0
FIELD_FAR_Z = -FIELD_DEPTH
LANE_LINE_NEAR_Z = FIELD_NEAR_Z
LANE_LINE_FAR_Z = FIELD_FAR_Z
JUDGE_LINE_NEAR_Z = -30.0
JUDGE_LINE_FAR_Z = 30.0

FOV_DEGREES = 45.0
MODEL_TRANSLATE_Z = -6.0
CAMERA_EYE = (0.0, 850.0, 850.0)
CAMERA_TARGET = (0.0, -290.0, -1536.0)
CAMERA_UP = (0.0, 1.0, 0.0)

TARGET_FPS = 60
REPAINT_INTERVAL_MS = max(1, round(1000 / TARGET_FPS))

FONT_FAMILY = "Segoe UI, Arial, sans-serif"


def _subtract3(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _dot3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross3(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _normalize3(v: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(_dot3(v, v))
    if length <= 0:
        return 0.0, 0.0, 0.0
    return v[0] / length, v[1] / length, v[2] / length


_CAMERA_FORWARD = _normalize3(_subtract3(CAMERA_TARGET, CAMERA_EYE))
_CAMERA_SIDE = _normalize3(_cross3(_CAMERA_FORWARD, CAMERA_UP))
_CAMERA_UP_VECTOR = _cross3(_CAMERA_SIDE, _CAMERA_FORWARD)


def _visible_window(render_speed: float) -> float:
    if render_speed <= 10:
        return VISIBLE_WINDOW_FACTOR / render_speed
    return VISIBLE_WINDOW_FACTOR / (
        (render_speed - 10) * (render_speed - 10) + 10
    )


def _world_depth(note_time_s: float, judge_time_s: float, window_s: float) -> float:
    if window_s < 0.001:
        return 0.0
    depth_frac = (note_time_s - judge_time_s) / window_s
    return depth_frac * VISIBLE_DEPTH


def _compact_depth_to_z(depth: float) -> float:
    return -(depth / VISIBLE_DEPTH) * FIELD_DEPTH


def _camera_space(
    x: float, y: float, z: float
) -> tuple[float, float, float]:
    translated = (
        x,
        y,
        z + MODEL_TRANSLATE_Z,
    )
    delta = _subtract3(translated, CAMERA_EYE)
    return (
        _dot3(_CAMERA_SIDE, delta),
        _dot3(_CAMERA_UP_VECTOR, delta),
        _dot3((-_CAMERA_FORWARD[0], -_CAMERA_FORWARD[1], -_CAMERA_FORWARD[2]), delta),
    )


def _project_point(
    x: float, y: float, z: float, viewport_w: float, viewport_h: float
) -> tuple[float, float]:
    if viewport_w <= 0 or viewport_h <= 0:
        return 0.0, 0.0

    cam_x, cam_y, cam_z = _camera_space(x, y, z)
    if cam_z >= -0.001:
        cam_z = -0.001

    focal = 1.0 / math.tan(math.radians(FOV_DEGREES) / 2.0)
    aspect = viewport_w / viewport_h
    ndc_x = (focal / aspect) * cam_x / -cam_z
    ndc_y = focal * cam_y / -cam_z
    return (
        (ndc_x + 1.0) * viewport_w / 2.0,
        (1.0 - ndc_y) * viewport_h / 2.0,
    )


def _projection_for_depth(
    depth: float, viewport_w: float, viewport_h: float
) -> tuple[float, float, float]:
    z = _compact_depth_to_z(depth)
    x0, screen_y = _project_point(0.0, 0.0, z, viewport_w, viewport_h)
    x1, _ = _project_point(1.0, 0.0, z, viewport_w, viewport_h)
    scale = abs(x1 - x0)
    t = min(1.0, max(-1.0, depth / VISIBLE_DEPTH))
    return scale, screen_y, t


def _projected_note_height(
    depth: float, viewport_w: float, viewport_h: float, *, big: bool = False
) -> float:
    z = _compact_depth_to_z(depth)
    half_depth = (RENDER_BIG_NOTE_DEPTH if big else RENDER_NOTE_DEPTH) / 2.0
    _, y0 = _project_point(0.0, 0.0, z - half_depth, viewport_w, viewport_h)
    _, y1 = _project_point(0.0, 0.0, z + half_depth, viewport_w, viewport_h)
    return abs(y1 - y0)


def _chart_air_height_to_g0(height: float) -> float:
    return (
        (height - RENDER_CHART_AIR_HEIGHT_MIN)
        / RENDER_CHART_AIR_HEIGHT_RANGE
        * RENDER_CHART_AIR_HEIGHT_STEPS
    )


def _air_action_world_y_from_g0(g0: float) -> float:
    return (g0 / 16.0) * 2.0 * RENDER_AIR_HEIGHT - RENDER_AIR_HEIGHT


def _air_trace_world_y_from_g0(g0: float) -> float:
    return (RENDER_AIR_TRACE_HEIGHT * g0) / 16.0


def _air_trace_width_factor_from_g0(g0: float) -> float:
    return max(0.0, RENDER_AIR_TRACE_WIDTH_HEIGHT_SLOPE * (g0 / 16.0) + 1.0)


def _air_trace_width_factor_from_world_y(world_y: float | None) -> float:
    if world_y is None:
        return 1.0
    g0 = world_y / RENDER_AIR_TRACE_HEIGHT * 16.0
    return _air_trace_width_factor_from_g0(g0)


def _air_action_world_y_from_chart_height(height: float) -> float:
    return _air_action_world_y_from_g0(_chart_air_height_to_g0(height))


def _air_path_source(note: Note, *, end: bool) -> Note:
    if isinstance(note, AirSlideStart) and note.steps:
        return note.steps[-1] if end else note.steps[0]
    return note


def _air_path_world_y(note: Note, *, end: bool = False) -> float | None:
    source = _air_path_source(note, end=end)
    attr = "target_height" if end else "starting_height"
    if hasattr(source, attr):
        g0 = _chart_air_height_to_g0(float(getattr(source, attr)))
        return _air_trace_world_y_from_g0(g0)
    if note.note_type in (NoteType.AHD, NoteType.AHX):
        g0 = 4.0
        return _air_trace_world_y_from_g0(g0)
    # Air arrows (AIR, AUR, AUL, ADW, ADR, ADL) use the minimum air height
    if note.note_type in {NoteType.AIR, NoteType.AUR, NoteType.AUL,
                          NoteType.ADW, NoteType.ADR, NoteType.ADL}:
        g0 = _chart_air_height_to_g0(RENDER_CHART_AIR_HEIGHT_MIN)
        return _air_trace_world_y_from_g0(g0)
    return None


def _air_action_marker_world_y(note: Note, *, end: bool = False) -> float | None:
    source = _air_path_source(note, end=end)
    attr = "target_height" if end else "starting_height"
    if hasattr(source, attr):
        return _air_action_world_y_from_chart_height(float(getattr(source, attr)))
    return None


def _note_screen_span(
    cell: float, width: float, vanish_x: float, scale: float
) -> tuple[float, float]:
    lane_x = vanish_x + ((cell * LANE_UNITS) - WORLD_HALF) * PIXELS_PER_UNIT * scale
    lane_w = LANE_UNITS * width * PIXELS_PER_UNIT * scale
    note_w = lane_w * NOTE_WIDTH_FRAC
    return lane_x + (lane_w - note_w) / 2.0, note_w


def _lerp(start: float, end: float, alpha: float) -> float:
    return start + (end - start) * alpha


def _has_sustain(note: Note) -> bool:
    return getattr(note, "duration", 0) > 0


def _depth_in_draw_range(depth: float) -> bool:
    return DRAW_DEPTH_MIN < depth < DRAW_DEPTH_MAX


def _sustain_draw_depths(
    start_depth: float, end_depth: float
) -> tuple[float, float] | None:
    if max(start_depth, end_depth) <= DRAW_DEPTH_MIN:
        return None
    if min(start_depth, end_depth) >= DRAW_DEPTH_MAX:
        return None

    draw_start = start_depth
    draw_end = end_depth
    if start_depth < 0.0 < end_depth:
        draw_start = 0.0
    elif end_depth < 0.0 < start_depth:
        draw_end = 0.0
    if start_depth < DRAW_DEPTH_MAX < end_depth:
        draw_end = DRAW_DEPTH_MAX
    elif end_depth < DRAW_DEPTH_MAX < start_depth:
        draw_start = DRAW_DEPTH_MAX
    return draw_start, draw_end


def _clip_sustain_start(
    start_cell: float,
    start_width: float,
    start_depth: float,
    end_cell: float,
    end_width: float,
    end_depth: float,
) -> tuple[float, float, float]:
    if start_depth < 0.0 < end_depth:
        alpha = (0.0 - start_depth) / (end_depth - start_depth)
        return (
            _lerp(start_cell, end_cell, alpha),
            _lerp(start_width, end_width, alpha),
            0.0,
        )
    return start_cell, start_width, start_depth


def _clip_air_path_start(
    start_cell: float,
    start_width: float,
    start_world_y: float | None,
    start_depth: float,
    end_cell: float,
    end_width: float,
    end_world_y: float | None,
    end_depth: float,
) -> tuple[float, float, float | None, float]:
    if start_depth < 0.0 < end_depth:
        alpha = (0.0 - start_depth) / (end_depth - start_depth)
        world_y = start_world_y
        if start_world_y is not None and end_world_y is not None:
            world_y = _lerp(start_world_y, end_world_y, alpha)
        return (
            _lerp(start_cell, end_cell, alpha),
            _lerp(start_width, end_width, alpha),
            world_y,
            0.0,
        )
    return start_cell, start_width, start_world_y, start_depth


def _render_width_scale(width: float) -> float:
    index = int(round(width))
    if 0 <= index < len(RENDER_WIDTH_SCALE):
        return RENDER_WIDTH_SCALE[index]
    return RENDER_MIN_AIR_PATH_WIDTH_SCALE


def _air_arrow_screen_span(
    cell: float, width: float, vanish_x: float, scale: float
) -> tuple[float, float]:
    _, lane_w = _note_screen_span(cell, width, vanish_x, scale)
    visual_w = lane_w * _render_width_scale(width)
    center_x = vanish_x + (
        ((cell + width / 2.0) * LANE_UNITS) - WORLD_HALF
    ) * PIXELS_PER_UNIT * scale
    return center_x - visual_w / 2.0, visual_w


def _air_path_screen_span(
    cell: float, width: float, vanish_x: float, scale: float
) -> tuple[float, float]:
    _, lane_w = _note_screen_span(cell, width, vanish_x, scale)
    visual_w = lane_w * max(
        _render_width_scale(width), RENDER_MIN_AIR_PATH_WIDTH_SCALE
    )
    center_x = vanish_x + (
        ((cell + width / 2.0) * LANE_UNITS) - WORLD_HALF
    ) * PIXELS_PER_UNIT * scale
    return center_x - visual_w / 2.0, visual_w


def _scaled_span_width(x: float, width: float, factor: float) -> tuple[float, float]:
    visual_w = width * factor
    return x + (width - visual_w) / 2.0, visual_w


def _scrubber_progress(
    current_pos: float, timeline: ChartTimeline
) -> tuple[float, float, float]:
    total_seconds = timeline.time_at_measure(timeline.calculate_max_measure())
    current_seconds = timeline.time_at_measure(current_pos)
    if total_seconds <= 0:
        return 0.0, current_seconds, total_seconds
    progress = min(1.0, max(0.0, current_seconds / total_seconds))
    return progress, current_seconds, total_seconds


def _scrubber_target_measure(ratio: float, timeline: ChartTimeline) -> float:
    total_seconds = timeline.time_at_measure(timeline.calculate_max_measure())
    target_seconds = max(0.0, min(1.0, ratio)) * total_seconds
    return timeline.pos_at_time(target_seconds)


class PlayView3D(QWidget):
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
                self._max_scroll_measure = float(
                    self.chart.timeline.calculate_max_measure() + 3
                )
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

        far_left = _project_point(
            -FIELD_HALF, 0.0, FIELD_FAR_Z, w, h
        )
        far_right = _project_point(
            FIELD_HALF, 0.0, FIELD_FAR_Z, w, h
        )
        near_left = _project_point(
            -FIELD_HALF, 0.0, FIELD_NEAR_Z, w, h
        )
        near_right = _project_point(
            FIELD_HALF, 0.0, FIELD_NEAR_Z, w, h
        )

        grad = QLinearGradient(0, far_left[1], 0, near_left[1])
        grad.setColorAt(0.0, QColor(16, 16, 22))
        grad.setColorAt(0.25, QColor(20, 22, 32))
        grad.setColorAt(0.7, QColor(26, 28, 38))
        grad.setColorAt(1.0, QColor(12, 14, 20))
        painter.fillRect(self.rect(), QBrush(grad))

        field_path = QColor(22, 24, 34, 140)
        painter.setBrush(field_path)
        painter.setPen(QPen(QColor(42, 44, 58), 1))
        poly = QPolygonF([
            QPointF(*far_left),
            QPointF(*far_right),
            QPointF(*near_right),
            QPointF(*near_left),
        ])
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

    def _air_path_screen_y(
        self, note: Note, depth: float, *, end: bool = False
    ) -> float | None:
        world_y = _air_path_world_y(note, end=end)
        if world_y is None:
            return None
        _, screen_y = _project_point(
            0.0,
            world_y,
            _compact_depth_to_z(depth),
            self.width(),
            self.height(),
        )
        return screen_y

    def _air_path_screen_span_at(
        self,
        cell: float,
        width: float,
        depth: float,
        world_y: float | None,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> tuple[float, float, float, float]:
        scale, screen_y, _ = self._world_z_to_screen(depth, vanish_y, judge_y)
        if world_y is not None:
            _, screen_y = _project_point(
                0.0,
                world_y,
                _compact_depth_to_z(depth),
                self.width(),
                self.height(),
            )
        screen_x, screen_w = _air_path_screen_span(cell, width, vanish_x, scale)
        return screen_x, screen_y, screen_w, scale

    def _air_action_screen_span_at(
        self,
        cell: float,
        width: float,
        depth: float,
        world_y: float | None,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> tuple[float, float, float, float]:
        return self._air_path_screen_span_at(
            cell, width, depth, world_y, vanish_x, vanish_y, judge_y
        )

    def _air_trace_screen_span_at(
        self,
        cell: float,
        width: float,
        depth: float,
        world_y: float | None,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> tuple[float, float, float, float]:
        screen_x, screen_y, screen_w, scale = self._air_path_screen_span_at(
            cell, width, depth, world_y, vanish_x, vanish_y, judge_y
        )
        trace_x, trace_w = _scaled_span_width(
            screen_x, screen_w, _air_trace_width_factor_from_world_y(world_y)
        )
        return trace_x, screen_y, trace_w, scale

    def _air_arrow_screen_span_at_anchor(
        self,
        note: Note,
        vanish_x: float,
        scale: float,
    ) -> tuple[float, float]:
        timeline = self.chart.timeline if self.chart else None
        if not timeline:
            return _air_arrow_screen_span(note.cell, note.width, vanish_x, scale)

        anchor = timeline.note_anchor(note)
        if not anchor:
            return _air_arrow_screen_span(note.cell, note.width, vanish_x, scale)

        tick = timeline.note_tick(note)
        anchor_end_tick = timeline.note_end_tick(anchor)
        if tick == anchor_end_tick and anchor_end_tick != timeline.note_tick(anchor):
            cell = getattr(anchor, "end_cell", anchor.cell)
            width = getattr(anchor, "end_width", anchor.width)
        else:
            span = timeline.span_at(anchor, tick)
            if span is None:
                cell, width = anchor.cell, anchor.width
            else:
                cell, width = span

        return _air_arrow_screen_span(cell, width, vanish_x, scale)

    def _air_anchor_for_note(self, note: Note) -> tuple[Note, bool] | None:
        timeline = self.chart.timeline if self.chart else None
        anchor = timeline.note_anchor(note) if timeline else getattr(note, "parent", None)
        if anchor is None:
            return None

        end = False
        if timeline:
            tick = timeline.note_tick(note)
            anchor_start = timeline.note_tick(anchor)
            anchor_end = timeline.note_end_tick(anchor)
            end = tick == anchor_end and anchor_end != anchor_start

        return anchor, end

    def _air_wrapped_start_world_y(self, note: Note) -> float | None:
        return _air_path_world_y(note)

    def _air_anchor_world_y(self, note: Note) -> float | None:
        anchor_info = self._air_anchor_for_note(note)
        if anchor_info is None:
            if note.note_type == NoteType.AHX:
                return 0.0
            return None
        anchor, end = anchor_info
        anchor_world_y = _air_path_world_y(anchor, end=end)
        if anchor_world_y is None:
            return 0.0
        return anchor_world_y

    def _air_anchor_screen_y(
        self,
        note: Note,
        depth: float,
        vanish_y: float,
        judge_y: float,
    ) -> float | None:
        anchor_info = self._air_anchor_for_note(note)
        if anchor_info is None:
            world_y = self._air_anchor_world_y(note)
            if world_y is None:
                return None
        else:
            anchor, end = anchor_info
            world_y = _air_path_world_y(anchor, end=end)
            if world_y is None:
                # Anchor is ground-level (TAP, CHR, etc.) — use default air height
                g0 = _chart_air_height_to_g0(RENDER_CHART_AIR_HEIGHT_MIN)
                world_y = _air_trace_world_y_from_g0(g0)

        _, screen_y = _project_point(
            0.0,
            world_y,
            _compact_depth_to_z(depth),
            self.width(),
            self.height(),
        )
        return screen_y

    def _draw_air_lift_if_needed(
        self,
        painter: QPainter,
        note: Note,
        cell: float,
        width: float,
        depth: float,
        path_world_y: float | None,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
        color: QColor,
        alpha: int,
    ) -> None:
        if not _depth_in_draw_range(depth) or path_world_y is None:
            return
        anchor_world_y = self._air_anchor_world_y(note)
        if anchor_world_y is None or abs(anchor_world_y - path_world_y) < 1.0:
            return

        x, y_top, w, scale = self._air_path_screen_span_at(
            cell, width, depth, path_world_y, vanish_x, vanish_y, judge_y
        )
        _, y_bottom, _, _ = self._air_path_screen_span_at(
            cell, width, depth, anchor_world_y, vanish_x, vanish_y, judge_y
        )
        overlap = max(3.0, scale * 6.0)
        y_top_overlapped = y_top - overlap if y_bottom > y_top else y_top + overlap
        self._draw_air_lift_connector(
            painter, x, y_bottom, y_top_overlapped, w, scale, color, alpha
        )

    def _draw_lane_lines(self, painter: QPainter, judge_time: float) -> None:
        w, h = self.width(), self.height()
        _ = judge_time

        for lane in range(self.total_lanes + 1):
            line_x = -FIELD_HALF + LANE_WIDTH * lane
            x_near, y_near = _project_point(
                line_x, 0.0, LANE_LINE_NEAR_Z, w, h
            )
            x_far, y_far = _project_point(
                line_x, 0.0, LANE_LINE_FAR_Z, w, h
            )
            alpha = 50 if lane == 0 or lane == self.total_lanes else 24
            painter.setPen(QPen(QColor(130, 140, 170, alpha), 1))
            painter.drawLine(
                int(x_far), int(y_far),
                int(x_near), int(y_near),
            )

        tick_count = 4
        for lane in range(0, self.total_lanes + 1, tick_count):
            line_x = -FIELD_HALF + LANE_WIDTH * lane
            x_near, y_near = _project_point(
                line_x, 0.0, LANE_LINE_NEAR_Z, w, h
            )
            x_far, y_far = _project_point(
                line_x, 0.0, LANE_LINE_FAR_Z, w, h
            )
            painter.setPen(QPen(QColor(170, 180, 210, 70), 1))
            painter.drawLine(
                int(x_far), int(y_far),
                int(x_near), int(y_near),
            )

        sub_count = 16
        for lane in range(0, self.total_lanes + 1, sub_count):
            line_x = -FIELD_HALF + LANE_WIDTH * lane
            x_near, y_near = _project_point(
                line_x, 0.0, LANE_LINE_NEAR_Z, w, h
            )
            x_far, y_far = _project_point(
                line_x, 0.0, LANE_LINE_FAR_Z, w, h
            )
            painter.setPen(QPen(QColor(210, 220, 250, 90), 1))
            painter.drawLine(
                int(x_far) - 1, int(y_far),
                int(x_near) + 1, int(y_near),
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
        left_front = _project_point(
            -FIELD_HALF, world_y, JUDGE_LINE_NEAR_Z, w, h
        )
        right_front = _project_point(
            FIELD_HALF, world_y, JUDGE_LINE_NEAR_Z, w, h
        )
        left_back = _project_point(
            -FIELD_HALF, world_y, JUDGE_LINE_FAR_Z, w, h
        )
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

    def _get_note_color(self, note: Note) -> QColor:
        if note.note_type == NoteType.ALD:
            color_code = getattr(note, "color", "DEF")
            return QColor(TRACE_COLORS.get(color_code, "#b4b4c8"))

        return get_note_color(note.note_type)

    def _draw_notes(self, painter: QPainter, judge_time: float) -> None:  # noqa: PLR0912
        w, h = self.width(), self.height()
        vanish_x = w / 2.0
        vanish_y = h * 0.10
        judge_y = h * 0.90

        if not self.chart:
            return
        visible_notes = []
        tl = self.chart.timeline
        for note in self._notes:
            if not self.visible_note_types.get(note.note_type.value, True):
                continue
            note_time = self._note_times.get(id(note), 0.0)
            end_time = self._note_end_times.get(id(note), note_time)
            depth = self._compute_note_depth(
                note, tl.note_tick(note), note_time, judge_time
            )
            end_depth = self._compute_note_depth(
                note, tl.note_end_tick(note), end_time, judge_time
            )

            if _has_sustain(note):
                if _sustain_draw_depths(depth, end_depth) is None:
                    continue
            else:
                if depth > ACTIVE_DEPTH_MAX:
                    continue
                if depth < ACTIVE_DEPTH_MIN:
                    continue

            visible_notes.append((note, depth, end_depth))

        visible_notes.sort(key=lambda x: x[1], reverse=True)

        self._deferred_air_arrows.clear()
        self._defer_air_arrows = True
        try:
            for note, depth, end_depth in visible_notes:
                if _has_sustain(note):
                    if _sustain_draw_depths(depth, end_depth) is None:
                        continue
                else:
                    if depth >= DRAW_DEPTH_MAX:
                        continue
                    if depth <= DRAW_DEPTH_MIN:
                        continue

                scale, screen_y, t = self._world_z_to_screen(
                    depth, vanish_y, judge_y
                )
                lane_x, note_w = _note_screen_span(note.cell, note.width, vanish_x, scale)
                if note_w < 2:
                    continue

                alpha = max(30, int(255 * (1.0 - abs(t) * 0.5)))

                self._draw_note(
                    painter,
                    note,
                    lane_x,
                    screen_y,
                    note_w,
                    scale,
                    alpha,
                    judge_time,
                    depth,
                    end_depth,
                    vanish_x,
                    vanish_y,
                    judge_y,
                )
        finally:
            self._defer_air_arrows = False

        for payload in self._deferred_air_arrows:
            self._draw_air_arrow_for_note(painter, *payload)
        self._deferred_air_arrows.clear()

    def _draw_note(  # noqa: PLR0912
        self,
        painter: QPainter,
        note: Note,
        x: float,
        y: float,
        w: float,
        scale: float,
        alpha: int,
        judge_time: float,
        depth: float,
        end_depth: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> None:
        nt = note.note_type
        color = self._get_note_color(note)
        color.setAlpha(alpha)

        has_duration = hasattr(note, "duration") and getattr(note, "duration", 0) > 0
        is_air_arrow = nt in {
            NoteType.AIR,
            NoteType.AUR,
            NoteType.AUL,
            NoteType.ADW,
            NoteType.ADR,
            NoteType.ADL,
        }

        air_y = self._air_path_screen_y(note, depth)
        if air_y is not None:
            y = air_y

        if is_air_arrow:
            x, w = self._air_arrow_screen_span_at_anchor(
                note, vanish_x, scale
            )
        elif nt in {
            NoteType.AHD,
            NoteType.AHX,
            NoteType.ALD,
            NoteType.ASD,
            NoteType.ASC,
            NoteType.ASO,
            NoteType.HHD,
            NoteType.HHX,
        }:
            x, w = _air_path_screen_span(note.cell, note.width, vanish_x, scale)

        if nt == NoteType.TAP:
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, depth)
        elif nt == NoteType.CHR:
            self._draw_extap_quad(painter, x, y, w, scale, color, alpha, note, depth)
        elif nt == NoteType.FLK:
            self._draw_flick(painter, x, y, w, scale, color, alpha, note, depth)
        elif nt == NoteType.MNE:
            self._draw_mine(painter, x, y, w, scale, color, alpha)
        elif nt == NoteType.AHD:
            self._draw_air_hold_segment(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
                is_start=True,
            )
        elif nt == NoteType.AHX:
            sustain_color = get_note_color(NoteType.AHD)
            sustain_color.setAlpha(alpha)
            self._draw_air_hold_segment(
                painter,
                note,
                x,
                y,
                w,
                scale,
                sustain_color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
                is_start=True,
            )
        elif nt in {NoteType.HLD, NoteType.HXD}:
            if has_duration:
                self._draw_hold(
                    painter, note, x, y, w, scale, color, alpha, judge_time,
                    depth, end_depth, vanish_x, vanish_y, judge_y
                )
            else:
                self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, depth)
        elif nt in {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC}:
            self._draw_slide(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        elif is_air_arrow:
            self._draw_or_defer_air_arrow(
                painter,
                note,
                x,
                y,
                w,
                scale,
                alpha,
                nt,
                depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        elif nt in {NoteType.ASD, NoteType.ASC}:
            self._draw_air_slide(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        elif nt == NoteType.ALD:
            self._draw_air_trace(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        elif nt == NoteType.ASO:
            self._draw_air_solid(
                painter, note, x, y, w, scale, color, alpha, judge_time,
                depth, end_depth, vanish_x, vanish_y, judge_y
            )
        elif nt in {NoteType.HHD, NoteType.HHX}:
            self._draw_heaven_hold(
                painter,
                note,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                judge_time,
                depth,
                end_depth,
                vanish_x,
                vanish_y,
                judge_y,
            )
        else:
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, depth)

    def _get_world_y(self, note: Note) -> float:
        wy = _air_path_world_y(note)
        return wy if wy is not None else 0.0

    def _project_flat_note_corners(
        self, note: Note, cell: float, width: float, depth: float
    ) -> list[QPointF]:
        w, h = self.width(), self.height()
        wy = self._get_world_y(note)
        w_x0 = cell * LANE_WIDTH - FIELD_HALF
        w_x1 = (cell + width) * LANE_WIDTH - FIELD_HALF
        z = _compact_depth_to_z(depth)
        is_big = note.note_type in {NoteType.HLD, NoteType.HXD, NoteType.SLD, NoteType.SXD}
        half_depth = (RENDER_BIG_NOTE_DEPTH if is_big else RENDER_NOTE_DEPTH) / 2.0
        z_far = z - half_depth
        z_near = z + half_depth
        pt0 = _project_point(w_x0, wy, z_far, w, h)
        pt1 = _project_point(w_x1, wy, z_far, w, h)
        pt2 = _project_point(w_x1, wy, z_near, w, h)
        pt3 = _project_point(w_x0, wy, z_near, w, h)
        return [QPointF(*pt0), QPointF(*pt1), QPointF(*pt2), QPointF(*pt3)]

    def _draw_flat_note_quad(
        self, painter: QPainter, cell: float, width: float, depth: float,
        color: QColor, alpha: int, note: Note, is_extap: bool = False,
    ) -> list[QPointF]:
        corners = self._project_flat_note_corners(note, cell, width, depth)
        if not all(math.isfinite(pt.x()) and math.isfinite(pt.y()) for pt in corners):
            return corners
        poly = QPolygonF(corners)
        scale = _projection_for_depth(depth, self.width(), self.height())[0]

        if is_extap:
            gold = QColor(255, 215, 0, alpha)
            painter.setPen(QPen(QColor(255, 240, 150, alpha), max(1, int(scale * 2))))
            painter.setBrush(gold)
            painter.drawPolygon(poly)

            left_mid = (corners[0] + corners[3]) * 0.5
            right_mid = (corners[1] + corners[2]) * 0.5
            painter.setPen(QPen(QColor(255, 255, 200, alpha // 2), 1))
            painter.drawLine(left_mid, right_mid)
        else:
            paint_alpha = QColor(color.red(), color.green(), color.blue(), alpha)
            painter.setPen(QPen(color.darker(130), max(1, int(scale * 2))))
            painter.setBrush(paint_alpha)
            painter.drawPolygon(poly)

            glow = QColor(color.red(), color.green(), color.blue(), alpha // 4)
            painter.setPen(QPen(glow, max(2, int(scale * 3))))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(poly)

        return corners

    def _draw_tap_quad(
        self, painter: QPainter, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, note: Note, depth: float,
        cell: float | None = None, width: float | None = None,
    ) -> None:
        if not _depth_in_draw_range(depth):
            return
        c_val = cell if cell is not None else float(note.cell)
        w_val = width if width is not None else float(note.width)
        self._draw_flat_note_quad(painter, c_val, w_val, depth, color, alpha, note, is_extap=False)

    def _draw_extap_quad(
        self, painter: QPainter, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, note: Note, depth: float,
        cell: float | None = None, width: float | None = None,
    ) -> None:
        if not _depth_in_draw_range(depth):
            return
        c_val = cell if cell is not None else float(note.cell)
        w_val = width if width is not None else float(note.width)
        self._draw_flat_note_quad(painter, c_val, w_val, depth, color, alpha, note, is_extap=True)

    def _draw_mine(
        self, painter: QPainter, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int,
    ) -> None:
        r = max(2, int(w * 0.35))
        cx, cy = int(x + w / 2), int(y)
        painter.setPen(QPen(QColor(200, 60, 60, alpha), max(1, int(scale * 2))))
        painter.setBrush(QColor(100, 20, 20, alpha))
        painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        painter.setPen(QPen(QColor(255, 100, 100, alpha), max(1, int(scale * 1.5))))
        painter.drawLine(cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2)
        painter.drawLine(cx + r // 2, cy - r // 2, cx - r // 2, cy + r // 2)

    def _draw_flick(
        self, painter: QPainter, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, note: Note, depth: float,
        cell: float | None = None, width: float | None = None,
    ) -> None:
        if not _depth_in_draw_range(depth):
            return
        c_val = cell if cell is not None else float(note.cell)
        w_val = width if width is not None else float(note.width)
        corners = self._project_flat_note_corners(note, c_val, w_val, depth)
        poly = QPolygonF(corners)

        painter.setPen(QPen(color.lighter(130), max(1, int(scale * 2))))
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), alpha))
        painter.drawPolygon(poly)

        left_mid = (corners[0] + corners[3]) * 0.5
        right_mid = (corners[1] + corners[2]) * 0.5
        center = (left_mid + right_mid) * 0.5

        painter.setPen(QPen(QColor(255, 255, 255, alpha), max(1, int(scale * 1.5))))
        dx = 3 * scale
        dy = 4 * scale
        painter.drawLine(
            QPointF(center.x() - dx, center.y() - dy),
            QPointF(center.x() + dx, center.y()),
        )
        painter.drawLine(
            QPointF(center.x() - dx, center.y() + dy),
            QPointF(center.x() + dx, center.y()),
        )

    def _draw_hold(
        self, painter: QPainter, note: Note, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, judge_time: float,
        depth: float, end_depth: float, vanish_x: float, vanish_y: float, judge_y: float,
    ) -> None:
        draw_depths = _sustain_draw_depths(depth, end_depth)
        if draw_depths is None:
            return
        draw_depth, draw_end_depth = draw_depths
        if draw_depth != depth:
            scale, y, _ = self._world_z_to_screen(draw_depth, vanish_y, judge_y)
            x, w = _note_screen_span(note.cell, note.width, vanish_x, scale)

        end_scale, end_y, _ = self._world_z_to_screen(
            draw_end_depth, vanish_y, judge_y
        )
        end_x, end_w = _note_screen_span(note.cell, note.width, vanish_x, end_scale)

        self._draw_sustain_body(
            painter, x, y, w, end_x, end_y, end_w,
            color, alpha, scale, end_scale,
        )

        if _depth_in_draw_range(depth):
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, draw_depth)
        if _depth_in_draw_range(draw_end_depth):
            end_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
            self._draw_tap_quad(
                painter, end_x, end_y, end_w, end_scale, end_color, alpha // 2,
                note, draw_end_depth
            )

    def _draw_slide(
        self, painter: QPainter, note: Note, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, judge_time: float,
        depth: float, end_depth: float, vanish_x: float, vanish_y: float, judge_y: float,
    ) -> None:
        if isinstance(note, Slide) and note.steps:
            self._draw_slide_steps(painter, note, x, y, w, scale, color, alpha, judge_time,
                                   depth, vanish_x, vanish_y, judge_y)
        elif isinstance(note, SlideTo):
            draw_depths = _sustain_draw_depths(depth, end_depth)
            if draw_depths is None:
                return
            draw_depth, draw_end_depth = draw_depths
            start_cell, start_width, draw_depth = _clip_sustain_start(
                note.cell,
                note.width,
                depth,
                note.end_cell,
                note.end_width,
                end_depth,
            )
            if draw_depth != depth:
                scale, y, _ = self._world_z_to_screen(draw_depth, vanish_y, judge_y)
                x, w = _note_screen_span(start_cell, start_width, vanish_x, scale)

            end_scale, end_y, _ = self._world_z_to_screen(
                draw_end_depth, vanish_y, judge_y
            )
            end_x, end_w = _note_screen_span(
                note.end_cell, note.end_width, vanish_x, end_scale
            )

            self._draw_sustain_body(
                painter, x, y, w, end_x, end_y, end_w,
                color, alpha, scale, end_scale,
                is_slide=True,
            )

            if _depth_in_draw_range(depth):
                self._draw_tap_quad(
                    painter,
                    x,
                    y,
                    w,
                    scale,
                    color,
                    alpha,
                    note,
                    draw_depth,
                    cell=start_cell,
                    width=start_width,
                )
            if _depth_in_draw_range(draw_end_depth):
                end_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
                self._draw_tap_quad(
                    painter, end_x, end_y, end_w, end_scale, end_color, alpha // 2,
                    note, draw_end_depth, cell=note.end_cell, width=note.end_width
                )

    def _draw_slide_steps(
        self, painter: QPainter, note: Slide, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, judge_time: float,
        depth: float, vanish_x: float, vanish_y: float, judge_y: float,
    ) -> None:
        tl = self.chart.timeline if self.chart else None
        if not tl or not note.steps:
            return

        if _depth_in_draw_range(depth) and self._should_draw_slide_head(note):
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, depth)

        prev_x, prev_y, prev_w, prev_scale = x, y, w, scale
        prev_cell, prev_width = float(note.cell), float(note.width)
        current_tick = tl.note_tick(note)
        prev_depth = depth
        last_depth = depth

        step_count = len(note.steps)
        for index, step in enumerate(note.steps):
            current_tick += step.duration
            step_time = tl.time_at(current_tick)
            step_depth = self._compute_note_depth(
                note,
                current_tick,
                step_time,
                judge_time,
                cell=float(step.end_cell),
                width=float(step.end_width),
            )
            last_depth = step_depth

            if min(prev_depth, step_depth) >= DRAW_DEPTH_MAX:
                break

            draw_depths = _sustain_draw_depths(prev_depth, step_depth)
            if draw_depths is None:
                step_scale, step_y, _ = self._world_z_to_screen(
                    step_depth, vanish_y, judge_y
                )
                step_x, step_w = _note_screen_span(
                    step.end_cell, step.end_width, vanish_x, step_scale
                )
                prev_x, prev_y, prev_w, prev_scale = step_x, step_y, step_w, step_scale
                prev_cell, prev_width = float(step.end_cell), float(step.end_width)
                prev_depth = step_depth
                continue

            draw_start_depth, draw_step_depth = draw_depths
            start_cell, start_width, draw_start_depth = _clip_sustain_start(
                prev_cell,
                prev_width,
                prev_depth,
                float(step.end_cell),
                float(step.end_width),
                step_depth,
            )
            prev_scale, prev_y, _ = self._world_z_to_screen(
                draw_start_depth, vanish_y, judge_y
            )
            prev_x, prev_w = _note_screen_span(
                start_cell, start_width, vanish_x, prev_scale
            )
            step_scale, step_y, _ = self._world_z_to_screen(
                draw_step_depth, vanish_y, judge_y
            )
            step_x, step_w = _note_screen_span(
                step.end_cell, step.end_width, vanish_x, step_scale
            )

            self._draw_sustain_body(
                painter, prev_x, prev_y, prev_w, step_x, step_y, step_w,
                color, alpha, prev_scale, step_scale,
                is_slide=True,
            )

            step_color = QColor(color.red(), color.green(), color.blue(), alpha * 3 // 4)
            if (
                self._should_draw_slide_step_head(index, step_count, step)
                and _depth_in_draw_range(step_depth)
                and self.visible_note_types.get(step.note_type.value, True)
            ):
                self._draw_tap_quad(
                    painter, step_x, step_y, step_w, step_scale, step_color, alpha,
                    note, step_depth, cell=step.end_cell, width=step.end_width
                )

            prev_x, prev_y, prev_w, prev_scale = step_x, step_y, step_w, step_scale
            prev_cell, prev_width = float(step.end_cell), float(step.end_width)
            prev_depth = step_depth

        if _depth_in_draw_range(last_depth):
            end_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
            self._draw_tap_quad(
                painter, prev_x, prev_y, prev_w, prev_scale, end_color, alpha // 2,
                note, prev_depth, cell=prev_cell, width=prev_width
            )

    def _should_draw_slide_head(self, note: Note) -> bool:
        timeline = self.chart.timeline if self.chart else None
        if not timeline:
            return True
        if timeline.note_render_role(note) == RenderRole.HEAD:
            return True
        if note.note_type not in (NoteType.SXD, NoteType.SXC):
            return False
        predecessor = timeline.note_chain_predecessor(note)
        return predecessor is not None and predecessor.note_type not in (
            NoteType.SXD,
            NoteType.SXC,
        )

    def _should_draw_slide_step_head(
        self, index: int, step_count: int, step: SlideTo
    ) -> bool:
        if index == step_count - 1:
            return False
        return step.note_type in {NoteType.SLD, NoteType.SXD}

    def _draw_air_path_line(
        self,
        painter: QPainter,
        x1: float, y1: float, w1: float,
        x2: float, y2: float, w2: float,
        color: QColor, alpha: int,
        scale1: float, scale2: float,
    ) -> None:
        if not all(
            math.isfinite(value)
            for value in (x1, y1, w1, x2, y2, w2, scale1, scale2)
        ):
            return
        if w1 <= 0.0 or w2 <= 0.0:
            return
        max_coord = 1e6
        if any(abs(value) > max_coord for value in (x1, y1, x2, y2)):
            return
        hw1 = w1 / 2.0
        hw2 = w2 / 2.0

        body_color = QColor(color.red(), color.green(), color.blue(), alpha // 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body_color)
        body_poly = QPolygonF([
            QPointF(x1, y1),
            QPointF(x1 + w1, y1),
            QPointF(x2 + w2, y2),
            QPointF(x2, y2),
        ])
        painter.drawPolygon(body_poly)

        pen_color = QColor(color.red(), color.green(), color.blue(), alpha)
        line_width = max(2, int(min(scale1, scale2) * 4))
        painter.setPen(QPen(pen_color, line_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(x1 + hw1, y1), QPointF(x2 + hw2, y2))

    def _draw_air_lift_connector(
        self,
        painter: QPainter,
        x: float,
        y_bottom: float,
        y_top: float,
        w: float,
        scale: float,
        color: QColor,
        alpha: int,
    ) -> None:
        if painter is None:
            return
        if not all(math.isfinite(value) for value in (x, y_bottom, y_top, w, scale)):
            return
        if w <= 0.0 or abs(y_bottom - y_top) < 1.0:
            return
        max_coord = 1e6
        if any(abs(value) > max_coord for value in (x, y_bottom, y_top)):
            return

        top = min(y_bottom, y_top)
        bottom = max(y_bottom, y_top)
        body_poly = QPolygonF(
            [
                QPointF(x, bottom),
                QPointF(x + w, bottom),
                QPointF(x + w, top),
                QPointF(x, top),
            ]
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), alpha // 3)))
        painter.drawPolygon(body_poly)

        center_x = x + w / 2.0
        edge_color = QColor(color.red(), color.green(), color.blue(), max(40, alpha // 2))
        painter.setPen(QPen(edge_color, max(1, int(scale * 2))))
        painter.drawLine(QPointF(x, bottom), QPointF(x, top))
        painter.drawLine(QPointF(x + w, bottom), QPointF(x + w, top))

        center_color = QColor(color.red(), color.green(), color.blue(), alpha)
        painter.setPen(QPen(center_color, max(2, int(scale * 4))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(center_x, y_bottom), QPointF(center_x, y_top))

    def _draw_sustain_body(
        self,
        painter: QPainter,
        x1: float, y1: float, w1: float,
        x2: float, y2: float, w2: float,
        color: QColor, alpha: int,
        scale1: float, scale2: float,
        is_slide: bool = False,
    ) -> None:
        if not all(
            math.isfinite(value)
            for value in (x1, y1, w1, x2, y2, w2, scale1, scale2)
        ):
            return

        if w1 <= 0.0 or w2 <= 0.0:
            return

        max_coord = 1e6
        if any(abs(value) > max_coord for value in (x1, y1, x2, y2)):
            return

        hw1 = w1 / 2.0
        hw2 = w2 / 2.0
        body_color = QColor(color.red(), color.green(), color.blue(), alpha // 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body_color)
        body_poly = QPolygonF([
            QPointF(x1, y1 - 1),
            QPointF(x1 + w1, y1 - 1),
            QPointF(x2 + w2, y2 - 1),
            QPointF(x2, y2 - 1),
        ])
        painter.drawPolygon(body_poly)

        pen_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
        painter.setPen(QPen(pen_color, max(1, int(min(scale1, scale2) * 2))))
        painter.drawLine(int(x1 + hw1), int(y1), int(x2 + hw2), int(y2))

    def _draw_air_arrow(
        self, painter: QPainter, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, nt: NoteType,
    ) -> None:
        sw = w * AIR_ARROW_WIDTH_SCALE
        sh = max(6.0, AIR_ARROW_HEIGHT_SCALE * scale)
        is_down = nt in {NoteType.ADW, NoteType.ADR, NoteType.ADL}

        painter.save()
        painter.translate(x + w / 2, y - AIR_ARROW_ANCHOR_OFFSET * scale)

        if is_down:
            painter.scale(1, -1)
            painter.translate(0, sh)

        if nt in {NoteType.AUL, NoteType.ADL}:
            painter.shear(0.5, 0)
        elif nt in {NoteType.AUR, NoteType.ADR}:
            painter.shear(-0.5, 0)

        points = [
            QPointF(-sw / 2, 0),
            QPointF(-sw / 2, -sh * 2 / 3),
            QPointF(0, -sh),
            QPointF(sw / 2, -sh * 2 / 3),
            QPointF(sw / 2, 0),
            QPointF(0, -sh * 1 / 3),
        ]
        polygon = QPolygonF(points)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), alpha)))
        painter.drawPolygon(polygon)

        border_width = max(1.5, sh * 0.12)
        border_color = QColor(220, 220, 220, alpha)
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(polygon)

        painter.restore()

    def _draw_or_defer_air_arrow(
        self,
        painter: QPainter,
        note: Note,
        x: float,
        y: float,
        w: float,
        scale: float,
        alpha: int,
        nt: NoteType,
        depth: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> None:
        if (
            self._defer_air_arrows
            and (
                self._air_anchor_for_note(note) is not None
                or note.note_type == NoteType.AHX
            )
        ):
            self._deferred_air_arrows.append(
                (note, x, y, w, scale, alpha, nt, depth, vanish_x, vanish_y, judge_y)
            )
            return

        self._draw_air_arrow_for_note(
            painter, note, x, y, w, scale, alpha, nt, depth, vanish_x, vanish_y, judge_y
        )

    def _draw_air_arrow_for_note(
        self,
        painter: QPainter,
        note: Note,
        x: float,
        y: float,
        w: float,
        scale: float,
        alpha: int,
        nt: NoteType,
        depth: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> None:
        if self._air_anchor_for_note(note) is not None or note.note_type == NoteType.AHX:
            anchored_y = self._air_anchor_screen_y(note, depth, vanish_y, judge_y)
            if anchored_y is not None:
                x, w = self._air_arrow_screen_span_at_anchor(note, vanish_x, scale)
                y = anchored_y

        arrow_color = get_note_color(nt)
        arrow_color.setAlpha(alpha)
        self._draw_air_arrow(painter, x, y, w, scale, arrow_color, alpha, nt)

    def _draw_air_start_arrow_if_needed(
        self, painter: QPainter, note: Note, x: float, y: float, w: float, scale: float, alpha: int,
        judge_time: float, vanish_x: float, vanish_y: float, judge_y: float,
        depth: float,
    ) -> None:
        target_type = getattr(note, "target_note", None)
        if not target_type:
            return

        arrow_type = None
        if target_type in {"AIR", "AUR", "AUL", "ADW", "ADR", "ADL"}:
            arrow_type = NoteType(target_type)
        elif target_type in {
            "TAP", "CHR", "HLD", "HXD", "SLD", "SXD", "SLC", "SXC",
            "AHD", "AHX", "FLK", "MNE", "DEF"
        }:
            arrow_type = NoteType.AIR

        if arrow_type is None:
            return

        self._draw_or_defer_air_arrow(
            painter,
            note,
            x,
            y,
            w,
            scale,
            alpha,
            arrow_type,
            depth,
            vanish_x,
            vanish_y,
            judge_y,
        )

    def _draw_air_action_bar_3d(
        self,
        painter: QPainter,
        x: float,
        y: float,
        w: float,
        scale: float,
        alpha: int,
        depth: float,
    ) -> None:
        note_h = _projected_note_height(depth, self.width(), self.height())
        bar_h = max(note_h * 2.0, 8.0)
        top = y - bar_h / 2
        bottom = y + bar_h / 2
        skew = min(w * 0.12, max(2.0, 8.0 * scale))
        edge = max(1, int(scale * 2))

        body = QPolygonF(
            [
                QPointF(x + skew, top),
                QPointF(x + w - skew, top),
                QPointF(x + w, y),
                QPointF(x + w - skew, bottom),
                QPointF(x + skew, bottom),
                QPointF(x, y),
            ]
        )
        grad = QLinearGradient(x, top, x, bottom)
        grad.setColorAt(0.0, QColor(110, 0, 160, max(0, alpha // 2)))
        grad.setColorAt(0.35, QColor(231, 92, 255, alpha))
        grad.setColorAt(0.5, QColor(255, 180, 255, min(255, alpha + 40)))
        grad.setColorAt(0.65, QColor(231, 92, 255, alpha))
        grad.setColorAt(1.0, QColor(110, 0, 160, max(0, alpha // 2)))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPolygon(body)

        highlight = QColor(255, 230, 255, min(255, alpha + 30))
        shadow = QColor(90, 0, 140, max(0, alpha // 2))
        painter.setPen(QPen(highlight, edge))
        painter.drawLine(
            QPointF(x + skew, top),
            QPointF(x + w - skew, top),
        )
        painter.setPen(QPen(shadow, edge))
        painter.drawLine(
            QPointF(x + skew, bottom),
            QPointF(x + w - skew, bottom),
        )

    def _draw_air_hold_segment(
        self, painter: QPainter, note: Note, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, judge_time: float,
        depth: float, end_depth: float, vanish_x: float, vanish_y: float, judge_y: float,
        is_start: bool,
    ) -> None:
        draw_depths = _sustain_draw_depths(depth, end_depth)
        if draw_depths is None:
            return
        draw_depth, draw_end_depth = draw_depths
        start_world_y = _air_path_world_y(note)
        end_world_y = _air_path_world_y(note, end=True)
        start_cell, start_width, start_world_y, draw_depth = _clip_air_path_start(
            note.cell,
            note.width,
            start_world_y,
            depth,
            note.cell,
            note.width,
            end_world_y,
            end_depth,
        )
        x, y, w, scale = self._air_path_screen_span_at(
            start_cell, start_width, draw_depth, start_world_y, vanish_x, vanish_y,
            judge_y
        )
        end_x, end_y, end_w, end_scale = self._air_path_screen_span_at(
            note.cell, note.width, draw_end_depth, end_world_y, vanish_x, vanish_y,
            judge_y
        )

        self._draw_air_lift_if_needed(
            painter,
            note,
            float(note.cell),
            float(note.width),
            depth,
            _air_path_world_y(note),
            vanish_x,
            vanish_y,
            judge_y,
            color,
            alpha,
        )

        self._draw_sustain_body(
            painter, x, y, w, end_x, end_y, end_w,
            color, alpha, scale, end_scale,
        )

        if is_start and _depth_in_draw_range(depth):
            self._draw_air_start_arrow_if_needed(
                painter, note, x, y, w, scale, alpha,
                judge_time, vanish_x, vanish_y, judge_y, depth,
            )

        if note.note_type != NoteType.AHX and _depth_in_draw_range(end_depth):
            self._draw_air_action_bar_3d(painter, end_x, end_y, end_w, end_scale, alpha, end_depth)

    def _draw_air_slide(
        self, painter: QPainter, note: Note, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, judge_time: float,
        depth: float, end_depth: float, vanish_x: float, vanish_y: float, judge_y: float,
    ) -> None:
        if isinstance(note, AirSlideStart) and note.steps:
            self._draw_air_slide_steps(painter, note, x, y, w, scale, color, alpha, judge_time,
                                        depth, vanish_x, vanish_y, judge_y)
        else:
            end_cell = getattr(note, "end_cell", note.cell)
            end_width = getattr(note, "end_width", note.width)
            draw_depths = _sustain_draw_depths(depth, end_depth)
            if draw_depths is None:
                return
            draw_depth, draw_end_depth = draw_depths
            start_world_y = self._air_wrapped_start_world_y(note)
            end_world_y = _air_path_world_y(note, end=True)
            start_cell, start_width, start_world_y, draw_depth = _clip_air_path_start(
                note.cell,
                note.width,
                start_world_y,
                depth,
                end_cell,
                end_width,
                end_world_y,
                end_depth,
            )
            x, y, w, scale = self._air_path_screen_span_at(
                start_cell, start_width, draw_depth, start_world_y, vanish_x, vanish_y,
                judge_y
            )
            end_x, end_y, end_w, end_scale = self._air_path_screen_span_at(
                end_cell, end_width, draw_end_depth, end_world_y, vanish_x, vanish_y,
                judge_y
            )
            self._draw_air_lift_if_needed(
                painter,
                note,
                float(note.cell),
                float(note.width),
                depth,
                _air_path_world_y(note),
                vanish_x,
                vanish_y,
                judge_y,
                color,
                alpha,
            )
            self._draw_air_path_line(
                painter, x, y, w, end_x, end_y, end_w,
                color, alpha, scale, end_scale,
            )

            if _depth_in_draw_range(depth):
                if self._air_anchor_for_note(note) is None:
                    self._draw_tap_quad(
                        painter,
                        x,
                        y,
                        w,
                        scale,
                        color,
                        alpha,
                        note,
                        depth,
                        cell=start_cell,
                        width=start_width,
                    )
                self._draw_air_start_arrow_if_needed(
                    painter, note, x, y, w, scale, alpha,
                    judge_time, vanish_x, vanish_y, judge_y, depth,
                )

            if _depth_in_draw_range(end_depth):
                self._draw_air_action_bar_3d(
                    painter,
                    end_x,
                    end_y,
                    end_w,
                    end_scale,
                    alpha,
                    end_depth,
                )

    def _draw_air_slide_steps(
        self, painter: QPainter, note: AirSlideStart, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, judge_time: float,
        depth: float, vanish_x: float, vanish_y: float, judge_y: float,
    ) -> None:
        tl = self.chart.timeline if self.chart else None
        if not tl or not note.steps:
            return

        if _depth_in_draw_range(depth):
            if self._air_anchor_for_note(note) is None:
                self._draw_tap_quad(
                    painter,
                    x,
                    y,
                    w,
                    scale,
                    color,
                    alpha,
                    note,
                    depth,
                    cell=note.cell,
                    width=note.width,
                )
            self._draw_air_start_arrow_if_needed(
                painter, note, x, y, w, scale, alpha,
                judge_time, vanish_x, vanish_y, judge_y, depth,
            )

        prev_cell, prev_width = float(note.cell), float(note.width)
        prev_world_y = self._air_wrapped_start_world_y(note)
        prev_depth = depth

        self._draw_air_lift_if_needed(
            painter,
            note,
            float(note.cell),
            float(note.width),
            depth,
            _air_path_world_y(note),
            vanish_x,
            vanish_y,
            judge_y,
            color,
            alpha,
        )

        step_count = len(note.steps)
        for index, step in enumerate(note.steps):
            step_abs = step.measure + step.offset / tl.resolution
            step_end_abs = step_abs + step.duration / tl.resolution
            step_time = tl.time_at_measure(step_end_abs)
            step_tick = tl.to_tick(step.measure, step.offset) + step.duration
            step_depth = self._compute_note_depth(
                note,
                step_tick,
                step_time,
                judge_time,
                cell=float(step.end_cell),
                width=float(step.end_width),
            )

            if min(prev_depth, step_depth) >= DRAW_DEPTH_MAX:
                break

            draw_depths = _sustain_draw_depths(prev_depth, step_depth)
            if draw_depths is None:
                prev_cell = float(step.end_cell)
                prev_width = float(step.end_width)
                prev_world_y = _air_path_world_y(step, end=True)
                prev_depth = step_depth
                continue

            draw_start_depth, draw_step_depth = draw_depths
            step_world_y = _air_path_world_y(step, end=True)
            start_cell, start_width, start_world_y, draw_start_depth = (
                _clip_air_path_start(
                    prev_cell,
                    prev_width,
                    prev_world_y,
                    prev_depth,
                    float(step.end_cell),
                    float(step.end_width),
                    step_world_y,
                    step_depth,
                )
            )
            prev_x, prev_y, prev_w, prev_scale = self._air_path_screen_span_at(
                start_cell, start_width, draw_start_depth, start_world_y, vanish_x,
                vanish_y, judge_y
            )
            step_x, step_y, step_w, step_scale = self._air_path_screen_span_at(
                step.end_cell, step.end_width, draw_step_depth, step_world_y, vanish_x,
                vanish_y, judge_y
            )

            self._draw_air_path_line(
                painter, prev_x, prev_y, prev_w, step_x, step_y, step_w,
                color, alpha, prev_scale, step_scale,
            )

            if (
                self._air_slide_step_draws_bar(index, step_count, step)
                and _depth_in_draw_range(step_depth)
                and self.visible_note_types.get("ASD", True)
            ):
                self._draw_air_action_bar_3d(
                    painter,
                    step_x,
                    step_y,
                    step_w,
                    step_scale,
                    alpha,
                    step_depth,
                )

            prev_cell = float(step.end_cell)
            prev_width = float(step.end_width)
            prev_world_y = step_world_y
            prev_depth = step_depth

    def _air_slide_step_draws_bar(
        self,
        index: int,
        step_count: int,
        step: Note,
    ) -> bool:
        return (
            step.note_type in {NoteType.ASD, NoteType.ASX}
            or index == step_count - 1
        )

    def _draw_air_trace(
        self, painter: QPainter, note: Note, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, judge_time: float,
        depth: float, end_depth: float, vanish_x: float, vanish_y: float, judge_y: float,
    ) -> None:
        dur = getattr(note, "duration", 0)
        if dur <= 0:
            self._draw_tap_quad(
                painter,
                x,
                y,
                w,
                scale,
                color,
                alpha,
                note,
                depth,
                cell=note.cell,
                width=note.width,
            )
            return

        end_cell = getattr(note, "end_cell", note.cell)
        end_width = getattr(note, "end_width", note.width)
        draw_depths = _sustain_draw_depths(depth, end_depth)
        if draw_depths is None:
            return
        draw_depth, draw_end_depth = draw_depths
        start_world_y = _air_path_world_y(note)
        end_world_y = _air_path_world_y(note, end=True)
        start_cell, start_width, start_world_y, draw_depth = _clip_air_path_start(
            note.cell,
            note.width,
            start_world_y,
            depth,
            end_cell,
            end_width,
            end_world_y,
            end_depth,
        )
        x, y, w, scale = self._air_trace_screen_span_at(
            start_cell, start_width, draw_depth, start_world_y, vanish_x, vanish_y,
            judge_y
        )
        end_x, end_y, end_w, _ = self._air_trace_screen_span_at(
            end_cell, end_width, draw_end_depth, end_world_y, vanish_x, vanish_y,
            judge_y
        )
        if not all(math.isfinite(value) for value in (x, y, w, end_x, end_y, end_w, scale)):
            return
        if w <= 0.0 or end_w <= 0.0:
            return
        max_coord = 1e6
        if any(abs(value) > max_coord for value in (x, y, end_x, end_y)):
            return

        trace_color = QColor(color.red(), color.green(), color.blue(), max(20, alpha // 2))
        trace_edge = QColor(color.red(), color.green(), color.blue(), alpha)
        trace_poly = QPolygonF(
            [
                QPointF(x, y),
                QPointF(end_x, end_y),
                QPointF(end_x + end_w, end_y),
                QPointF(x + w, y),
            ]
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(trace_color))
        painter.drawPolygon(trace_poly)
        painter.setPen(QPen(trace_edge, max(1, int(scale))))
        painter.drawLine(QPointF(x + w / 2, y), QPointF(end_x + end_w / 2, end_y))

        crush_interval = getattr(note, "crush_interval", getattr(note, "crush_tick", 0))
        if crush_interval > 0:
            if not self.chart:
                return
            tl = self.chart.timeline
            start_tick = tl.note_tick(note)
            for offset_tick in range(0, dur + 1, crush_interval):
                current_abs_tick = start_tick + offset_tick
                progress = offset_tick / dur if dur > 0 else 0
                curr_cell = note.cell + (end_cell - note.cell) * progress
                curr_width = note.width + (end_width - note.width) * progress
                curr_time = tl.time_at(current_abs_tick)
                curr_depth = self._compute_note_depth(
                    note,
                    current_abs_tick,
                    curr_time,
                    judge_time,
                    cell=curr_cell,
                    width=curr_width,
                )

                if not _depth_in_draw_range(curr_depth):
                    continue

                start_height = float(getattr(note, "starting_height", 1.0))
                target_height = float(getattr(note, "target_height", start_height))
                curr_height = _lerp(start_height, target_height, progress)
                curr_world_y = _air_action_world_y_from_chart_height(curr_height)
                cx, cy, cw, c_scale = self._air_action_screen_span_at(
                    curr_cell,
                    curr_width,
                    curr_depth,
                    curr_world_y,
                    vanish_x,
                    vanish_y,
                    judge_y,
                )

                self._draw_air_action_bar_3d(painter, cx, cy, cw, c_scale, alpha, curr_depth)

    def _draw_air_solid(
        self, painter: QPainter, note: Note, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, judge_time: float,
        depth: float, end_depth: float, vanish_x: float, vanish_y: float, judge_y: float,
    ) -> None:
        end_cell = getattr(note, "end_cell", note.cell)
        end_width = getattr(note, "end_width", note.width)
        draw_depths = _sustain_draw_depths(depth, end_depth)
        if draw_depths is None:
            return
        draw_depth, draw_end_depth = draw_depths
        start_world_y = _air_path_world_y(note)
        end_world_y = _air_path_world_y(note, end=True)
        start_cell, start_width, start_world_y, draw_depth = _clip_air_path_start(
            note.cell,
            note.width,
            start_world_y,
            depth,
            end_cell,
            end_width,
            end_world_y,
            end_depth,
        )
        x, y, w, scale = self._air_path_screen_span_at(
            start_cell, start_width, draw_depth, start_world_y, vanish_x, vanish_y,
            judge_y
        )
        end_x, end_y, end_w, end_scale = self._air_path_screen_span_at(
            end_cell, end_width, draw_end_depth, end_world_y, vanish_x, vanish_y,
            judge_y
        )

        self._draw_air_path_line(
            painter, x, y, w, end_x, end_y, end_w,
            color, alpha, scale, end_scale,
        )

        if _depth_in_draw_range(depth):
            painter.setPen(QPen(color.lighter(140), max(1, int(scale * 2))))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), alpha))
            painter.drawRoundedRect(
                int(x), int(y - w * 0.3), int(w), int(w * 0.6),
                int(max(1, scale * 3)), int(max(1, scale * 3)),
            )

    def _draw_heaven_hold(
        self, painter: QPainter, note: Note, x: float, y: float, w: float,
        scale: float, color: QColor, alpha: int, judge_time: float,
        depth: float, end_depth: float, vanish_x: float, vanish_y: float, judge_y: float,
    ) -> None:
        end_cell = getattr(note, "end_cell", note.cell)
        end_width = getattr(note, "end_width", note.width)
        draw_depths = _sustain_draw_depths(depth, end_depth)
        if draw_depths is None:
            return
        draw_depth, draw_end_depth = draw_depths
        start_world_y = _air_path_world_y(note)
        end_world_y = _air_path_world_y(note, end=True)
        start_cell, start_width, start_world_y, draw_depth = _clip_air_path_start(
            note.cell,
            note.width,
            start_world_y,
            depth,
            end_cell,
            end_width,
            end_world_y,
            end_depth,
        )
        x, y, w, scale = self._air_path_screen_span_at(
            start_cell, start_width, draw_depth, start_world_y, vanish_x, vanish_y,
            judge_y
        )
        end_x, end_y, end_w, end_scale = self._air_path_screen_span_at(
            end_cell, end_width, draw_end_depth, end_world_y, vanish_x, vanish_y,
            judge_y
        )

        heaven_color = QColor(200, 100, 255, alpha)
        self._draw_sustain_body(
            painter, x, y, w, end_x, end_y, end_w,
            heaven_color, alpha, scale, end_scale,
        )

        if _depth_in_draw_range(depth):
            self._draw_tap_quad(
                painter, x, y, w, scale, heaven_color, alpha, note, depth,
                cell=start_cell, width=start_width
            )
        if _depth_in_draw_range(draw_end_depth):
            end_color = QColor(
                heaven_color.red(), heaven_color.green(), heaven_color.blue(), alpha // 2
            )
            self._draw_tap_quad(
                painter, end_x, end_y, end_w, end_scale, end_color, alpha // 2,
                note, draw_end_depth, cell=end_cell, width=end_width
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

        time_text = f"{current_seconds:.2f}s / {total_seconds:.2f}s"
        painter.setPen(QColor(160, 170, 190))
        f = QFont(FONT_FAMILY, 8)
        painter.setFont(f)
        painter.drawText(
            int(scrubber_x + 4), int(scrubber_y) + 12,
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
