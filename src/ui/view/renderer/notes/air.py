from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from src.core.const import AIR_ARROW_NOTES, GROUND_NOTE_TYPES, NoteType
from src.notes.air import AirSlideStart
from src.ui.theme.color_profile import GradientColor
from src.ui.theme.notes import get_action_bar_color, get_note_color
from src.ui.view import timeline_compat

NOTE_ROLE_START = "ST"
NOTE_ROLE_LINE_CONTROL = "LC"
NOTE_ROLE_ACTION = "EX"
NOTE_ROLE_END = "EN"

AIR_DIRECTION_VALUES = {note_type.value for note_type in AIR_ARROW_NOTES}


class AirRendererMixin:
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
        return QRectF(
            x, y - self.constants.HEAD_HEIGHT / 2, w, self.constants.HEAD_HEIGHT
        )

    def _air_replaces_long_endpoint(self, note: Any, timeline: Any) -> bool:
        target_note = getattr(note, "target_note", "")
        if target_note not in {"HLD", "SLD"}:
            return False
        anchor = timeline.note_anchor(note)
        if not anchor:
            return False
        tick = timeline.note_tick(note)
        return (
            tick == timeline.note_end_tick(anchor)
            and tick != timeline.note_tick(anchor)
        )

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
            if (
                timeline.note_tick(note) == tick
                and note.cell == cell
                and note.width == width
            ):
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

    def _draw_air_arrow_head(
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
            color.rgba()
            if isinstance(color, QColor)
            else (color.light.rgba(), color.dark.rgba())
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
                self.constants.AIR_SUSTAIN_WIDTH,
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
            return
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        ys = self.projection.y(timeline.note_abs_pos(note), current_position)
        ye = self.projection.y(timeline.note_abs_end_pos(note), current_position)
        xs, ws = self.projection.x(float(note.cell)), self.projection.w(
            float(note.width)
        )
        xe, we = self.projection.x(float(note.end_cell)), self.projection.w(
            float(note.end_width)
        )
        painter.setPen(
            QPen(
                self._air_base_note_color(note),
                self.constants.AIR_SUSTAIN_WIDTH,
            )
        )
        painter.drawLine(
            QPointF(xs + ws / 2, ys), QPointF(xe + we / 2, ye)
        )

    def _draw_air_slide_chain(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        master_type = (
            NoteType.ASD
            if note.note_type == NoteType.ASC
            else note.note_type
        )
        if not self.visible_note_types.get(master_type.value, True):
            return
        ct, cc, cw = timeline.note_abs_pos(note), note.cell, note.width
        for step in note.steps:
            ys = self.projection.y(ct, current_position)
            ye = self.projection.y(
                ct + step.duration / timeline.resolution, current_position
            )
            xs = self.projection.x(float(cc))
            ws = self.projection.w(float(cw))
            xe = self.projection.x(float(step.end_cell))
            we = self.projection.w(float(step.end_width))
            painter.setPen(
                QPen(
                    self._air_base_note_color(step),
                    self.constants.AIR_SUSTAIN_WIDTH,
                )
            )
            painter.drawLine(
                QPointF(xs + ws / 2, ys), QPointF(xe + we / 2, ye)
            )
            ct += step.duration / timeline.resolution
            cc, cw = step.end_cell, step.end_width

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
        xs, ws = self.projection.x(float(note.cell)), self.projection.w(
            float(note.width)
        )
        xe, we = self.projection.x(float(note.end_cell)), self.projection.w(
            float(note.end_width)
        )
        painter.setPen(
            QPen(
                self._air_base_note_color(note),
                self.constants.AIR_SUSTAIN_WIDTH,
            )
        )
        painter.drawLine(
            QPointF(xs + ws / 2, ys), QPointF(xe + we / 2, ye)
        )

    def _draw_air_solid_background(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        start, end = self._air_path_endpoints(note, current_position, timeline)
        color = self._air_base_note_color(note)
        fill = QColor(color)
        fill.setAlpha(54)
        painter.setPen(QPen(color, self.constants.AIR_SUSTAIN_WIDTH * 2.5))
        painter.drawLine(start, end)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(fill))
        radius = max(4.0, self.projection.w(float(note.width)) * 0.16)
        painter.drawEllipse(start, radius, radius)
        painter.drawEllipse(end, radius, radius)

    def _air_path_endpoints(
        self,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> tuple[QPointF, QPointF]:
        x_start = (
            self.projection.x(float(note.cell))
            + self.projection.w(float(note.width)) / 2
        )
        x_end = (
            self.projection.x(float(getattr(note, "end_cell", note.cell)))
            + self.projection.w(
                float(getattr(note, "end_width", note.width))
            )
            / 2
        )
        y_start = self.projection.y(
            timeline.note_abs_pos(note), current_position
        )
        y_end = self.projection.y(
            timeline.note_abs_end_pos(note), current_position
        )
        y_start -= self._air_height_pixel_offset(
            float(getattr(note, "starting_height", 1.0))
        )
        y_end -= self._air_height_pixel_offset(
            float(getattr(note, "target_height", 1.0))
        )
        return QPointF(x_start, y_start), QPointF(x_end, y_end)

    def _air_path_head_rect(
        self, cell: int, width: int, center: QPointF
    ) -> QRectF:
        w = self.projection.w(float(width))
        return QRectF(
            self.projection.x(float(cell)),
            center.y() - self.constants.HEAD_HEIGHT / 2,
            w,
            self.constants.HEAD_HEIGHT,
        )

    def _air_height_pixel_offset(self, height: float) -> float:
        return (
            timeline_compat.air_height_to_editor_units(height)
            * self.constants.AIR_SYMBOL_OFFSET
        )

    def _air_slide_step_role(
        self, index: int, step_count: int, step: Any
    ) -> str:
        if step.note_type == NoteType.ASX:
            return NOTE_ROLE_ACTION
        if index == step_count - 1:
            return NOTE_ROLE_END
        if step.note_type == NoteType.ASD:
            return NOTE_ROLE_START
        return NOTE_ROLE_LINE_CONTROL

    def _air_hold_step_role(
        self, note: Any, timeline: Any | None = None
    ) -> str:
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
            if not (target and target in {"ASD", "ASC", "ASX"}):
                self._draw_air_slide_arrow(painter, note, current_position, timeline)
            self._draw_air_slide_step_bars(painter, note, current_position, timeline)
            return

        if not self.visible_note_types.get(note.note_type.value, True):
            return

        if note.note_type != NoteType.ALD:
            target_type = getattr(note, "target_note", None)
            if target_type and (
                any(gn.value == target_type for gn in GROUND_NOTE_TYPES)
                or target_type
                in {"AIR", "AUR", "AUL", "ADW", "ADR", "ADL", "AHD", "AHX", "DEF"}
            ):
                x_pos = self.projection.x(note.cell)
                width = self.projection.w(note.width)
                y_pos = self.projection.y(
                    timeline.note_abs_pos(note), current_position
                )
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
                self._draw_air_arrow_head(
                    painter, note, x_pos, y_pos, width, color
                )

        is_action = self._air_hold_step_role(note, timeline) == NOTE_ROLE_ACTION
        is_crush = False

        if not is_action:
            if note.note_type == NoteType.ALD:
                is_crush = getattr(note, "crush_interval", 0) > 0
            else:
                is_action = False

        if is_crush:
            self._draw_air_crush_elements(
                painter, note, current_position, timeline
            )
        elif note.note_type in (NoteType.AHD, NoteType.ASD, NoteType.ASC, NoteType.ASX):
            self._draw_air_end_bar(painter, note, current_position, timeline)
        elif is_action:
            self._draw_air_joint_bar(
                painter, note, current_position, timeline
            )

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
            curr_cell = note.cell + (
                getattr(note, "end_cell", note.cell) - note.cell
            ) * progress
            curr_width = note.width + (
                getattr(note, "end_width", note.width) - note.width
            ) * progress
            x_pos = self.projection.x(float(curr_cell))
            width = self.projection.w(float(curr_width))
            y_pos = self.projection.y(
                current_abs_tick / res, current_position
            )
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
                def __init__(self, cell, width):
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
                if (timeline.note_tick(existing) == tick
                    and existing.cell == note.cell
                    and existing.width == note.width):
                    return
        x_pos = self.projection.x(float(note.cell))
        width = self.projection.w(float(note.width))
        y_pos = self.projection.y(timeline.note_abs_pos(note), current_position)
        class _AirSlideArrowNote:
            def __init__(self):
                self.note_type = NoteType.AIR
        self._draw_air_arrow_head(
            painter,
            _AirSlideArrowNote(),
            x_pos,
            y_pos,
            width,
            self.colors.air_up,
        )

    def _draw_air_bar_at(
        self,
        cell: int,
        width: int,
        abs_pos: float,
        painter: QPainter,
        current_position: float,
        timeline: Any,
    ) -> None:
        y = self.projection.y(abs_pos, current_position)
        x = self.projection.x(float(cell))
        w = self.projection.w(float(width))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(get_action_bar_color()))
        painter.drawRect(
            QRectF(
                x,
                y - self.constants.ACTION_BAR_HEIGHT / 2,
                w,
                self.constants.ACTION_BAR_HEIGHT,
            )
        )

    def _draw_air_end_bar(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        self._draw_air_bar_at(
            getattr(note, "end_cell", note.cell),
            getattr(note, "end_width", note.width),
            timeline.note_abs_end_pos(note),
            painter,
            current_position,
            timeline,
        )

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
            if not self._air_slide_step_draws_bar(index, step_count, step):
                continue
            self._draw_air_bar_at(
                step.end_cell,
                step.end_width,
                abs_pos,
                painter,
                current_position,
                timeline,
            )

    def _air_slide_step_draws_bar(
        self,
        index: int,
        step_count: int,
        step: Any,
    ) -> bool:
        return (
            step.note_type in {NoteType.ASD, NoteType.ASX}
            or index == step_count - 1
        )

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
        y = self.projection.y(abs_pos, current_position)
        x = self.projection.x(float(cell))
        w = self.projection.w(float(width))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(get_action_bar_color()))
        painter.drawRect(
            QRectF(
                x,
                y - self.constants.ACTION_BAR_HEIGHT / 2,
                w,
                self.constants.ACTION_BAR_HEIGHT,
            )
        )

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
                self.constants.AIR_SUSTAIN_WIDTH,
            )
        )
        painter.drawLine(QPointF(x + w / 2, ys), QPointF(x + w / 2, ye))
