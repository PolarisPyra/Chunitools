"""Coordinate projection and geometry mapping for the chart view."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.ui.view import timeline_compat

if TYPE_CHECKING:
    from src.engine.timeline import ChartTimeline


@dataclass(slots=True)
class ViewProjection:
    """Encapsulates mapping between chart coordinates and screen pixels."""

    lane_width: float = timeline_compat.LANE_WIDTH
    base_scroll_scale: float = timeline_compat.MEASURE_HEIGHT
    scroll_speed: float = 1.0
    speed_factor: float = 1.0
    timeline_engine: ChartTimeline | None = field(default=None)

    @property
    def measure_height(self) -> float:
        """Effective height of a single measure in pixels."""
        return self.base_scroll_scale * self.scroll_speed * self.speed_factor

    @measure_height.setter
    def measure_height(self, value: float) -> None:
        """Compatibility setter that adjusts base_scroll_scale."""
        denominator = self.scroll_speed * self.speed_factor
        if denominator != 0:
            self.base_scroll_scale = value / denominator
        else:
            self.base_scroll_scale = value

    def x(self, cell: float) -> float:
        """Map chart lane cell to horizontal pixel coordinate."""
        return cell * self.lane_width

    def w(self, width: float) -> float:
        """Map chart lane width to pixel width."""
        return width * self.lane_width

    def y(self, abs_pos: float, current_pos: float = 0.0) -> float:
        """
        Map absolute measure position to vertical pixel coordinate relative to playhead.
        Formula: Y = -(baseScrollScale * timeDelta * ScrollSpeed * chartSpeedFactor)
        """
        time_delta = abs_pos - current_pos
        return -(self.base_scroll_scale * time_delta * self.scroll_speed * self.speed_factor)

    def y_abs(self, abs_pos: float) -> float:
        """Map absolute measure position to a fixed vertical pixel coordinate (anchor at 0.0)."""
        return -abs_pos * self.measure_height

    def pos_at(self, y_px: float, current_pos: float) -> float:
        """Inverse map: vertical pixel to absolute measure position."""
        if self.measure_height == 0:
            return current_pos
        return current_pos - (y_px / self.measure_height)

    def cell_at(self, x_px: float) -> float:
        """Inverse map: horizontal pixel to chart lane cell."""
        return x_px / self.lane_width
