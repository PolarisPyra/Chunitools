from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src.core.const import NoteType
from src.core.models import Chart, ChartMetadata
from src.core.read import parse_c2s
from src.notes.air import Air, AirHoldStart, AirSlide, AirSlideStart
from src.ui.components.note_debug_overlay import (
    AIR_ARROW_DEBUG_LABEL_OFFSET,
    DEFAULT_DEBUG_LABEL_OFFSET,
    NoteDebugOverlay,
)


def test_air_path_debug_label_anchors_to_action_bar_end() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    step = AirSlide(
        note_type=NoteType.ASD,
        measure=0,
        offset=0,
        cell=4,
        width=2,
        target_note="TAP",
        starting_height=5.0,
        duration=96,
        end_cell=12,
        end_width=4,
        target_height=5.0,
        color="DEF",
    )
    air_slide = AirSlideStart(
        note_type=NoteType.ASD,
        measure=0,
        offset=0,
        cell=4,
        width=2,
        steps=(step,),
    )
    air_hold = AirHoldStart(
        note_type=NoteType.AHD,
        measure=0,
        offset=0,
        cell=6,
        width=3,
        target_note="TAP",
        duration=96,
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[air_slide, air_hold],
    )
    timeline = chart.timeline
    overlay = NoteDebugOverlay()

    assert overlay._label_anchor(air_slide, timeline) == (
        pytest.approx(timeline.note_abs_end_pos(air_slide)),
        12.0,
        4.0,
    )
    assert overlay._label_anchor(air_hold, timeline) == (
        pytest.approx(timeline.note_abs_end_pos(air_hold)),
        6.0,
        3.0,
    )


def test_directional_air_debug_label_stays_on_air_note() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    air = Air(
        note_type=NoteType.ADW,
        measure=0,
        offset=96,
        cell=10,
        width=3,
        target_note="TAP",
    )
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]), notes=[air])
    overlay = NoteDebugOverlay()

    assert overlay._label_anchor(air, chart.timeline) == (
        pytest.approx(chart.timeline.note_abs_pos(air)),
        10.0,
        3.0,
    )
    assert overlay._label_y_offset(air) == AIR_ARROW_DEBUG_LABEL_OFFSET


def test_non_air_arrow_debug_labels_keep_default_offset() -> None:
    app = QApplication.instance() or QApplication([])
    _ = app
    air_hold = AirHoldStart(
        note_type=NoteType.AHD,
        measure=0,
        offset=0,
        cell=6,
        width=3,
        target_note="TAP",
        duration=96,
    )
    overlay = NoteDebugOverlay()

    assert overlay._label_y_offset(air_hold) == DEFAULT_DEBUG_LABEL_OFFSET


def test_hxd_up_sequence_does_not_create_air_hold_action() -> None:
    chart = parse_c2s(
        "TAP\t13\t240\t4\t4\n"
        "TAP\t13\t240\t8\t4\n"
        "TAP\t13\t288\t4\t4\n"
        "TAP\t13\t288\t8\t4\n"
        "TAP\t13\t336\t9\t2\n"
        "TAP\t13\t352\t5\t2\n"
        "TAP\t13\t368\t9\t2\n"
        "CHR\t14\t0\t0\t4\tUP\n"
        "HXD\t14\t0\t12\t4\t48\tUP\n"
        "TAP\t14\t48\t0\t4\n"
        "CHR\t14\t96\t0\t4\tUP\n"
        "HXD\t14\t96\t11\t5\t48\tUP\n"
        "TAP\t14\t144\t0\t4\n"
        "CHR\t14\t192\t0\t4\tUP\n"
        "HXD\t14\t192\t10\t6\t48\tUP\n"
        "TAP\t14\t240\t0\t4\n"
        "CHR\t14\t288\t0\t4\tUP\n"
        "HXD\t14\t288\t9\t7\t48\tUP\n"
        "TAP\t14\t336\t0\t4\n"
        "CHR\t15\t0\t0\t4\tUP\n"
        "HXD\t15\t0\t8\t8\t48\tUP\n"
        "TAP\t15\t48\t0\t4\n"
    )

    assert {note.note_type for note in chart.notes} == {NoteType.TAP, NoteType.CHR, NoteType.HXD}
    assert all(note.note_type != NoteType.AHX for note in chart.notes)
