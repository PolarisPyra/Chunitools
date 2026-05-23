"""Flick note (FLK)."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.const import NoteType  # noqa: TC001
from src.notes.base import Note, NoteHead
from src.notes.schema import parse_schema_fields


@dataclass(frozen=True, kw_only=True, slots=True, init=False)
class Flick(Note):
    """Flick note (FLK)."""

    # Game format: "FLK\t%d\t%d\t%d\t%d\t%s\n"
    #              MS   OFF  CEL  WID  DIR

    direction: str

    def __init__(self, *, note_type: NoteType, measure: int, offset: int,
                 cell: int, width: int, parent: Note | None = None,
                 direction: str | None = None,
                 unknown: str | None = None) -> None:
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

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(note_type=note_type, measure=head["measure"], offset=head["offset"],
                   cell=head["cell"], width=head["width"], direction=f["direction"])

    @classmethod
    def build(cls, note_type: NoteType, *, measure=0, offset=0, cell=0, width=0,
              parent=None, **ignored) -> Note:
        return cls(note_type=note_type, measure=measure, offset=offset,
                   cell=cell, width=width, parent=parent, direction="L")

    @property
    def unknown(self) -> str:
        """Compatibility alias for older callers."""
        return self.direction

    def get_extra_parts(self) -> list[str]:
        return [self.direction]
