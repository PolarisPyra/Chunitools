from __future__ import annotations

# ruff: noqa: PLR0913
import math
from typing import TYPE_CHECKING

from src.core.const import NoteType
from src.notes import AirSlideStart, Note
from src.ui.view import timeline_compat

if TYPE_CHECKING:
    from PySide6.QtCore import QPointF

    from src.engine.timeline import ChartTimeline

# World-space coordinate system.
# Ghidra ScoreReader evidence accepts chart cells from -16 through 32, and
# the renderer maps the visible 16-lane playfield to -512..512.
WORLD_WIDTH = 32.0  # 16 lanes x 2 units/lane
WORLD_HALF = 16.0
LANE_UNITS = 2.0
PIXELS_PER_UNIT = 32.0  # screen pixels per world unit
LANE_WIDTH = int(LANE_UNITS * PIXELS_PER_UNIT)  # 64

# Widget depth is a compact equivalent of the normalized render depth.
VISIBLE_DEPTH = 20.0  # world units from judge to vanish plane

# Tap quads are full lane-span quads:
# x0 = 64 * lane - 512; x1 = x0 + 64 * width.
NOTE_WIDTH_FRAC = 1.0
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
    0.0,
    0.4,
    0.5,
    0.63,
    0.69,
    0.7,
    0.7,
    0.73,
    0.75,
    0.765,
    0.78,
    0.795,
    0.81,
    0.825,
    0.84,
    0.855,
    0.87,
)
RENDER_MIN_AIR_PATH_WIDTH_SCALE = 0.734375
MAX_PROJECTED_POLYGON_VIEWPORT_MULTIPLE = 4.0
MAX_PROJECTED_POLYGON_AREA_MULTIPLE = 4.0

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
    return VISIBLE_WINDOW_FACTOR / ((render_speed - 10) * (render_speed - 10) + 10)


def _world_depth(note_time_s: float, judge_time_s: float, window_s: float) -> float:
    if window_s < 0.001:
        return 0.0
    depth_frac = (note_time_s - judge_time_s) / window_s
    return depth_frac * VISIBLE_DEPTH


def _compact_depth_to_z(depth: float) -> float:
    return -(depth / VISIBLE_DEPTH) * FIELD_DEPTH


def _camera_space(x: float, y: float, z: float) -> tuple[float, float, float]:
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
    cam_z = min(-0.001, cam_z)

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


def _projected_polygon_is_bounded(
    points: list[QPointF],
    viewport_w: float,
    viewport_h: float,
) -> bool:
    if viewport_w <= 0.0 or viewport_h <= 0.0:
        return False
    if not all(math.isfinite(point.x()) and math.isfinite(point.y()) for point in points):
        return False

    xs = [point.x() for point in points]
    ys = [point.y() for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    bounds_margin = max(viewport_w, viewport_h) * MAX_PROJECTED_POLYGON_VIEWPORT_MULTIPLE
    if (
        min_x < -bounds_margin
        or max_x > viewport_w + bounds_margin
        or min_y < -bounds_margin
        or max_y > viewport_h + bounds_margin
    ):
        return False

    polygon_area = max(0.0, max_x - min_x) * max(0.0, max_y - min_y)
    viewport_area = viewport_w * viewport_h
    return polygon_area <= viewport_area * MAX_PROJECTED_POLYGON_AREA_MULTIPLE


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
    # Air arrows sit just above the ground note they're anchored to,
    # not at the top of the stem. Use minimum air lane (g0=0, chart height 1.0)
    if note.note_type in {
        NoteType.AIR,
        NoteType.AUR,
        NoteType.AUL,
        NoteType.ADW,
        NoteType.ADR,
        NoteType.ADL,
    }:
        return _air_trace_world_y_from_g0(0.0)
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


def _sustain_draw_depths(start_depth: float, end_depth: float) -> tuple[float, float] | None:
    if max(start_depth, end_depth) <= DRAW_DEPTH_MIN:
        return None
    if min(start_depth, end_depth) >= DRAW_DEPTH_MAX:
        return None

    draw_start = start_depth
    draw_end = end_depth
    if start_depth < DRAW_DEPTH_MIN < end_depth:
        draw_start = DRAW_DEPTH_MIN
    elif end_depth < DRAW_DEPTH_MIN < start_depth:
        draw_end = DRAW_DEPTH_MIN
    if start_depth < DRAW_DEPTH_MAX < end_depth:
        draw_end = DRAW_DEPTH_MAX
    elif end_depth < DRAW_DEPTH_MAX < start_depth:
        draw_start = DRAW_DEPTH_MAX
    return draw_start, draw_end


def _interpolate_at_depth(
    start_value: float,
    end_value: float,
    start_depth: float,
    end_depth: float,
    draw_depth: float,
) -> float:
    if start_depth == end_depth:
        return start_value
    alpha = (draw_depth - start_depth) / (end_depth - start_depth)
    return _lerp(start_value, end_value, alpha)


def _interpolate_optional_at_depth(
    start_value: float | None,
    end_value: float | None,
    start_depth: float,
    end_depth: float,
    draw_depth: float,
) -> float | None:
    if start_value is None or end_value is None:
        return start_value
    return _interpolate_at_depth(start_value, end_value, start_depth, end_depth, draw_depth)


def _clip_sustain_segment(
    start_cell: float,
    start_width: float,
    start_depth: float,
    end_cell: float,
    end_width: float,
    end_depth: float,
) -> tuple[float, float, float, float, float, float]:
    draw_depths = _sustain_draw_depths(start_depth, end_depth)
    if draw_depths is None:
        return start_cell, start_width, start_depth, end_cell, end_width, end_depth

    draw_start_depth, draw_end_depth = draw_depths
    draw_start_cell = _interpolate_at_depth(
        start_cell, end_cell, start_depth, end_depth, draw_start_depth
    )
    draw_start_width = _interpolate_at_depth(
        start_width, end_width, start_depth, end_depth, draw_start_depth
    )
    draw_end_cell = _interpolate_at_depth(end_cell, start_cell, end_depth, start_depth, draw_end_depth)
    draw_end_width = _interpolate_at_depth(
        end_width, start_width, end_depth, start_depth, draw_end_depth
    )
    return (
        draw_start_cell,
        draw_start_width,
        draw_start_depth,
        draw_end_cell,
        draw_end_width,
        draw_end_depth,
    )


def _clip_air_path_segment(
    start_cell: float,
    start_width: float,
    start_world_y: float | None,
    start_depth: float,
    end_cell: float,
    end_width: float,
    end_world_y: float | None,
    end_depth: float,
) -> tuple[float, float, float | None, float, float, float, float | None, float]:
    draw_depths = _sustain_draw_depths(start_depth, end_depth)
    if draw_depths is None:
        return (
            start_cell,
            start_width,
            start_world_y,
            start_depth,
            end_cell,
            end_width,
            end_world_y,
            end_depth,
        )

    draw_start_depth, draw_end_depth = draw_depths
    draw_start_cell = _interpolate_at_depth(
        start_cell, end_cell, start_depth, end_depth, draw_start_depth
    )
    draw_start_width = _interpolate_at_depth(
        start_width, end_width, start_depth, end_depth, draw_start_depth
    )
    draw_start_world_y = _interpolate_optional_at_depth(
        start_world_y, end_world_y, start_depth, end_depth, draw_start_depth
    )
    draw_end_cell = _interpolate_at_depth(end_cell, start_cell, end_depth, start_depth, draw_end_depth)
    draw_end_width = _interpolate_at_depth(
        end_width, start_width, end_depth, start_depth, draw_end_depth
    )
    draw_end_world_y = _interpolate_optional_at_depth(
        end_world_y, start_world_y, end_depth, start_depth, draw_end_depth
    )
    return (
        draw_start_cell,
        draw_start_width,
        draw_start_world_y,
        draw_start_depth,
        draw_end_cell,
        draw_end_width,
        draw_end_world_y,
        draw_end_depth,
    )


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
    center_x = (
        vanish_x + (((cell + width / 2.0) * LANE_UNITS) - WORLD_HALF) * PIXELS_PER_UNIT * scale
    )
    return center_x - visual_w / 2.0, visual_w


def _air_path_screen_span(
    cell: float, width: float, vanish_x: float, scale: float
) -> tuple[float, float]:
    _, lane_w = _note_screen_span(cell, width, vanish_x, scale)
    visual_w = lane_w * _air_path_width_factor(width)
    center_x = (
        vanish_x + (((cell + width / 2.0) * LANE_UNITS) - WORLD_HALF) * PIXELS_PER_UNIT * scale
    )
    return center_x - visual_w / 2.0, visual_w


def _air_path_width_factor(width: float) -> float:
    return max(_render_width_scale(width), RENDER_MIN_AIR_PATH_WIDTH_SCALE)


def _scaled_span_width(x: float, width: float, factor: float) -> tuple[float, float]:
    visual_w = width * factor
    return x + (width - visual_w) / 2.0, visual_w


def _format_time(seconds: float) -> str:
    """Format seconds as m:ss or h:mm:ss."""
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _scrubber_progress(current_pos: float, timeline: ChartTimeline) -> tuple[float, float, float]:
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
