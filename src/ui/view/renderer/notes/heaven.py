from __future__ import annotations

from typing import Any

from PySide6.QtGui import QPainter, QPen

from src.core.const import NoteType
from src.ui.theme.notes import get_note_color
from src.ui.view.renderer.notes.support import RendererMixinSupport


class HeavenHoldRendererMixin(RendererMixinSupport):
    def _draw_heaven_hold_background(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        start, end = self._air_path_endpoints(note, current_position, timeline)
        color = get_note_color(note.note_type)
        painter.setPen(QPen(color, self.constants.AIR_PATH_WIDTH * 2.0))
        painter.drawLine(start, end)

    def _draw_heaven_hold_foreground(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        start, end = self._air_path_endpoints(note, current_position, timeline)
        start_rect = self._air_path_head_rect(note.cell, note.width, start)
        end_rect = self._air_path_head_rect(
            getattr(note, "end_cell", note.cell),
            getattr(note, "end_width", note.width),
            end,
        )
        color = self.colors.ex_tap if note.note_type == NoteType.HHX else self.colors.hold
        self._draw_rounded_rect(painter, start_rect, color)
        self._draw_tap_symbol_for_type(
            painter,
            start_rect,
            f"ex:{getattr(note, 'animation', None) or 'UP'}"
            if note.note_type == NoteType.HHX
            else "tap",
        )
        self._draw_rounded_rect(painter, end_rect, self.colors.hold)
        self._draw_tap_symbol(painter, end_rect)
