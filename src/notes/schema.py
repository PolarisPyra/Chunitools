"""Canonical serialized field schemas for playable C2S note types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.core.const import NoteType


class FieldKind(str, Enum):
    """C2S registration field kinds recovered from the game registry."""

    STRING = "string"
    FLOAT = "float"
    INTEGER = "integer"
    NOTE_TYPE = "note_type"
    FLICK_DIRECTION = "flick_direction"


REGISTER_TYPE_KIND: dict[int, FieldKind] = {
    0: FieldKind.STRING,
    1: FieldKind.FLOAT,
    2: FieldKind.INTEGER,
    3: FieldKind.NOTE_TYPE,
    4: FieldKind.FLICK_DIRECTION,
}


@dataclass(frozen=True, slots=True)
class FieldSchema:
    name: str
    kind: FieldKind
    required: bool = True
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NoteSchema:
    note_type: NoteType
    fields: tuple[FieldSchema, ...] = ()
    evidence: tuple[str, ...] = field(default_factory=tuple)
    parser_only: bool = False

    @property
    def required_count(self) -> int:
        return sum(1 for field_schema in self.fields if field_schema.required)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(field_schema.name for field_schema in self.fields)


INT = FieldKind.INTEGER
FLOAT = FieldKind.FLOAT
STRING = FieldKind.STRING
NOTE = FieldKind.NOTE_TYPE
DIRECTION = FieldKind.FLICK_DIRECTION


NOTE_SCHEMAS: dict[NoteType, NoteSchema] = {
    NoteType.TAP: NoteSchema(NoteType.TAP, evidence=("RegisterNoteType",)),
    NoteType.CHR: NoteSchema(
        NoteType.CHR,
        (FieldSchema("animation", STRING, aliases=("unknown",)),),
        ("RegisterNoteType", "real charts"),
    ),
    NoteType.FLK: NoteSchema(
        NoteType.FLK,
        (FieldSchema("direction", DIRECTION, aliases=("unknown",)),),
        ("RegisterNoteType type code 4", "export format FLK ... %s"),
    ),
    NoteType.MNE: NoteSchema(NoteType.MNE, evidence=("RegisterNoteType",)),
    NoteType.HLD: NoteSchema(
        NoteType.HLD,
        (FieldSchema("duration", INT), FieldSchema("animation", STRING, required=False)),
        ("RegisterNoteType", "parser compatibility"),
    ),
    NoteType.HXD: NoteSchema(
        NoteType.HXD,
        (FieldSchema("duration", INT), FieldSchema("animation", STRING, required=False)),
        ("RegisterNoteType", "parser compatibility"),
    ),
    NoteType.SLD: NoteSchema(
        NoteType.SLD,
        (
            FieldSchema("duration", INT),
            FieldSchema("end_cell", INT),
            FieldSchema("end_width", INT),
            FieldSchema("target_id", STRING, required=False),
            FieldSchema("animation", STRING, required=False),
        ),
        ("RegisterNoteType",),
    ),
    NoteType.SLC: NoteSchema(
        NoteType.SLC,
        (
            FieldSchema("duration", INT),
            FieldSchema("end_cell", INT),
            FieldSchema("end_width", INT),
            FieldSchema("target_id", STRING, required=False),
            FieldSchema("animation", STRING, required=False),
        ),
        ("RegisterNoteType",),
    ),
    NoteType.SXD: NoteSchema(
        NoteType.SXD,
        (
            FieldSchema("duration", INT),
            FieldSchema("end_cell", INT),
            FieldSchema("end_width", INT),
            FieldSchema("target_id", STRING, required=False),
            FieldSchema("animation", STRING, required=False),
        ),
        ("RegisterNoteType",),
    ),
    NoteType.SXC: NoteSchema(
        NoteType.SXC,
        (
            FieldSchema("duration", INT),
            FieldSchema("end_cell", INT),
            FieldSchema("end_width", INT),
            FieldSchema("target_id", STRING, required=False),
            FieldSchema("animation", STRING, required=False),
        ),
        ("RegisterNoteType",),
    ),
    NoteType.AIR: NoteSchema(
        NoteType.AIR,
        (FieldSchema("target_note", NOTE), FieldSchema("color", STRING, required=False)),
        ("RegisterNoteType",),
    ),
    NoteType.AUR: NoteSchema(
        NoteType.AUR,
        (FieldSchema("target_note", NOTE), FieldSchema("color", STRING, required=False)),
        ("RegisterNoteType",),
    ),
    NoteType.AUL: NoteSchema(
        NoteType.AUL,
        (FieldSchema("target_note", NOTE), FieldSchema("color", STRING, required=False)),
        ("RegisterNoteType",),
    ),
    NoteType.ADW: NoteSchema(
        NoteType.ADW,
        (FieldSchema("target_note", NOTE), FieldSchema("color", STRING, required=False)),
        ("RegisterNoteType",),
    ),
    NoteType.ADR: NoteSchema(
        NoteType.ADR,
        (FieldSchema("target_note", NOTE), FieldSchema("color", STRING, required=False)),
        ("RegisterNoteType",),
    ),
    NoteType.ADL: NoteSchema(
        NoteType.ADL,
        (FieldSchema("target_note", NOTE), FieldSchema("color", STRING, required=False)),
        ("RegisterNoteType",),
    ),
    NoteType.AHD: NoteSchema(
        NoteType.AHD,
        (
            FieldSchema("target_note", NOTE),
            FieldSchema("duration", INT),
            FieldSchema("color", STRING, required=False),
        ),
        ("RegisterNoteType", "export format AHD ... %s %d %s"),
    ),
    NoteType.AHX: NoteSchema(
        NoteType.AHX,
        (
            FieldSchema("target_note", NOTE),
            FieldSchema("duration", INT),
            FieldSchema("color", STRING, required=False),
        ),
        ("RegisterNoteType",),
    ),
    NoteType.ALD: NoteSchema(
        NoteType.ALD,
        (
            FieldSchema("crush_interval", INT),
            FieldSchema("starting_height", FLOAT, aliases=("start_height",)),
            FieldSchema("duration", INT),
            FieldSchema("end_cell", INT),
            FieldSchema("end_width", INT),
            FieldSchema("target_height", FLOAT),
            FieldSchema("color", STRING),
        ),
        ("RegisterNoteType", "export format ALD ... %d %3.1f %d %d %d %3.1f %s"),
    ),
    NoteType.ASD: NoteSchema(
        NoteType.ASD,
        (
            FieldSchema("target_note", NOTE, aliases=("wrapped_type",)),
            FieldSchema("starting_height", FLOAT, aliases=("start_height",)),
            FieldSchema("duration", INT),
            FieldSchema("end_cell", INT),
            FieldSchema("end_width", INT),
            FieldSchema("target_height", FLOAT),
            FieldSchema("color", STRING),
        ),
        ("RegisterNoteType", "export format ASD ... %s %3.1f %d %d %d %3.1f %s"),
    ),
    NoteType.ASC: NoteSchema(
        NoteType.ASC,
        (
            FieldSchema("target_note", NOTE, aliases=("wrapped_type",)),
            FieldSchema("starting_height", FLOAT, aliases=("start_height",)),
            FieldSchema("duration", INT),
            FieldSchema("end_cell", INT),
            FieldSchema("end_width", INT),
            FieldSchema("target_height", FLOAT),
            FieldSchema("color", STRING),
        ),
        ("RegisterNoteType", "export format ASC ... %s %3.1f %d %d %d %3.1f %s"),
    ),
}

PLAYABLE_NOTE_TYPES: frozenset[NoteType] = frozenset(NOTE_SCHEMAS)


def parse_schema_fields(note_type: NoteType, data: tuple[str, ...]) -> dict[str, Any]:
    """Parse serialized extra fields for *note_type* according to ``NOTE_SCHEMAS``."""
    schema = NOTE_SCHEMAS[note_type]
    if len(data) < schema.required_count:
        raise IndexError(note_type.value)

    parsed: dict[str, Any] = {}
    for index, field_schema in enumerate(schema.fields):
        if index >= len(data):
            continue
        value = data[index]
        if field_schema.kind == FieldKind.INTEGER:
            parsed[field_schema.name] = int(float(value))
        elif field_schema.kind == FieldKind.FLOAT:
            parsed[field_schema.name] = float(value)
        else:
            parsed[field_schema.name] = value
    return parsed
