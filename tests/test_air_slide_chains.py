from src.core.enums import NoteType
from src.core.metadata import load_chart_file
from src.engine.timeline import ChartTimeline
from src.notes import AirSlideStart


def test_air_slide_chain_anchoring():
    """
    Verifies Air Slide joining and anchoring for complex sustain chains.
    Ensures that ASD segments are correctly joined into
    a chain and that each step correctly references its parent.
    """
    chart = load_chart_file("charts/0006_04.c2s")
    timeline = ChartTimeline(chart)

    # Verify that the ASD segments at 10:288 are correctly handled
    # We expect ASD at 10:288 to be a STEP in a chain starting earlier
    # Let's find all steps across all AirSlideStarts that land on 10:288
    all_steps = []
    for n in chart.notes:
        if isinstance(n, AirSlideStart):
            all_steps.extend(n.steps)

    m10_288_steps = [
        s for s in all_steps
        if s.measure == 10 and s.offset == 288 and s.note_type == NoteType.ASD
    ]

    assert len(m10_288_steps) > 0, "Should have found ASD steps at 10:288"

    for step in m10_288_steps:
        # Each step should have a parent ground note if it targets one
        # In this chart, ASD 10:288 targets SLD 5.0
        assert step.target_note in ("SLD", "ASC")

        parent = timeline.note_anchor(step)
        if step.target_note == "SLD":
            assert parent is not None, f"Step {step} at 10:288 should have an anchor"
            assert parent.note_type in {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC}
        else:
            assert parent is None
            assert (
                f"{step.note_type.value} at {step.measure}:{step.offset} "
                f"(cell={step.cell}, width={step.width}) has 2 matching targets "
                f"for '{step.target_note}' at this timestamp"
            ) in "\n".join(chart.warnings)

def test_air_slide_action_bar_segments():
    """Verify ASD steps in a sustain chain are identified for action bar rendering."""
    chart = load_chart_file("charts/0006_04.c2s")

    # Find all ASD segments in Measure 10
    asd_segments = []
    for note in chart.notes:
        if isinstance(note, AirSlideStart):
            for step in note.steps:
                if step.measure == 10 and step.note_type == NoteType.ASD:
                    asd_segments.append(step)

    # Specifically looking for the ones at 10:96 and 10:288
    ticks = {s.offset for s in asd_segments}
    assert 96 in ticks
    assert 288 in ticks


def test_simultaneous_hitsounds_are_not_deduplicated():
    chart = load_chart_file("charts/0006_04.c2s")
    timeline = ChartTimeline(chart)

    tick = 10 * timeline.resolution + 96 + 288

    assert timeline.audible_ticks.count(tick) == 5


def test_air_arrow_and_source_note_both_make_hitsounds():
    chart = load_chart_file("charts/0006_04.c2s")
    timeline = ChartTimeline(chart)

    tick = 11 * timeline.resolution
    selected_ticks = [
        note
        for note in chart.notes
        if timeline.note_tick(note) == tick and note.note_type in {NoteType.ADW, NoteType.CHR}
    ]

    assert {note.note_type for note in selected_ticks} == {NoteType.ADW, NoteType.CHR}
    assert timeline.audible_ticks.count(tick) == 5


def test_playback_groups_simultaneous_hitsound_count():
    from src.engine.hitsounds import RENDER_AIR_JUDGEMENT_DELAY_SECONDS
    from src.engine.playback import PlaybackController

    chart = load_chart_file("charts/0006_04.c2s")
    ChartTimeline(chart)
    controller = PlaybackController()
    controller.set_chart(chart)

    tick = 11 * chart.timeline.resolution
    pos = tick / chart.timeline.resolution
    trigger_time = chart.timeline.time_at(tick)

    assert controller.audible_triggers == sorted(controller.audible_triggers)
    assert any(time == trigger_time for time, _ in controller.audible_triggers)
    assert any(
        time == trigger_time + RENDER_AIR_JUDGEMENT_DELAY_SECONDS
        for time, _ in controller.audible_triggers
    )
    assert controller.audible_trigger_count_at(pos) == 5


def test_air_hitsounds_use_render_air_judgement_delay():
    from src.core.metadata import parse_c2s
    from src.engine.hitsounds import RENDER_AIR_JUDGEMENT_DELAY_SECONDS
    from src.engine.playback import PlaybackController

    chart = parse_c2s(
        "\n".join(
            [
                "TAP\t0\t0\t4\t2",
                "AIR\t0\t0\t4\t2\tTAP\tDEF",
            ]
        )
    )
    controller = PlaybackController()
    controller.set_chart(chart)

    base_time = chart.timeline.time_at(0)
    air_time = base_time + RENDER_AIR_JUDGEMENT_DELAY_SECONDS

    assert controller.audible_triggers == [(base_time, 1), (air_time, 1)]


def test_air_slide_control_points_do_not_make_hitsounds():
    chart = load_chart_file("charts/0006_04.c2s")
    timeline = ChartTimeline(chart)

    assert (23 * timeline.resolution + 352) not in timeline.audible_ticks
    assert (23 * timeline.resolution + 370) not in timeline.audible_ticks
    assert (24 * timeline.resolution + 5) not in timeline.audible_ticks
    assert (24 * timeline.resolution + 288) in timeline.audible_ticks


def test_visible_slide_steps_in_middle_chain_segments_make_hitsounds():
    chart = load_chart_file("charts/0006_04.c2s")
    timeline = ChartTimeline(chart)

    assert (44 * timeline.resolution + 96) in timeline.audible_ticks


def test_air_down_can_anchor_to_ex_slide_chain_end():
    chart = load_chart_file("charts/2950_03.c2s")
    timeline = ChartTimeline(chart)

    air_down = next(
        note
        for note in chart.notes
        if note.note_type == NoteType.ADW and note.measure == 21 and note.offset == 288
    )
    anchor = timeline.note_anchor(air_down)

    assert anchor is not None
    assert anchor.note_type in {NoteType.SLD, NoteType.SLC, NoteType.SXD, NoteType.SXC}
    assert not any("ADW at 21:288" in warning for warning in chart.warnings)
