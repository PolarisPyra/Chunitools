from __future__ import annotations

from src.core.const import NoteType

NOTE_TYPE_DISPLAY_NAMES: dict[NoteType, str] = {
    NoteType.TAP: "Tap",
    NoteType.CHR: "Extap",
    NoteType.FLK: "Flick",
    NoteType.MNE: "Damage",
    NoteType.HLD: "Hold",
    NoteType.HXD: "Hold",
    NoteType.SLD: "Slide Begin",
    NoteType.SLC: "Slide Control",
    NoteType.SXD: "Slide Begin",
    NoteType.SXC: "Slide Control",
    NoteType.AIR: "Air Up",
    NoteType.AUR: "Air Up Right",
    NoteType.AUL: "Air Up Left",
    NoteType.ADW: "Air down",
    NoteType.ADR: "Air down right",
    NoteType.ADL: "Air down left",
    NoteType.AHD: "Air Hold",
    NoteType.AHX: "Air Hold",
    NoteType.ASD: "Air Slide",
    NoteType.ASC: "Air Slide",
    NoteType.ALD: "Air Slide Pattern",
}

NOTE_TYPE_SHORT_NAMES: dict[NoteType, str] = {
    NoteType.TAP: "TAP",
    NoteType.CHR: "EXTAP",
    NoteType.FLK: "FLICK",
    NoteType.MNE: "DAMAGE",
    NoteType.HLD: "HOLD",
    NoteType.HXD: "HOLD",
    NoteType.SLD: "SLIDE BEGIN",
    NoteType.SLC: "SLIDE CONTROL",
    NoteType.SXD: "SLIDE BEGIN",
    NoteType.SXC: "SLIDE CONTROL",
    NoteType.AIR: "AIR UP",
    NoteType.AUR: "AIR UP RIGHT",
    NoteType.AUL: "AIR UP LEFT",
    NoteType.ADW: "AIR DOWN",
    NoteType.ADR: "AIR DOWN RIGHT",
    NoteType.ADL: "AIR DOWN LEFT",
    NoteType.AHD: "AIR HOLD",
    NoteType.AHX: "AIR HOLD",
    NoteType.ASD: "AIR SLIDE",
    NoteType.ASC: "AIR SLIDE",
    NoteType.ALD: "AIR SLIDE PATTERN",
}


def note_type_display_name(note_type: NoteType) -> str:
    return NOTE_TYPE_DISPLAY_NAMES.get(note_type, note_type.value)


def note_type_short_name(note_type: NoteType) -> str:
    return NOTE_TYPE_SHORT_NAMES.get(note_type, note_type.value)
