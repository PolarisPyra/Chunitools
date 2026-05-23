from __future__ import annotations

from dataclasses import dataclass, field

from src.notes.base import Note


@dataclass(frozen=True, kw_only=True, slots=True)
class Air(Note):
    """Air arrow notes (AIR, AUR, AUL, ADW, ADR, ADL)."""

    target_note: str
    color: str = "DEF"
    color_is_explicit: bool = field(default=False, repr=False)

    def get_extra_parts(self) -> list[str]:
        if self.color == "DEF" and not self.color_is_explicit:
            return [self.target_note]
        return [self.target_note, self.color]


@dataclass(frozen=True, kw_only=True, slots=True)
class AirHoldStart(Note):
    """Air Hold Start (AHD)."""

    target_note: str
    duration: int
    color: str = "DEF"
    color_is_explicit: bool = field(default=False, repr=False)

    def get_extra_parts(self) -> list[str]:
        parts = [self.target_note, str(self.duration)]
        if self.color != "DEF" or self.color_is_explicit:
            parts.append(self.color)
        return parts


@dataclass(frozen=True, kw_only=True, slots=True)
class AirHold(Note):
    """Purple air-action note attached to an air hold (AHX)."""

    target_note: str
    duration: int
    color: str

    def get_extra_parts(self) -> list[str]:
        return [self.target_note, str(self.duration), self.color]


@dataclass(frozen=True, kw_only=True, slots=True)
class CrashSlide(Note):
    """ALD air trace/effect; color NON is AIR-ACTION/AIR CRUSH."""

    crush_interval: int
    """Tick interval between crush elements (0 = no crush, 38400 = single-shot AIR-ACTION)."""
    starting_height: float
    duration: int
    end_cell: int
    end_width: int
    target_height: float
    color: str

    def get_extra_parts(self) -> list[str]:
        return [
            str(self.crush_interval),
            str(self.starting_height),
            str(self.duration),
            str(self.end_cell),
            str(self.end_width),
            str(self.target_height),
            self.color,
        ]


@dataclass(frozen=True, kw_only=True, slots=True)
class AirSlide(Note):
    """ASD/ASC air slide wrapper segment."""

    target_note: str
    starting_height: float
    duration: int
    end_cell: int
    end_width: int
    target_height: float
    color: str

    def get_extra_parts(self) -> list[str]:
        return [
            self.target_note,
            str(self.starting_height),
            str(self.duration),
            str(self.end_cell),
            str(self.end_width),
            str(self.target_height),
            self.color,
        ]


@dataclass(frozen=True, kw_only=True, slots=True)
class AirSlideStart(Note):
    """Joined ASD/ASC air slide wrapper."""

    steps: tuple[AirSlide, ...]

    @property
    def duration(self) -> int:
        return sum(s.duration for s in self.steps)

    @property
    def end_cell(self) -> int:
        return self.steps[-1].end_cell if self.steps else self.cell

    @property
    def end_width(self) -> int:
        return self.steps[-1].end_width if self.steps else self.width

    @property
    def target_note(self) -> str:
        return self.steps[0].target_note if self.steps else ""

    @property
    def color(self) -> str:
        return self.steps[0].color if self.steps else "DEF"

    def get_extra_parts(self) -> list[str]:
        return []
