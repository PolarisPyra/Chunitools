from src.core.const import NoteType
from src.core.metadata import parse_c2s
from src.core.write import serialize_c2s
from src.notes import AirSolid, HeavenHold
from src.ui.view.projection import ViewProjection
from src.ui.view.renderer.base import BaseRenderer


def test_game_registered_air_solid_and_heaven_hold_parse_and_serialize() -> None:
    chart = parse_c2s(
        "\n".join(
            [
                "ASO\t1\t0\t2\t4\t1.0\t2.0\t96\t6\t4\t3.0\t4.0\tCYN",
                "HHD\t2\t0\t3\t5\t1.0\t192\t8\t5\t4.0\t7",
                "HHX\t3\t0\t4\t6\t2.0\t288\t10\t4\t5.0\t9\tUP",
            ]
        )
    )

    air_solid = next(note for note in chart.notes if isinstance(note, AirSolid))
    heaven_hold = next(
        note
        for note in chart.notes
        if isinstance(note, HeavenHold) and note.note_type == NoteType.HHD
    )
    heaven_ex = next(
        note
        for note in chart.notes
        if isinstance(note, HeavenHold) and note.note_type == NoteType.HHX
    )
    serialized = serialize_c2s(chart)

    assert air_solid.duration == 96
    assert air_solid.end_cell == 6
    assert air_solid.target_depth == 4.0
    assert heaven_hold.duration == 192
    assert heaven_hold.heaven_id == 7
    assert heaven_ex.animation == "UP"
    assert "ASO\t1\t0\t2\t4\t1.0\t2.0\t96\t6\t4\t3.0\t4.0\tCYN" in serialized
    assert "HHD\t2\t0\t3\t5\t1.0\t192\t8\t5\t4.0\t7" in serialized
    assert "HHX\t3\t0\t4\t6\t2.0\t288\t10\t4\t5.0\t9\tUP" in serialized


def test_game_registered_air_effects_dispatch_render_tasks() -> None:
    chart = parse_c2s(
        "\n".join(
            [
                "ASO\t0\t0\t2\t4\t1.0\t1.0\t96\t6\t4\t3.0\t1.0\tDEF",
                "HHD\t0\t96\t3\t4\t1.0\t96\t7\t4\t3.0\t1",
                "HHX\t0\t192\t4\t4\t1.0\t96\t8\t4\t3.0\t1\tUP",
            ]
        )
    )
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))

    task_names_by_type = {}
    for note in chart.notes:
        tasks = []
        renderer._dispatch_note_tasks(tasks, note, chart.timeline)
        task_names_by_type[note.note_type] = [task.function.__name__ for task in tasks]

    assert task_names_by_type[NoteType.ASO] == ["_draw_air_solid_background"]
    assert task_names_by_type[NoteType.HHD] == [
        "_draw_heaven_hold_background",
        "_draw_heaven_hold_foreground",
    ]
    assert task_names_by_type[NoteType.HHX] == [
        "_draw_heaven_hold_background",
        "_draw_heaven_hold_foreground",
    ]
