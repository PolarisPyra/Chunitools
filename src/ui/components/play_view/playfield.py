from __future__ import annotations

# ruff: noqa: PLR0913
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen, QPolygonF

from src.core.const import AIR_NOTE_TYPES
from src.ui.components.play_view.geometry import (
    FIELD_FAR_Z,
    FIELD_HALF,
    FIELD_NEAR_Z,
    FONT_FAMILY,
    JUDGE_LINE_FAR_Z,
    JUDGE_LINE_NEAR_Z,
    LANE_LINE_FAR_Z,
    LANE_LINE_NEAR_Z,
    LANE_WIDTH,
    RENDER_CHART_AIR_HEIGHT_STEPS,
    _air_trace_world_y_from_g0,
    _format_time,
    _project_point,
    _projection_for_depth,
    _scrubber_progress,
)


class PlayViewPlayfieldMixin:
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

