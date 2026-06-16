
from pathlib import Path

import pytest

from src.core.enums import NoteType
from src.core.models import Chart, ChartMetadata
from src.engine.timeline import ChartTimeline
from src.notes.air import AirHoldStart, AirSlide, AirSlideStart, CrashSlide

CHUNITHM_3003_MASTER = Path(
    "/home/polaris/Documents/Projects/Arcade/resources/chunithm/charts/"
    "A252/music/music3003/3003_03.c2s"
)

def test_air_note_end_tick():
    chart = Chart(metadata=ChartMetadata(resolution=384))

    # ALD with duration 192
    ald = CrashSlide(
        note_type=NoteType.ALD, measure=1, offset=0, cell=0, width=4,
        crush_interval=0, starting_height=1.0, duration=192,
        end_cell=0, end_width=4, target_height=1.0, color="PPL"
    )

    # AHD with duration 384
    ahd = AirHoldStart(
        note_type=NoteType.AHD, measure=1, offset=192, cell=0, width=4,
        target_note="TAP", duration=384
    )

    chart.notes = [ald, ahd]
    timeline = ChartTimeline(chart)

    assert timeline.note_tick(ald) == 384
    assert timeline.note_end_tick(ald) == 384 + 192

    assert timeline.note_tick(ahd) == 384 + 192
    assert timeline.note_end_tick(ahd) == 384 + 192 + 384

def test_air_trace_fields():
    # Test if ALD fields are correctly assigned
    ald = CrashSlide(
        note_type=NoteType.ALD, measure=1, offset=0, cell=0, width=4,
        crush_interval=0, starting_height=1.0, duration=768,
        end_cell=8, end_width=2, target_height=2.0, color="CYN"
    )
    assert ald.duration == 768
    assert ald.end_cell == 8
    assert ald.end_width == 2
    assert ald.starting_height == 1.0
    assert ald.target_height == 2.0

def test_painter_draw_notes():
    # Clear log
    import os
    import sys

    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication

    from src.core.metadata import load_chart_file
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection
    if os.path.exists("logs/renderer.log"):
        with open("logs/renderer.log", "w") as f:
            f.truncate(0)

    QApplication.instance() or QApplication(sys.argv)
    chart = load_chart_file("charts/0006_04.c2s")
    timeline = ChartTimeline(chart)
    proj = ViewProjection(timeline_engine=timeline)
    painter = ChartRenderer(proj)

    img = QImage(QSize(800, 600), QImage.Format_ARGB32)
    p = QPainter(img)
    painter.draw_notes(p, chart.notes, 0.0)
    p.end()

    # Check if the log was populated
    import os

def test_air_slide_chaining():
    from src.core.metadata import parse_c2s
    from src.notes import AirSlideStart
    content = """
ASD	10	0	4	4	ASC	5.0	96	6	4	5.0	DEF
ASC	10	96	6	4	ASC	5.0	96	8	4	5.0	DEF
"""
    chart = parse_c2s(content)
    air_slides = [n for n in chart.notes if isinstance(n, AirSlideStart)]
    assert len(air_slides) == 1
    assert len(air_slides[0].steps) == 2

def test_air_arrow_anchoring_to_air_slide():
    from src.core.metadata import parse_c2s
    from src.notes import AirSlide
    content = """
ASD	10	0	4	4	ASC	5.0	96	6	4	5.0	DEF
AIR	10	96	6	4	ASD	DEF
"""
    chart = parse_c2s(content)
    air_notes = [n for n in chart.notes if n.note_type == NoteType.AIR]
    assert len(air_notes) == 1
    assert air_notes[0].parent is not None
    assert isinstance(air_notes[0].parent, AirSlide)


def test_3003_long_note_air_arrows_anchor_to_exact_end_steps():
    from src.core.metadata import load_chart_file
    from src.notes import Air, SlideTo

    chart = load_chart_file(CHUNITHM_3003_MASTER)
    timeline = chart.timeline
    long_end_airs = [
        note
        for note in chart.notes
        if isinstance(note, Air) and note.target_note in {"HLD", "SLD"}
    ]

    assert len(long_end_airs) == 47
    assert all(note.parent is not None for note in long_end_airs)
    assert all(timeline.note_anchor(note) is not None for note in long_end_airs)

    slide_end_air = next(
        note
        for note in long_end_airs
        if note.measure == 7 and note.offset == 168 and note.target_note == "SLD"
    )
    hold_end_air = next(
        note
        for note in long_end_airs
        if note.measure == 7 and note.offset == 180 and note.target_note == "HLD"
    )

    assert isinstance(slide_end_air.parent, SlideTo)
    assert timeline.note_tick(slide_end_air) == timeline.note_end_tick(slide_end_air.parent)
    assert timeline.note_tick(hold_end_air) == timeline.note_end_tick(hold_end_air.parent)


def test_air_arrow_color_modifiers_follow_inversion_flag():
    from src.core.metadata import parse_c2s
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s(
        "\n".join(
            [
                "TAP\t0\t0\t4\t2",
                "TAP\t0\t96\t6\t2",
                "AIR\t0\t0\t4\t2\tTAP\tPNK",
                "ADW\t0\t96\t6\t2\tTAP\tGRN",
            ]
        )
    )
    renderer = ChartRenderer(ViewProjection(timeline_engine=chart.timeline))
    up_air = next(note for note in chart.notes if note.note_type == NoteType.AIR)
    down_air = next(note for note in chart.notes if note.note_type == NoteType.ADW)

    assert renderer._air_arrow_color(up_air) == renderer.colors.air_down
    assert renderer._air_arrow_color(down_air) == renderer.colors.air_up


def test_air_base_color_uses_own_type_not_target_for_air_hold():
    """Per Margrete spec, air holds use their own type color, not target note color."""
    from src.core.enums import NoteType
    from src.notes.air import AirHoldStart
    from src.ui.theme.notes import get_note_color
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    renderer = ChartRenderer(ViewProjection())
    air_hold = AirHoldStart(
        note_type=NoteType.AHD,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="TAP",
        duration=384,
    )

    assert renderer._air_base_note_color(air_hold).rgba() == get_note_color(NoteType.AHD).rgba()


def test_air_base_color_uses_own_type_not_target_for_air_slide_step():
    """Per Margrete spec, air slides use their own type color, not target note color."""
    from src.core.enums import NoteType
    from src.ui.theme.notes import get_note_color
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    renderer = ChartRenderer(ViewProjection())
    air_slide = AirSlide(
        note_type=NoteType.ASD,
        measure=0,
        offset=0,
        cell=0,
        width=4,
        target_note="SLD",
        starting_height=1.0,
        duration=96,
        end_cell=8,
        end_width=2,
        target_height=1.0,
        color="DEF",
    )

    assert renderer._air_base_note_color(air_slide).rgba() == get_note_color(NoteType.ASD).rgba()


def test_air_arrow_uses_anchor_endpoint_rect_for_slide_end():
    from src.core.metadata import parse_c2s
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s(
        "\n".join(
            [
                "SLD\t0\t0\t4\t2\t96\t10\t2",
                "AIR\t0\t96\t10\t2\tSLD\tDEF",
            ]
        )
    )
    timeline = ChartTimeline(chart)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))
    air = next(note for note in chart.notes if note.note_type == NoteType.AIR)
    drawn: list[tuple[float, float, float]] = []

    renderer._draw_air_arrow_head = (
        lambda painter, note, x, y, width, color: drawn.append((x, y, width))
    )

    renderer._draw_air(None, air, 0.0, timeline)

    assert drawn == [
        (
            renderer.projection.x(10),
            renderer.projection.y(96 / timeline.resolution, 0.0),
            renderer.projection.w(2),
        )
    ]


def test_air_arrow_color_uses_own_color_for_anchored_air_note():
    """Per Margrete spec, air arrows use own type color, not target note color."""
    from src.core.metadata import parse_c2s
    from src.ui.theme.notes import get_note_color
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s(
        "\n".join(
            [
                "SLD\t0\t0\t4\t2\t96\t10\t2",
                "AIR\t0\t96\t10\t2\tSLD\tDEF",
            ]
        )
    )
    timeline = ChartTimeline(chart)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))
    air = next(note for note in chart.notes if note.note_type == NoteType.AIR)

    assert renderer._air_arrow_color(air, timeline).rgba() == get_note_color(NoteType.AIR).rgba()


def test_air_reference_replaces_hold_tail_with_air_step():
    from src.core.metadata import parse_c2s
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s(
        "\n".join(
            [
                "HLD\t0\t0\t4\t2\t96",
                "AIR\t0\t96\t4\t2\tHLD\tDEF",
            ]
        )
    )
    timeline = ChartTimeline(chart)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))
    hold = next(note for note in chart.notes if note.note_type == NoteType.HLD)
    air = next(note for note in chart.notes if note.note_type == NoteType.AIR)
    steps: list[object] = []
    tails: list[object] = []

    renderer._draw_tap = lambda *args: None
    renderer._draw_air_step = lambda painter, rect: steps.append(rect)
    renderer._draw_rounded_rect = lambda *args: tails.append(args[1])

    renderer._draw_hold_foreground(None, hold, 0.0, timeline)
    renderer._draw_air_step_for_air(None, air, 0.0, timeline)

    assert tails == []
    assert len(steps) == 1


def test_air_reference_replaces_slide_tail_with_air_step():
    from src.core.metadata import parse_c2s
    from src.notes import Slide
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s(
        "\n".join(
            [
                "SLD\t0\t0\t4\t2\t96\t10\t2",
                "AIR\t0\t96\t10\t2\tSLD\tDEF",
            ]
        )
    )
    timeline = ChartTimeline(chart)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))
    slide = next(note for note in chart.notes if isinstance(note, Slide))
    air = next(note for note in chart.notes if note.note_type == NoteType.AIR)
    steps: list[object] = []
    tails: list[object] = []

    renderer._draw_tap = lambda *args: None
    renderer._draw_step_tap = lambda *args: None
    renderer._draw_air_step = lambda painter, rect: steps.append(rect)
    renderer._draw_rounded_rect = lambda *args: tails.append(args[1])

    renderer._draw_slide_foreground(None, slide, 0.0, timeline)
    renderer._draw_air_step_for_air(None, air, 0.0, timeline)

    assert tails == []
    assert len(steps) == 1


def test_anchored_air_draws_before_slide_foreground():
    from src.core.metadata import parse_c2s
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s(
        "\n".join(
            [
                "SLD\t0\t0\t4\t2\t96\t10\t2",
                "AIR\t0\t96\t10\t2\tSLD\tDEF",
            ]
        )
    )
    timeline = ChartTimeline(chart)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))

    air = next(note for note in chart.notes if note.note_type == NoteType.AIR)
    slide = next(note for note in chart.notes if note.note_type == NoteType.SLD)

    air_tasks: list = []
    slide_tasks: list = []

    renderer._dispatch_air_tasks(air_tasks, air, air.note_type, timeline.note_tick(air))
    renderer._dispatch_foreground_tasks(slide_tasks, slide, slide.note_type, timeline.note_tick(slide))

    air_priorities = {task.priority for task in air_tasks}
    slide_priorities = {task.priority for task in slide_tasks}

    assert any(priority < 32 for priority in air_priorities)
    assert 32 in slide_priorities


def test_air_notes_do_not_anchor_to_air_traces():
    from src.core.metadata import parse_c2s

    content = """
ALD	10	0	4	4	0	1.0	96	6	4	1.0	NON
AIR	10	0	4	4	ALD	DEF
"""
    chart = parse_c2s(content)
    timeline = ChartTimeline(chart)
    air = next(note for note in chart.notes if note.note_type == NoteType.AIR)

    assert air.parent is None
    assert timeline.note_anchor(air) is None


def test_deduplication():
    from src.core.metadata import parse_c2s
    content = """
TAP	10	0	4	4
TAP	10	0	4	4
"""
    chart = parse_c2s(content)
    taps = [n for n in chart.notes if n.note_type == NoteType.TAP]
    assert len(taps) == 1
def test_air_step_duration():
    from src.core.metadata import parse_c2s
    from src.notes import AirSlideStart
    content = """
ASD	10	0	4	4	ASC	5.0	96	6	4	5.0	DEF
"""
    chart = parse_c2s(content)
    timeline = ChartTimeline(chart)

    air_slides = [n for n in chart.notes if isinstance(n, AirSlideStart)]
    step = air_slides[0].steps[0]

    assert step.duration == 96
    assert timeline.note_abs_pos(step) == 10.0
    # If this is 10.0, then duration is being read as 0
    assert timeline.note_abs_end_pos(step) == 10.25 # 96/384 = 0.25


def test_air_slide_ground_target_draws_start_air_and_end_action_bar_for_2960():
    """Air slide chains draw start arrow at ground anchor + action bar at chain end."""
    from src.core.metadata import load_chart_file
    from src.notes import AirSlideStart
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = load_chart_file("charts/2960_03.c2s")
    timeline = chart.timeline
    asd = next(
        note
        for note in chart.notes
        if isinstance(note, AirSlideStart) and note.measure == 1 and note.offset == 120
    )
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))
    drawn: list[tuple[float, int, int]] = []
    arrows: list[NoteType] = []

    def record_joint_bar(painter, note, current_position, timeline):
        drawn.append(
            (
                timeline.note_abs_end_pos(note),
                getattr(note, "end_cell", note.cell),
                getattr(note, "end_width", note.width),
            )
        )

    renderer._draw_air_joint_bar = record_joint_bar
    renderer._draw_air_bar_at = lambda cell, width, abs_pos, *args: drawn.append(
        (abs_pos, cell, width)
    )
    renderer._draw_air_arrow_head = (
        lambda painter, note, x, y, width, color: arrows.append(note.note_type)
    )
    renderer._draw_air_action_bar(None, asd, 1.0, timeline)

    assert arrows == [NoteType.AIR]
    assert drawn == _air_slide_step_bar_positions(asd, timeline)


def test_air_slide_asc_chains_draw_end_action_bars_for_2960():
    """Air slide chains always draw an action bar at their last step."""
    from src.core.metadata import load_chart_file
    from src.notes import AirSlideStart
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = load_chart_file("charts/2960_03.c2s")
    timeline = chart.timeline
    asc_notes = [
        note
        for note in chart.notes
        if isinstance(note, AirSlideStart)
        and note.measure == 22
        and note.offset == 240
    ]
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))
    drawn: list[tuple[float, int, int]] = []

    def record_joint_bar(painter, note, current_position, timeline):
        drawn.append(
            (
                timeline.note_abs_end_pos(note),
                getattr(note, "end_cell", note.cell),
                getattr(note, "end_width", note.width),
            )
    )

    renderer._draw_air_joint_bar = record_joint_bar
    renderer._draw_air_bar_at = lambda cell, width, abs_pos, *args: drawn.append(
        (abs_pos, cell, width)
    )
    renderer._draw_air_arrow_head = lambda painter, note, x, y, width, color: None
    for asc in asc_notes:
        renderer._draw_air_action_bar(None, asc, 22.0, timeline)

    assert drawn == [
        bar
        for asc in asc_notes
        for bar in _air_slide_step_bar_positions(asc, timeline)
    ]


def test_final_ex_slide_step_is_end_role_for_2960():
    from src.core.enums import NoteType
    from src.core.metadata import load_chart_file
    from src.notes import Slide
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = load_chart_file("charts/2960_03.c2s")
    timeline = chart.timeline
    slide = next(
        note
        for note in chart.notes
        if isinstance(note, Slide)
        and note.note_type == NoteType.SXC
        and note.measure == 23
        and note.offset == 0
    )
    visible_ex_step = next(step for step in slide.steps if step.note_type == NoteType.SXD)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))

    assert visible_ex_step.measure == 23
    assert visible_ex_step.offset == 88
    assert renderer._slide_step_role(
        slide.steps.index(visible_ex_step),
        len(slide.steps),
        visible_ex_step,
    ) == "EN"
    assert renderer._slide_endpoint_color(visible_ex_step) == renderer.colors.slide


def test_air_hold_start_draws_action_bar_at_end():
    from src.core.metadata import parse_c2s
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s("AHD\t0\t0\t4\t2\tTAP\t96\n")
    timeline = ChartTimeline(chart)
    ahd = next(note for note in chart.notes if note.note_type == NoteType.AHD)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))
    drawn: list[tuple[float, int, int]] = []

    renderer._draw_air_arrow_head = lambda painter, note, x, y, width, color: None
    renderer._draw_air_bar_at = lambda cell, width, abs_pos, *args: drawn.append(
        (abs_pos, cell, width)
    )

    renderer._draw_air_action_bar(None, ahd, 0.0, timeline)

    assert drawn == [
        (
            timeline.note_abs_end_pos(ahd),
            getattr(ahd, "end_cell", ahd.cell),
            getattr(ahd, "end_width", ahd.width),
        )
    ]


def test_air_hold_action_draws_green_air_path_line():
    from src.core.metadata import parse_c2s
    from src.ui.theme.notes import get_note_color
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s("AHX\t0\t0\t4\t2\tSLD\t96\tDEF\n")
    timeline = ChartTimeline(chart)
    ahx = next(note for note in chart.notes if note.note_type == NoteType.AHX)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))

    class Painter:
        def __init__(self) -> None:
            self.pen = None
            self.lines = []

        def setPen(self, pen):  # noqa: N802
            self.pen = pen

        def drawLine(self, start, end):  # noqa: N802
            self.lines.append((self.pen.color(), self.pen.width(), start, end))

    painter = Painter()

    renderer._draw_air_hold_background(painter, ahx, 0.0, timeline)

    assert len(painter.lines) == 1
    color, width, start, end = painter.lines[0]
    assert color.rgba() == get_note_color(NoteType.AHD).rgba()
    assert width == renderer.constants.AIR_PATH_WIDTH
    assert start.y() == pytest.approx(
        renderer.projection.y(timeline.note_abs_pos(ahx), 0.0)
    )
    assert end.y() == pytest.approx(
        renderer.projection.y(timeline.note_abs_end_pos(ahx), 0.0)
    )


def test_air_hold_action_does_not_draw_own_air_action_bar():
    from src.core.metadata import parse_c2s
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s(
        "CHR\t10\t0\t12\t4\tUP\n"
        "AHX\t10\t0\t12\t4\tCHR\t384\tDEF\n"
        "ALD\t10\t96\t12\t4\t6\t5.0\t1\t12\t4\t5.0\tNON\n"
    )
    timeline = ChartTimeline(chart)
    ahx = next(note for note in chart.notes if note.note_type == NoteType.AHX)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))

    joints = []
    renderer._draw_air_arrow_head = lambda *args: None
    renderer._draw_air_joint_bar = lambda *args: joints.append(args[1])

    renderer._draw_air_action_bar(None, ahx, 10.0, timeline)

    assert joints == []


def test_air_slide_air_target_continues_existing_chain_to_end_bar():
    from src.core.metadata import parse_c2s
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s(
        "\n".join(
            [
                "ASC\t0\t0\t0\t4\tTAP\t5.0\t4\t12\t4\t5.0\tDEF",
                "ASC\t0\t4\t12\t4\tASC\t5.0\t4\t0\t4\t5.0\tDEF",
                "ASD\t0\t8\t0\t4\tASC\t5.0\t4\t12\t4\t5.0\tDEF",
            ]
        )
    )
    timeline = ChartTimeline(chart)
    air_slides = [
        note
        for note in chart.notes
        if isinstance(note, AirSlideStart)
    ]
    chain = air_slides[0]
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))
    drawn: list[tuple[float, int, int]] = []
    arrows: list[object] = []

    assert len(air_slides) == 1
    assert [step.note_type for step in chain.steps] == [
        NoteType.ASC,
        NoteType.ASC,
        NoteType.ASD,
    ]

    renderer._draw_air_bar_at = lambda cell, width, abs_pos, *args: drawn.append(
        (abs_pos, cell, width)
    )
    renderer._draw_air_slide_arrow = lambda *args: arrows.append(args[1])

    renderer._draw_air_action_bar(None, chain, 0.0, timeline)

    assert drawn == _air_slide_step_bar_positions(chain, timeline)


def _air_slide_step_bar_positions(note: AirSlideStart, timeline: ChartTimeline):
    abs_pos = timeline.note_abs_pos(note)
    bars = []
    step_count = len(note.steps)
    for index, step in enumerate(note.steps):
        abs_pos += step.duration / timeline.resolution
        if step.note_type != NoteType.ASD and index != step_count - 1:
            continue
        bars.append((abs_pos, step.end_cell, step.end_width))
    return bars


def test_ald_air_crush_markers_follow_crush_interval_not_color():
    from src.core.metadata import parse_c2s
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = parse_c2s(
        "\n".join(
            [
                "ALD\t0\t0\t4\t2\t0\t1.0\t96\t6\t2\t1.0\tNON",
                "ALD\t1\t0\t4\t2\t24\t1.0\t96\t6\t2\t1.0\tRED",
            ]
        )
    )
    timeline = ChartTimeline(chart)
    ald_non = next(
        note
        for note in chart.notes
        if note.note_type == NoteType.ALD and note.color == "NON"
    )
    ald_red = next(
        note
        for note in chart.notes
        if note.note_type == NoteType.ALD and note.color == "RED"
    )
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))
    crushed: list[object] = []

    renderer._draw_air_joint_bar = lambda *args: crushed.append(("joint", args[1]))
    renderer._draw_air_crush_elements = lambda *args: crushed.append(("crush", args[1]))

    renderer._draw_air_action_bar(None, ald_non, 0.0, timeline)
    renderer._draw_air_action_bar(None, ald_red, 0.0, timeline)

    assert crushed == [("crush", ald_red)]


def test_ex_slide_start_is_not_chained_to_air_slide_for_2960():
    from src.core.enums import NoteType
    from src.core.metadata import load_chart_file
    from src.notes import Slide
    from src.ui.view.chart_renderer import ChartRenderer
    from src.ui.view.projection import ViewProjection

    chart = load_chart_file("charts/2960_03.c2s")
    timeline = chart.timeline
    slide = next(
        note
        for note in chart.notes
        if isinstance(note, Slide)
        and note.note_type == NoteType.SXC
        and note.measure == 23
        and note.offset == 0
    )
    predecessor = timeline.note_chain_predecessor(slide)
    renderer = ChartRenderer(ViewProjection(timeline_engine=timeline))

    assert predecessor is None
    assert renderer._should_draw_slide_head(slide, timeline)
    assert renderer._slide_start_color(slide) == renderer.colors.ex_tap


def test_parsed_air_slide_wrapped_heads_dispatch_as_wrapped_ground_types():
    from src.core.metadata import parse_c2s
    from src.ui.view.projection import ViewProjection
    from src.ui.view.renderer.base import BaseRenderer

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
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))
    taps: list[tuple[NoteType, object]] = []
    flicks: list[NoteType] = []
    mines: list[NoteType] = []

    renderer._draw_soflan_areas = lambda *args: None
    renderer._draw_air_slide_background = lambda *args: None
    renderer._draw_air_action_bar = lambda *args: None
    renderer._draw_tap_at_abs_pos = (
        lambda painter, note, abs_pos, current_position, color: taps.append(
            (note.note_type, color, abs_pos)
        )
    )
    renderer._draw_flick_at_abs_pos = (
        lambda painter, note, abs_pos, current_position: flicks.append((note.note_type, abs_pos))
    )
    renderer._draw_damage_at_abs_pos = (
        lambda painter, note, abs_pos, current_position: mines.append((note.note_type, abs_pos))
    )

    renderer.draw_notes(None, chart.notes, 0.0)

    assert taps == [
        (NoteType.TAP, renderer.colors.tap, 0.0),
        (NoteType.SLD, renderer.colors.slide, 0.0625),
        (NoteType.CHR, renderer.colors.ex_tap, 0.125),
        (NoteType.HLD, renderer.colors.hold, 0.3125),
        (NoteType.HXD, renderer.colors.ex_tap, 0.375),
        (NoteType.SLC, renderer.colors.slide, 0.4375),
        (NoteType.SXC, renderer.colors.ex_tap, 0.5),
    ]
    assert flicks == [(NoteType.FLK, 0.1875)]
    assert mines == [(NoteType.MNE, 0.25)]


def test_chained_air_slide_wrapped_heads_dispatch_each_step_wrapped_type():
    from src.core.metadata import parse_c2s
    from src.notes.air import AirSlideStart
    from src.ui.view.projection import ViewProjection
    from src.ui.view.renderer.base import BaseRenderer

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
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))
    taps: list[tuple[NoteType, object, float]] = []
    flicks: list[tuple[NoteType, float]] = []

    assert len(chains) == 1
    assert [step.target_note for step in chains[0].steps] == ["TAP", "CHR", "FLK", "SLC"]

    renderer._draw_soflan_areas = lambda *args: None
    renderer._draw_air_slide_background = lambda *args: None
    renderer._draw_air_action_bar = lambda *args: None
    renderer._draw_tap_at_abs_pos = (
        lambda painter, note, abs_pos, current_position, color: taps.append(
            (note.note_type, color, abs_pos)
        )
    )
    renderer._draw_flick_at_abs_pos = (
        lambda painter, note, abs_pos, current_position: flicks.append((note.note_type, abs_pos))
    )

    renderer.draw_notes(None, chart.notes, 0.0)

    assert taps == [
        (NoteType.TAP, renderer.colors.tap, 0.0),
        (NoteType.CHR, renderer.colors.ex_tap, 0.0625),
        (NoteType.SLC, renderer.colors.slide, 0.1875),
    ]
    assert flicks == [(NoteType.FLK, 0.125)]


def test_chained_air_slide_wrapped_heads_schedule_when_first_step_wraps_air_slide():
    from src.core.metadata import parse_c2s
    from src.notes.air import AirSlideStart
    from src.ui.view.projection import ViewProjection
    from src.ui.view.renderer.base import BaseRenderer

    chart = parse_c2s(
        "\n".join(
            [
                "ASD\t0\t0\t0\t1\tASC\t1.0\t24\t1\t1\t1.0\tDEF",
                "ASC\t0\t24\t1\t1\tCHR\t1.0\t24\t2\t1\t1.0\tDEF",
            ]
        )
    )
    chains = [note for note in chart.notes if isinstance(note, AirSlideStart)]
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))
    taps: list[tuple[NoteType, object, float]] = []

    assert len(chains) == 1
    assert [step.target_note for step in chains[0].steps] == ["ASC", "CHR"]

    renderer._draw_soflan_areas = lambda *args: None
    renderer._draw_air_slide_background = lambda *args: None
    renderer._draw_air_action_bar = lambda *args: None
    renderer._draw_tap_at_abs_pos = (
        lambda painter, note, abs_pos, current_position, color: taps.append(
            (note.note_type, color, abs_pos)
        )
    )

    renderer.draw_notes(None, chart.notes, 0.0)

    assert taps == [(NoteType.CHR, renderer.colors.ex_tap, 0.0625)]
