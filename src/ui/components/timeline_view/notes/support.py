from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QColor, QPainter

    from src.ui.theme.color_profile import ColorProfile, GradientColor
    from src.ui.view.projection import ViewProjection


@dataclass(frozen=True, slots=True)
class SlidePathPoint:
    center: QPointF
    left: QPointF
    right: QPointF
    visible: bool = True


class RendererMixinSupport:
    """Shared renderer contract used by note renderer mixins."""

    projection = cast("ViewProjection", None)
    total_lanes = cast("int", None)
    visible_note_types = cast("dict[str, bool]", None)
    colors = cast("ColorProfile", None)
    constants = cast("Any", None)
    cache = cast("Any", None)

    def _draw_rounded_rect(
        self,
        painter: QPainter,
        rect: QRectF,
        color: GradientColor | QColor,
    ) -> None:
        raise NotImplementedError

    def _draw_tap(
        self,
        painter: QPainter,
        note: Any,
        current_position: float,
        timeline: Any,
        color: GradientColor | QColor,
    ) -> None:
        raise NotImplementedError

    def _draw_tap_symbol(self, painter: QPainter, rect: QRectF) -> None:
        raise NotImplementedError

    def _draw_tap_symbol_for_type(
        self,
        painter: QPainter,
        rect: QRectF,
        symbol_type: str,
    ) -> None:
        raise NotImplementedError

    def _draw_note_base(
        self,
        painter: QPainter,
        rect: QRectF,
        color: GradientColor | QColor,
    ) -> None:
        raise NotImplementedError

    def _draw_border(self, painter: QPainter, rect: QRectF) -> None:
        raise NotImplementedError

    def _air_path_endpoints(
        self,
        note: Any,
        current_position: float,
        timeline: Any,
    ) -> tuple[QPointF, QPointF]:
        raise NotImplementedError

    def _air_path_head_rect(self, cell: int, width: int, center: QPointF) -> QRectF:
        raise NotImplementedError

    def _tap_pixmap_key(
        self,
        color: GradientColor | QColor,
        width: float,
        symbol_type: str,
    ) -> tuple[Any, ...]:
        raise NotImplementedError

    def _has_air_reference_at(
        self,
        tick: int,
        cell: int,
        width: int,
        target_note: str,
        timeline: Any,
    ) -> bool:
        raise NotImplementedError
