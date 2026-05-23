"""Hold / sustain note (HLD, HXD)."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.const import NoteType  # noqa: TC001
from src.notes.base import Note, NoteHead
from src.notes.schema import parse_schema_fields


@dataclass(frozen=True, kw_only=True, slots=True)
class Hold(Note):
    """Hold / sustain note (HLD, HXD)."""

    # HLD format: "HLD\t%d\t%d\t%d\t%d\t%d\n"       MS OFF CEL WID DUR
    # HXD format: "HXD\t%d\t%d\t%d\t%d\t%d\t%s\n"    MS OFF CEL WID DUR ANI
    # (game picks HXD when animation_id < 8)

    duration: int
    animation: str | None = None

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(note_type=note_type, measure=head["measure"], offset=head["offset"],
                   cell=head["cell"], width=head["width"],
                   duration=f["duration"], animation=f.get("animation"))

    @classmethod
    def build(cls, note_type: NoteType, *, measure=0, offset=0, cell=0, width=0,
              parent=None, duration=384, **ignored) -> Note:
        return cls(note_type=note_type, measure=measure, offset=offset,
                   cell=cell, width=width, parent=parent, duration=duration)

    def get_extra_parts(self) -> list[str]:
        parts = [str(self.duration)]
        if self.animation is not None:
            parts.append(self.animation)
        return parts
