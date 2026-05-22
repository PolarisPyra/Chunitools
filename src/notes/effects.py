from __future__ import annotations

from dataclasses import dataclass

from src.notes.base import Note


@dataclass(frozen=True, kw_only=True, slots=True)
class AirSolid(Note):
    """ASO air-solid note exported by the game."""

    starting_height: float
    starting_depth: float
    duration: int
    end_cell: int
    end_width: int
    target_height: float
    target_depth: float
    color: str

    def get_extra_parts(self) -> list[str]:
        return [
            f"{self.starting_height:.1f}",
            f"{self.starting_depth:.1f}",
            str(self.duration),
            str(self.end_cell),
            str(self.end_width),
            f"{self.target_height:.1f}",
            f"{self.target_depth:.1f}",
            self.color,
        ]


@dataclass(frozen=True, kw_only=True, slots=True)
class HeavenHold(Note):
    """HHD/HHX height-aware hold note exported by the game."""

    starting_height: float
    duration: int
    end_cell: int
    end_width: int
    target_height: float
    heaven_id: int
    animation: str | None = None

    def get_extra_parts(self) -> list[str]:
        parts = [
            f"{self.starting_height:.1f}",
            str(self.duration),
            str(self.end_cell),
            str(self.end_width),
            f"{self.target_height:.1f}",
            str(self.heaven_id),
        ]
        if self.animation is not None:
            parts.append(self.animation)
        return parts
