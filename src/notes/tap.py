from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.notes.base import Note

if TYPE_CHECKING:
    from src.core.const import NoteType


@dataclass(frozen=True, kw_only=True, slots=True)
class Tap(Note):
    """Standard tap note (TAP)."""

    def get_extra_parts(self) -> list[str]:
        return []


@dataclass(frozen=True, kw_only=True, slots=True, init=False)
class ExTap(Note):
    """Ex-Tap note (CHR)."""

    animation: str

    def __init__(  # noqa: PLR0913
        self,
        *,
        note_type: NoteType,
        measure: int,
        offset: int,
        cell: int,
        width: int,
        parent: Note | None = None,
        animation: str | None = None,
        unknown: str | None = None,
    ) -> None:
        if animation is None:
            if unknown is None:
                msg = "ExTap requires animation"
                raise TypeError(msg)
            animation = unknown
        object.__setattr__(self, "note_type", note_type)
        object.__setattr__(self, "measure", measure)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "cell", cell)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "parent", parent)
        object.__setattr__(self, "animation", animation)

    @property
    def unknown(self) -> str:
        """Compatibility alias for older CHR callers."""
        return self.animation

    def get_extra_parts(self) -> list[str]:
        return [self.animation]


@dataclass(frozen=True, kw_only=True, slots=True)
class Mine(Note):
    """Mine note (MNE)."""

    def get_extra_parts(self) -> list[str]:
        return []
