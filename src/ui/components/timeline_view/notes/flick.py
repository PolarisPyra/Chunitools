from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QRectF

if TYPE_CHECKING:
    from PySide6.QtGui import QPainter

from src.ui.components.timeline_view.notes.support import RendererMixinSupport


class FlickRendererMixin(RendererMixinSupport):
    def _draw_flick(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> None:
        if not self.visible_note_types.get(note.note_type.value, True):
            return
        y, x, w = (
            self.projection.y(timeline.note_abs_pos(note), current_position),
            self.projection.x(note.cell),
            self.projection.w(note.width),
        )
        rect = QRectF(x, y - self.constants.HEAD_HEIGHT / 2, w, self.constants.HEAD_HEIGHT)

        base_color = self.colors.flick_base
        fg_color = self.colors.flick_foreground
        color_key = (
            base_color.light.rgba(),
            base_color.dark.rgba(),
            fg_color.light.rgba(),
            fg_color.dark.rgba(),
        )
        pixmap_key = ("flick", color_key, w)
        pixmap = self.cache.get_pixmap(
            pixmap_key,
            lambda p, r: self._draw_flick_graphics(p, r, base_color, fg_color),
            w,
            self.constants.HEAD_HEIGHT,
        )
        painter.drawPixmap(rect.topLeft().toPoint(), pixmap)

    def _draw_flick_graphics(
        self,
        painter: QPainter,
        rect: QRectF,
        base_color: Any,
        fg_color: Any,
    ) -> None:
        w = rect.width()
        fg_rect = QRectF(rect.x() + w / 4, rect.y(), w / 2, rect.height())
        self._draw_note_base(painter, rect, base_color)
        self._draw_note_base(painter, fg_rect, fg_color)
        self._draw_border(painter, rect)
        self._draw_tap_symbol(painter, fg_rect)
