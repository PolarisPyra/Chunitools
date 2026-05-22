from __future__ import annotations

from dataclasses import dataclass
from src.notes.base import Note

@dataclass(frozen=True, kw_only=True, slots=True)
class Tap(Note):
    """Standard tap note (TAP)."""
    def get_extra_parts(self) -> list[str]:
        return []

@dataclass(frozen=True, kw_only=True, slots=True)
class ExTap(Note):
    """Ex-Tap note (CHR)."""
    unknown: str
    def get_extra_parts(self) -> list[str]:
        return [self.unknown]

@dataclass(frozen=True, kw_only=True, slots=True)
class Mine(Note):
    """Mine note (MNE)."""
    def get_extra_parts(self) -> list[str]:
        return []
