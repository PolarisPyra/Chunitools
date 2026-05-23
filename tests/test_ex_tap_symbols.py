from __future__ import annotations

from pathlib import Path

from src.core.const import NoteType
from src.core.metadata import load_chart_file, parse_c2s
from src.notes import Hold, Slide
from src.ui.view.projection import ViewProjection
from src.ui.view.renderer.base import BaseRenderer

CHUNITHM_3002_MASTER = Path(
    "/home/polaris/Documents/Projects/Arcade/resources/chunithm/charts/"
    "A291/music/music3002/3002_03.c2s"
)


def test_ex_tap_subtypes_match_verified_shape_codes() -> None:
    renderer = BaseRenderer(ViewProjection())

    assert {
        ex_type: renderer._ex_tap_shape_code(ex_type)
        for ex_type in ("UP", "DW", "CE", "RC", "LC", "RS", "LS", "BS")
    } == {
        "UP": "U",
        "DW": "D",
        "CE": "C",
        "RC": "R",
        "LC": "L",
        "RS": "RR",
        "LS": "RL",
        "BS": "I",
    }


def test_ex_tap_symbol_type_is_preserved_for_chr_hxd_and_sx_heads() -> None:
    chart = parse_c2s(
        "\n".join(
            [
                "CHR\t0\t0\t0\t2\tBS",
                "HXD\t1\t0\t0\t2\t96\tDW",
                "SXD\t2\t0\t0\t2\t96\t4\t2\tchain-a\tCE",
            ]
        )
    )
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))

    chr_note = next(note for note in chart.notes if note.note_type == NoteType.CHR)
    hxd_note = next(note for note in chart.notes if note.note_type == NoteType.HXD)
    sx_slide = next(
        note
        for note in chart.notes
        if isinstance(note, Slide) and note.note_type == NoteType.SXD
    )

    assert renderer._ex_tap_symbol_type(chr_note) == "BS"
    assert renderer._ex_tap_symbol_type(hxd_note) == "DW"
    assert renderer._ex_tap_symbol_type(sx_slide) == "CE"


def test_ex_tap_subtypes_use_distinct_pixmap_cache_keys() -> None:
    chart = parse_c2s(
        "\n".join(
            [
                "CHR\t0\t0\t0\t2\tUP",
                "CHR\t0\t96\t0\t2\tDW",
            ]
        )
    )
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))
    up_note, down_note = [
        note for note in chart.notes if note.note_type == NoteType.CHR
    ]

    up_key = renderer._tap_pixmap_key(
        renderer.colors.ex_tap,
        80.0,
        renderer._tap_symbol_type(up_note),
    )
    down_key = renderer._tap_pixmap_key(
        renderer.colors.ex_tap,
        80.0,
        renderer._tap_symbol_type(down_note),
    )

    assert up_key != down_key


def test_3002_ex_tap_subtypes_are_available_to_renderer() -> None:
    chart = load_chart_file(CHUNITHM_3002_MASTER)
    renderer = BaseRenderer(ViewProjection(timeline_engine=chart.timeline))
    rendered_types: set[str] = set()

    for note in chart.notes:
        ex_type = renderer._ex_tap_symbol_type(note)
        if ex_type is not None:
            rendered_types.add(ex_type)

    assert {"UP", "DW", "CE", "RC", "RS", "LS", "BS"} <= rendered_types
    assert any(
        isinstance(note, Hold)
        and note.note_type == NoteType.HXD
        and renderer._ex_tap_symbol_type(note) == "DW"
        for note in chart.notes
    )
    assert any(
        isinstance(note, Slide)
        and note.note_type in (NoteType.SXC, NoteType.SXD)
        and renderer._ex_tap_symbol_type(note) == "CE"
        for note in chart.notes
    )
