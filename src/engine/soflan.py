"""Scroll-speed projection helpers for SFL and SLA/SLP effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.models import Chart, SofLanArea
    from src.engine.timeline import ChartTimeline
    from src.notes import Note


@dataclass(frozen=True, slots=True)
class ScrollEvent:
    """A scroll speed change in song seconds."""

    time: float
    speed: float


class SoflanProjector:
    """Game-style integrated scroll transform for visible note depth."""

    def __init__(self, chart: Chart) -> None:
        self.chart = chart
        self.timeline: ChartTimeline = chart.timeline
        self.groups: dict[int, list[ScrollEvent]] = self._build_groups()
        self._areas: list[tuple[int, int, SofLanArea]] = [
            (
                self.timeline.to_tick(area.measure, area.tick),
                self.timeline.to_tick(area.measure, area.tick) + area.duration,
                area,
            )
            for area in chart.soflan_areas
        ]

    def has_scroll_effects(self) -> bool:
        return bool(self.groups or self._areas)

    def depth_for_note_tick(
        self,
        note: Note,
        tick: int,
        note_time: float,
        judge_time: float,
        window: float,
        *,
        cell: float | None = None,
        width: float | None = None,
    ) -> float:
        if window < 0.001:
            return 0.0

        normal_depth = (note_time - judge_time) / window
        if note_time < judge_time:
            return normal_depth

        group = self._group_for_note_at(note, tick, cell=cell, width=width)
        if group is None or group not in self.groups:
            return normal_depth

        note_scroll = self._integrated_scroll(note_time, group)
        judge_scroll = self._integrated_scroll(judge_time, group)
        return (note_scroll - judge_scroll) / window

    def _build_groups(self) -> dict[int, list[ScrollEvent]]:
        groups: dict[int, list[ScrollEvent]] = {}

        for speed in self.chart.scroll_speeds:
            start_tick = self.timeline.to_tick(speed.measure, speed.tick)
            end_tick = start_tick + max(0, speed.duration)
            self._add_event(groups, 0, start_tick, speed.multiplier)
            self._add_event(groups, 0, end_tick, 1.0)

        for pattern in self.chart.soflan_patterns:
            start_tick = self.timeline.to_tick(pattern.measure, pattern.tick)
            end_tick = start_tick + max(0, pattern.duration)
            self._add_event(groups, pattern.pattern_id, start_tick, pattern.speed)
            self._add_event(groups, pattern.pattern_id, end_tick, 1.0)

        return {
            group: sorted(events, key=lambda event: event.time)
            for group, events in groups.items()
        }

    def _add_event(
        self,
        groups: dict[int, list[ScrollEvent]],
        group: int,
        tick: int,
        speed: float,
    ) -> None:
        groups.setdefault(group, []).append(
            ScrollEvent(self.timeline.time_at(max(0, tick)), speed)
        )

    def _group_for_note_at(
        self,
        note: Note,
        tick: int,
        *,
        cell: float | None = None,
        width: float | None = None,
    ) -> int | None:
        note_cell = float(note.cell if cell is None else cell)
        note_width = float(note.width if width is None else width)
        note_end = note_cell + note_width

        matches = []
        for start_tick, end_tick, area in self._areas:
            if not (start_tick <= tick <= end_tick):
                continue
            area_cell = float(area.cell)
            area_end = area_cell + float(area.width)
            if note_cell >= area_cell and note_end <= area_end:
                matches.append(area)

        if not matches:
            return 0 if self.chart.scroll_speeds else None

        # Prefer the tightest matching area so full-width helper notes are not
        # pulled into a narrow lane-local soflan strip.
        return min(matches, key=lambda area: (area.width, area.cell)).area_id

    def _integrated_scroll(self, time: float, group: int) -> float:
        events = self.groups.get(group)
        if not events:
            return time

        clamped_time = max(0.0, time)
        current_speed = 1.0
        accumulated = 0.0
        previous_time = 0.0

        for event in events:
            if clamped_time < event.time:
                break
            accumulated += (event.time - previous_time) * current_speed
            previous_time = event.time
            current_speed = event.speed

        return accumulated + (clamped_time - previous_time) * current_speed
