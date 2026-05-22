from src.core.const import NoteType
from src.core.metadata import parse_c2s
from src.core.write import serialize_c2s


def test_sla_lines_are_stored_as_soflan_areas_not_notes() -> None:
    chart = parse_c2s(
        "\n".join(
            [
                "BPM_DEF\t120.000\t120.000\t120.000\t120.000",
                "SLA\t8\t336\t0\t16\t3600\t2",
                "TAP\t8\t336\t4\t2",
            ]
        )
    )

    assert not hasattr(NoteType, "SLA")
    assert [note.note_type for note in chart.notes] == [NoteType.TAP]
    assert len(chart.soflan_areas) == 1
    area = chart.soflan_areas[0]
    assert area.measure == 8
    assert area.tick == 336
    assert area.cell == 0
    assert area.width == 16
    assert area.duration == 3600
    assert area.area_id == 2
    assert "SLA\t" in serialize_c2s(chart)
