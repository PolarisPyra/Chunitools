from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from src.core.const import NoteType
from src.core.models import Chart, ChartMetadata
from src.notes.air import Air, AirHold, AirHoldStart, AirSlide, AirSlideStart, CrashSlide
from src.notes.hold import Hold
from src.notes.slide import Slide, SlideTo
from src.notes.tap import ExTap, Tap
from src.ui.components.play_view import (
    ACTIVE_DEPTH_MAX,
    DRAW_DEPTH_MAX,
    DRAW_DEPTH_MIN,
    FIELD_HALF,
    LANE_UNITS,
    LANE_WIDTH,
    NOTE_WIDTH_FRAC,
    PIXELS_PER_UNIT,
    VISIBLE_DEPTH,
    WORLD_HALF,
    PlayView3D,
    _air_action_world_y_from_g0,
    _air_arrow_screen_span,
    _air_path_screen_span,
    _air_path_world_y,
    _air_trace_width_factor_from_g0,
    _air_trace_world_y_from_g0,
    _chart_air_height_to_g0,
    _clip_air_path_start,
    _compact_depth_to_z,
    _note_screen_span,
    _project_point,
    _projected_note_height,
    _projected_polygon_is_bounded,
    _projection_for_depth,
    _scrubber_progress,
    _scrubber_target_measure,
    _sustain_draw_depths,
    _visible_window,
    _world_depth,
)
from src.ui.theme.notes import get_note_color


class _JudgeLinePainter:
    def __init__(self) -> None:
        self.lines: list[tuple[QColor, QPointF, QPointF, int]] = []
        self._pen = None

    def setBrush(self, *_args) -> None:  # noqa: N802
        pass

    def setPen(self, pen) -> None:  # noqa: N802
        self._pen = pen

    def drawLine(self, start: QPointF, end: QPointF) -> None:  # noqa: N802
        assert self._pen is not None
        self.lines.append((self._pen.color(), start, end, self._pen.width()))


def test_3d_depth_culling_uses_world_units_not_normalized_fraction() -> None:
    window_s = _visible_window(9.0)
    draw_edge_depth = _world_depth(window_s * 0.84, 0.0, window_s)
    beyond_draw_depth = _world_depth(window_s * 1.1, 0.0, window_s)
    passed_depth = _world_depth(-window_s * 0.1, 0.0, window_s)

    assert window_s == pytest.approx(7.0 / 9.0)
    assert draw_edge_depth == pytest.approx(VISIBLE_DEPTH * 0.84)
    assert passed_depth == pytest.approx(VISIBLE_DEPTH * -0.1)
    assert pytest.approx(VISIBLE_DEPTH * 0.84) == DRAW_DEPTH_MAX
    assert draw_edge_depth <= DRAW_DEPTH_MAX
    assert beyond_draw_depth > DRAW_DEPTH_MAX
    assert pytest.approx(VISIBLE_DEPTH * 0.84) == ACTIVE_DEPTH_MAX


def test_note_screen_span_keeps_chart_cell_center_with_game_lane_units() -> None:
    vanish_x = WORLD_HALF * PIXELS_PER_UNIT
    x, width = _note_screen_span(cell=0.0, width=1.0, vanish_x=vanish_x, scale=1.0)

    full_lane_width = LANE_UNITS * PIXELS_PER_UNIT
    assert pytest.approx(1.0) == NOTE_WIDTH_FRAC
    assert width == pytest.approx(full_lane_width * NOTE_WIDTH_FRAC)
    assert x + width / 2.0 == pytest.approx(full_lane_width / 2.0)


def test_sustain_depths_clip_crossing_segments_at_judge_line() -> None:
    start_depth, end_depth = _sustain_draw_depths(-2.0, 8.0)

    assert start_depth == pytest.approx(0.0)
    assert end_depth == pytest.approx(8.0)
    assert _sustain_draw_depths(2.0, 8.0) == pytest.approx((2.0, 8.0))
    assert _sustain_draw_depths(-4.0, -2.0) is None


def test_air_path_start_clipping_interpolates_lane_width_and_height() -> None:
    cell, width, world_y, depth = _clip_air_path_start(
        0.0,
        2.0,
        0.0,
        -2.0,
        4.0,
        4.0,
        200.0,
        6.0,
    )

    assert cell == pytest.approx(1.0)
    assert width == pytest.approx(2.5)
    assert world_y == pytest.approx(50.0)
    assert depth == pytest.approx(0.0)


def test_projection_matches_recovered_camera() -> None:
    left_judge = _project_point(-512.0, 0.0, 0.0, 1280.0, 720.0)
    right_judge = _project_point(512.0, 0.0, 0.0, 1280.0, 720.0)
    left_far = _project_point(-512.0, 0.0, -5120.0, 1280.0, 720.0)
    right_far = _project_point(512.0, 0.0, -5120.0, 1280.0, 720.0)

    assert left_judge == pytest.approx((249.252136, 663.690002))
    assert right_judge == pytest.approx((1030.747864, 663.690002))
    assert left_far == pytest.approx((562.726243, 86.924312))
    assert right_far == pytest.approx((717.273757, 86.924312))
    assert right_judge[0] - left_judge[0] > right_far[0] - left_far[0]


def test_depth_projection_and_note_height_use_render_units() -> None:
    scale, screen_y, depth_ratio = _projection_for_depth(0.0, 1280.0, 720.0)

    assert scale == pytest.approx(0.763179)
    assert screen_y == pytest.approx(663.690002)
    assert depth_ratio == pytest.approx(0.0)
    assert _projected_note_height(0.0, 1280.0, 720.0) == pytest.approx(61.953792)


def test_3d_sustain_body_corners_stay_on_projected_lane_edges() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    view = PlayView3D()
    view.resize(1280, 720)
    note = Hold(
        note_type=NoteType.HLD,
        measure=0,
        offset=0,
        cell=2,
        width=3,
        duration=384,
    )

    corners = view._project_sustain_corners(
        note,
        start_cell=2.0,
        start_width=3.0,
        start_depth=2.0,
        end_cell=2.0,
        end_width=3.0,
        end_depth=8.0,
    )

    lane_left = 2.0 * LANE_WIDTH - FIELD_HALF
    lane_right = 5.0 * LANE_WIDTH - FIELD_HALF
    expected_points = [
        _project_point(lane_left, 0.0, _compact_depth_to_z(2.0), 1280.0, 720.0),
        _project_point(lane_right, 0.0, _compact_depth_to_z(2.0), 1280.0, 720.0),
        _project_point(lane_right, 0.0, _compact_depth_to_z(8.0), 1280.0, 720.0),
        _project_point(lane_left, 0.0, _compact_depth_to_z(8.0), 1280.0, 720.0),
    ]
    for corner, expected in zip(corners, expected_points, strict=True):
        assert corner.x() == pytest.approx(expected[0])
        assert corner.y() == pytest.approx(expected[1])


def test_3d_ground_judge_line_is_gold_without_air_notes() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[Tap(note_type=NoteType.TAP, measure=0, offset=0, cell=4, width=4)],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)
    painter = _JudgeLinePainter()

    view._draw_judge_line(painter)

    assert len(painter.lines) == 1
    color, _start, _end, width = painter.lines[0]
    assert color.red() > 240
    assert 180 < color.green() < color.red()
    assert color.blue() < 80
    assert width == 1


def test_3d_air_judge_line_is_green_above_gold_ground_line() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[
            Tap(note_type=NoteType.TAP, measure=0, offset=0, cell=4, width=4),
            Air(
                note_type=NoteType.AIR,
                measure=0,
                offset=0,
                cell=4,
                width=4,
                target_note="TAP",
            ),
        ],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)
    painter = _JudgeLinePainter()

    view._draw_judge_line(painter)

    assert len(painter.lines) == 2
    ground_color, ground_start, _ground_end, _ground_width = painter.lines[0]
    air_color, air_start, _air_end, air_width = painter.lines[1]
    assert ground_color.red() > air_color.red()
    assert air_color.green() > 240
    assert air_color.green() > air_color.red()
    assert air_color.green() > air_color.blue()
    assert air_start.y() < ground_start.y()
    assert air_width == 1


def test_air_height_mapping_uses_g0_and_trace_units() -> None:
    assert _chart_air_height_to_g0(1.0) == pytest.approx(0.0)
    assert _chart_air_height_to_g0(5.0) == pytest.approx(8.0)
    assert _air_action_world_y_from_g0(0.0) == pytest.approx(-233.0)
    assert _air_action_world_y_from_g0(8.0) == pytest.approx(0.0)
    assert _air_trace_world_y_from_g0(8.0) == pytest.approx(233.0)
    assert _air_trace_width_factor_from_g0(0.0) == pytest.approx(1.0)
    assert _air_trace_width_factor_from_g0(8.0) == pytest.approx(0.875)
    assert _air_trace_width_factor_from_g0(16.0) == pytest.approx(0.75)


def test_air_visual_widths_use_render_mesh_scale_table() -> None:
    vanish_x = WORLD_HALF * PIXELS_PER_UNIT

    arrow_x, arrow_w = _air_arrow_screen_span(cell=4.0, width=1.0, vanish_x=vanish_x, scale=1.0)
    path_x, path_w = _air_path_screen_span(cell=4.0, width=1.0, vanish_x=vanish_x, scale=1.0)
    wide_path_x, wide_path_w = _air_path_screen_span(
        cell=0.0, width=16.0, vanish_x=vanish_x, scale=1.0
    )

    assert arrow_w == pytest.approx(64.0 * 0.4)
    assert path_w == pytest.approx(64.0 * 0.734375)
    assert arrow_x + arrow_w / 2.0 == pytest.approx(path_x + path_w / 2.0)
    assert wide_path_x == pytest.approx((1024.0 - 1024.0 * 0.87) / 2.0)
    assert wide_path_w == pytest.approx(1024.0 * 0.87)


def test_air_arrow_screen_span_at_anchor_uses_target_note_span() -> None:
    from src.core.metadata import parse_c2s

    app = QApplication.instance() or QApplication([])
    _ = app

    chart = parse_c2s(
        "\n".join(
            [
                "SLD\t0\t0\t4\t2\t96\t10\t2",
                "AIR\t0\t96\t10\t2\tSLD\tDEF",
            ]
        )
    )
    view = PlayView3D()
    view.chart = chart
    note = next(n for n in chart.notes if n.note_type == NoteType.AIR)
    vanish_x = 0.0

    x, width = view._air_arrow_screen_span_at_anchor(note, vanish_x, 1.0)

    assert (x, width) == _air_arrow_screen_span(10.0, 2.0, vanish_x, 1.0)


def test_play_view_air_color_uses_own_color_for_anchored_air_note() -> None:
    from src.core.metadata import parse_c2s

    app = QApplication.instance() or QApplication([])
    _ = app

    chart = parse_c2s(
        "\n".join(
            [
                "SLD\t0\t0\t4\t2\t96\t10\t2",
                "AIR\t0\t96\t10\t2\tSLD\tDEF",
            ]
        )
    )
    view = PlayView3D()
    view.chart = chart
    air = next(n for n in chart.notes if n.note_type == NoteType.AIR)

    assert view._get_note_color(air).rgba() == get_note_color(NoteType.AIR).rgba()


def test_air_paths_use_explicit_chart_heights_not_default_fake_g0() -> None:
    trace = CrashSlide(
        note_type=NoteType.ALD,
        measure=1,
        offset=0,
        cell=0,
        width=4,
        crush_interval=0,
        starting_height=1.0,
        duration=192,
        end_cell=4,
        end_width=4,
        target_height=5.0,
        color="CYN",
    )
    assert _air_path_world_y(trace) == pytest.approx(0.0)
    assert _air_path_world_y(trace, end=True) == pytest.approx(233.0)

    step = AirSlide(
        note_type=NoteType.ASD,
        measure=1,
        offset=0,
        cell=0,
        width=4,
        target_note="TAP",
        starting_height=1.0,
        duration=192,
        end_cell=4,
        end_width=4,
        target_height=3.0,
        color="DEF",
    )
    chain = AirSlideStart(
        note_type=NoteType.ASD,
        measure=1,
        offset=0,
        cell=0,
        width=4,
        steps=(step,),
    )
    assert _air_path_world_y(chain) == pytest.approx(0.0)
    assert _air_path_world_y(chain, end=True) == pytest.approx(116.5)


def test_air_slide_endpoint_bar_uses_trace_height(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    step = AirSlide(
        note_type=NoteType.ASD,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="CHR",
        starting_height=5.0,
        duration=1,
        end_cell=0,
        end_width=4,
        target_height=6.0,
        color="DEF",
    )
    chain = AirSlideStart(
        note_type=NoteType.ASD,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        steps=(step,),
    )
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]), notes=[chain])
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    assert _air_path_world_y(chain) == pytest.approx(233.0)
    assert _air_path_world_y(chain, end=True) == pytest.approx(291.25)

    action_bars: list[tuple[float, float]] = []
    monkeypatch.setattr(view, "_draw_tap_quad", lambda *args, **kwargs: None)
    monkeypatch.setattr(view, "_draw_extap_quad", lambda *args, **kwargs: None)
    monkeypatch.setattr(view, "_draw_air_path_line", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(
        view,
        "_draw_air_action_bar_3d",
        lambda _painter, _cell, _width, world_y, _alpha, depth: action_bars.append(
            (world_y, depth)
        ),
    )

    tl = chart.timeline
    judge_time = tl.time_at(1)
    depth = view._compute_depth(tl.time_at(0), judge_time)
    view._draw_air_slide_steps(
        None,
        chain,
        0.0,
        0.0,
        1.0,
        1.0,
        QColor("green"),
        255,
        judge_time,
        depth,
        640.0,
        72.0,
        648.0,
    )

    expected_depth = view._compute_depth(tl.time_at(1), judge_time)
    expected_world_y = _air_path_world_y(chain, end=True)

    assert action_bars[-1] == (pytest.approx(expected_world_y), pytest.approx(expected_depth))
    assert len(action_bars) == 1


def test_air_action_bar_uses_flat_world_projection_like_tap_notes() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    view = PlayView3D()
    view.resize(1280, 720)
    tap = Tap(note_type=NoteType.TAP, measure=0, offset=0, cell=4, width=4)
    depth = -0.05

    tap_corners = view._project_flat_note_corners(tap, 4.0, 4.0, depth)
    action_corners = view._project_flat_note_corners_at_world_y(4.0, 4.0, depth, 0.0)

    assert len(action_corners) == 4
    for action_corner, tap_corner in zip(action_corners, tap_corners, strict=True):
        assert action_corner.x() == pytest.approx(tap_corner.x())
        assert action_corner.y() == pytest.approx(tap_corner.y())


def test_air_slide_final_action_step_draws_one_3d_bar(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    step = AirSlide(
        note_type=NoteType.ASC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="TAP",
        starting_height=5.0,
        duration=1,
        end_cell=0,
        end_width=4,
        target_height=6.0,
        color="DEF",
    )
    chain = AirSlideStart(
        note_type=NoteType.ASD,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        steps=(step,),
    )
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]), notes=[chain])
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    action_bars: list[tuple[float, float]] = []
    monkeypatch.setattr(view, "_draw_tap_quad", lambda *args, **kwargs: None)
    monkeypatch.setattr(view, "_draw_air_path_line", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(
        view,
        "_draw_air_action_bar_3d",
        lambda _painter, _cell, _width, world_y, _alpha, depth: action_bars.append(
            (world_y, depth)
        ),
    )

    tl = chart.timeline
    judge_time = tl.time_at(1)
    depth = view._compute_depth(tl.time_at(0), judge_time)
    view._draw_air_slide_steps(
        None,
        chain,
        0.0,
        0.0,
        1.0,
        1.0,
        QColor("green"),
        255,
        judge_time,
        depth,
        640.0,
        72.0,
        648.0,
    )

    assert len(action_bars) == 1


def test_parented_asc_start_arrow_uses_ground_chr_anchor(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    parent = ExTap(note_type=NoteType.CHR, measure=0, offset=0, cell=0, width=4, unknown="UP")
    step = AirSlide(
        note_type=NoteType.ASC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="CHR",
        starting_height=5.0,
        duration=1,
        end_cell=0,
        end_width=4,
        target_height=6.0,
        color="DEF",
    )
    chain = AirSlideStart(
        note_type=NoteType.ASC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        steps=(step,),
        parent=parent,
    )
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]), notes=[chain, parent])
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    drawn: list[tuple[float, float, float, NoteType]] = []
    monkeypatch.setattr(
        view,
        "_draw_air_arrow",
        lambda _painter, x, y, width, _scale, _color, _alpha, nt: drawn.append((x, y, width, nt)),
    )

    vanish_x = 640.0
    vanish_y = 72.0
    judge_y = 648.0
    scale, _, _ = _projection_for_depth(0.0, 1280.0, 720.0)
    path_y = view._air_path_screen_y(chain, 0.0)
    path_x, path_w = _air_path_screen_span(chain.cell, chain.width, vanish_x, scale)

    view._draw_air_start_arrow_if_needed(
        None,
        chain,
        path_x,
        path_y,
        path_w,
        scale,
        255,
        0.0,
        vanish_x,
        vanish_y,
        judge_y,
        0.0,
    )

    # Start arrows on ground-note targets render at ground level, not
    # at the air hold/slide's elevated height. The green stem lifts from
    # the ground-note arrow upward.
    _, ground_y, _ = _projection_for_depth(0.0, 1280.0, 720.0)
    assert drawn == [
        (
            pytest.approx(_air_arrow_screen_span(0.0, 4.0, vanish_x, scale)[0]),
            pytest.approx(ground_y),
            pytest.approx(_air_arrow_screen_span(0.0, 4.0, vanish_x, scale)[1]),
            NoteType.AIR,
        )
    ]


def test_parented_asc_chain_does_not_draw_floating_end_cap(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    parent = ExTap(note_type=NoteType.CHR, measure=0, offset=0, cell=0, width=4, unknown="UP")
    step = AirSlide(
        note_type=NoteType.ASC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="CHR",
        starting_height=5.0,
        duration=1,
        end_cell=0,
        end_width=4,
        target_height=6.0,
        color="DEF",
    )
    chain = AirSlideStart(
        note_type=NoteType.ASC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        steps=(step,),
        parent=parent,
    )
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]), notes=[chain, parent])
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    tap_quads: list[object] = []
    action_bars: list[tuple[float, float]] = []
    monkeypatch.setattr(view, "_draw_tap_quad", lambda *args: tap_quads.append(args))
    monkeypatch.setattr(view, "_draw_extap_quad", lambda *args: tap_quads.append(args))
    monkeypatch.setattr(view, "_draw_air_path_line", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(
        view,
        "_draw_air_action_bar_3d",
        lambda _painter, _cell, _width, world_y, _alpha, depth: action_bars.append(
            (world_y, depth)
        ),
    )

    tl = chart.timeline
    judge_time = tl.time_at(1)
    depth = view._compute_depth(tl.time_at(0), judge_time)
    view._draw_air_slide_steps(
        None,
        chain,
        0.0,
        0.0,
        1.0,
        1.0,
        QColor("green"),
        255,
        judge_time,
        depth,
        640.0,
        72.0,
        648.0,
    )

    assert tap_quads == []
    assert action_bars


def test_ahd_hold_draws_vertical_lift_from_ground_anchor(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    parent = Tap(note_type=NoteType.TAP, measure=0, offset=0, cell=0, width=4)
    air_hold = AirHoldStart(
        note_type=NoteType.AHD,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="TAP",
        duration=96,
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[parent, air_hold],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    lifts: list[tuple[float, float, float]] = []
    monkeypatch.setattr(view, "_draw_sustain_body", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_action_bar_3d", lambda *args: None)
    monkeypatch.setattr(
        view,
        "_draw_air_lift_connector",
        lambda _painter, _x, y_bottom, y_top, w, *_args: lifts.append((y_bottom, y_top, w)),
    )

    view._draw_air_hold_segment(
        None,
        air_hold,
        0.0,
        0.0,
        1.0,
        1.0,
        QColor("green"),
        255,
        0.0,
        0.0,
        2.0,
        640.0,
        72.0,
        648.0,
        is_start=True,
    )

    assert lifts
    assert lifts[0][0] > lifts[0][1]
    assert lifts[0][2] > 0.0


def test_air_lift_connector_overlaps_sustain_start(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    parent = Tap(note_type=NoteType.TAP, measure=0, offset=0, cell=0, width=4)
    air_hold = AirHoldStart(
        note_type=NoteType.AHD,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="TAP",
        duration=96,
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[parent, air_hold],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    vanish_x = 640.0
    vanish_y = 72.0
    judge_y = 648.0
    depth = 0.0
    path_world_y = _air_path_world_y(air_hold)
    _, path_y, _, _ = view._air_path_screen_span_at(
        air_hold.cell,
        air_hold.width,
        depth,
        path_world_y,
        vanish_x,
        vanish_y,
        judge_y,
    )
    lifts: list[tuple[float, float]] = []
    monkeypatch.setattr(
        view,
        "_draw_air_lift_connector",
        lambda _painter, _x, y_bottom, y_top, *_args: lifts.append((y_bottom, y_top)),
    )

    view._draw_air_lift_if_needed(
        None,
        air_hold,
        float(air_hold.cell),
        float(air_hold.width),
        depth,
        path_world_y,
        vanish_x,
        vanish_y,
        judge_y,
        QColor("green"),
        255,
    )

    assert lifts
    assert lifts[0][0] > path_y
    assert lifts[0][1] < path_y


def test_ahd_start_arrow_uses_ground_anchor(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    parent = Tap(note_type=NoteType.TAP, measure=0, offset=0, cell=0, width=4)
    air_hold = AirHoldStart(
        note_type=NoteType.AHD,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="TAP",
        duration=96,
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[parent, air_hold],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    drawn: list[tuple[float, float, float, NoteType]] = []
    monkeypatch.setattr(
        view,
        "_draw_air_arrow",
        lambda _painter, x, y, width, _scale, _color, _alpha, nt: drawn.append((x, y, width, nt)),
    )

    vanish_x = 640.0
    vanish_y = 72.0
    judge_y = 648.0
    scale, _, _ = _projection_for_depth(0.0, 1280.0, 720.0)
    path_x, path_w = _air_path_screen_span(air_hold.cell, air_hold.width, vanish_x, scale)
    path_y = view._air_path_screen_y(air_hold, 0.0)

    view._draw_air_start_arrow_if_needed(
        None,
        air_hold,
        path_x,
        path_y,
        path_w,
        scale,
        255,
        0.0,
        vanish_x,
        vanish_y,
        judge_y,
        0.0,
    )

    # Start arrows on ground-note targets render at ground level, not
    # at the air hold/slide's elevated height. The green stem lifts from
    # the ground-note arrow upward.
    _, ground_y, _ = _projection_for_depth(0.0, 1280.0, 720.0)
    assert drawn == [
        (
            pytest.approx(_air_arrow_screen_span(0.0, 4.0, vanish_x, scale)[0]),
            pytest.approx(ground_y),
            pytest.approx(_air_arrow_screen_span(0.0, 4.0, vanish_x, scale)[1]),
            NoteType.AIR,
        )
    ]


def test_ahx_independent_hold_draws_green_lift_from_ground(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    air_action = AirHold(
        note_type=NoteType.AHX,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="SLD",
        duration=96,
        color="DEF",
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[air_action],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    lifts: list[tuple[float, float, int]] = []
    bodies: list[QColor] = []
    monkeypatch.setattr(
        view,
        "_draw_air_lift_connector",
        lambda _painter, _x, y_bottom, y_top, _w, _scale, color, *_args: lifts.append(
            (y_bottom, y_top, color.rgba())
        ),
    )
    monkeypatch.setattr(
        view,
        "_draw_projected_sustain_body",
        lambda _painter, *_args, **_kwargs: bodies.append(_args[7]),
    )
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_action_bar_3d", lambda *args: None)

    view._draw_air_hold_segment(
        None,
        air_action,
        0.0,
        0.0,
        1.0,
        1.0,
        QColor("#33ff55"),
        255,
        0.0,
        0.0,
        2.0,
        640.0,
        72.0,
        648.0,
        is_start=True,
    )

    assert lifts
    assert lifts[0][0] > lifts[0][1]
    assert lifts[0][2] == QColor("#33ff55").rgba()
    assert bodies and bodies[0].rgba() == QColor("#33ff55").rgba()


def test_ahx_3d_dispatch_uses_green_sustain_and_start_arrow(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    air_action = AirHold(
        note_type=NoteType.AHX,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="SLD",
        duration=96,
        color="DEF",
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[air_action],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    calls: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        view,
        "_draw_air_hold_segment",
        lambda _painter, _note, _x, _y, _w, _scale, color, _alpha, *_args, is_start: calls.append(
            (color.rgba(), is_start)
        ),
    )

    view._draw_note(
        None,
        air_action,
        0.0,
        0.0,
        1.0,
        1.0,
        255,
        0.0,
        0.0,
        2.0,
        640.0,
        72.0,
        648.0,
    )

    assert calls == [(QColor("#33ff55").rgba(), True)]


def test_ahx_3d_hold_has_no_terminal_action_bar(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    air_action = AirHold(
        note_type=NoteType.AHX,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="CHR",
        duration=384,
        color="DEF",
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[air_action],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    action_bars = []
    monkeypatch.setattr(view, "_draw_air_lift_connector", lambda *args: None)
    monkeypatch.setattr(view, "_draw_sustain_body", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(
        view,
        "_draw_air_action_bar_3d",
        lambda *args: action_bars.append(args),
    )

    view._draw_air_hold_segment(
        None,
        air_action,
        0.0,
        0.0,
        1.0,
        1.0,
        QColor("#33ff55"),
        255,
        0.0,
        0.0,
        2.0,
        640.0,
        72.0,
        648.0,
        is_start=True,
    )

    assert action_bars == []


def test_ahx_independent_start_arrow_uses_ground_anchor(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    air_action = AirHold(
        note_type=NoteType.AHX,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="SLD",
        duration=96,
        color="DEF",
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[air_action],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    drawn: list[tuple[float, float, float, NoteType]] = []
    monkeypatch.setattr(
        view,
        "_draw_air_arrow",
        lambda _painter, x, y, width, _scale, _color, _alpha, nt: drawn.append((x, y, width, nt)),
    )

    vanish_x = 640.0
    vanish_y = 72.0
    judge_y = 648.0
    scale, _, _ = _projection_for_depth(0.0, 1280.0, 720.0)
    path_x, path_w = _air_path_screen_span(air_action.cell, air_action.width, vanish_x, scale)
    path_y = view._air_path_screen_y(air_action, 0.0)

    view._draw_air_start_arrow_if_needed(
        None,
        air_action,
        path_x,
        path_y,
        path_w,
        scale,
        255,
        0.0,
        vanish_x,
        vanish_y,
        judge_y,
        0.0,
    )

    # Start arrows on ground-note targets render at ground level, not
    # at the air hold/slide's elevated height. The green stem lifts from
    # the ground-note arrow upward.
    _, ground_y, _ = _projection_for_depth(0.0, 1280.0, 720.0)
    assert drawn == [
        (
            pytest.approx(_air_arrow_screen_span(0.0, 4.0, vanish_x, scale)[0]),
            pytest.approx(ground_y),
            pytest.approx(_air_arrow_screen_span(0.0, 4.0, vanish_x, scale)[1]),
            NoteType.AIR,
        )
    ]


def test_parented_asc_chain_starts_path_from_chr_anchor(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    parent = ExTap(note_type=NoteType.CHR, measure=0, offset=0, cell=0, width=4, unknown="UP")
    step = AirSlide(
        note_type=NoteType.ASC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="CHR",
        starting_height=5.0,
        duration=1,
        end_cell=0,
        end_width=4,
        target_height=6.0,
        color="DEF",
    )
    chain = AirSlideStart(
        note_type=NoteType.ASC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        steps=(step,),
        parent=parent,
    )
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]), notes=[chain, parent])
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    projected_world_y: list[float | None] = []
    original_project = view._air_path_screen_span_at

    def record_projection(*args):
        projected_world_y.append(args[3])
        return original_project(*args)

    monkeypatch.setattr(view, "_air_path_screen_span_at", record_projection)
    monkeypatch.setattr(view, "_draw_air_lift_connector", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_path_line", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_action_bar_3d", lambda *args: None)

    tl = chart.timeline
    judge_time = tl.time_at(1)
    depth = view._compute_depth(tl.time_at(0), judge_time)
    view._draw_air_slide_steps(
        None,
        chain,
        0.0,
        0.0,
        1.0,
        1.0,
        QColor("green"),
        255,
        judge_time,
        depth,
        640.0,
        72.0,
        648.0,
    )

    assert projected_world_y == [
        pytest.approx(_air_path_world_y(chain)),
        pytest.approx(0.0),
    ]


def test_timeline_anchored_chr_air_slide_does_not_draw_fake_start_cap(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    parent = ExTap(note_type=NoteType.CHR, measure=0, offset=0, cell=0, width=4, unknown="UP")
    step = AirSlide(
        note_type=NoteType.ASC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="CHR",
        starting_height=5.0,
        duration=1,
        end_cell=0,
        end_width=4,
        target_height=6.0,
        color="DEF",
    )
    chain = AirSlideStart(
        note_type=NoteType.ASC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        steps=(step,),
    )
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]), notes=[chain, parent])
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    drawn_caps: list[NoteType] = []
    monkeypatch.setattr(
        view,
        "_draw_tap_quad",
        lambda _painter, *_args, **_kwargs: drawn_caps.append(_args[6].note_type),
    )
    monkeypatch.setattr(
        view,
        "_draw_extap_quad",
        lambda _painter, *_args, **_kwargs: drawn_caps.append(_args[6].note_type),
    )
    monkeypatch.setattr(view, "_draw_air_lift_connector", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_path_line", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_action_bar_3d", lambda *args: None)

    tl = chart.timeline
    judge_time = tl.time_at(1)
    depth = view._compute_depth(tl.time_at(0), judge_time)
    view._draw_air_slide_steps(
        None,
        chain,
        0.0,
        0.0,
        1.0,
        1.0,
        QColor("green"),
        255,
        judge_time,
        depth,
        640.0,
        72.0,
        648.0,
    )

    assert tl.note_anchor(chain) is parent
    assert drawn_caps == []


def test_air_lift_connector_uses_full_ribbon_width(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    view = PlayView3D()
    view.resize(1280, 720)
    image = QImage(QSize(1280, 720), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    polygons: list[list[tuple[float, float]]] = []

    original_draw_polygon = painter.drawPolygon

    def record_polygon(poly):
        polygons.append([(poly.at(i).x(), poly.at(i).y()) for i in range(poly.count())])
        original_draw_polygon(poly)

    monkeypatch.setattr(painter, "drawPolygon", record_polygon)
    try:
        view._draw_air_lift_connector(
            painter,
            x=100.0,
            y_bottom=500.0,
            y_top=300.0,
            w=80.0,
            scale=1.0,
            color=QColor("green"),
            alpha=240,
        )
    finally:
        painter.end()

    assert polygons[0] == [
        (100.0, 500.0),
        (180.0, 500.0),
        (180.0, 300.0),
        (100.0, 300.0),
    ]


def test_parented_air_arrow_draws_after_ground_anchor(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    parent = ExTap(note_type=NoteType.CHR, measure=0, offset=0, cell=4, width=4, unknown="UP")
    air = Air(
        note_type=NoteType.AUL,
        measure=0,
        offset=0,
        cell=4,
        width=4,
        target_note="CHR",
        parent=parent,
    )
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]), notes=[air, parent])
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    draw_order: list[str] = []
    monkeypatch.setattr(view, "_draw_extap_quad", lambda *args: draw_order.append("chr"))
    monkeypatch.setattr(view, "_draw_air_arrow", lambda *args: draw_order.append("air"))

    view._draw_notes(None, 0.0)

    assert draw_order == ["chr", "air"]


def test_3d_slide_steps_skip_slc_control_heads(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    first = SlideTo(
        note_type=NoteType.SLC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        duration=96,
        end_cell=4,
        end_width=4,
    )
    second = SlideTo(
        note_type=NoteType.SLC,
        measure=0,
        offset=96,
        cell=4,
        width=4,
        duration=96,
        end_cell=8,
        end_width=4,
    )
    slide = Slide(
        note_type=NoteType.SLC,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        steps=(first, second),
    )
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]), notes=[slide])
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)

    drawn_cells: list[float | None] = []
    monkeypatch.setattr(view, "_draw_sustain_body", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        view,
        "_draw_tap_quad",
        lambda *args, **kwargs: drawn_cells.append(kwargs.get("cell")),
    )

    view._draw_slide_steps(
        None,
        slide,
        0.0,
        0.0,
        1.0,
        1.0,
        QColor("green"),
        255,
        0.0,
        0.0,
        640.0,
        72.0,
        648.0,
    )

    assert 4 not in drawn_cells


def test_scrubber_uses_timeline_seconds_but_seeks_back_to_measure_positions() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    timeline = chart.timeline

    progress, current_seconds, total_seconds = _scrubber_progress(4.0, timeline)

    assert timeline.calculate_max_measure() == 8
    assert total_seconds == pytest.approx(16.0)
    assert current_seconds == pytest.approx(8.0)
    assert progress == pytest.approx(0.5)
    assert _scrubber_target_measure(0.25, timeline) == pytest.approx(2.0)


def test_3d_wheel_scroll_uses_2d_timeline_measure_delta() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    view = PlayView3D()
    view.draw_chart(chart)
    view.set_total_measures(8.0)
    view.set_current_pos(1.0)
    seen: list[float] = []
    view.user_seeked.connect(seen.append)

    view._scroll_by_delta(120.0)

    expected_pos = 1.0 + 100.0 / view.measure_height
    assert view.current_pos == pytest.approx(expected_pos)
    assert seen == [pytest.approx(expected_pos)]


def test_3d_wheel_scroll_clamps_to_timeline_bounds() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    view = PlayView3D()
    view.set_total_measures(2.0)
    view.set_current_pos(4.95)

    view._scroll_by_delta(1200.0)

    assert view.current_pos == pytest.approx(5.0)


def test_play_view_3d_renders_synthetic_chart_offscreen() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[
            Tap(note_type=NoteType.TAP, measure=0, offset=96, cell=4, width=4),
            CrashSlide(
                note_type=NoteType.ALD,
                measure=0,
                offset=192,
                cell=8,
                width=4,
                crush_interval=0,
                starting_height=1.0,
                duration=192,
                end_cell=10,
                end_width=4,
                target_height=5.0,
                color="CYN",
            ),
        ],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)
    view.set_current_pos(0.0)

    image = QImage(QSize(1280, 720), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    view.render(image)

    assert image.pixelColor(640, 650).alpha() > 0


def test_projected_polygon_guard_rejects_screen_flash_geometry() -> None:
    normal = [
        QPointF(249.0, 108.0),
        QPointF(1031.0, 108.0),
        QPointF(1031.0, 664.0),
        QPointF(249.0, 664.0),
    ]
    exploding = [
        QPointF(-20000.0, -20000.0),
        QPointF(20000.0, -20000.0),
        QPointF(20000.0, 20000.0),
        QPointF(-20000.0, 20000.0),
    ]

    assert _projected_polygon_is_bounded(normal, 1280.0, 720.0)
    assert not _projected_polygon_is_bounded(exploding, 1280.0, 720.0)


def test_play_view_3d_skips_exploding_air_crush_body_polygon(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    view = PlayView3D()
    view.resize(1280, 720)
    note = CrashSlide(
        note_type=NoteType.ALD,
        measure=0,
        offset=0,
        cell=4,
        width=4,
        crush_interval=0,
        starting_height=1.0,
        duration=192,
        end_cell=8,
        end_width=4,
        target_height=5.0,
        color="RED",
    )
    calls: list[str] = []

    class FakePainter:
        def setPen(self, *_args) -> None:
            calls.append("pen")

        def setBrush(self, *_args) -> None:
            calls.append("brush")

        def drawPolygon(self, *_args) -> None:
            calls.append("polygon")

        def drawLine(self, *_args) -> None:
            calls.append("line")

    monkeypatch.setattr(
        view,
        "_project_sustain_corners",
        lambda *_args, **_kwargs: [
            QPointF(-20000.0, -20000.0),
            QPointF(20000.0, -20000.0),
            QPointF(20000.0, 20000.0),
            QPointF(-20000.0, 20000.0),
        ],
    )

    view._draw_projected_sustain_body(
        FakePainter(),
        note,
        4.0,
        4.0,
        0.0,
        8.0,
        4.0,
        8.0,
        QColor("#ff0000"),
        255,
    )

    assert "polygon" not in calls
    assert "line" not in calls


def test_play_view_3d_draws_ald_crush_markers_from_crush_interval(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[
            CrashSlide(
                note_type=NoteType.ALD,
                measure=0,
                offset=96,
                cell=6,
                width=4,
                crush_interval=96,
                starting_height=1.0,
                duration=192,
                end_cell=8,
                end_width=4,
                target_height=5.0,
                color="NON",
            ),
        ],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)
    view.set_current_pos(0.0)

    marker_depths: list[float] = []
    monkeypatch.setattr(
        view,
        "_draw_air_action_bar_3d",
        lambda *args: marker_depths.append(args[-1]),
    )

    image = QImage(QSize(1280, 720), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    view.render(image)

    assert marker_depths
    assert all(DRAW_DEPTH_MIN < depth < DRAW_DEPTH_MAX for depth in marker_depths)


def test_tap_quad_ignores_extreme_out_of_range_projection() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    view = PlayView3D()
    view.resize(1280, 720)
    image = QImage(QSize(1280, 720), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    try:
        view._draw_tap_quad(
            painter,
            x=3_300_000_000.0,
            y=3_300_000_000.0,
            w=1_000_000.0,
            scale=1_000_000.0,
            color=QColor(255, 0, 0),
            alpha=255,
            note=Tap(note_type=NoteType.TAP, measure=0, offset=0, cell=0, width=1),
            depth=-5.0,
        )
    finally:
        painter.end()


def test_play_view_keeps_crossing_sustains_but_culls_past_taps(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[
            Tap(note_type=NoteType.TAP, measure=0, offset=0, cell=0, width=2),
            Hold(
                note_type=NoteType.HLD,
                measure=0,
                offset=0,
                cell=4,
                width=2,
                duration=384,
            ),
            SlideTo(
                note_type=NoteType.SLD,
                measure=0,
                offset=0,
                cell=8,
                width=2,
                duration=384,
                end_cell=10,
                end_width=2,
            ),
        ],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)
    view.set_current_pos(0.2)

    drawn_heads: list[NoteType] = []
    drawn_bodies: list[object] = []
    monkeypatch.setattr(
        view,
        "_draw_tap_quad",
        lambda *args: drawn_heads.append(args[7].note_type),
    )
    monkeypatch.setattr(
        view,
        "_draw_projected_sustain_body",
        lambda *args, **kwargs: drawn_bodies.append(args),
    )
    image = QImage(QSize(1280, 720), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    view.render(image)

    assert NoteType.TAP not in drawn_heads
    assert drawn_bodies


def test_play_view_clips_crossing_air_paths_to_judge_line(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    step = AirSlide(
        note_type=NoteType.ASD,
        measure=0,
        offset=0,
        cell=4,
        width=2,
        target_note="AIR",
        starting_height=1.0,
        duration=384,
        end_cell=8,
        end_width=2,
        target_height=5.0,
        color="DEF",
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[
            CrashSlide(
                note_type=NoteType.ALD,
                measure=0,
                offset=0,
                cell=0,
                width=2,
                crush_interval=0,
                starting_height=1.0,
                duration=384,
                end_cell=4,
                end_width=2,
                target_height=5.0,
                color="CYN",
            ),
            AirSlideStart(
                note_type=NoteType.ASD,
                measure=0,
                offset=0,
                cell=4,
                width=2,
                steps=(step,),
            ),
        ],
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)
    view.set_current_pos(0.2)

    sustain_depths: list[float] = []
    head_depths: list[float] = []

    def record_sustain_projection(*args, **_kwargs):
        sustain_depths.extend([args[4], args[7]])

    monkeypatch.setattr(view, "_draw_projected_sustain_body", record_sustain_projection)
    monkeypatch.setattr(
        view,
        "_draw_tap_quad",
        lambda *args: head_depths.append(args[-1]),
    )
    monkeypatch.setattr(view, "_draw_sustain_body", lambda *args, **kwargs: None)

    image = QImage(QSize(1280, 720), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    view.render(image)

    assert any(depth == pytest.approx(0.0) for depth in sustain_depths)
    assert any(depth > 0.0 for depth in sustain_depths)
    assert all(depth > DRAW_DEPTH_MIN for depth in head_depths)


def test_3d_parsed_air_slide_wrapped_heads_dispatch_as_wrapped_ground_types(
    monkeypatch,
) -> None:
    from src.core.metadata import parse_c2s

    app = QApplication.instance() or QApplication([])
    _ = app
    chart = parse_c2s(
        "\n".join(
            [
                "ASD\t0\t0\t0\t1\tTAP\t1.0\t24\t0\t1\t1.0\tDEF",
                "ASD\t0\t24\t1\t1\tSLD\t1.0\t24\t1\t1\t1.0\tDEF",
                "ASD\t0\t48\t2\t1\tCHR\t1.0\t24\t2\t1\t1.0\tDEF",
                "ASD\t0\t72\t3\t1\tFLK\t1.0\t24\t3\t1\t1.0\tDEF",
                "ASD\t0\t96\t4\t1\tMNE\t1.0\t24\t4\t1\t1.0\tDEF",
                "ASD\t0\t120\t5\t1\tHLD\t1.0\t24\t5\t1\t1.0\tDEF",
                "ASD\t0\t144\t6\t1\tHXD\t1.0\t24\t6\t1\t1.0\tDEF",
                "ASD\t0\t168\t7\t1\tSLC\t1.0\t24\t7\t1\t1.0\tDEF",
                "ASD\t0\t192\t8\t1\tSXC\t1.0\t24\t8\t1\t1.0\tDEF",
            ]
        )
    )
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)
    taps: list[NoteType] = []
    extaps: list[NoteType] = []
    flicks: list[NoteType] = []
    mines: list[str] = []

    monkeypatch.setattr(view, "_draw_air_path_line", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_action_bar_3d", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_lift_if_needed", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(
        view,
        "_draw_tap_quad",
        lambda painter, x, y, w, scale, color, alpha, note, depth, cell=None, width=None: (
            taps.append(note.note_type)
        ),
    )
    monkeypatch.setattr(
        view,
        "_draw_extap_quad",
        lambda painter, x, y, w, scale, color, alpha, note, depth, cell=None, width=None: (
            extaps.append(note.note_type)
        ),
    )
    monkeypatch.setattr(
        view,
        "_draw_flick",
        lambda painter, x, y, w, scale, color, alpha, note, depth, cell=None, width=None: (
            flicks.append(note.note_type)
        ),
    )
    monkeypatch.setattr(view, "_draw_mine", lambda *args: mines.append("mine"))

    for note in chart.notes:
        view._draw_note(
            None,
            note,
            0.0,
            0.0,
            1.0,
            1.0,
            255,
            chart.timeline.time_at(0),
            1.0,
            2.0,
            640.0,
            72.0,
            648.0,
        )

    assert taps == [NoteType.TAP, NoteType.SLD, NoteType.HLD, NoteType.SLC]
    assert extaps == [NoteType.CHR, NoteType.HXD, NoteType.SXC]
    assert flicks == [NoteType.FLK]
    assert mines == ["mine"]


def test_3d_chained_air_slide_wrapped_heads_dispatch_each_step_wrapped_type(
    monkeypatch,
) -> None:
    from src.core.metadata import parse_c2s
    from src.notes.air import AirSlideStart

    app = QApplication.instance() or QApplication([])
    _ = app
    chart = parse_c2s(
        "\n".join(
            [
                "ASD\t0\t0\t0\t1\tTAP\t1.0\t24\t1\t1\t1.0\tDEF",
                "ASC\t0\t24\t1\t1\tCHR\t1.0\t24\t2\t1\t1.0\tDEF",
                "ASC\t0\t48\t2\t1\tFLK\t1.0\t24\t3\t1\t1.0\tDEF",
                "ASC\t0\t72\t3\t1\tSLC\t1.0\t24\t4\t1\t1.0\tDEF",
            ]
        )
    )
    chains = [note for note in chart.notes if isinstance(note, AirSlideStart)]
    view = PlayView3D()
    view.resize(1280, 720)
    view.draw_chart(chart)
    taps: list[NoteType] = []
    extaps: list[NoteType] = []
    flicks: list[NoteType] = []

    assert len(chains) == 1
    assert [step.target_note for step in chains[0].steps] == ["TAP", "CHR", "FLK", "SLC"]

    monkeypatch.setattr(view, "_draw_air_path_line", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_action_bar_3d", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_lift_if_needed", lambda *args: None)
    monkeypatch.setattr(view, "_draw_air_start_arrow_if_needed", lambda *args: None)
    monkeypatch.setattr(
        view,
        "_draw_tap_quad",
        lambda painter, x, y, w, scale, color, alpha, note, depth, cell=None, width=None: (
            taps.append(note.note_type)
        ),
    )
    monkeypatch.setattr(
        view,
        "_draw_extap_quad",
        lambda painter, x, y, w, scale, color, alpha, note, depth, cell=None, width=None: (
            extaps.append(note.note_type)
        ),
    )
    monkeypatch.setattr(
        view,
        "_draw_flick",
        lambda painter, x, y, w, scale, color, alpha, note, depth, cell=None, width=None: (
            flicks.append(note.note_type)
        ),
    )

    view._draw_note(
        None,
        chains[0],
        0.0,
        0.0,
        1.0,
        1.0,
        255,
        chart.timeline.time_at(0),
        1.0,
        2.0,
        640.0,
        72.0,
        648.0,
    )

    assert taps == [NoteType.TAP, NoteType.SLC]
    assert extaps == [NoteType.CHR]
    assert flicks == [NoteType.FLK]
