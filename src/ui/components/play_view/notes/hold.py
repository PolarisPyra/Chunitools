from __future__ import annotations

# ruff: noqa: PLR0912, PLR0913, PLR0915
from typing import TYPE_CHECKING

from PySide6.QtGui import QColor, QPainter

from src.ui.components.play_view.geometry import (
    _depth_in_draw_range,
    _note_screen_span,
    _sustain_draw_depths,
)

if TYPE_CHECKING:
    from src.notes import Note


class PlayViewHoldNotesMixin:
    def _draw_hold(
        self,
        painter: QPainter,
        note: Note,
        x: float,
        y: float,
        w: float,
        scale: float,
        color: QColor,
        alpha: int,
        judge_time: float,
        depth: float,
        end_depth: float,
        vanish_x: float,
        vanish_y: float,
        judge_y: float,
    ) -> None:
        draw_depths = _sustain_draw_depths(depth, end_depth)
        if draw_depths is None:
            return
        draw_depth, draw_end_depth = draw_depths
        if draw_depth != depth:
            scale, y, _ = self._world_z_to_screen(draw_depth, vanish_y, judge_y)
            x, w = _note_screen_span(note.cell, note.width, vanish_x, scale)

        end_scale, end_y, _ = self._world_z_to_screen(draw_end_depth, vanish_y, judge_y)
        end_x, end_w = _note_screen_span(note.cell, note.width, vanish_x, end_scale)

        self._draw_projected_sustain_body(
            painter,
            note,
            note.cell,
            note.width,
            draw_depth,
            note.cell,
            note.width,
            draw_end_depth,
            color,
            alpha,
        )

        if _depth_in_draw_range(depth):
            self._draw_tap_quad(painter, x, y, w, scale, color, alpha, note, draw_depth)
        end_tick = self.chart.timeline.note_end_tick(note) if self.chart else 0
        if (
            _depth_in_draw_range(draw_end_depth)
            and not self._air_replaces_endpoint(note, end_tick, note.cell, note.width)
        ):
            end_color = QColor(color.red(), color.green(), color.blue(), alpha // 2)
            self._draw_tap_quad(
                painter, end_x, end_y, end_w, end_scale, end_color, alpha // 2, note, draw_end_depth
            )
