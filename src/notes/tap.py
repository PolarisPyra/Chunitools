"""Tap, ExTap, and Mine notes."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.const import NoteType  # noqa: TC001
from src.notes.base import Note, NoteHead
from src.notes.schema import parse_schema_fields


@dataclass(frozen=True, kw_only=True, slots=True)
class Tap(Note):
    """Standard tap note (TAP)."""

    # Game format: "TAP\t%d\t%d\t%d\t%d\n"
    #              MS   OFF  CEL  WID

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        return cls(
            note_type=note_type,
            measure=head["measure"],
            offset=head["offset"],
            cell=head["cell"],
            width=head["width"],
        )

    @classmethod
    def build(
        cls, note_type: NoteType, *, measure=0, offset=0, cell=0, width=0, parent=None, **ignored
    ) -> Note:
        return cls(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            parent=parent,
        )

    def get_extra_parts(self) -> list[str]:
        return []


@dataclass(frozen=True, kw_only=True, slots=True, init=False)
class ExTap(Note):
    """ExTap / TapEx note (CHR)."""

    # Game format: "CHR\t%d\t%d\t%d\t%d\t%s\n"
    #              MS   OFF  CEL  WID  ANI

    animation: str

    def __init__(
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

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(
            note_type=note_type,
            measure=head["measure"],
            offset=head["offset"],
            cell=head["cell"],
            width=head["width"],
            animation=f["animation"],
        )

    @classmethod
    def build(
        cls, note_type: NoteType, *, measure=0, offset=0, cell=0, width=0, parent=None, **ignored
    ) -> Note:
        return cls(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            parent=parent,
            animation="0",
        )

    @property
    def unknown(self) -> str:
        """Compatibility alias for older callers."""
        return self.animation

    def get_extra_parts(self) -> list[str]:
        return [self.animation]


@dataclass(frozen=True, kw_only=True, slots=True)
class Mine(Note):
    """Mine note (MNE)."""

    # Game format: "MNE\t%d\t%d\t%d\t%d\n"
    #              MS   OFF  CEL  WID

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        return cls(
            note_type=note_type,
            measure=head["measure"],
            offset=head["offset"],
            cell=head["cell"],
            width=head["width"],
        )

    @classmethod
    def build(
        cls, note_type: NoteType, *, measure=0, offset=0, cell=0, width=0, parent=None, **ignored
    ) -> Note:
        return cls(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            parent=parent,
        )

    def get_extra_parts(self) -> list[str]:
        return []
