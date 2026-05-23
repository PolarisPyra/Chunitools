"""Temporal/spatial helper for Chunithm charts."""

from __future__ import annotations

import bisect
import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Iterator

from src.core.const import AIR_NOTE_TYPES, NoteType, RenderRole
from src.notes import (
    Air,
    AirSlide,
    AirSlideStart,
    Note,
    Slide,
    SlideTo,
)
from src.notes.geometry import (
    note_duration,
    note_end_cell,
    note_end_width,
    note_get_steps,
    note_has_steps,
    note_target_note,
)

if TYPE_CHECKING:
    from src.core.models import Chart
    from src.engine.hitsounds import AudibleEvent

__all__ = ["BpmPoint", "ChartTimeline", "TimelineProtocol"]


class TimelineProtocol(Protocol):
    """Structural protocol for chart temporal/spatial queries.

    Consumers may accept any object conforming to this protocol instead of
    depending directly on :class:`ChartTimeline`.
    """

    resolution: int

    def note_tick(self, note: Note) -> int: ...
    def note_end_tick(self, note: Note) -> int: ...
    def note_abs_pos(self, note: Note) -> float: ...
    def note_abs_end_pos(self, note: Note) -> float: ...
    def note_z_index(self, note: Note) -> int: ...
    def note_anchor(self, note: Note) -> Note | None: ...
    def note_has_successor(self, note: Note) -> bool: ...
    def note_render_role(self, note: Note) -> RenderRole | None: ...
    def note_chain_root(self, note: Note) -> Note: ...
    def note_chain_successor(self, note: Note) -> Note | None: ...
    def note_chain_predecessor(self, note: Note) -> Note | None: ...
    def to_tick(self, measure: int, offset: int) -> int: ...
    def time_at(self, tick: int) -> float: ...
    def time_at_measure(self, abs_pos: float) -> float: ...
    def pos_at_time(self, seconds: float) -> float: ...
    def bpm_at(self, tick: int) -> float: ...
    def bpm_at_pos(self, abs_pos: float) -> float: ...
    def span_at(self, note: Note, tick: int) -> tuple[int, int] | None: ...
    def overlaps(self, a_cell: int, a_width: int, b_cell: int, b_width: int) -> bool: ...
    def is_mid_air(self, tick: int, cell: int, width: int) -> bool: ...
    def resolve_anchor(self, note: Note) -> Note | None: ...
    def calculate_max_measure(self) -> int: ...


GeometryKey: TypeAlias = tuple[int, int, int, int]
SlideChainKey: TypeAlias = tuple[str, int, int, int, int]
FORCED_WIDTHS: tuple[int, ...] = (1, 2, 3, 4, 6, 8, 16)
SLIDE_CHAIN_TYPES: frozenset[NoteType] = frozenset(
    {
        NoteType.SLD,
        NoteType.SXD,
        NoteType.SLC,
        NoteType.SXC,
        NoteType.ASD,
        NoteType.ASC,
        NoteType.ALD,
    }
)
CONTROL_POINT_TYPES: frozenset[NoteType] = frozenset(
    {NoteType.SLC, NoteType.SXC, NoteType.ASC, NoteType.ASX}
)
TARGET_NOTE_FAMILIES: dict[NoteType, frozenset[NoteType]] = {
    NoteType.HLD: frozenset({NoteType.HLD, NoteType.HXD}),
    NoteType.SLD: frozenset({NoteType.SLD, NoteType.SXD, NoteType.SLC, NoteType.SXC}),
    NoteType.ASD: frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX}),
    NoteType.ASC: frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX}),
    NoteType.ASX: frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX}),
}
AIR_ANCHOR_TYPES: frozenset[NoteType] = AIR_NOTE_TYPES - {NoteType.ALD}
AIR_PATH_TYPES: frozenset[NoteType] = frozenset(
    {NoteType.AHD, NoteType.ASD, NoteType.ASC, NoteType.ASX, NoteType.AHX}
)
"""Note types that create active sustained paths in the air region."""
GROUND_SLIDE_TYPES: frozenset[NoteType] = frozenset(
    {NoteType.SLD, NoteType.SXD, NoteType.SLC, NoteType.SXC}
)
AIR_SLIDE_TYPES: frozenset[NoteType] = frozenset({NoteType.ASD, NoteType.ASC, NoteType.ASX})
BEATS_PER_MEASURE = 4.0


@dataclass(frozen=True, slots=True)
class BpmPoint:
    """A point in time where the BPM changes."""

    tick: int
    bpm: float
    time: float
    abs_pos: float = 0.0


class ChartTimeline:
    """Temporal/spatial helper for Chunithm charts."""

    def __init__(self, chart: Chart) -> None:
        self.chart = chart
        self.resolution = max(1, int(chart.metadata.resolution))

        self._bpm_points: list[BpmPoint] = self._build_bpm_points()

        # External state for frozen notes
        self._abs_pos: dict[Note, float] = {}
        self._abs_end_pos: dict[Note, float] = {}
        self._z_index: dict[Note, int] = {}
        self._anchors: dict[Note, Note] = {}
        self._has_successor: dict[Note, bool] = {}
        self._render_roles: dict[Note, RenderRole | None] = {}
        self._predecessor_map: dict[Note, Note] = {}
        self._chain_root_map: dict[Note, Note] = {}
        self._successor_map: dict[Note, Note] = {}

        self._tick_index: dict[int, list[Note]] = {}
        self._end_tick_index: dict[int, list[Note]] = {}
        self._rebuild_indices()

        self._apply_structural_rules()
        self.audible_ticks: list[int] = self._calculate_audible_ticks()
        self._max_measure: int = self._calculate_max_measure_uncached()

    def _calculate_max_measure_uncached(self) -> int:
        if not self.chart or not self.chart.notes:
            return 8
        return max(note.measure for note in self.chart.notes) + 1

    def calculate_max_measure(self) -> int:
        """Get the cached maximum measure number in the chart."""
        return self._max_measure

    def note_abs_pos(self, note: Note) -> float:
        """Get the absolute spatial position of a note."""
        return self._abs_pos.get(note, 0.0)

    def note_abs_end_pos(self, note: Note) -> float:
        """Get the absolute spatial end position of a note."""
        return self._abs_end_pos.get(note, 0.0)

    def note_z_index(self, note: Note) -> int:
        """Get the visual layer Z-index for a note."""
        return self._z_index.get(note, 0)

    def note_anchor(self, note: Note) -> Note | None:
        """Get the anchor/parent note for an air modifier."""
        return self._anchors.get(note)

    def note_has_successor(self, note: Note) -> bool:
        """Check if this note is followed by another in a chain."""
        return self._has_successor.get(note, False)

    def note_chain_root(self, note: Note) -> Note:
        """Get the root head of the chain this note belongs to."""
        return self._chain_root_map.get(note, note)

    def note_chain_successor(self, note: Note) -> Note | None:
        """Get the next note in the chain."""
        return self._successor_map.get(note)

    def note_render_role(self, note: Note) -> RenderRole | None:
        """Get the structural rendering role for this note."""
        return self._render_roles.get(note)

    def _calculate_audible_ticks(self) -> list[int]:
        from src.engine.hitsounds import get_audible_ticks  # noqa: PLC0415

        ticks: list[int] = []

        for note in self.chart.notes:
            for tick in get_audible_ticks(note, self):
                ticks.append(tick)

        return sorted(ticks)

    def audible_events(self) -> list[AudibleEvent]:
        """Return hitsound events with per-note render timing adjustments."""
        from src.engine.hitsounds import get_audible_events  # noqa: PLC0415

        events = []
        for note in self.chart.notes:
            events.extend(get_audible_events(note, self))
        return sorted(events, key=lambda event: (event.tick, event.delay_seconds))

    def _apply_structural_rules(self) -> None:
        """Calculate render helper fields."""
        for note in self._iter_notes_with_steps():
            self._cache_note_layout(note)

        self.chart.notes.sort(
            key=lambda note: (
                self.note_abs_pos(note),
                note.cell,
                note.width,
                note.note_type.value,
            )
        )
        self._rebuild_indices()

        self._classify_slide_roles()
        self.chart.warnings = self._resolve_anchors_and_validate()

    def _get_note_duration(self, note: Note) -> int:
        return note_duration(note)

    def _get_note_end_cell(self, note: Note) -> int:
        return note_end_cell(note)

    def _get_note_end_width(self, note: Note) -> int:
        return note_end_width(note)

    def _get_note_target_note(self, note: Note) -> str:
        return note_target_note(note)

    def _iter_notes_with_steps(self) -> Iterator[Note]:
        """Yield top-level notes and nested slide steps in render order."""
        for note in self.chart.notes:
            yield note
            if note_has_steps(note):
                yield from note_get_steps(note)

    def _cache_note_layout(self, note: Note) -> None:
        abs_pos = note.measure + note.offset / self.resolution
        duration = self._get_note_duration(note)

        self._abs_pos[note] = abs_pos
        self._abs_end_pos[note] = abs_pos + max(0, duration) / self.resolution
        self._z_index[note] = self._calculate_z_index(note)

    def _calculate_z_index(self, note: Note) -> int:
        if note.note_type == NoteType.CHR:
            return 10
        if note.note_type == NoteType.FLK:
            return 15
        if note.note_type in AIR_ANCHOR_TYPES:
            return 20
        return 0

    def round_forced_width(self, width: int) -> int:
        """Return the nearest forced visual width without mutating source data."""
        width = max(1, min(16, int(width)))
        return min(FORCED_WIDTHS, key=lambda forced: (abs(forced - width), forced))

    def visual_forced_width(self, note: Note) -> int:
        """Optional render-only forced width."""
        return self.round_forced_width(note.width)

    def _get_geometry_key(self, note: Note, use_end: bool = False) -> GeometryKey:
        if use_end:
            end_tick = self.note_end_tick(note)
            measure = end_tick // self.resolution
            offset = end_tick % self.resolution
            cell = int(round(float(self._get_note_end_cell(note))))
            width = max(1, int(round(float(self._get_note_end_width(note)))))
        else:
            measure = note.measure
            offset = note.offset
            cell = int(round(float(note.cell)))
            width = max(1, int(round(float(note.width))))
        return measure, offset, cell, width

    def _get_slide_chain_key(self, note: Note, use_end: bool = False) -> SlideChainKey:
        family = self._slide_chain_family(note.note_type)
        return (family, *self._get_geometry_key(note, use_end))

    def _slide_chain_family(self, note_type: NoteType) -> str:
        if note_type in GROUND_SLIDE_TYPES:
            return "ground"
        if note_type in AIR_SLIDE_TYPES:
            return "air"
        return note_type.value

    def _find_slide_predecessors(
        self, note: Note, end_map: dict[SlideChainKey, list[Note]]
    ) -> list[Note]:
        start_key = self._get_slide_chain_key(note, use_end=False)
        return [cand for cand in end_map.get(start_key, []) if cand is not note]

    def _find_slide_successor(
        self, note: Note, start_map: dict[SlideChainKey, list[Note]]
    ) -> Note | None:
        end_key = self._get_slide_chain_key(note, use_end=True)
        successors = [cand for cand in start_map.get(end_key, []) if cand is not note]
        return successors[0] if len(successors) == 1 else None

    def _classify_slide_roles(self) -> None:
        """Assign slide render roles from structural continuity."""
        slide_notes = [
            note for note in self._iter_notes_with_steps() if note.note_type in SLIDE_CHAIN_TYPES
        ]

        start_map: dict[SlideChainKey, list[Note]] = {}
        end_map: dict[SlideChainKey, list[Note]] = {}
        for note in slide_notes:
            start_map.setdefault(self._get_slide_chain_key(note, False), []).append(note)
            end_map.setdefault(self._get_slide_chain_key(note, True), []).append(note)

        for note in slide_notes:
            predecessors = self._find_slide_predecessors(note, end_map)
            has_predecessor = bool(predecessors)
            if has_predecessor:
                self._predecessor_map.setdefault(note, predecessors[0])
            successor = self._find_slide_successor(note, start_map)
            has_successor = successor is not None
            self._has_successor[note] = has_successor
            if successor:
                self._successor_map[note] = successor
                self._predecessor_map[successor] = note

            if note.note_type in CONTROL_POINT_TYPES:
                self._render_roles[note] = (
                    RenderRole.CONTROL if has_predecessor else RenderRole.HEAD
                )
                continue

            if has_predecessor and has_successor:
                self._render_roles[note] = RenderRole.TAP
            elif not has_predecessor:
                self._render_roles[note] = RenderRole.HEAD
            else:
                self._render_roles[note] = None

        # Pre-calculate chain roots for all slide/trace notes
        self._chain_root_map.clear()
        for note in slide_notes:
            self._chain_root_map[note] = self._find_slide_chain_root(note, end_map)

    def _find_slide_chain_root(self, note: Note, end_map: dict[SlideChainKey, list[Note]]) -> Note:
        current = note
        visited = {id(current)}

        while True:
            predecessors = self._find_slide_predecessors(current, end_map)
            if not predecessors or id(predecessors[0]) in visited:
                return current

            current = predecessors[0]
            visited.add(id(current))

    def _resolve_anchors_and_validate(self) -> list[str]:
        warnings: list[str] = []
        for note in self._iter_notes_with_steps():
            warning = self._resolve_note_anchor(note)
            if warning:
                warnings.append(warning)

        for note in self._iter_notes_with_steps():
            warning = self._validate_note(note)
            if warning:
                warnings.append(warning)

        return warnings

    def _validate_note(self, note: Note) -> str | None:
        if note.note_type == NoteType.ALD:
            crush_interval = getattr(note, "crush_interval", 0)
            duration = getattr(note, "duration", 0)
            if crush_interval > 0 and duration <= 0:
                return (
                    f"ALD at {note.measure}:{note.offset} "
                    f"(cell={note.cell}, width={note.width}) has "
                    f"crush_interval={crush_interval} but duration={duration}; "
                    f"no crush elements will be drawn"
                )

        return None

    def _resolve_note_anchor(self, note: Note) -> str | None:  # noqa: PLR0911
        if note.parent is not None:
            self._anchors[note] = note.parent
            return None

        if note.note_type not in AIR_ANCHOR_TYPES:
            return None

        target_type = self._get_note_target_note(note)
        if not target_type:
            return (
                f"{note.note_type.value} at {note.measure}:{note.offset} "
                f"(cell={note.cell}, width={note.width}) missing target note type"
            )

        required_type = self._parse_note_type(target_type)
        if required_type is None:
            return (
                f"{note.note_type.value} at {note.measure}:{note.offset} "
                f"(cell={note.cell}, width={note.width}) has unresolved target "
                f"'{target_type}' at this timestamp"
            )

        candidates = self._anchor_candidates(note, required_type)
        if len(candidates) == 0:
            return (
                f"{note.note_type.value} at {note.measure}:{note.offset} "
                f"(cell={note.cell}, width={note.width}) has unresolved target "
                f"'{target_type}' at this timestamp"
            )
        if len(candidates) > 1:
            return (
                f"{note.note_type.value} at {note.measure}:{note.offset} "
                f"(cell={note.cell}, width={note.width}) has {len(candidates)} "
                f"matching targets for '{target_type}' at this timestamp"
            )

        self._anchors[note] = candidates[0]
        return None

    def _build_bpm_points(self) -> list[BpmPoint]:
        raw_bpms = sorted(
            self.chart.bpms,
            key=lambda entry: self.to_tick(entry["measure"], entry["offset"]),
        )

        default_bpm = 120.0
        if self.chart.metadata.bpm_def:
            with contextlib.suppress(ValueError, IndexError):
                default_bpm = float(self.chart.metadata.bpm_def[0])

        points: list[BpmPoint] = []
        current_tick = 0
        current_time = 0.0
        current_bpm = default_bpm

        if not raw_bpms or self.to_tick(raw_bpms[0]["measure"], raw_bpms[0]["offset"]) > 0:
            points.append(BpmPoint(0, current_bpm, 0.0, 0.0))

        for entry in raw_bpms:
            tick = self.to_tick(entry["measure"], entry["offset"])
            bpm = float(entry["bpm"])

            delta_ticks = tick - current_tick
            if delta_ticks > 0:
                current_time += self._seconds_for_ticks(delta_ticks, current_bpm)

            current_tick = tick
            current_bpm = bpm
            points.append(BpmPoint(tick, bpm, current_time, tick / self.resolution))

        if not points:
            points.append(BpmPoint(0, default_bpm, 0.0, 0.0))

        return points

    def _rebuild_indices(self) -> None:
        self._tick_index.clear()
        self._end_tick_index.clear()
        for note in self._iter_notes_with_steps():
            self._tick_index.setdefault(self.note_tick(note), []).append(note)
            self._end_tick_index.setdefault(self.note_end_tick(note), []).append(note)

    def to_tick(self, measure: int, offset: int) -> int:
        """Convert measure and offset to absolute tick."""
        return measure * self.resolution + offset

    def note_tick(self, note: Note) -> int:
        """Get the absolute start tick of a note."""
        return self.to_tick(note.measure, note.offset)

    def note_end_tick(self, note: Note) -> int:
        """Get the absolute end tick of a note."""
        duration = max(0, self._get_note_duration(note))
        return self.note_tick(note) + duration

    def bpm_at(self, tick: int) -> float:
        """Get the BPM active at a specific tick."""
        index = bisect.bisect_right(self._bpm_points, tick, key=lambda point: point.tick)
        return self._bpm_points[max(0, index - 1)].bpm

    def bpm_at_pos(self, abs_pos: float) -> float:
        """Get the BPM active at an absolute spatial position."""
        index = bisect.bisect_right(self._bpm_points, abs_pos, key=lambda point: point.abs_pos)
        return self._bpm_points[max(0, index - 1)].bpm

    def time_at(self, tick: int) -> float:
        """Get the absolute time in seconds at a specific tick."""
        return self.time_at_measure(tick / self.resolution)

    def time_at_measure(self, abs_pos: float) -> float:
        """Get the absolute time in seconds at a fractional measure position."""
        clamped_pos = max(0.0, abs_pos)
        index = bisect.bisect_right(self._bpm_points, clamped_pos, key=lambda point: point.abs_pos)
        point = self._bpm_points[max(0, index - 1)]

        delta_pos = clamped_pos - point.abs_pos
        if delta_pos <= 0:
            return point.time

        return point.time + self._seconds_for_measures(delta_pos, point.bpm)

    def pos_at_time(self, seconds: float) -> float:
        """Get the absolute chart position in measures at a song time."""
        clamped_seconds = max(0.0, seconds)
        index = bisect.bisect_right(self._bpm_points, clamped_seconds, key=lambda point: point.time)
        point = self._bpm_points[max(0, index - 1)]
        delta_seconds = clamped_seconds - point.time
        if delta_seconds <= 0.0:
            return point.abs_pos

        return point.abs_pos + self._measures_for_seconds(delta_seconds, point.bpm)

    def _seconds_for_ticks(self, ticks: int, bpm: float) -> float:
        return self._seconds_for_measures(ticks / self.resolution, bpm)

    def _seconds_for_measures(self, measures: float, bpm: float) -> float:
        # 1 measure = BEATS_PER_MEASURE beats
        # beats = measures * BEATS_PER_MEASURE
        # seconds = beats / (bpm / 60)
        return (measures * BEATS_PER_MEASURE) / (bpm / 60.0)

    def _ticks_for_seconds(self, seconds: float, bpm: float) -> float:
        return self._measures_for_seconds(seconds, bpm) * self.resolution

    def _measures_for_seconds(self, seconds: float, bpm: float) -> float:
        # beats = seconds * (bpm / 60)
        # measures = beats / BEATS_PER_MEASURE
        return (seconds * (bpm / 60.0)) / BEATS_PER_MEASURE

    def span_at(self, note: Note, tick: int) -> tuple[int, int] | None:
        """Interpolate a note span (cell, width) at an absolute tick."""
        start = self.note_tick(note)
        duration = max(0, self._get_note_duration(note))
        end = start + duration

        if tick < start or tick > end:
            return None

        if duration <= 0:
            return int(round(float(note.cell))), max(1, int(round(float(note.width))))

        ratio = (tick - start) / duration
        start_cell = float(note.cell)
        start_width = float(note.width)
        end_cell = float(self._get_note_end_cell(note))
        end_width = float(self._get_note_end_width(note))

        cell = int(round(start_cell + (end_cell - start_cell) * ratio))
        width = max(1, int(round(start_width + (end_width - start_width) * ratio)))

        return cell, width

    def overlaps(self, a_cell: int, a_width: int, b_cell: int, b_width: int) -> bool:
        """Check if two lane spans overlap."""
        a_end = int(a_cell) + max(1, int(a_width))
        b_end = int(b_cell) + max(1, int(b_width))
        return not (a_end <= int(b_cell) or b_end <= int(a_cell))

    def note_chain_predecessor(self, note: Note) -> Note | None:
        """Get the immediate predecessor of a note in a slide chain, if any."""
        return self._predecessor_map.get(note)

    def resolve_anchor(self, note: Note) -> Note | None:
        """Find the single exact parent/anchor note for AIR/AHD/ASD/ASC/etc."""
        target_type = self._get_note_target_note(note)
        if not target_type:
            return None

        required_type = self._parse_note_type(target_type)
        if required_type is None:
            return None

        candidates = self._anchor_candidates(note, required_type)
        return candidates[0] if candidates else None

    def _parse_note_type(self, value: str) -> NoteType | None:
        try:
            return NoteType(value)
        except ValueError:
            return None

    def _anchor_candidates(self, note: Note, required_type: NoteType) -> list[Note]:
        tick = self.note_tick(note)
        raw_matches = []
        required_types = TARGET_NOTE_FAMILIES.get(required_type, frozenset({required_type}))
        for candidate in self._iter_notes_with_steps():
            if (
                candidate is note
                or candidate.note_type == NoteType.ALD
                or candidate.note_type not in required_types
            ):
                continue

            for anchor_tick, anchor_cell, anchor_width in self._exact_anchor_points(candidate):
                if anchor_tick != tick or anchor_cell != note.cell or anchor_width != note.width:
                    continue
                if candidate not in raw_matches:
                    raw_matches.append(candidate)
                break

        preferred_matches = self._preferred_anchor_matches(raw_matches, required_type)
        matches = []
        for candidate in preferred_matches:
            anchor = (
                candidate if isinstance(note, Air) else self._canonical_anchor_candidate(candidate)
            )
            if anchor not in matches:
                matches.append(anchor)
        return matches

    def _preferred_anchor_matches(
        self, candidates: list[Note], required_type: NoteType
    ) -> list[Note]:
        exact_matches = [
            candidate for candidate in candidates if candidate.note_type == required_type
        ]
        if exact_matches:
            return exact_matches

        step_matches: list[Note] = [
            candidate for candidate in candidates if isinstance(candidate, (SlideTo, AirSlide))
        ]
        if step_matches:
            return step_matches

        return candidates

    def _exact_anchor_points(self, note: Note) -> tuple[tuple[int, int, int], ...]:
        points = [(self.note_tick(note), int(note.cell), int(note.width))]
        if self._get_note_duration(note) > 0:
            points.append(
                (
                    self.note_end_tick(note),
                    int(round(float(self._get_note_end_cell(note)))),
                    max(1, int(round(float(self._get_note_end_width(note))))),
                )
            )
        return tuple(points)

    def _canonical_anchor_candidate(self, candidate: Note) -> Note:
        if not isinstance(candidate, (SlideTo, AirSlide)):
            return candidate

        for note in self.chart.notes:
            if isinstance(note, (Slide, AirSlideStart)) and candidate in note.steps:
                return note

        return candidate

    def is_mid_air(self, tick: int, cell: int, width: int) -> bool:
        """Check if a coordinate is inside an active air path."""
        for note in self.chart.notes:
            if note.note_type not in AIR_PATH_TYPES:
                continue

            start = self.note_tick(note)
            end = self.note_end_tick(note)
            if start < tick <= end:
                span = self.span_at(note, tick)
                if span and self.overlaps(cell, width, span[0], span[1]):
                    return True
        return False
