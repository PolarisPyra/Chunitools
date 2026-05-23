"""Note models for the CHUNITHM chart domain."""

from src.notes.air import (
    Air,
    AirHold,
    AirHoldStart,
    AirSlide,
    AirSlideStart,
    CrashSlide,
)
from src.notes.base import Note
from src.notes.effects import AirSolid, HeavenHold

# Factory-level groupings (game-accurate categories)
from src.notes.factory import (
    AIR_ARROW_NOTE_TYPES,
    AIR_HOLD_NOTE_TYPES,
    AIR_SLIDE_NOTE_TYPES,
    AIR_SOLID_NOTE_TYPES,
    AIR_TRACE_NOTE_TYPES,
    CRUSH_NOTE_TYPES,
    FLICK_NOTE_TYPES,
    GROUND_NOTE_TYPES,
    HEAVEN_NOTE_TYPES,
    HOLD_NOTE_TYPES,
    SLIDE_NOTE_TYPES,
    build_editor_note,
    clamp_note_geometry,
    parse_note,
)
from src.notes.flick import Flick
from src.notes.hold import Hold
from src.notes.slide import Slide, SlideTo
from src.notes.tap import ExTap, Mine, Tap

__all__ = [
    "Note",
    "Tap",
    "ExTap",
    "Mine",
    "Hold",
    "Slide",
    "SlideTo",
    "Flick",
    "AirSolid",
    "HeavenHold",
    "Air",
    "AirHoldStart",
    "AirHold",
    "CrashSlide",
    "AirSlideStart",
    "AirSlide",
    # Factory
    "parse_note",
    "build_editor_note",
    "clamp_note_geometry",
    # Game-accurate groupings
    "GROUND_NOTE_TYPES",
    "CRUSH_NOTE_TYPES",
    "FLICK_NOTE_TYPES",
    "HOLD_NOTE_TYPES",
    "SLIDE_NOTE_TYPES",
    "AIR_ARROW_NOTE_TYPES",
    "AIR_HOLD_NOTE_TYPES",
    "AIR_SLIDE_NOTE_TYPES",
    "AIR_TRACE_NOTE_TYPES",
    "AIR_SOLID_NOTE_TYPES",
    "HEAVEN_NOTE_TYPES",
]
