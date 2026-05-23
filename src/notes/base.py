"""Abstract base for all CHUNITHM chart notes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from src.core.const import NoteType

DEFAULT_NOTE_DURATION = 384


# ── Shared utilities ───────────────────────────────────────────────────────


def int_from_float(value: str) -> int:
    return int(float(value))


def _valid_note_geometry(cell: int, width: int) -> bool:
    return 0 <= cell <= 15 and 1 <= width <= 16 and cell + width <= 16


class NoteHead(TypedDict):
    measure: int
    offset: int
    cell: int
    width: int
    data: tuple[str, ...]


def parse_note_head(args: list[str], *, validate_geometry: bool = False) -> NoteHead | None:
    if len(args) < 4:
        return None
    try:
        measure = int_from_float(args[0])
        offset = int_from_float(args[1])
        cell = int_from_float(args[2])
        width = int_from_float(args[3])
    except (ValueError, TypeError):
        return None
    if validate_geometry and (measure < 0 or offset < 0 or not _valid_note_geometry(cell, width)):
        return None
    return NoteHead(measure=measure, offset=offset, cell=cell, width=width, data=tuple(args[4:]))


def clamp_note_geometry(cell: int, width: int) -> tuple[int, int]:
    c = max(0, min(15, int(cell)))
    w = max(1, min(16 - c, int(width)))
    return c, w


# ── Abstract note base ─────────────────────────────────────────────────────


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
    def get_extra_parts(self) -> list[str]: ...

    def serialize(self) -> str:
        parts = [self.note_type.value, str(self.measure), str(self.offset),
                 str(self.cell), str(self.width)]
        parts.extend(str(p) for p in self.get_extra_parts())
        return "\t".join(parts)

    @classmethod
    @abstractmethod
    def parse(cls, note_type: str, head: NoteHead) -> Note:
        """Reconstruct from .c2s columns. *note_type* is a string key like ``\"TAP\"``."""

    @classmethod
    @abstractmethod
    def build(cls, note_type: str, *, measure: int = 0, offset: int = 0,
              cell: int = 0, width: int = 0, parent: Note | None = None,
              duration: int = DEFAULT_NOTE_DURATION,
              end_cell: int | None = None, end_width: int | None = None,
              target_note: str | None = None, **ignored: object) -> Note:
        """Create an editor-default note from a string key."""
