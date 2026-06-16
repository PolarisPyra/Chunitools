"""Air-system notes: arrows, holds, traces, and slides."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.const import NoteType  # noqa: TC001
from src.notes.base import Note, NoteHead, clamp_note_geometry as _clamp
from src.notes.schema import parse_schema_fields


@dataclass(frozen=True, kw_only=True, slots=True)
class Air(Note):
    """Air arrow notes (AIR, AUR, AUL, ADW, ADR, ADL)."""

    # Game format (all air arrows share this pattern):
    #   "%s\t%d\t%d\t%d\t%d\t%s\t%s\n"
    #   TYPE MS  OFF CEL WID TRG CLR
    #
    # TRG = target note type (e.g. "TAP", "DEF")
    # CLR = color ("DEF", "PNK", "GRN") — always present in game output

    target_note: str
    color: str = "DEF"
    color_is_explicit: bool = field(default=False, repr=False)

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(
            note_type=note_type,
            measure=head["measure"],
            offset=head["offset"],
            cell=head["cell"],
            width=head["width"],
            target_note=f["target_note"],
            color=f.get("color", "DEF"),
            color_is_explicit="color" in f,
        )

    @classmethod
    def build(
        cls,
        note_type: NoteType,
        *,
        measure=0,
        offset=0,
        cell=0,
        width=0,
        parent=None,
        target_note=None,
        **ignored,
    ) -> Note:
        return cls(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            parent=parent,
            target_note=target_note or "DEF",
        )

    def get_extra_parts(self) -> list[str]:
        if self.color == "DEF" and not self.color_is_explicit:
            return [self.target_note]
        return [self.target_note, self.color]


@dataclass(frozen=True, kw_only=True, slots=True)
class AirHoldStart(Note):
    """Air Hold Start (AHD)."""

    # Game format: "AHD\t%d\t%d\t%d\t%d\t%s\t%d\t%s\n"
    #              MS   OFF  CEL  WID  TRG  DUR  CLR

    target_note: str
    duration: int
    color: str = "DEF"
    color_is_explicit: bool = field(default=False, repr=False)

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(
            note_type=note_type,
            measure=head["measure"],
            offset=head["offset"],
            cell=head["cell"],
            width=head["width"],
            target_note=f["target_note"],
            duration=f["duration"],
            color=f.get("color", "DEF"),
            color_is_explicit="color" in f,
        )

    @classmethod
    def build(
        cls,
        note_type: NoteType,
        *,
        measure=0,
        offset=0,
        cell=0,
        width=0,
        parent=None,
        duration=384,
        target_note=None,
        **ignored,
    ) -> Note:
        return cls(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            parent=parent,
            target_note=target_note or "DEF",
            duration=duration,
        )

    def get_extra_parts(self) -> list[str]:
        parts = [self.target_note, str(self.duration)]
        if self.color != "DEF" or self.color_is_explicit:
            parts.append(self.color)
        return parts


@dataclass(frozen=True, kw_only=True, slots=True)
class AirHold(Note):
    """Air hold action (AHX) — purple action bar along an air hold."""

    # Game format: "AHX\t%d\t%d\t%d\t%d\t%s\t%d\t%s\n"
    #              MS   OFF  CEL  WID  TRG  DUR  CLR

    target_note: str
    duration: int
    color: str

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(
            note_type=note_type,
            measure=head["measure"],
            offset=head["offset"],
            cell=head["cell"],
            width=head["width"],
            target_note=f["target_note"],
            duration=f["duration"],
            color=f["color"],
        )

    @classmethod
    def build(
        cls,
        note_type: NoteType,
        *,
        measure=0,
        offset=0,
        cell=0,
        width=0,
        parent=None,
        duration=384,
        target_note=None,
        **ignored,
    ) -> Note:
        return cls(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            parent=parent,
            target_note=target_note or "DEF",
            duration=duration,
            color="DEF",
        )

    def get_extra_parts(self) -> list[str]:
        return [self.target_note, str(self.duration), self.color]


@dataclass(frozen=True, kw_only=True, slots=True)
class AirSlidePattern(Note):
    """Air slide pattern/effect carrier (ALD).

    ALD color controls the concrete visual role:
    DEF = regular air slide pattern, NON = AIR-ACTION, GRY = wind/effect,
    YEL = fake ExTap AIR-ACTION, BLK = hidden/invisible effect.
    """

    # Game format: "ALD\t%d\t%d\t%d\t%d\t%d\t%3.1f\t%d\t%d\t%d\t%3.1f\t%s\n"
    #              MS   OFF  CEL  WID  TICK HGT   DUR  ECL  EWD  EHGT  CLR
    #
    # HGT/EHGT are scaled by a constant (DAT_01868720) in the game,
    # likely 0.1 for internal → display conversion.

    crush_interval: int
    starting_height: float
    duration: int
    end_cell: int
    end_width: int
    target_height: float
    color: str

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(
            note_type=note_type,
            measure=head["measure"],
            offset=head["offset"],
            cell=head["cell"],
            width=head["width"],
            crush_interval=f["crush_interval"],
            starting_height=f["starting_height"],
            duration=f["duration"],
            end_cell=f["end_cell"],
            end_width=f["end_width"],
            target_height=f["target_height"],
            color=f["color"],
        )

    @classmethod
    def build(
        cls,
        note_type: NoteType,
        *,
        measure=0,
        offset=0,
        cell=0,
        width=0,
        parent=None,
        duration=384,
        end_cell=None,
        end_width=None,
        **ignored,
    ) -> Note:
        ec, ew = _clamp(
            cell if end_cell is None else end_cell, width if end_width is None else end_width
        )
        return cls(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            parent=parent,
            crush_interval=0,
            starting_height=1.0,
            duration=duration,
            end_cell=ec,
            end_width=ew,
            target_height=1.0,
            color="NON",
        )

    def get_extra_parts(self) -> list[str]:
        return [
            str(self.crush_interval),
            f"{self.starting_height:.1f}",
            str(self.duration),
            str(self.end_cell),
            str(self.end_width),
            f"{self.target_height:.1f}",
            self.color,
        ]


@dataclass(frozen=True, kw_only=True, slots=True)
class AirSlide(Note):
    """ASD/ASC air slide segment."""

    # Game format: "ASD\t%d\t%d\t%d\t%d\t%s\t%3.1f\t%d\t%d\t%d\t%3.1f\t%s\n"
    #              MS   OFF  CEL  WID  TRG HGT   DUR  ECL  EWD  EHGT  CLR
    #
    # ASC is identical: "ASC\t%d\t%d\t%d\t%d\t%s\t%3.1f\t%d\t%d\t%d\t%3.1f\t%s\n"

    target_note: str
    starting_height: float
    duration: int
    end_cell: int
    end_width: int
    target_height: float
    color: str

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        f = parse_schema_fields(note_type, head["data"])
        return cls(
            note_type=note_type,
            measure=head["measure"],
            offset=head["offset"],
            cell=head["cell"],
            width=head["width"],
            target_note=f["target_note"],
            starting_height=f["starting_height"],
            duration=f["duration"],
            end_cell=f["end_cell"],
            end_width=f["end_width"],
            target_height=f["target_height"],
            color=f["color"],
        )

    @classmethod
    def build(
        cls,
        note_type: NoteType,
        *,
        measure=0,
        offset=0,
        cell=0,
        width=0,
        parent=None,
        duration=384,
        target_note=None,
        end_cell=None,
        end_width=None,
        **ignored,
    ) -> Note:
        ec, ew = _clamp(
            cell if end_cell is None else end_cell, width if end_width is None else end_width
        )
        return cls(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            target_note=target_note or "DEF",
            starting_height=1.0,
            duration=duration,
            end_cell=ec,
            end_width=ew,
            target_height=1.0,
            color="DEF",
        )

    def get_extra_parts(self) -> list[str]:
        return [
            self.target_note,
            f"{self.starting_height:.1f}",
            str(self.duration),
            str(self.end_cell),
            str(self.end_width),
            f"{self.target_height:.1f}",
            self.color,
        ]


@dataclass(frozen=True, kw_only=True, slots=True)
class AirSlideStart(Note):
    """Joined ASD/ASC air slide wrapper."""

    steps: tuple[AirSlide, ...]

    @property
    def duration(self) -> int:
        return sum(s.duration for s in self.steps)

    @property
    def end_cell(self) -> int:
        return self.steps[-1].end_cell if self.steps else self.cell

    @property
    def end_width(self) -> int:
        return self.steps[-1].end_width if self.steps else self.width

    @property
    def target_note(self) -> str:
        return self.steps[0].target_note if self.steps else ""

    @property
    def color(self) -> str:
        return self.steps[0].color if self.steps else "DEF"

    @classmethod
    def parse(cls, note_type: NoteType, head: NoteHead) -> Note:
        raise NotImplementedError("AirSlideStart is a composite wrapper")

    @classmethod
    def build(
        cls,
        note_type: NoteType,
        *,
        measure=0,
        offset=0,
        cell=0,
        width=0,
        parent=None,
        duration=384,
        target_note=None,
        end_cell=None,
        end_width=None,
        **ignored,
    ) -> Note:
        ec, ew = _clamp(
            cell if end_cell is None else end_cell, width if end_width is None else end_width
        )
        step = AirSlide(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            target_note=target_note or "DEF",
            starting_height=1.0,
            duration=duration,
            end_cell=ec,
            end_width=ew,
            target_height=1.0,
            color="DEF",
        )
        return cls(
            note_type=note_type,
            measure=measure,
            offset=offset,
            cell=cell,
            width=width,
            parent=parent,
            steps=(step,),
        )

    def get_extra_parts(self) -> list[str]:
        return []
