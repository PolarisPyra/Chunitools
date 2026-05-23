"""Clean-room reference-compatible chart geometry constants."""

from __future__ import annotations

LANES = 16
PLAYFIELD_WIDTH = 256.0
LANE_WIDTH = PLAYFIELD_WIDTH / LANES
MEASURE_HEIGHT = 96.0
BEATS_PER_MEASURE = 4.0
CHART_RENDER_TICKS_PER_MEASURE = 1920
NOTE_HEAD_HEIGHT = 12.0
ACTION_BAR_HEIGHT = 6.0
HOLD_STROKE_WIDTH = 2.0
"""Stroke width for hold/air-path lines in the renderer."""
AIR_HEIGHT_MIN = 1.0
AIR_HEIGHT_RANGE = 4.0
AIR_HEIGHT_STEPS = 8.0


def chart_tick_to_editor_tick(measure: int, offset: int, resolution: int) -> int:
    """Convert official chart timing to the renderer's 1920 ticks per measure."""
    if resolution <= 0:
        raise ValueError("resolution must be positive")
    return round(
        measure * CHART_RENDER_TICKS_PER_MEASURE
        + offset / resolution * CHART_RENDER_TICKS_PER_MEASURE
    )


def air_height_to_editor_units(height: float) -> float:
    """Map c2s air height values onto the reference editor's 0-8 vertical air units."""
    return (height - AIR_HEIGHT_MIN) / AIR_HEIGHT_RANGE * AIR_HEIGHT_STEPS
