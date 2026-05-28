from __future__ import annotations

import logging

NOTE_DEBUG = logging.getLogger("note_rendering_debug")
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.models import Chart
    from src.ui.view.projection import ViewProjection
    from src.ui.view.renderer.notes.support import SlidePathPoint

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from src.core.const import (
    AIR_ARROW_NOTES,
    AnimationType,
    NoteType,
)
from src.notes.air import AirSlideStart
from src.notes.slide import Slide
from src.ui.theme.color_profile import DEFAULT_COLOR_PROFILE, GradientColor
from src.ui.theme.ui import TEXT_MEASURE, qt as theme_qt
from src.ui.view import timeline_compat
from src.ui.view.renderer.notes import (
    AirRendererMixin,
    DamageRendererMixin,
    FlickRendererMixin,
    HeavenHoldRendererMixin,
    HoldRendererMixin,
    SlideRendererMixin,
)

# Set up logging
logger = logging.getLogger("chart_renderer")

CHED_BAR_LINE = QColor(160, 160, 160)
CHED_BEAT_LINE = QColor(80, 80, 80)
CHED_MINOR_LINE = QColor(48, 48, 48)


@dataclass(frozen=True, slots=True)
class RendererConstants:
    """Standardized geometric constants for the chart renderer."""

    HEAD_HEIGHT: float = timeline_compat.NOTE_HEAD_HEIGHT
    ACTION_BAR_HEIGHT: float = timeline_compat.ACTION_BAR_HEIGHT
    AIR_SYMBOL_HEIGHT: float = 30.0
    AIR_SYMBOL_WIDTH_RATIO: float = 0.9
    AIR_SYMBOL_OFFSET: float = 5.0
    BORDER_WIDTH_RATIO: float = 0.1
    CORNER_RADIUS_RATIO: float = 0.3
    SLIDE_LINE_WIDTH: float = timeline_compat.HOLD_STROKE_WIDTH
    AIR_PATH_WIDTH: float = timeline_compat.HOLD_STROKE_WIDTH
    """Stroke width for air path lines (holds, slides, traces)."""
    TRAPEZOID_HINT_ALPHA: int = 180
    CONTROL_POINT_ALPHA: int = 60


RenderFunction = Callable[[QPainter, Any, float, Any], None]  # noqa: UP006


@dataclass(frozen=True, slots=True)
class RenderTask:
    """A single rendering operation within the priority-based pipeline."""

    priority: int
    function: RenderFunction
    note: Any
    tick: int


AIR_DIRECTION_VALUES = {note_type.value for note_type in AIR_ARROW_NOTES}
NOTE_ROLE_START = "ST"
NOTE_ROLE_LINE_CONTROL = "LC"
NOTE_ROLE_END = "EN"
NOTE_ROLE_ACTION = "EX"
EX_TAP_TYPES = {animation_type.value for animation_type in AnimationType}
EX_TAP_SHAPE_CODES = {
    "UP": "U",
    "DW": "D",
    "CE": "C",
    "RC": "R",
    "LC": "L",
    "RS": "RR",
    "LS": "RL",
    "BS": "I",
}


@dataclass(slots=True)
class RenderCache:
    """Internal cache for Pens, Brushes, Pixmaps, and reusable point buffers."""

    pens: dict[tuple[int, float], QPen] = field(default_factory=dict)
    brushes: dict[int, QBrush] = field(default_factory=dict)
    pixmaps: dict[tuple[Any, ...], QPixmap] = field(default_factory=dict)
    tasks: dict[int, list[RenderTask]] = field(default_factory=dict)
    # Pre-allocated point buffers to avoid per-frame list allocations
    _lane_buf: list[QPointF] = field(default_factory=list)
    _measure_buf: list[QPointF] = field(default_factory=list)
    _minor_buf: list[QPointF] = field(default_factory=list)
    _beat_buf: list[QPointF] = field(default_factory=list)

    def get_pen(self, color: QColor, width: float = 1.0) -> QPen:
        key = (color.rgba(), width)
        if key not in self.pens:
            self.pens[key] = QPen(color, width)
        return self.pens[key]

    def get_brush(self, color: QColor, alpha: int = 255) -> QBrush:
        brush_color = QColor(color)
        brush_color.setAlpha(alpha)
        key = brush_color.rgba()
        if key not in self.brushes:
            self.brushes[key] = QBrush(brush_color)
        return self.brushes[key]

    def get_pixmap(
        self,
        key: tuple[Any, ...],
        draw_func: Callable[[QPainter, QRectF], None],  # noqa: UP006
        width: float,
        height: float,
    ) -> QPixmap:
        if key not in self.pixmaps:
            pixmap = QPixmap(int(width), int(height))
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            draw_func(painter, QRectF(0, 0, width, height))
            painter.end()
            self.pixmaps[key] = pixmap
        return self.pixmaps[key]

    def clear(self) -> None:
        """Clear all cached resources."""
        self.pens.clear()
        self.brushes.clear()
        self.pixmaps.clear()
        self.tasks.clear()


class BaseRenderer(
    AirRendererMixin,
    DamageRendererMixin,
    FlickRendererMixin,
    HeavenHoldRendererMixin,
    HoldRendererMixin,
    SlideRendererMixin,
):
    """
    Consolidated rendering engine for CHUNITHM charts.

    This engine is backwards-compatible across all C2S versions (1.00 through modern).
    It uses version-based runtime switching to handle legacy behavioral quirks
    (like automatic Air Hold action bars) and modern features (Air Slide chains).
    """

    def __init__(
        self,
        projection: ViewProjection,
        total_lanes: int = 16,
        visible_note_types: dict[str, bool] | None = None,
        subdivisions: int = 4,
        version: str = "1.13.00",
    ) -> None:
        self.projection: ViewProjection = projection
        self.total_lanes: int = total_lanes
        self.visible_note_types: dict[str, bool] = visible_note_types or {}
        self.subdivisions: int = subdivisions

        self.colors = DEFAULT_COLOR_PROFILE
        self.constants = RendererConstants()
        self.cache = RenderCache()
        self.logger = logger

        # Parse version for runtime behavior switching
        try:
            parts = [int(p) for p in version.split(maxsplit=1)[0].split(".")]
            self.major = parts[0] if len(parts) > 0 else 1
            self.minor = parts[1] if len(parts) > 1 else 13
        except (ValueError, IndexError):
            self.major, self.minor = 1, 13

    # --- Public API ---

    def draw_lane_lines(
        self, painter: QPainter, current_position: float, top_measure: float, bottom_measure: float
    ) -> None:
        if not hasattr(self, "_lane_pen"):
            self._lane_pen = self.cache.get_pen(QColor(100, 100, 100))
        painter.setPen(self._lane_pen)
        y_start, y_end = (
            self.projection.y(top_measure, current_position),
            self.projection.y(bottom_measure, current_position),
        )

        buf = self.cache._lane_buf
        buf.clear()
        for lane_index in range(self.total_lanes + 1):
            x_pos = self.projection.x(lane_index)
            buf.append(QPointF(x_pos, y_start))
            buf.append(QPointF(x_pos, y_end))
        painter.drawLines(buf)

    def draw_measure_lines(  # noqa: PLR0913
        self,
        painter: QPainter,
        start_measure: int,
        end_measure: int,
        current_position: float,
        viewport_width: int,
        show_labels: bool = True,
    ) -> None:
        vw_f = float(viewport_width)

        _qt = theme_qt
        if self.subdivisions > 1:
            if not hasattr(self, "_minor_subdiv_pen"):
                self._minor_subdiv_pen = self.cache.get_pen(CHED_MINOR_LINE, 1)
            if not hasattr(self, "_beat_subdiv_pen"):
                self._beat_subdiv_pen = self.cache.get_pen(CHED_BEAT_LINE, 1)
            beat_step = max(1, self.subdivisions // 4)
            minor_lines = self.cache._minor_buf
            minor_lines.clear()
            beat_lines = self.cache._beat_buf
            beat_lines.clear()
            for measure_idx in range(start_measure, end_measure):
                for sub_idx in range(1, self.subdivisions):
                    y_pos = self.projection.y(
                        float(measure_idx) + sub_idx / self.subdivisions,
                        current_position,
                    )
                    target = beat_lines if sub_idx % beat_step == 0 else minor_lines
                    target.append(QPointF(0.0, y_pos))
                    target.append(QPointF(vw_f, y_pos))
            if minor_lines:
                painter.setPen(self._minor_subdiv_pen)
                painter.drawLines(minor_lines)
            if beat_lines:
                painter.setPen(self._beat_subdiv_pen)
                painter.drawLines(beat_lines)

        if not hasattr(self, "_measure_pen"):
            self._measure_pen = self.cache.get_pen(CHED_BAR_LINE, 1)
        painter.setPen(self._measure_pen)
        m_lines = self.cache._measure_buf
        m_lines.clear()
        # Collect label data first so we can batch render them
        label_data: list[tuple[QRectF, str]] = []
        for measure_idx in range(start_measure, end_measure + 1):
            y_pos = self.projection.y(float(measure_idx), current_position)
            m_lines.append(QPointF(0.0, y_pos))
            m_lines.append(QPointF(vw_f, y_pos))

            if show_labels:
                label_data.append((
                    QRectF(-44, y_pos - 10, 40, 20),
                    f"{measure_idx + 1:03d}",
                ))

        painter.drawLines(m_lines)

        # Batched label rendering — one save/restore for all labels
        if label_data:
            painter.save()
            painter.setPen(theme_qt(TEXT_MEASURE))
            for rect, text in label_data:
                painter.drawText(
                    rect,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    text,
                )
            painter.restore()

    def draw_notes(self, painter: QPainter, notes: list[Any], current_position: float) -> None:
        if not self.projection.timeline_engine:
            return
        timeline = self.projection.timeline_engine

        self._draw_soflan_areas(painter, current_position, timeline)

        # Bucketed dispatch for O(N) Z-ordering
        buckets: dict[int, list[RenderTask]] = {}

        for note in notes:
            note_id = id(note)
            if note_id in self.cache.tasks:
                note_tasks = self.cache.tasks[note_id]
            else:
                note_tasks = []
                self._dispatch_note_tasks(note_tasks, note, timeline)
                self.cache.tasks[note_id] = note_tasks

            NOTE_DEBUG.debug("dispatch: %s m=%d:%d c=%d w=%d tasks=%d priorities=%s",
                             note.note_type.value, note.measure, note.offset,
                             note.cell, note.width, len(note_tasks),
                             [t.priority for t in note_tasks])

            for task in note_tasks:
                buckets.setdefault(task.priority, []).append(task)

        # Execute buckets in priority order
        for priority in sorted(buckets.keys()):
            bucket_tasks = buckets[priority]
            bucket_tasks.sort(key=lambda t: t.tick)
            for task in bucket_tasks:
                task.function(painter, task.note, current_position, timeline)

    # --- Dispatch Logic ---

    def _dispatch_note_tasks(
        self, render_tasks: list[RenderTask], note: Any, timeline: Any
    ) -> None:
        note_type, note_tick = note.note_type, timeline.note_tick(note)
        if note_type in (NoteType.HLD, NoteType.HXD):
            render_tasks.append(RenderTask(10, self._draw_hold_background, note, note_tick))
        elif note_type in (NoteType.SLD, NoteType.SXD, NoteType.SLC, NoteType.SXC):
            render_tasks.append(RenderTask(12, self._draw_slide_background, note, note_tick))
        elif note_type == NoteType.ASO:
            render_tasks.append(RenderTask(20, self._draw_air_solid_background, note, note_tick))
        elif note_type in (NoteType.HHD, NoteType.HHX):
            render_tasks.append(RenderTask(20, self._draw_heaven_hold_background, note, note_tick))
        self._dispatch_air_tasks(render_tasks, note, note_type, note_tick)
        self._dispatch_foreground_tasks(render_tasks, note, note_type, note_tick)

    def _dispatch_air_tasks(
        self, render_tasks: list[RenderTask], note: Any, note_type: NoteType, tick: int
    ) -> None:
        """Version-aware air task dispatcher."""
        if note_type in (NoteType.ASD, NoteType.ASC, NoteType.ASX) or isinstance(
            note, AirSlideStart
        ):
            render_tasks.append(RenderTask(20, self._draw_air_slide_background, note, tick))
            render_tasks.append(RenderTask(35, self._draw_air_action_bar, note, tick))
            # If wrapper resolves to a ground note type, dispatch its foreground
            resolved = self._resolve_air_wrapped_foreground(note)
            if resolved is not None:
                render_tasks.append(RenderTask(38, resolved, note, tick))

        elif note_type == NoteType.ALD:
            render_tasks.append(RenderTask(20, self._draw_crash_slide_background, note, tick))
            render_tasks.append(RenderTask(35, self._draw_air_action_bar, note, tick))

        elif note_type in (NoteType.AHD, NoteType.AHX):
            render_tasks.append(RenderTask(20, self._draw_air_hold_background, note, tick))
            # AHX is hybrid ground bar — no floating action bar in air zone
            if note_type == NoteType.AHD:
                render_tasks.append(RenderTask(35, self._draw_air_action_bar, note, tick))

        elif note_type in AIR_ARROW_NOTES:
            # Air arrows render in the air foreground layer above all ground notes.
            render_tasks.append(RenderTask(38, self._draw_air_step_for_air, note, tick))
            render_tasks.append(RenderTask(55, self._draw_air, note, tick))

    def _dispatch_foreground_tasks(
        self, render_tasks: list[RenderTask], note: Any, note_type: NoteType, tick: int
    ) -> None:
        if note_type in (NoteType.HLD, NoteType.HXD):
            render_tasks.append(RenderTask(31, self._draw_hold_foreground, note, tick))
        elif note_type in (NoteType.SLD, NoteType.SXD, NoteType.SLC, NoteType.SXC):
            render_tasks.append(RenderTask(32, self._draw_slide_foreground, note, tick))
        elif note_type == NoteType.TAP:
            render_tasks.append(
                RenderTask(
                    40, lambda p, n, c, t: self._draw_tap(p, n, c, t, self.colors.tap), note, tick
                )
            )
        elif note_type == NoteType.CHR:
            render_tasks.append(
                RenderTask(
                    41,
                    lambda p, n, c, t: self._draw_tap(p, n, c, t, self.colors.ex_tap),
                    note,
                    tick,
                )
            )
        elif note_type == NoteType.MNE:
            render_tasks.append(RenderTask(40, self._draw_damage, note, tick))
        elif note_type == NoteType.FLK:
            render_tasks.append(RenderTask(40, self._draw_flick, note, tick))
        elif note_type in (NoteType.HHD, NoteType.HHX):
            render_tasks.append(RenderTask(40, self._draw_heaven_hold_foreground, note, tick))

    def _resolve_air_wrapped_foreground(
        self, note: Any
    ) -> Any | None:
        """Resolve ASC/ASD wrapper to a foreground draw function for the wrapped type.

        When ASC/ASD wraps a ground note (TAP, CHR, HLD, SLD, FLK), the foreground
        head should match the wrapped type, not air.
        """
        if not hasattr(note, "target_note"):
            return None
        wrapped: str = note.target_note
        if not isinstance(wrapped, str):
            return None
        if wrapped == "TAP":
            return lambda p, n, c, t, __self=self: __self._draw_tap(
                p, n, c, t, __self.colors.tap
            )
        if wrapped == "CHR":
            return lambda p, n, c, t, __self=self: __self._draw_tap(
                p, n, c, t, __self.colors.ex_tap
            )
        if wrapped == "FLK":
            return self._draw_flick
        return None

    # --- Core Note Drawing ---

    def _draw_tap(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
        color: GradientColor | QColor,
    ) -> None:
        if note.note_type == NoteType.SLC:
            if not self.visible_note_types.get(NoteType.SLD.value, True):
                return
        elif note.note_type == NoteType.SXC:
            if not self.visible_note_types.get(NoteType.SXD.value, True):
                return
        elif not self.visible_note_types.get(note.note_type.value, True):
            return
        y, x, w = (
            self.projection.y(timeline.note_abs_pos(note), current_position),
            self.projection.x(note.cell),
            self.projection.w(note.width),
        )
        rect = QRectF(x, y - self.constants.HEAD_HEIGHT / 2, w, self.constants.HEAD_HEIGHT)

        # Optimization: use pixmap cache for note heads
        symbol_type = self._tap_symbol_type(note)
        pixmap_key = self._tap_pixmap_key(color, w, symbol_type)

        def draw_cached_tap(p: QPainter, r: QRectF) -> None:
            self._draw_rounded_rect(p, r, color)
            self._draw_tap_symbol_for_type(p, r, symbol_type)

        pixmap = self.cache.get_pixmap(
            pixmap_key,
            draw_cached_tap,
            w,
            self.constants.HEAD_HEIGHT,
        )
        painter.drawPixmap(rect.topLeft().toPoint(), pixmap)

    def _build_slide_body_path(self, points: list[SlidePathPoint]) -> QPainterPath:
        left_path = self._build_bezier_path([point.left for point in points])
        right_path = self._build_bezier_path([point.right for point in reversed(points)])
        path = QPainterPath(left_path)
        if points:
            path.lineTo(points[-1].right)
        self._append_path_segments(path, right_path)
        path.closeSubpath()
        return path

    def _build_bezier_path(self, points: list[QPointF], tension: float = 0.5) -> QPainterPath:
        """Build a smooth Catmull-Rom spline path through control points.

        Converts Catmull-Rom control points to cubic B\u00e9zier curve segments
        matching the game's ``SpkInterpolationBezierAD3`` rendering.
        """
        path = QPainterPath()
        n = len(points)
        if n == 0:
            return path
        path.moveTo(points[0])
        if n <= 2:
            for pt in points[1:]:
                path.lineTo(pt)
            return path

        for i in range(n - 1):
            p0 = points[max(0, i - 1)]
            p1 = points[i]
            p2 = points[i + 1]
            p3 = points[min(n - 1, i + 2)]
            # Catmull-Rom → cubic Bézier control points with tension τ = 0.5
            cp1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0, p1.y() + (p2.y() - p0.y()) / 6.0)
            cp2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0, p2.y() - (p3.y() - p1.y()) / 6.0)
            path.cubicTo(cp1, cp2, p2)

        return path

    def _build_polyline_path(self, points: list[QPointF]) -> QPainterPath:
        """Build a straight polyline path through control points."""
        path = QPainterPath()
        if not points:
            return path
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        return path

    def _append_path_segments(self, target: QPainterPath, source: QPainterPath) -> None:
        for index in range(1, source.elementCount()):
            element = source.elementAt(index)
            target.lineTo(QPointF(element.x, element.y))

    # --- Soflan Area Rendering ---

    def _draw_soflan_areas(self, painter: QPainter, current_position: float, timeline: Any) -> None:
        chart = getattr(timeline, "chart", None)
        if not chart:
            return
        areas = getattr(chart, "soflan_areas", None)
        if not areas:
            return
        res = timeline.resolution
        for area in areas:
            start_tick = timeline.to_tick(area.measure, area.tick)
            end_tick = start_tick + area.duration
            y_start = self.projection.y(start_tick / res, current_position)
            y_end = self.projection.y(end_tick / res, current_position)
            x = self.projection.x(float(area.cell))
            w = self.projection.w(float(area.width))
            top = min(y_start, y_end)
            height = abs(y_end - y_start)
            if height < 1:
                continue
            rect = QRectF(x, top, w, height)
            painter.fillRect(rect, QColor(255, 255, 100, 24))
            painter.setPen(QPen(QColor(255, 255, 100, 48), 1))
            painter.drawRect(rect)

    # --- Air Element Methods ---

    def _draw_rounded_rect(
        self, painter: QPainter, rect: QRectF, color: GradientColor | QColor
    ) -> None:
        self._draw_note_base(painter, rect, color)
        self._draw_border(painter, rect)

    def _draw_note_base(
        self, painter: QPainter, rect: QRectF, color: GradientColor | QColor
    ) -> None:
        gradient_color = self._gradient_color(color)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, gradient_color.light)
        gradient.setColorAt(1, gradient_color.dark)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(self._note_head_path(rect))

    def _draw_border(self, painter: QPainter, rect: QRectF) -> None:
        border_width = rect.height() * self.constants.BORDER_WIDTH_RATIO
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, self.colors.border.light)
        gradient.setColorAt(1, self.colors.border.dark)
        painter.setPen(QPen(QBrush(gradient), border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._note_head_path(rect))

    def _note_head_path(self, rect: QRectF) -> QPainterPath:
        chamfer = min(rect.height() * 0.35, rect.width() * 0.18)
        path = QPainterPath()
        path.moveTo(rect.left() + chamfer, rect.top())
        path.lineTo(rect.right() - chamfer, rect.top())
        path.lineTo(rect.right(), rect.center().y())
        path.lineTo(rect.right() - chamfer, rect.bottom())
        path.lineTo(rect.left() + chamfer, rect.bottom())
        path.lineTo(rect.left(), rect.center().y())
        path.closeSubpath()
        return path

    def _draw_tap_symbol(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(
            QPen(Qt.GlobalColor.white, rect.height() * self.constants.BORDER_WIDTH_RATIO)
        )
        y, xs, xe = (
            rect.center().y(),
            rect.left() + rect.width() * 0.2,
            rect.right() - rect.width() * 0.2,
        )
        painter.drawLine(QPointF(xs, y), QPointF(xe, y))

    def _tap_symbol_type(self, note: Any) -> str:
        ex_tap_type = self._ex_tap_symbol_type(note)
        return f"ex:{ex_tap_type}" if ex_tap_type else "tap"

    def _tap_pixmap_key(
        self,
        color: GradientColor | QColor,
        width: float,
        symbol_type: str,
    ) -> tuple[Any, ...]:
        return ("tap", self._color_cache_key(color), width, symbol_type)

    def _color_cache_key(self, color: GradientColor | QColor) -> Any:
        return (
            color.rgba() if isinstance(color, QColor) else (color.light.rgba(), color.dark.rgba())
        )

    def _ex_tap_symbol_type(self, note: Any) -> str | None:
        ex_type: str | None = None
        if note.note_type in (NoteType.CHR, NoteType.HXD):
            ex_type = getattr(note, "animation", None)
        elif note.note_type in (NoteType.SXD, NoteType.SXC):
            ex_type = getattr(note, "animation", None)
            if ex_type is None and isinstance(note, Slide) and note.steps:
                ex_type = getattr(note.steps[0], "animation", None)
        return self._normalize_ex_tap_type(ex_type) if ex_type is not None else None

    def _normalize_ex_tap_type(self, ex_type: str) -> str:
        return ex_type if ex_type in EX_TAP_TYPES else "UP"

    def _ex_tap_shape_code(self, ex_type: str) -> str:
        return EX_TAP_SHAPE_CODES[self._normalize_ex_tap_type(ex_type)]

    def _draw_tap_symbol_for_type(self, painter: QPainter, rect: QRectF, symbol_type: str) -> None:
        if symbol_type.startswith("ex:"):
            self._draw_ex_tap_symbol(painter, rect, symbol_type[3:])
            return
        self._draw_tap_symbol(painter, rect)

    def _draw_ex_tap_symbol(self, painter: QPainter, rect: QRectF, ex_type: str) -> None:
        code = self._ex_tap_shape_code(ex_type)
        pen_width = max(1.0, rect.height() * self.constants.BORDER_WIDTH_RATIO)
        painter.setPen(QPen(Qt.GlobalColor.white, pen_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        center = rect.center()
        size = min(rect.height() * 0.34, rect.width() * 0.16)
        gap = max(size * 0.55, 1.0)

        def draw_horizontal_chevron(x: float, direction: int) -> None:
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(x - direction * size, center.y() - size),
                        QPointF(x + direction * size, center.y()),
                        QPointF(x - direction * size, center.y() + size),
                    ]
                )
            )

        def draw_vertical_chevron(y: float, direction: int) -> None:
            painter.drawPolyline(
                QPolygonF(
                    [
                        QPointF(center.x() - size, y - direction * size),
                        QPointF(center.x(), y + direction * size),
                        QPointF(center.x() + size, y - direction * size),
                    ]
                )
            )

        if code == "U":
            draw_vertical_chevron(center.y(), -1)
        elif code == "D":
            draw_vertical_chevron(center.y(), 1)
        elif code == "C":
            painter.drawLine(
                QPointF(center.x(), center.y() - size * 1.25),
                QPointF(center.x(), center.y() + size * 1.25),
            )
            painter.drawLine(
                QPointF(center.x() - size * 1.25, center.y()),
                QPointF(center.x() + size * 1.25, center.y()),
            )
        elif code == "R":
            draw_horizontal_chevron(center.x(), 1)
        elif code == "L":
            draw_horizontal_chevron(center.x(), -1)
        elif code == "RR":
            draw_horizontal_chevron(center.x() - gap, 1)
            draw_horizontal_chevron(center.x() + gap, 1)
        elif code == "RL":
            draw_horizontal_chevron(center.x() - gap, -1)
            draw_horizontal_chevron(center.x() + gap, -1)
        else:
            draw_horizontal_chevron(center.x() - gap, 1)
            draw_horizontal_chevron(center.x() + gap, -1)

    def _gradient_color(self, color: GradientColor | QColor) -> GradientColor:
        if isinstance(color, GradientColor):
            return color
        return GradientColor(dark=color.darker(130), light=color.lighter(130))

    def _fill_metallic_path(
        self, painter: QPainter, path: QPainterPath, color_group: GradientColor
    ) -> None:
        rect = path.boundingRect()
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0, color_group.dark)
        gradient.setColorAt(0.3, color_group.light)
        gradient.setColorAt(0.7, color_group.light)
        gradient.setColorAt(1, color_group.dark)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(path)


def create_renderer(
    chart: Chart,
    projection: ViewProjection,
    total_lanes: int = 16,
    visible_note_types: dict[str, bool] | None = None,
    subdivisions: int = 4,
) -> BaseRenderer:
    return BaseRenderer(
        projection,
        total_lanes,
        visible_note_types,
        subdivisions,
        version=chart.metadata.version,
    )
