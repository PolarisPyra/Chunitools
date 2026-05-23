from __future__ import annotations

import pytest

from src.core.const import NoteType
from src.notes import (
    Air,
    AirHold,
    AirHoldStart,
    AirSlide,
    AirSlideStart,
    AirSolid,
    CrashSlide,
    ExTap,
    Flick,
    HeavenHold,
    Hold,
    Mine,
    Slide,
    SlideTo,
    Tap,
)
from src.notes.factory import (
    AIR_MODIFIER_NOTE_TYPES,
    AIR_SLIDE_NOTE_TYPES,
    AIR_SUSTAIN_NOTE_TYPES,
    EDITOR_NOTE_TYPES,
    NOTE_FACTORIES,
    PARSER_NOTE_TYPES,
    SLIDE_NOTE_TYPES,
    build_editor_note,
    clamp_note_geometry,
    parse_note,
)
from src.notes.schema import NOTE_SCHEMAS, PLAYABLE_NOTE_TYPES


@pytest.mark.parametrize(
    ("line", "expected_type", "serialized"),
    [
        ("TAP\t1.0\t2.0\t3.0\t4.0", Tap, "TAP\t1\t2\t3\t4"),
        ("CHR\t1\t2\t3\t4\t9", ExTap, "CHR\t1\t2\t3\t4\t9"),
        ("FLK\t1\t2\t3\t4\tR", Flick, "FLK\t1\t2\t3\t4\tR"),
        ("MNE\t1\t2\t3\t4", Mine, "MNE\t1\t2\t3\t4"),
        ("HLD\t1\t2\t3\t4\t192\tUP", Hold, "HLD\t1\t2\t3\t4\t192\tUP"),
        ("HXD\t1\t2\t3\t4\t192", Hold, "HXD\t1\t2\t3\t4\t192"),
        ("SLD\t1\t2\t3\t4\t192\t5\t6\t\tUP", SlideTo, "SLD\t1\t2\t3\t4\t192\t5\t6\t\tUP"),
        ("SLC\t1\t2\t3\t4\t192\t5\t6", SlideTo, "SLC\t1\t2\t3\t4\t192\t5\t6\t"),
        ("AIR\t1\t2\t3\t4\tTAP\tPNK", Air, "AIR\t1\t2\t3\t4\tTAP\tPNK"),
        ("AUR\t1\t2\t3\t4\tTAP", Air, "AUR\t1\t2\t3\t4\tTAP"),
        ("AUL\t1\t2\t3\t4\tTAP", Air, "AUL\t1\t2\t3\t4\tTAP"),
        ("ADW\t1\t2\t3\t4\tTAP", Air, "ADW\t1\t2\t3\t4\tTAP"),
        ("ADR\t1\t2\t3\t4\tTAP", Air, "ADR\t1\t2\t3\t4\tTAP"),
        ("ADL\t1\t2\t3\t4\tTAP", Air, "ADL\t1\t2\t3\t4\tTAP"),
        ("AHD\t1\t2\t3\t4\tTAP\t192", AirHoldStart, "AHD\t1\t2\t3\t4\tTAP\t192"),
        ("AHD\t1\t2\t3\t4\tTAP\t192\tGRN", AirHoldStart, "AHD\t1\t2\t3\t4\tTAP\t192\tGRN"),
        ("AHX\t1\t2\t3\t4\tAHD\t192\tGRN", AirHold, "AHX\t1\t2\t3\t4\tAHD\t192\tGRN"),
        (
            "ALD\t1\t2\t3\t4\t0\t1.0\t192\t5\t6\t2.0\tNON",
            CrashSlide,
            "ALD\t1\t2\t3\t4\t0\t1.0\t192\t5\t6\t2.0\tNON",
        ),
        (
            "ASD\t1\t2\t3\t4\tTAP\t1.0\t192\t5\t6\t2.0\tDEF",
            AirSlide,
            "ASD\t1\t2\t3\t4\tTAP\t1.0\t192\t5\t6\t2.0\tDEF",
        ),
        (
            "ASC\t1\t2\t3\t4\tASD\t1.0\t192\t5\t6\t2.0\tCYN",
            AirSlide,
            "ASC\t1\t2\t3\t4\tASD\t1.0\t192\t5\t6\t2.0\tCYN",
        ),
        (
            "ASX\t1\t2\t3\t4\tASC\t1.0\t192\t5\t6\t2.0\tDEF",
            AirSlide,
            "ASX\t1\t2\t3\t4\tASC\t1.0\t192\t5\t6\t2.0\tDEF",
        ),
        (
            "ASO\t1\t2\t3\t4\t1.0\t2.0\t192\t5\t6\t3.0\t4.0\tCYN",
            AirSolid,
            "ASO\t1\t2\t3\t4\t1.0\t2.0\t192\t5\t6\t3.0\t4.0\tCYN",
        ),
        (
            "HHD\t1\t2\t3\t4\t1.0\t192\t5\t6\t2.0\t7",
            HeavenHold,
            "HHD\t1\t2\t3\t4\t1.0\t192\t5\t6\t2.0\t7",
        ),
        (
            "HHX\t1\t2\t3\t4\t1.0\t192\t5\t6\t2.0\t7\tUP",
            HeavenHold,
            "HHX\t1\t2\t3\t4\t1.0\t192\t5\t6\t2.0\t7\tUP",
        ),
    ],
)
def test_parse_note_serializes_with_existing_model_rules(
    line: str, expected_type: type, serialized: str
) -> None:
    command, *args = line.split("\t")
    note = parse_note(NoteType(command), args)

    assert isinstance(note, expected_type)
    assert note.serialize() == serialized


@pytest.mark.parametrize("line", ["TAP\t1\t2\t3", "CHR\t1\t2\t3\t4", "HLD\t1\t2\t3\t4"])
def test_parse_note_returns_none_for_malformed_lines(line: str) -> None:
    command, *args = line.split("\t")

    assert parse_note(NoteType(command), args) is None


def test_parser_note_type_groups_match_current_c2s_parser_needs() -> None:
    assert {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC} == SLIDE_NOTE_TYPES
    assert {NoteType.ASD, NoteType.ASC, NoteType.ASX} == AIR_SLIDE_NOTE_TYPES
    assert {
        NoteType.AIR,
        NoteType.AUR,
        NoteType.AUL,
        NoteType.ADW,
        NoteType.ADR,
        NoteType.ADL,
    } == AIR_MODIFIER_NOTE_TYPES
    assert {NoteType.AHD, NoteType.ALD, NoteType.AHX} == AIR_SUSTAIN_NOTE_TYPES
    assert NoteType.ASX in PARSER_NOTE_TYPES
    assert NoteType.ASX not in EDITOR_NOTE_TYPES


def test_playable_note_types_have_schema_and_factory_entries() -> None:
    assert set(NOTE_SCHEMAS) == PLAYABLE_NOTE_TYPES
    assert set(NOTE_FACTORIES) == PLAYABLE_NOTE_TYPES
    assert all(NOTE_SCHEMAS[note_type].evidence for note_type in PLAYABLE_NOTE_TYPES)


def test_renamed_fields_keep_compatibility_aliases() -> None:
    extap = ExTap(note_type=NoteType.CHR, measure=1, offset=2, cell=3, width=4, animation="UP")
    old_extap = ExTap(note_type=NoteType.CHR, measure=1, offset=2, cell=3, width=4, unknown="DW")
    flick = Flick(note_type=NoteType.FLK, measure=1, offset=2, cell=3, width=4, direction="L")
    old_flick = Flick(note_type=NoteType.FLK, measure=1, offset=2, cell=3, width=4, unknown="R")
    air_slide = AirSlide(
        note_type=NoteType.ASD,
        measure=1,
        offset=2,
        cell=3,
        width=4,
        target_note="TAP",
        starting_height=1.0,
        duration=192,
        end_cell=5,
        end_width=6,
        target_height=2.0,
        color="DEF",
    )

    assert extap.unknown == "UP"
    assert old_extap.animation == "DW"
    assert flick.unknown == "L"
    assert old_flick.direction == "R"
    assert air_slide.wrapped_type == "TAP"


@pytest.mark.parametrize(
    ("note_type", "expected_type"),
    [
        (NoteType.TAP, Tap),
        (NoteType.CHR, ExTap),
        (NoteType.FLK, Flick),
        (NoteType.MNE, Mine),
        (NoteType.HLD, Hold),
        (NoteType.HXD, Hold),
        (NoteType.SLD, Slide),
        (NoteType.SLC, Slide),
        (NoteType.AIR, Air),
        (NoteType.AUR, Air),
        (NoteType.AUL, Air),
        (NoteType.ADW, Air),
        (NoteType.ADR, Air),
        (NoteType.ADL, Air),
        (NoteType.AHD, AirHoldStart),
        (NoteType.AHX, AirHold),
        (NoteType.ALD, CrashSlide),
        (NoteType.ASD, AirSlideStart),
        (NoteType.ASC, AirSlideStart),
        (NoteType.ASO, AirSolid),
        (NoteType.HHD, HeavenHold),
        (NoteType.HHX, HeavenHold),
    ],
)
def test_build_editor_note_uses_existing_defaults(note_type: NoteType, expected_type: type) -> None:
    note = build_editor_note(
        note_type,
        measure=-1,
        offset=-2,
        cell=15,
        width=4,
        duration=0,
        end_cell=20,
        end_width=4,
        target_note="TAP",
    )

    assert isinstance(note, expected_type)
    assert note.measure == 0
    assert note.offset == 0
    assert note.cell == 15
    assert note.width == 1


def test_build_editor_note_rejects_parse_only_asx() -> None:
    with pytest.raises(ValueError, match="Unsupported note type: ASX"):
        build_editor_note(NoteType.ASX)


def test_clamp_note_geometry_preserves_editor_contract() -> None:
    assert clamp_note_geometry(-1, 0) == (0, 1)
    assert clamp_note_geometry(15, 99) == (15, 1)
    assert clamp_note_geometry(3, 20) == (3, 13)
