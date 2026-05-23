from __future__ import annotations

from src.ui.view import timeline_compat
from src.ui.view.projection import ViewProjection
from src.ui.view.renderer.base import RendererConstants


def test_projection_defaults_match_editor_playfield_geometry() -> None:
    projection = ViewProjection(scroll_speed=1.0)

    assert timeline_compat.LANES == 16
    assert projection.lane_width == 16.0
    assert projection.x(0) == 0.0
    assert projection.x(16) == 256.0
    assert projection.w(4) == 64.0
    assert projection.cell_at(255.9) == 15.99375


def test_projection_defaults_match_editor_tick_linear_vertical_model() -> None:
    projection = ViewProjection(scroll_speed=1.0)

    assert timeline_compat.CHART_RENDER_TICKS_PER_MEASURE == 1920
    assert timeline_compat.chart_tick_to_editor_tick(1, 0, 384) == 1920
    assert timeline_compat.chart_tick_to_editor_tick(0, 120, 384) == 600
    assert projection.measure_height == 96.0
    assert projection.y(1.0, 0.0) == -96.0
    assert projection.y(1.25, 1.0) == -24.0
    assert projection.pos_at(-24.0, 1.0) == 1.25


def test_air_height_conversion_matches_verified_reference_mapping() -> None:
    assert timeline_compat.air_height_to_editor_units(1.0) == 0.0
    assert timeline_compat.air_height_to_editor_units(3.0) == 4.0
    assert timeline_compat.air_height_to_editor_units(5.0) == 8.0


def test_renderer_constants_match_verified_editor_gdiplus_values() -> None:
    constants = RendererConstants()

    assert constants.HEAD_HEIGHT == 12.0
    assert constants.ACTION_BAR_HEIGHT == 6.0
    assert constants.SLIDE_LINE_WIDTH == 2.0
    assert constants.AIR_PATH_WIDTH == 2.0
