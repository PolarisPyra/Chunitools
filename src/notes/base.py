from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from src.core.const import NoteType

@dataclass(frozen=True, kw_only=True, slots=True)
class Note:
    """Base class for all chart notes."""

    note_type: NoteType
    measure: int
    offset: int
    cell: int
    width: int
    parent: Optional[Note] = None
