from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QPainterPath

from src.core.const import NoteType
from src.core.metadata import load_chart_file, parse_c2s
from src.engine.hitsounds import get_audible_ticks
from src.notes import Slide
from src.ui.view.projection import ViewProjection
from src.ui.view.renderer.base import BaseRenderer

CHUNITHM_2964_MASTER = Path(
    "/home/polaris/Documents/Projects/Arcade/resources/chunithm/charts/"
    "A283/music/music2964/2964_03.c2s"
)


def test_2964_ex_slide_start_does_not_force_ex_tail() -> None:
    chart = load_chart_file(CHUNITHM_2964_MASTER)
    slide = next(
        note
        for note in chart.notes
        if isinstance(note, Slide)
        and note.note_type == NoteType.SXD
        and note.measure == 2
        and note.offset == 0
        and note.cell == 8
    )
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))

    assert slide.steps[-1].note_type == NoteType.SXD
    assert renderer._slide_start_color(slide) == renderer.colors.ex_tap
    assert renderer._slide_endpoint_color(slide.steps[-1]) == renderer.colors.slide


def test_2964_ex_slide_foreground_draws_ex_start_and_tail_only() -> None:
    chart = load_chart_file(CHUNITHM_2964_MASTER)
    slide = next(
        note
        for note in chart.notes
        if isinstance(note, Slide)
        and note.note_type == NoteType.SXD
        and note.measure == 2
        and note.offset == 0
        and note.cell == 8
    )
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))
    drawn: list[tuple[str, object]] = []

    renderer._draw_tap = lambda painter, note, pos, timeline, color: drawn.append(
        ("start", color)
    )
    renderer._draw_step_tap = (
        lambda painter, step, tick, pos, timeline: drawn.append(
            ("step", renderer._slide_endpoint_color(step))
        )
    )
    renderer._draw_rounded_rect = lambda painter, rect, color: drawn.append(
        ("tail", color)
    )

    renderer._draw_slide_foreground(None, slide, 2.0, chart.timeline)

    assert drawn[0] == ("start", renderer.colors.ex_tap)
    assert not any(kind == "step" for kind, _ in drawn)
    assert drawn[-1] == ("tail", renderer.colors.slide)


def test_ground_slides_do_not_chain_to_air_slides_at_same_geometry() -> None:
    chart = load_chart_file("charts/2960_03.c2s")
    slide = next(
        note
        for note in chart.notes
        if isinstance(note, Slide)
        and note.note_type == NoteType.SXC
        and note.measure == 23
        and note.offset == 0
        and note.cell == 0
    )

    assert chart.timeline.note_chain_predecessor(slide) is None


def test_slide_control_points_follow_line_control_role_without_tap() -> None:
    chart = parse_c2s(
        "\n".join(
            [
                "SLD\t0\t0\t4\t2\t96\t6\t2",
                "SLC\t0\t96\t6\t2\t96\t8\t2",
                "SLD\t0\t192\t8\t2\t96\t10\t2",
            ]
        )
    )
    slide = next(note for note in chart.notes if isinstance(note, Slide))
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))
    drawn: list[NoteType] = []

    renderer._draw_tap = lambda *args: None
    renderer._draw_step_tap = lambda painter, step, tick, pos, timeline: drawn.append(
        step.note_type
    )
    renderer._draw_rounded_rect = lambda *args: None

    renderer._draw_slide_foreground(None, slide, 0.0, chart.timeline)

    assert [
        renderer._slide_step_role(index, len(slide.steps), step)
        for index, step in enumerate(slide.steps)
    ] == ["ST", "LC", "EN"]
    assert drawn == [NoteType.SLD]


def test_multi_segment_c2s_slide_background_uses_bezier_curves() -> None:
    """Slide body paths should use cubic B\u00e9zier curves matching the game's SpkInterpolationBezierAD3."""
    chart = parse_c2s(
        "\n".join(
            [
                "SLD\t0\t0\t4\t2\t96\t8\t2",
                "SLC\t0\t96\t8\t2\t96\t2\t2",
                "SLC\t0\t192\t2\t2\t96\t10\t2",
            ]
        )
    )
    slide = next(note for note in chart.notes if isinstance(note, Slide))
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))

    points = renderer._slide_path_points(slide, 0.0, chart.timeline)
    body_path = renderer._build_slide_body_path(points)

    assert _path_has_cubic_curve(body_path), "Slide body should use B\u00e9zier curves"


def _path_has_cubic_curve(path: QPainterPath) -> bool:
    return any(
        path.elementAt(index).type == QPainterPath.ElementType.CurveToElement
        for index in range(path.elementCount())
    )


def test_ex_slide_start_hitsound_is_deduplicated_against_matching_chr() -> None:
    chart = load_chart_file("charts/0006_04.c2s")
    slide = next(
        note
        for note in chart.notes
        if isinstance(note, Slide)
        and note.note_type == NoteType.SXC
        and note.measure == 11
        and note.offset == 0
        and note.cell == 6
        and note.width == 4
    )

    assert get_audible_ticks(slide, chart.timeline) == [4464]
