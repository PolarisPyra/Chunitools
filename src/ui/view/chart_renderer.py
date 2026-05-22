from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.core.models import Chart
from src.ui.view.projection import ViewProjection
from src.ui.view.renderer.base import BaseRenderer, create_renderer

class ChartRenderer(BaseRenderer):
    """
    Version-aware proxy renderer that delegates to the consolidated BaseRenderer logic.
    
    This class maintains compatibility with the existing ChartViewport lifecycle
    by lazily instantiating the core engine once the chart context is available.
    """

    def __init__(
        self,
        projection: ViewProjection,
        total_lanes: int = 16,
        visible_note_types: Optional[Dict[str, bool]] = None,
        subdivisions: int = 4,
    ) -> None:
        """Initialize the proxy renderer with its projection and visibility settings."""
        super().__init__(projection, total_lanes, visible_note_types, subdivisions)
        self._delegate: Optional[BaseRenderer] = None

    def draw_notes(self, painter: Any, notes: List[Any], current_position: float) -> None:
        """
        Orchestrate note rendering by delegating to the version-aware engine.
        The engine is lazily instantiated once the chart context is available.
        """
        if not notes or not self.projection.timeline_engine:
            return
        
        if self._delegate is None:
            # Retrieve the chart from the timeline engine to determine the correct version behavior
            chart = self.projection.timeline_engine.chart
            self._delegate = create_renderer(
                chart,
                self.projection,
                self.total_lanes,
                self.visible_note_types,
                self.subdivisions
            )
        
        self._delegate.draw_notes(painter, notes, current_position)

    def draw_lane_lines(self, *args, **kwargs) -> None:
        if self._delegate:
            return self._delegate.draw_lane_lines(*args, **kwargs)
        return super().draw_lane_lines(*args, **kwargs)

    def draw_measure_lines(self, *args, **kwargs) -> None:
        if self._delegate:
            return self._delegate.draw_measure_lines(*args, **kwargs)
        return super().draw_measure_lines(*args, **kwargs)
