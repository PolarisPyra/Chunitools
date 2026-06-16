from __future__ import annotations

# ruff: noqa: PLR0912, PLR0913, PLR0915
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF

from src.core.const import NoteType
from src.ui.components.play_view.geometry import (
    ACTIVE_DEPTH_MAX,
    ACTIVE_DEPTH_MIN,
    DRAW_DEPTH_MAX,
    DRAW_DEPTH_MIN,
    FIELD_HALF,
    LANE_WIDTH,
    NOTE_WIDTH_FRAC,
    RENDER_BIG_NOTE_DEPTH,
    RENDER_NOTE_DEPTH,
    _air_path_world_y,
    _compact_depth_to_z,
    _has_sustain,
    _note_screen_span,
    _project_point,
    _projected_polygon_is_bounded,
    _projection_for_depth,
    _sustain_draw_depths,
)
from src.ui.theme.notes import TRACE_COLORS, get_note_color

if TYPE_CHECKING:
    from src.notes import Note

AIR_WRAPPED_GROUND_TYPES = {
    NoteType.TAP,
    NoteType.CHR,
    NoteType.FLK,
    NoteType.MNE,
    NoteType.HLD,
    NoteType.HXD,
    NoteType.SLD,
    NoteType.SLC,
    NoteType.SXD,
    NoteType.SXC,
}
AIR_WRAPPED_EX_HEAD_TYPES = {NoteType.CHR, NoteType.HXD, NoteType.SXD, NoteType.SXC}


class PlayViewSupportNotesMixin:
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
            depth = self._compute_note_depth(note, tl.note_tick(note), note_time, judge_time)
            end_depth = self._compute_note_depth(note, tl.note_end_tick(note), end_time, judge_time)

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

                scale, screen_y, t = self._world_z_to_screen(depth, vanish_y, judge_y)
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
    def _get_world_y(self, note: Note) -> float:
        wy = _air_path_world_y(note)
        return wy if wy is not None else 0.0
    def _project_flat_note_corners(
        self, note: Note, cell: float, width: float, depth: float
    ) -> list[QPointF]:
        is_big = note.note_type in {NoteType.HLD, NoteType.HXD, NoteType.SLD, NoteType.SXD}
        return self._project_flat_note_corners_at_world_y(
            cell,
            width,
            depth,
            self._get_world_y(note),
            is_big=is_big,
        )
    def _project_flat_note_corners_at_world_y(
        self,
        cell: float,
        width: float,
        depth: float,
        world_y: float,
        *,
        is_big: bool = False,
    ) -> list[QPointF]:
        w, h = self.width(), self.height()
        w_x0 = cell * LANE_WIDTH - FIELD_HALF
        w_x1 = (cell + width) * LANE_WIDTH - FIELD_HALF
        z = _compact_depth_to_z(depth)
        half_depth = (RENDER_BIG_NOTE_DEPTH if is_big else RENDER_NOTE_DEPTH) / 2.0
        z_far = z - half_depth
        z_near = z + half_depth
        pt0 = _project_point(w_x0, world_y, z_far, w, h)
        pt1 = _project_point(w_x1, world_y, z_far, w, h)
        pt2 = _project_point(w_x1, world_y, z_near, w, h)
        pt3 = _project_point(w_x0, world_y, z_near, w, h)
        return [QPointF(*pt0), QPointF(*pt1), QPointF(*pt2), QPointF(*pt3)]
    def _project_sustain_corners(
        self,
        note: Note,
        start_cell: float,
        start_width: float,
        start_depth: float,
        end_cell: float,
        end_width: float,
        end_depth: float,
        *,
        start_world_y: float | None = None,
        end_world_y: float | None = None,
        start_width_factor: float = NOTE_WIDTH_FRAC,
        end_width_factor: float = NOTE_WIDTH_FRAC,
    ) -> list[QPointF]:
        viewport_w, viewport_h = self.width(), self.height()
        start_y = self._get_world_y(note) if start_world_y is None else start_world_y
        end_y = self._get_world_y(note) if end_world_y is None else end_world_y
        start_center = (start_cell + start_width / 2.0) * LANE_WIDTH - FIELD_HALF
        end_center = (end_cell + end_width / 2.0) * LANE_WIDTH - FIELD_HALF
        start_visual_width = start_width * LANE_WIDTH * start_width_factor
        end_visual_width = end_width * LANE_WIDTH * end_width_factor
        start_x0 = start_center - start_visual_width / 2.0
        start_x1 = start_center + start_visual_width / 2.0
        end_x0 = end_center - end_visual_width / 2.0
        end_x1 = end_center + end_visual_width / 2.0
        start_z = _compact_depth_to_z(start_depth)
        end_z = _compact_depth_to_z(end_depth)
        return [
            QPointF(*_project_point(start_x0, start_y, start_z, viewport_w, viewport_h)),
            QPointF(*_project_point(start_x1, start_y, start_z, viewport_w, viewport_h)),
            QPointF(*_project_point(end_x1, end_y, end_z, viewport_w, viewport_h)),
            QPointF(*_project_point(end_x0, end_y, end_z, viewport_w, viewport_h)),
        ]
    def _draw_projected_sustain_body(
        self,
        painter: QPainter,
        note: Note,
        start_cell: float,
        start_width: float,
        start_depth: float,
        end_cell: float,
        end_width: float,
        end_depth: float,
        color: QColor,
        alpha: int,
        *,
        start_world_y: float | None = None,
        end_world_y: float | None = None,
        start_width_factor: float = NOTE_WIDTH_FRAC,
        end_width_factor: float = NOTE_WIDTH_FRAC,
    ) -> None:
        if painter is None:
            return
        corners = self._project_sustain_corners(
            note,
            start_cell,
            start_width,
            start_depth,
            end_cell,
            end_width,
            end_depth,
            start_world_y=start_world_y,
            end_world_y=end_world_y,
            start_width_factor=start_width_factor,
            end_width_factor=end_width_factor,
        )
        if not _projected_polygon_is_bounded(corners, self.width(), self.height()):
            return

        body_color = QColor(color.red(), color.green(), color.blue(), alpha // 3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body_color)
        painter.drawPolygon(QPolygonF(corners))

        start_mid = (corners[0] + corners[1]) * 0.5
        end_mid = (corners[2] + corners[3]) * 0.5
        start_scale = _projection_for_depth(start_depth, self.width(), self.height())[0]
        end_scale = _projection_for_depth(end_depth, self.width(), self.height())[0]
        pen_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
        painter.setPen(QPen(pen_color, max(1, int(min(start_scale, end_scale) * 2))))
        painter.drawLine(start_mid, end_mid)
