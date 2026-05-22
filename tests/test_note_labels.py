from src.core.enums import NoteType
from src.notes.air import AirHold, Air, CrashSlide
from src.notes.flick import Flick
from src.ui.window.inspectors import format_render_behavior, _get_header_parts


def test_air_direction_label_uses_direction_words() -> None:
    note = Air(
        note_type=NoteType.AIR,
        measure=1,
        offset=0,
        cell=4,
        width=4,
        target_note="TAP",
    )

    assert "BEH:  AIR UP" in format_render_behavior(note)


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

    assert "BEH:  AIR HOLD ACTION" in format_render_behavior(note)
    assert _get_header_parts(NoteType.AHX) == ["MS", "OFF", "CEL", "WID", "TRG", "DUR", "CLR"]


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

    assert "BEH:  AIR ACTION / AIR CRUSH" in format_render_behavior(note)


def test_headers_match_extra_fields() -> None:
    note = Flick(
        note_type=NoteType.FLK,
        measure=1,
        offset=0,
        cell=4,
        width=4,
        unknown="L",
    )

    assert _get_header_parts(NoteType.FLK) == ["MS", "OFF", "CEL", "WID", "UNK"]
    assert len(_get_header_parts(NoteType.FLK)) == 4 + len(note.get_extra_parts())
    assert _get_header_parts(NoteType.AIR) == ["MS", "OFF", "CEL", "WID", "TRG"]
    assert _get_header_parts(NoteType.AHD) == ["MS", "OFF", "CEL", "WID", "TRG", "DUR"]
