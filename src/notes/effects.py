"""Air Solid (ASO) and Heaven Hold (HHD, HHX) notes."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.const import NoteType  # noqa: TC001
from src.notes.base import Note, NoteHead, clamp_note_geometry as _clamp
from src.notes.schema import parse_schema_fields


@dataclass(frozen=True, kw_only=True, slots=True)
class AirSolid(Note):
    """ASO — air solid path between start and target lane/height."""

    # Game format: "ASO\t%d\t%d\t%d\t%d\t%3.1f\t%3.1f\t%d\t%d\t%d\t%3.1f\t%3.1f\t%s\n"
    #              MS   OFF  CEL  WID  SHGT  SDEP  DUR  ECL  EWD  THGT  TDEP  CLR

    starting_height: float
    starting_depth: float
    duration: int
    end_cell: int
    end_width: int
    target_height: float
    target_depth: float
    color: str

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(note_type=note_type, measure=head["measure"], offset=head["offset"],
                   cell=head["cell"], width=head["width"],
                   starting_height=f["starting_height"],
                   starting_depth=f["starting_depth"], duration=f["duration"],
                   end_cell=f["end_cell"], end_width=f["end_width"],
                   target_height=f["target_height"], target_depth=f["target_depth"],
                   color=f["color"])

    @classmethod
    def build(cls, note_type: NoteType, *, measure=0, offset=0, cell=0, width=0,
              parent=None, duration=384,
              end_cell=None, end_width=None, **ignored) -> Note:
        ec, ew = _clamp(cell if end_cell is None else end_cell,
                        width if end_width is None else end_width)
        return cls(note_type=note_type, measure=measure, offset=offset,
                   cell=cell, width=width, parent=parent,
                   starting_height=1.0, starting_depth=1.0, duration=duration,
                   end_cell=ec, end_width=ew, target_height=1.0,
                   target_depth=1.0, color="DEF")

    def get_extra_parts(self) -> list[str]:
        return [f"{self.starting_height:.1f}", f"{self.starting_depth:.1f}",
                str(self.duration), str(self.end_cell), str(self.end_width),
                f"{self.target_height:.1f}", f"{self.target_depth:.1f}", self.color]

@dataclass(frozen=True, kw_only=True, slots=True)
class HeavenHold(Note):
    """HHD / HHX — height-aware hold note."""

    # HHD format: "HHD\t%d\t%d\t%d\t%d\t%3.1f\t%d\t%d\t%d\t%3.1f\t%d\n"
    #              MS   OFF  CEL  WID  SHGT  DUR  ECL  EWD  THGT  HID
    # HHX format: "HHX\t%d\t%d\t%d\t%d\t%3.1f\t%d\t%d\t%d\t%3.1f\t%d\t%s\n"
    #              MS   OFF  CEL  WID  SHGT  DUR  ECL  EWD  THGT  HID  ANI

    starting_height: float
    duration: int
    end_cell: int
    end_width: int
    target_height: float
    heaven_id: int
    animation: str | None = None

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(note_type=note_type, measure=head["measure"], offset=head["offset"],
                   cell=head["cell"], width=head["width"],
                   starting_height=f["starting_height"], duration=f["duration"],
                   end_cell=f["end_cell"], end_width=f["end_width"],
                   target_height=f["target_height"], heaven_id=f["heaven_id"],
                   animation=f.get("animation"))

    @classmethod
    def build(cls, note_type: NoteType, *, measure=0, offset=0, cell=0, width=0,
              parent=None, duration=384,
              end_cell=None, end_width=None, **ignored) -> Note:
        ec, ew = _clamp(cell if end_cell is None else end_cell,
                        width if end_width is None else end_width)
        return cls(note_type=note_type, measure=measure, offset=offset,
                   cell=cell, width=width, parent=parent,
                   starting_height=1.0, duration=duration,
                   end_cell=ec, end_width=ew, target_height=1.0,
                   heaven_id=0,
                   animation="UP" if note_type == 'HHX' else None)

    def get_extra_parts(self) -> list[str]:
        parts = [f"{self.starting_height:.1f}", str(self.duration),
                 str(self.end_cell), str(self.end_width),
                 f"{self.target_height:.1f}", str(self.heaven_id)]
        if self.animation is not None:
            parts.append(self.animation)
        return parts
