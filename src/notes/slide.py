"""Slide chain notes (SLD, SLC, SXD, SXC)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.const import NoteType  # noqa: TC001
from src.notes.base import Note, NoteHead, clamp_note_geometry as _clamp
from src.notes.schema import parse_schema_fields


@dataclass(frozen=True, kw_only=True, slots=True)
class SlideTo(Note):
    """A single segment/step within a slide chain."""

    # SLD format: "SLD\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\n"
    #              MS   OFF  CEL  WID  DUR  ECL  EWD  ANI
    # SLC format: "SLC\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\n"
    #              MS   OFF  CEL  WID  DUR  ECL  EWD  TRG
    # SXD format: "SXD\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\n"
    #              MS   OFF  CEL  WID  DUR  ECL  EWD  TRG  ANI
    # SXC format: "SXC\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\n"
    #              MS   OFF  CEL  WID  DUR  ECL  EWD  TRG  ANI
    #
    # Game dispatches SLD vs SXD, SLC vs SXC based on animation_id < 8.

    duration: int
    end_cell: int
    end_width: int
    target_id: str | None = None
    animation: str | None = None
    is_visible: bool = True

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(
            note_type=note_type, measure=head["measure"], offset=head["offset"],
            cell=head["cell"], width=head["width"],
            duration=f["duration"], end_cell=f["end_cell"], end_width=f["end_width"],
            target_id=f.get("target_id"), animation=f.get("animation"),
            is_visible=note_type.value.endswith("D"),
        )

    @classmethod
    def build(cls, note_type: NoteType, *, measure=0, offset=0, cell=0, width=0,
              parent=None, duration=384,
              end_cell=None, end_width=None, **ignored) -> Note:
        ec, ew = _clamp(cell if end_cell is None else end_cell,
                        width if end_width is None else end_width)
        return cls(note_type=note_type, measure=measure, offset=offset,
                   cell=cell, width=width, parent=parent,
                   duration=duration, end_cell=ec, end_width=ew,
                   target_id="", animation=None,
                   is_visible=note_type in {'SLD', 'SXD'})

    def get_extra_parts(self) -> list[str]:
        parts = [str(self.duration), str(self.end_cell), str(self.end_width)]
        parts.append(self.target_id if self.target_id is not None else "")
        if self.animation is not None:
            parts.append(self.animation)
        return parts

@dataclass(frozen=True, kw_only=True, slots=True)
class Slide(Note):
    """Hierarchical slide note containing multiple steps."""

    steps: tuple[SlideTo, ...] = field(default_factory=tuple)

    @property
    def duration(self) -> int:
        return sum(s.duration for s in self.steps)

    @property
    def end_cell(self) -> int:
        return self.steps[-1].end_cell if self.steps else self.cell

    @property
    def end_width(self) -> int:
        return self.steps[-1].end_width if self.steps else self.width

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        # Slide is a wrapper; individual steps are parsed as SlideTo.
        raise NotImplementedError("Slide is a composite wrapper; parse SlideTo instead")

    @classmethod
    def build(cls, note_type: NoteType, *, measure=0, offset=0, cell=0, width=0,
              parent=None, duration=384,
              end_cell=None, end_width=None, **ignored) -> Note:
        step = SlideTo.build(note_type, measure=measure, offset=offset, cell=cell,
                             width=width, duration=duration,
                             end_cell=end_cell, end_width=end_width)
        return cls(note_type=note_type, measure=measure, offset=offset,
                   cell=cell, width=width, parent=parent, steps=(step,))

    def get_extra_parts(self) -> list[str]:
        return []
