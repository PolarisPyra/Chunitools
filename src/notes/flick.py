from __future__ import annotations

from dataclasses import dataclass

from src.notes.base import Note


@dataclass(frozen=True, kw_only=True, slots=True)
class Flick(Note):
    """Flick note (FLK)."""

    unknown: str  # Usually "L"

    def get_extra_parts(self) -> list[str]:
        return [self.unknown]
