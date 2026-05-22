from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from src.notes.base import Note

@dataclass(frozen=True, kw_only=True, slots=True)
class Hold(Note):
    """Hold / Sustain note (HLD, HXD)."""
    duration: int
    animation: Optional[str] = None

    def get_extra_parts(self) -> list[str]:
        parts = [str(self.duration)]
        if self.animation is not None:
            parts.append(self.animation)
        return parts
