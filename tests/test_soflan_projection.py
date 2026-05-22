from __future__ import annotations

import pytest

from src.core.const import NoteType
from src.core.models import Chart, ChartMetadata, SofLanArea, SofLanPattern
from src.engine.soflan import SoflanProjector
from src.notes.hold import Hold
from src.notes.tap import ExTap
from src.ui.components.play_view import _visible_window


def _music2978_slowflan_fixture() -> tuple[Chart, Hold, ExTap]:
    hold = Hold(
        note_type=NoteType.HXD,
        measure=84,
        offset=0,
        cell=0,
        width=4,
        duration=1344,
        animation="BS",
    )
    full_width_action = ExTap(
        note_type=NoteType.CHR,
        measure=84,
        offset=0,
        cell=0,
        width=16,
        unknown="BS",
    )
    chart = Chart(
        metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]),
        notes=[hold, full_width_action],
        soflan_patterns=[
            SofLanPattern(75, 0, 24, 1000.0, 6),
            SofLanPattern(75, 24, 4776, -1.0, 6),
        ],
        soflan_areas=[
            SofLanArea(84, 0, 0, 4, 1368, 6),
            SofLanArea(84, 0, 12, 4, 1368, 6),
        ],
    )
    return chart, hold, full_width_action


def test_sla_slp_projects_hold_end_with_lane_local_reverse_scroll() -> None:
    chart, hold, _full_width_action = _music2978_slowflan_fixture()
    timeline = chart.timeline
    projector = SoflanProjector(chart)
    window = _visible_window(9.0)

    end_tick = timeline.note_end_tick(hold)
    end_time = timeline.time_at(end_tick)
    before_end_time = timeline.time_at(timeline.to_tick(86, 0))

    normal_depth = (end_time - before_end_time) / window
    soflan_depth = projector.depth_for_note_tick(
        hold,
        end_tick,
        end_time,
        before_end_time,
        window,
    )

    assert normal_depth > 0
    assert soflan_depth < 0
    assert projector.depth_for_note_tick(
        hold,
        end_tick,
        end_time,
        end_time,
        window,
    ) == pytest.approx(0.0)


def test_sla_uses_contained_lane_spans_not_any_overlap() -> None:
    chart, _hold, full_width_action = _music2978_slowflan_fixture()
    timeline = chart.timeline
    projector = SoflanProjector(chart)
    window = _visible_window(9.0)

    note_tick = timeline.note_tick(full_width_action)
    note_time = timeline.time_at(note_tick)
    judge_time = timeline.time_at(timeline.to_tick(83, 0))
    normal_depth = (note_time - judge_time) / window

    assert projector.depth_for_note_tick(
        full_width_action,
        note_tick,
        note_time,
        judge_time,
        window,
    ) == pytest.approx(normal_depth)
