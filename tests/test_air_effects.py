from src.core.const import NoteType
from src.core.metadata import parse_c2s
from src.core.write import serialize_c2s
from src.notes.air import AirHold, AirSlideStart, CrashSlide
from src.ui.view.projection import ViewProjection
from src.ui.view.renderer.base import BaseRenderer


def test_supported_air_effect_types_parse_and_serialize() -> None:
    chart = parse_c2s(
        "\n".join(
            [
                "AHX\t0\t48\t4\t2\tAHD\t96\tDEF",
                "ALD\t1\t0\t2\t4\t24\t1.0\t96\t6\t4\t3.0\tCYN",
                "ASD\t2\t0\t2\t4\tTAP\t1.0\t96\t6\t4\t3.0\tDEF",
                "ASC\t2\t96\t6\t4\tASD\t3.0\t96\t8\t4\t4.0\tDEF",
            ]
        )
    )

    action = next(note for note in chart.notes if isinstance(note, AirHold))
    crush = next(note for note in chart.notes if isinstance(note, CrashSlide))
    air_slide = next(note for note in chart.notes if isinstance(note, AirSlideStart))
    serialized = serialize_c2s(chart)

    assert action.duration == 96
    assert crush.crush_interval == 24
    assert crush.end_cell == 6
    assert [step.note_type for step in air_slide.steps] == [NoteType.ASD, NoteType.ASC]
    assert air_slide.end_cell == 8
    assert "AHX\t0\t48\t4\t2\tAHD\t96\tDEF" in serialized
    assert "ALD\t1\t0\t2\t4\t24\t1.0\t96\t6\t4\t3.0\tCYN" in serialized
    assert "ASD\t2\t0\t2\t4\tTAP\t1.0\t96\t6\t4\t3.0\tDEF" in serialized
    assert "ASC\t2\t96\t6\t4\tASD\t3.0\t96\t8\t4\t4.0\tDEF" in serialized


def test_unsupported_air_effect_tokens_are_ignored() -> None:
    chart = parse_c2s(
        "\n".join(
            [
                "ASX\t0\t0\t2\t4\tASC\t1.0\t96\t6\t4\t3.0\tDEF",
                "ASO\t0\t96\t2\t4\t1.0\t1.0\t96\t6\t4\t3.0\t1.0\tDEF",
                "HHD\t1\t0\t3\t4\t1.0\t96\t7\t4\t3.0\t1",
                "HHX\t1\t96\t4\t4\t1.0\t96\t8\t4\t3.0\t1\tUP",
            ]
        )
    )

    assert chart.notes == []


def test_supported_air_effects_dispatch_render_tasks() -> None:
    chart = parse_c2s(
        "\n".join(
            [
                "AHX\t0\t48\t4\t2\tAHD\t96\tDEF",
                "ALD\t0\t96\t2\t4\t24\t1.0\t96\t6\t4\t3.0\tCYN",
                "ASD\t0\t192\t2\t4\tTAP\t1.0\t96\t6\t4\t3.0\tDEF",
                "ASC\t0\t288\t6\t4\tASD\t3.0\t96\t8\t4\t4.0\tDEF",
            ]
        )
    )
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))

    task_names_by_type = {}
    for note in chart.notes:
        tasks = []
        renderer._dispatch_note_tasks(tasks, note, chart.timeline)
        task_names_by_type[note.note_type] = [task.function.__name__ for task in tasks]

    assert task_names_by_type[NoteType.AHX] == ["_draw_air_hold_background"]
    assert task_names_by_type[NoteType.ALD] == [
        "_draw_crash_slide_background",
        "_draw_air_action_bar",
    ]
    assert task_names_by_type[NoteType.ASD] == [
        "_draw_air_slide_background",
        "_draw_air_action_bar",
        "_draw_air_wrapped_ground_head",
    ]
    air_slide = next(note for note in chart.notes if isinstance(note, AirSlideStart))
    assert [step.note_type for step in air_slide.steps] == [NoteType.ASD, NoteType.ASC]
