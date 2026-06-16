from __future__ import annotations

import logging
from typing import Any, cast

NOTE_DEBUG = logging.getLogger("note_rendering_debug")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF

from src.core.const import AIR_ARROW_NOTES, GROUND_NOTE_TYPES, NoteType
from src.notes.air import AirSlideStart
from src.ui.components.timeline_view.notes.support import RendererMixinSupport
from src.ui.theme.color_profile import GradientColor
from src.ui.theme.notes import get_action_bar_color, get_note_color
from src.ui.view import timeline_compat

NOTE_ROLE_START = "ST"
NOTE_ROLE_LINE_CONTROL = "LC"
NOTE_ROLE_ACTION = "EX"
NOTE_ROLE_END = "EN"

AIR_DIRECTION_VALUES = {note_type.value for note_type in AIR_ARROW_NOTES}


class AirRendererMixin(RendererMixinSupport):
    def _draw_air(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        rect = self._air_anchor_rect(note, current_position, timeline)
        y, x, w = rect.center().y(), rect.x(), rect.width()
        c = self._air_arrow_color(note, timeline)
        self._draw_air_arrow_head(painter, note, x, y, w, c)

    def _draw_air_step_for_air(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        if not self._air_replaces_long_endpoint(note, timeline):
            return
        rect = self._air_anchor_rect(note, current_position, timeline)
        self._draw_air_step(painter, rect)

    def _draw_air_step(self, painter: QPainter, rect: QRectF) -> None:
        self._draw_rounded_rect(painter, rect, self.colors.air_step)

    def _air_anchor_rect(
        self,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> QRectF:
        anchor = timeline.note_anchor(note)
        tick = timeline.note_tick(note)
        if anchor:
            anchor_end_tick = timeline.note_end_tick(anchor)
            if tick == anchor_end_tick and anchor_end_tick != timeline.note_tick(anchor):
                cell = getattr(anchor, "end_cell", anchor.cell)
                width = getattr(anchor, "end_width", anchor.width)
            else:
                span = timeline.span_at(anchor, tick)
                cell, width = span if span else (anchor.cell, anchor.width)
        else:
            cell = note.cell
            width = note.width
        y = self.projection.y(tick / timeline.resolution, current_position)
        x = self.projection.x(float(cell))
        w = self.projection.w(float(width))
        return QRectF(x, y - self.constants.HEAD_HEIGHT / 2, w, self.constants.HEAD_HEIGHT)

    def _air_replaces_long_endpoint(self, note: Any, timeline: Any) -> bool:
        target_note = getattr(note, "target_note", "")
        if target_note not in {"HLD", "SLD"}:
            return False
        anchor = timeline.note_anchor(note)
        if not anchor:
            return False
        tick = timeline.note_tick(note)
        return bool(tick == timeline.note_end_tick(anchor) and tick != timeline.note_tick(anchor))

    def _has_air_reference_at(
        self,
        tick: int,
        cell: int,
        width: int,
        target_note: str,
        timeline: Any,
    ) -> bool:
        for note in getattr(timeline.chart, "notes", []):
            if note.note_type not in AIR_ARROW_NOTES:
                continue
            if getattr(note, "target_note", "") != target_note:
                continue
            if timeline.note_tick(note) == tick and note.cell == cell and note.width == width:
                return True
        return False

    def _air_arrow_color(self, note: Any, timeline: Any | None = None) -> QColor:
        if timeline is not None:
            anchor = timeline.note_anchor(note)
            if anchor is not None and anchor.note_type in {
                NoteType.HLD,
                NoteType.HXD,
                NoteType.SLD,
                NoteType.SXD,
                NoteType.SLC,
                NoteType.SXC,
            }:
                return self._air_base_note_color(note)
        elif getattr(note, "parent", None) is not None:
            parent = note.parent
            if parent.note_type in {
                NoteType.HLD,
                NoteType.HXD,
                NoteType.SLD,
                NoteType.SXD,
                NoteType.SLC,
                NoteType.SXC,
            }:
                return self._air_base_note_color(note)

        is_down = note.note_type in (NoteType.ADW, NoteType.ADR, NoteType.ADL)
        color_modifier = getattr(note, "color", "DEF")
        is_inverted = (not is_down and color_modifier == "PNK") or (
            is_down and color_modifier == "GRN"
        )
        if is_inverted:
            is_down = not is_down
        return self.colors.air_down if is_down else self.colors.air_up

    def _air_base_note_color(self, note: Any) -> QColor:
        if note.note_type in (NoteType.AHD, NoteType.AHX) or note.note_type in AIR_ARROW_NOTES:
            return get_note_color(note.note_type)
        return get_note_color(note.note_type, getattr(note, "color", "DEF"))

    def _draw_air_arrow_head(  # noqa: PLR0913
        self,
        painter: QPainter,
        note: Any,
        x: float,
        y: float,
        w: float,
        color: GradientColor | QColor,
    ) -> None:
        sw = w * self.constants.AIR_SYMBOL_WIDTH_RATIO
        sh = self.constants.AIR_SYMBOL_HEIGHT

        color_key = (
            color.rgba() if isinstance(color, QColor) else (color.light.rgba(), color.dark.rgba())
        )
        pixmap_key = ("air_arrow", color_key, sw, sh)

        pixmap = self.cache.get_pixmap(
            pixmap_key,
            lambda p, r: self._draw_air_arrow_graphics(p, r, color),
            sw,
            sh,
        )

        painter.save()
        painter.translate(x + w / 2, y - self.constants.AIR_SYMBOL_OFFSET)
        if note.note_type in (NoteType.ADW, NoteType.ADR, NoteType.ADL):
            painter.scale(1, -1)
            painter.translate(0, sh)
        if note.note_type in (NoteType.AUL, NoteType.ADL):
            painter.shear(0.5, 0)
        elif note.note_type in (NoteType.AUR, NoteType.ADR):
            painter.shear(-0.5, 0)

        painter.drawPixmap(int(-sw / 2), int(-sh), pixmap)
        painter.restore()

    def _draw_air_arrow_graphics(
        self,
        painter: QPainter,
        rect: QRectF,
        color: GradientColor | QColor,
    ) -> None:
        sw, sh = rect.width(), rect.height()
        points = [
            QPointF(0, sh),
            QPointF(0, sh * 1 / 3),
            QPointF(sw / 2, 0),
            QPointF(sw, sh * 1 / 3),
            QPointF(sw, sh),
            QPointF(sw / 2, sh * 2 / 3),
        ]
        polygon = QPolygonF(points)
        brush_color = color.light if isinstance(color, GradientColor) else color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.cache.get_brush(brush_color))
        painter.drawPolygon(polygon)
        painter.setPen(
            QPen(
                self.colors.border.light,
                sh * self.constants.BORDER_WIDTH_RATIO,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(polygon)

    def _draw_air_hold_background(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        anchor = timeline.note_anchor(note)
        if anchor:
            ys = self.projection.y(timeline.note_abs_end_pos(anchor), current_position)
            ye = self.projection.y(timeline.note_abs_end_pos(note), current_position)
            x = self.projection.x(getattr(anchor, "end_cell", anchor.cell))
            w = self.projection.w(float(getattr(anchor, "end_width", anchor.width)))
        else:
            ys = self.projection.y(timeline.note_abs_pos(note), current_position)
            ye = self.projection.y(timeline.note_abs_end_pos(note), current_position)
            x = self.projection.x(note.cell)
            w = self.projection.w(note.width)
        painter.setPen(
            QPen(
                get_note_color(NoteType.AHD)
                if note.note_type == NoteType.AHX
                else self._air_base_note_color(note),
                self.constants.AIR_PATH_WIDTH,
            )
        )
        painter.drawLine(QPointF(x + w / 2, ys), QPointF(x + w / 2, ye))

    def _draw_air_slide_background(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if isinstance(note, AirSlideStart):
            self._draw_air_slide_chain(painter, note, current_position, timeline)
            if self.debug_active:
                self._draw_air_wrapper_debug_outline(painter, note, current_position, timeline)
            return
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        # Debug outline for standalone ASC/ASD wrappers
        if self.debug_active and note.note_type in (NoteType.ASD, NoteType.ASC):
            self._draw_air_wrapper_debug_outline(painter, note, current_position, timeline)
        ys = self.projection.y(timeline.note_abs_pos(note), current_position)
        ye = self.projection.y(timeline.note_abs_end_pos(note), current_position)
        xs = self.projection.x(float(note.cell))
        ws = self.projection.w(float(note.width))
        xe = self.projection.x(float(note.end_cell))
        we = self.projection.w(float(note.end_width))
        painter.setPen(
            QPen(
                self._air_base_note_color(note),
                self.constants.AIR_PATH_WIDTH,
            )
        )
        self._draw_bezier_line(painter, QPointF(xs + ws / 2, ys), QPointF(xe + we / 2, ye))

    def _draw_air_slide_chain(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        master_type = NoteType.ASD if note.note_type == NoteType.ASC else note.note_type
        if not self.visible_note_types.get(master_type.value, True):
            return
        # Collect all points along the chain
        chain_points: list[QPointF] = []
        ct, cc, cw = timeline.note_abs_pos(note), note.cell, note.width
        for step in note.steps:
            ys = self.projection.y(ct, current_position)
            xs = self.projection.x(float(cc))
            ws = self.projection.w(float(cw))
            chain_points.append(QPointF(xs + ws / 2, ys))
            ct += step.duration / timeline.resolution
            cc, cw = step.end_cell, step.end_width
        # Last point
        ye = self.projection.y(ct, current_position)
        xe = self.projection.x(float(cc))
        we = self.projection.w(float(cw))
        chain_points.append(QPointF(xe + we / 2, ye))

        painter.setPen(
            QPen(
                self._air_base_note_color(note.steps[0] if note.steps else note),
                self.constants.AIR_PATH_WIDTH,
            )
        )
        if len(chain_points) <= 2:
            for pt in chain_points[1:]:
                painter.drawLine(chain_points[0], pt)
        else:
            self._draw_bezier_path(painter, chain_points)

    def _draw_bezier_line(self, painter: QPainter, p1: QPointF, p2: QPointF) -> None:
        """Draw a smooth bezier arc between two points with natural tangents."""
        dx = (p2.x() - p1.x()) * 0.25
        path = QPainterPath()
        path.moveTo(p1)
        path.cubicTo(QPointF(p1.x() + dx, p1.y()), QPointF(p2.x() - dx, p2.y()), p2)
        painter.strokePath(path, painter.pen())

    def _draw_bezier_path(self, painter: QPainter, points: list[QPointF]) -> None:
        """Draw a smooth Catmull-Rom spline through control points."""
        n = len(points)
        if n <= 2:
            return
        path = QPainterPath()
        path.moveTo(points[0])
        for i in range(n - 1):
            p0 = points[max(0, i - 1)]
            p1 = points[i]
            p2 = points[i + 1]
            p3 = points[min(n - 1, i + 2)]
            cp1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0, p1.y() + (p2.y() - p0.y()) / 6.0)
            cp2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0, p2.y() - (p3.y() - p1.y()) / 6.0)
            path.cubicTo(cp1, cp2, p2)
        painter.strokePath(path, painter.pen())

    def _draw_crash_slide_background(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        ys = self.projection.y(timeline.note_abs_pos(note), current_position)
        ye = self.projection.y(timeline.note_abs_end_pos(note), current_position)
        xs, ws = self.projection.x(float(note.cell)), self.projection.w(float(note.width))
        xe, we = self.projection.x(float(note.end_cell)), self.projection.w(float(note.end_width))
        painter.setPen(
            QPen(
                self._air_base_note_color(note),
                self.constants.AIR_PATH_WIDTH,
            )
        )
        self._draw_bezier_line(painter, QPointF(xs + ws / 2, ys), QPointF(xe + we / 2, ye))

    def _air_path_endpoints(
        self,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> tuple[QPointF, QPointF]:
        x_start = self.projection.x(float(note.cell)) + self.projection.w(float(note.width)) / 2
        x_end = (
            self.projection.x(float(getattr(note, "end_cell", note.cell)))
            + self.projection.w(float(getattr(note, "end_width", note.width))) / 2
        )
        y_start = self.projection.y(timeline.note_abs_pos(note), current_position)
        y_end = self.projection.y(timeline.note_abs_end_pos(note), current_position)
        y_start -= self._air_height_pixel_offset(float(getattr(note, "starting_height", 1.0)))
        y_end -= self._air_height_pixel_offset(float(getattr(note, "target_height", 1.0)))
        return QPointF(x_start, y_start), QPointF(x_end, y_end)

    def _air_path_head_rect(self, cell: int, width: int, center: QPointF) -> QRectF:
        w = self.projection.w(float(width))
        return QRectF(
            self.projection.x(float(cell)),
            center.y() - self.constants.HEAD_HEIGHT / 2,
            w,
            self.constants.HEAD_HEIGHT,
        )

    def _air_height_pixel_offset(self, height: float) -> float:
        return cast(
            "float",
            timeline_compat.air_height_to_editor_units(height) * self.constants.AIR_SYMBOL_OFFSET,
        )

    def _air_slide_step_role(self, index: int, step_count: int, step: Any) -> str:
        if index == step_count - 1:
            return NOTE_ROLE_END
        if step.note_type == NoteType.ASD:
            return NOTE_ROLE_START
        return NOTE_ROLE_LINE_CONTROL

    def _air_hold_step_role(self, note: Any, timeline: Any | None = None) -> str:
        if note.note_type == NoteType.AHX:
            return NOTE_ROLE_LINE_CONTROL
        return NOTE_ROLE_END

    def _draw_air_action_bar(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if isinstance(note, AirSlideStart):
            target = getattr(note, "target_note", None)
            if not (target and target in {"ASD", "ASC"}):
                self._draw_air_slide_arrow(painter, note, current_position, timeline)
            self._draw_air_slide_step_bars(painter, note, current_position, timeline)
            return

        if not self.visible_note_types.get(note.note_type.value, True):
            return

        if note.note_type != NoteType.ALD:
            target_type = getattr(note, "target_note", None)
            if target_type and (
                any(gn.value == target_type for gn in GROUND_NOTE_TYPES)
                or target_type in {"AIR", "AUR", "AUL", "ADW", "ADR", "ADL", "AHD", "AHX", "DEF"}
            ):
                x_pos = self.projection.x(note.cell)
                width = self.projection.w(note.width)
                y_pos = self.projection.y(timeline.note_abs_pos(note), current_position)
                is_down = target_type in (
                    "ADW",
                    "ADR",
                    "ADL",
                ) or note.note_type in (
                    NoteType.ADW,
                    NoteType.ADR,
                    NoteType.ADL,
                )
                color = self.colors.air_down if is_down else self.colors.air_up
                self._draw_air_arrow_head(painter, note, x_pos, y_pos, width, color)

        is_action = self._air_hold_step_role(note, timeline) == NOTE_ROLE_ACTION
        is_crush = False

        if not is_action:
            if note.note_type == NoteType.ALD:
                is_crush = getattr(note, "crush_interval", 0) > 0
            else:
                is_action = False

        if is_crush:
            self._draw_air_crush_elements(painter, note, current_position, timeline)
        elif note.note_type in (NoteType.ALD, NoteType.AHD, NoteType.AHX, NoteType.ASD, NoteType.ASC):
            self._draw_air_end_bar(painter, note, current_position, timeline)
        elif is_action:
            self._draw_air_joint_bar(painter, note, current_position, timeline)

    def _draw_air_crush_elements(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        duration = getattr(note, "duration", 0)
        crush_interval = getattr(note, "crush_interval", 0)
        if crush_interval <= 0:
            return
        start_tick = timeline.note_tick(note)
        res = timeline.resolution
        for offset_tick in range(0, duration + 1, crush_interval):
            current_abs_tick = start_tick + offset_tick
            progress = offset_tick / duration if duration > 0 else 0
            curr_cell = note.cell + (getattr(note, "end_cell", note.cell) - note.cell) * progress
            curr_width = (
                note.width + (getattr(note, "end_width", note.width) - note.width) * progress
            )
            x_pos = self.projection.x(float(curr_cell))
            width = self.projection.w(float(curr_width))
            y_pos = self.projection.y(current_abs_tick / res, current_position)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(get_action_bar_color()))
            painter.drawRect(
                QRectF(
                    x_pos,
                    y_pos - self.constants.ACTION_BAR_HEIGHT / 2,
                    width,
                    self.constants.ACTION_BAR_HEIGHT,
                )
            )

            class MockDownNote:
                def __init__(self, cell: int, width: int) -> None:
                    self.note_type = NoteType.ADW
                    self.cell = cell
                    self.width = width

            self._draw_air_arrow_head(
                painter,
                MockDownNote(curr_cell, curr_width),
                x_pos,
                y_pos,
                width,
                self.colors.air_down,
            )

    def _draw_air_slide_arrow(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        tick = timeline.note_tick(note)
        chart = getattr(timeline, "chart", None)
        if chart is not None:
            for existing in chart.notes:
                if existing is note:
                    continue
                if existing.note_type not in AIR_ARROW_NOTES:
                    continue
                if (
                    timeline.note_tick(existing) == tick
                    and existing.cell == note.cell
                    and existing.width == note.width
                ):
                    return
        x_pos = self.projection.x(float(note.cell))
        width = self.projection.w(float(note.width))
        y_pos = self.projection.y(timeline.note_abs_pos(note), current_position)

        class _AirSlideArrowNote:
            def __init__(self) -> None:
                self.note_type = NoteType.AIR

        self._draw_air_arrow_head(
            painter,
            _AirSlideArrowNote(),
            x_pos,
            y_pos,
            width,
            self.colors.air_up,
        )

    def _draw_air_wrapper_debug_outline(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        """Draw a debug outline for ASC/ASD wrapper nodes showing wrapped type."""
        y = self.projection.y(timeline.note_abs_pos(note), current_position)
        x = self.projection.x(float(note.cell))
        w = self.projection.w(float(note.width))
        rect = QRectF(x, y - self.constants.HEAD_HEIGHT / 2, w, self.constants.HEAD_HEIGHT)

        # Dashed outline in wrapper color
        wrapper_color = QColor("#c0c0c0")
        wrapper_color.setAlpha(140)
        pen = QPen(wrapper_color, 1.5, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            rect,
            rect.height() * self.constants.CORNER_RADIUS_RATIO,
            rect.height() * self.constants.CORNER_RADIUS_RATIO,
        )

        # Label with wrapped type
        wrapped = getattr(note, "target_note", "?")
        label = f"{note.note_type.value}→{wrapped}"
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#c0c0c0")))
        text_rect = QRectF(x, y - self.constants.HEAD_HEIGHT / 2 - 16, w, 14)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)

    def _draw_air_bar_at(
        self,
        cell: int,
        width: int,
        abs_pos: float,
        painter: QPainter,
        current_position: float,
    ) -> None:
        y = self.projection.y(abs_pos, current_position)
        x = self.projection.x(float(cell))
        w = self.projection.w(float(width))
        h = self.constants.HEAD_HEIGHT
        rect = QRectF(x, y - h / 2, w, h)

        color = get_action_bar_color()
        # Draw as tap-style note head: gradient fill, border, white line
        self._draw_rounded_rect(painter, rect, color)
        self._draw_tap_symbol(painter, rect)

    def _draw_air_end_bar(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        anchor = timeline.note_anchor(note)
        if anchor is not None:
            cell = getattr(anchor, "end_cell", anchor.cell)
            width = getattr(anchor, "end_width", anchor.width)
            abs_pos = timeline.note_abs_end_pos(note)
        else:
            cell = getattr(note, "end_cell", note.cell)
            width = getattr(note, "end_width", note.width)
            abs_pos = timeline.note_abs_end_pos(note)
        NOTE_DEBUG.debug("  air_end_bar: %s cell=%s w=%s pos=%.4f",
                         note.note_type.value, cell, width, abs_pos)
        self._draw_air_bar_at(cell, width, abs_pos, painter, current_position)

    def _draw_air_slide_step_bars(
        self,
        painter: QPainter,
        note: AirSlideStart,
        current_position: float,
        timeline: Any,
    ) -> None:
        abs_pos = timeline.note_abs_pos(note)
        step_count = len(note.steps)
        for index, step in enumerate(note.steps):
            abs_pos += step.duration / timeline.resolution
            # ASC steps (except the last) draw as slim transparent grey control points
            if step.note_type == NoteType.ASC and index != step_count - 1:
                y = self.projection.y(abs_pos, current_position)
                x = self.projection.x(float(step.end_cell))
                w = self.projection.w(float(step.end_width))
                h = self.constants.ACTION_BAR_HEIGHT
                rect = QRectF(x, y - h / 2, w, h)
                radius = rect.height() * self.constants.CORNER_RADIUS_RATIO
                border_color = QColor("#808080")
                border_color.setAlpha(127)
                fill_color = QColor("#808080")
                fill_color.setAlpha(self.constants.CONTROL_POINT_ALPHA)
                painter.setPen(QPen(border_color, 1))
                painter.setBrush(QBrush(fill_color))
                painter.drawRoundedRect(rect, radius, radius)
                continue
            if not self._air_slide_step_draws_bar(index, step_count, step):
                continue
            NOTE_DEBUG.debug("  air_step_bar: step=%d/%d %s cell=%s w=%s pos=%.4f",
                             index, step_count, step.note_type.value,
                             step.end_cell, step.end_width, abs_pos)
            self._draw_air_bar_at(
                step.end_cell,
                step.end_width,
                abs_pos,
                painter,
                current_position,
            )

    def _air_slide_step_draws_bar(
        self,
        index: int,
        step_count: int,
        step: Any,
    ) -> bool:
        # ASD starts the chain and the final segment gets the purple action bar.
        # ASC gets a transparent grey control-point rect (like SLC).
        # The last step always gets a purple action bar regardless of type.
        return step.note_type == NoteType.ASD or index == step_count - 1

    def _air_slide_step_is_control_point(self, step: Any) -> bool:
        """ASC steps that aren't the chain's last step draw as control points."""
        return step.note_type == NoteType.ASC

    def _draw_air_joint_bar(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if note.note_type == NoteType.AHX:
            abs_pos = timeline.note_abs_pos(note)
            cell = note.cell
            width = note.width
        else:
            anchor = timeline.note_anchor(note)
            if anchor:
                abs_pos = timeline.note_abs_end_pos(anchor)
                cell = getattr(anchor, "end_cell", anchor.cell)
                width = getattr(anchor, "end_width", anchor.width)
            else:
                abs_pos = timeline.note_abs_end_pos(note)
                cell = getattr(note, "end_cell", note.cell)
                width = getattr(note, "end_width", note.width)
        self._draw_air_bar_at(cell, width, abs_pos, painter, current_position)
