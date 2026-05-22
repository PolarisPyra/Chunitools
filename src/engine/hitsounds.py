"""Playback logic for triggering hitsounds."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.const import NoteType, RenderRole
from src.notes import (
    Air,
    AirHold,
    AirHoldStart,
    AirSlide,
    AirSlideStart,
    Hold,
    Slide,
    SlideTo,
)

if TYPE_CHECKING:
    from src.engine.timeline import ChartTimeline
    from src.notes import Note


RENDER_DEFAULT_JDG_TIMING_AIR = 20
RENDER_AIR_JUDGEMENT_DELAY_SECONDS = RENDER_DEFAULT_JDG_TIMING_AIR / 6000


@dataclass(frozen=True, slots=True)
class AudibleEvent:
    """A hitsound event with render-compatible timing adjustment."""

    tick: int
    delay_seconds: float = 0.0


def get_audible_ticks(note: "Note", timeline: "ChartTimeline") -> list[int]:
    """Return ticks where this note should trigger a hitsound."""
    return [event.tick for event in get_audible_events(note, timeline)]


def get_audible_events(note: "Note", timeline: "ChartTimeline") -> list[AudibleEvent]:
    """Return hitsound events where this note should pass the judgement line."""
    if isinstance(note, Hold):
        return [
            AudibleEvent(timeline.note_tick(note)),
            AudibleEvent(timeline.note_end_tick(note)),
        ]

    if isinstance(note, Slide):
        render_role = timeline.note_render_role(note)
        events = (
            [AudibleEvent(timeline.note_tick(note))]
            if render_role == RenderRole.HEAD and not _has_matching_extap_head(note, timeline)
            else []
        )
        events.extend(
            AudibleEvent(timeline.note_end_tick(step))
            for step in note.steps
            if isinstance(step, SlideTo) and step.is_visible
        )
        return events

    if isinstance(note, (AirHoldStart, AirHold)):
        return [_air_event(timeline.note_end_tick(note))]

    if isinstance(note, AirSlideStart):
        return [
            _air_event(timeline.note_end_tick(step))
            for step in note.steps
            if isinstance(step, AirSlide) and step.note_type == NoteType.ASD
        ]

    if isinstance(note, Air):
        return [_air_event(timeline.note_tick(note))]

    # Default for other notes (TAP, CHR, etc.)
    if note.note_type in (NoteType.TAP, NoteType.CHR, NoteType.FLK):
        return [AudibleEvent(timeline.note_tick(note))]

    return []


def _air_event(tick: int) -> AudibleEvent:
    return AudibleEvent(tick, RENDER_AIR_JUDGEMENT_DELAY_SECONDS)


def _has_matching_extap_head(note: "Note", timeline: "ChartTimeline") -> bool:
    if note.note_type not in (NoteType.SXD, NoteType.SXC):
        return False

    tick = timeline.note_tick(note)
    return any(
        other is not note
        and other.note_type == NoteType.CHR
        and timeline.note_tick(other) == tick
        and other.cell == note.cell
        and other.width == note.width
        for other in timeline.chart.notes
    )
