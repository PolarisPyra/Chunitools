from src.core.enums import NoteType
from src.core.models import Chart, ChartMetadata
from src.notes.air import Air, AirHold, AirHoldStart, CrashSlide
from src.notes.flick import Flick
from src.notes.slide import Slide, SlideTo
from src.ui.window.inspectors import _get_header_parts, format_render_behavior


def test_air_direction_label_uses_direction_words() -> None:
    note = Air(
        note_type=NoteType.AIR,
        measure=1,
        offset=0,
        cell=4,
        width=4,
        target_note="TAP",
    )

    assert "AIR UP" in format_render_behavior(note)


def test_ahx_is_labeled_as_air_hold_action() -> None:
    note = AirHold(
        note_type=NoteType.AHX,
        measure=1,
        offset=0,
        cell=4,
        width=4,
        target_note="SLD",
        duration=96,
        color="DEF",
    )

    assert "AIR HOLD ACTION" in format_render_behavior(note)
    assert _get_header_parts(NoteType.AHX) == ["MS", "OFF", "CEL", "WID", "TRG", "DUR", "[CLR]"]


def test_ald_non_is_labeled_as_air_action() -> None:
    note = CrashSlide(
        note_type=NoteType.ALD,
        measure=1,
        offset=0,
        cell=4,
        width=4,
        crush_interval=38400,
        starting_height=5.0,
        duration=1,
        end_cell=4,
        end_width=4,
        target_height=5.0,
        color="NON",
    )

    assert "AIR ACTION / AIR CRUSH" in format_render_behavior(note)


def test_note_type_and_anchor_tags_render_as_rich_html() -> None:
    step = SlideTo(
        note_type=NoteType.SLD,
        measure=48,
        offset=0,
        cell=0,
        width=4,
        duration=192,
        end_cell=0,
        end_width=4,
    )
    slide = Slide(
        note_type=NoteType.SLD,
        measure=48,
        offset=0,
        cell=0,
        width=4,
        steps=(step,),
    )
    note = AirHoldStart(
        note_type=NoteType.AHD,
        measure=48,
        offset=192,
        cell=0,
        width=4,
        parent=slide,
        target_note="SLD",
        duration=96,
    )
    chart = Chart(metadata=ChartMetadata(resolution=384), notes=[slide, note])

    html = format_render_behavior(note, chart)

    assert '<span style="color:#33ff55;font-weight:bold;">AHD</span>' in html
    assert '<span style="color:#0090ff;font-weight:bold;">SLD</span>' in html
    assert "&lt;span" not in html


def test_headers_match_extra_fields() -> None:
    note = Flick(
        note_type=NoteType.FLK,
        measure=1,
        offset=0,
        cell=4,
        width=4,
        direction="L",
    )

    assert _get_header_parts(NoteType.FLK) == ["MS", "OFF", "CEL", "WID", "DIR"]
    assert len(_get_header_parts(NoteType.FLK)) == 4 + len(note.get_extra_parts())
    assert _get_header_parts(NoteType.AIR) == ["MS", "OFF", "CEL", "WID", "TRG", "[CLR]"]
    assert _get_header_parts(NoteType.AHD) == ["MS", "OFF", "CEL", "WID", "TRG", "DUR", "[CLR]"]
