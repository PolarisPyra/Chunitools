from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.core.const import NoteType


@dataclass(frozen=True, kw_only=True, slots=True)
class Note(ABC):
    """Base class for all chart notes."""

    note_type: NoteType
    measure: int
    offset: int
    cell: int
    width: int
    parent: Note | None = None

    @abstractmethod
    def get_extra_parts(self) -> list[str]:
        """Serializable fields beyond the common 5-column header."""

    def serialize(self) -> str:
        """Produce a tab-separated .c2s line for this note."""
        parts = [
            self.note_type.value,
            str(self.measure),
            str(self.offset),
            str(self.cell),
            str(self.width),
        ]
        parts.extend(str(p) for p in self.get_extra_parts())
        return "\t".join(parts)
