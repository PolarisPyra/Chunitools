from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.notes.base import Note

if TYPE_CHECKING:
    from src.core.const import NoteType


@dataclass(frozen=True, kw_only=True, slots=True, init=False)
class Flick(Note):
    """Flick note (FLK)."""

    direction: str

    def __init__(  # noqa: PLR0913
        self,
        *,
        note_type: NoteType,
        measure: int,
        offset: int,
        cell: int,
        width: int,
        parent: Note | None = None,
        direction: str | None = None,
        unknown: str | None = None,
    ) -> None:
        if direction is None:
            if unknown is None:
                msg = "Flick requires direction"
                raise TypeError(msg)
            direction = unknown
        object.__setattr__(self, "note_type", note_type)
        object.__setattr__(self, "measure", measure)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "cell", cell)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "parent", parent)
        object.__setattr__(self, "direction", direction)

    @property
    def unknown(self) -> str:
        """Compatibility alias for older FLK callers."""
        return self.direction

    def get_extra_parts(self) -> list[str]:
        return [self.direction]
