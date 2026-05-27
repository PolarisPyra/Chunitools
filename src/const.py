"""Domain constants, enums, and note-type groupings."""

from __future__ import annotations

import enum

# ── Primary enums ────────────────────────────────────────────────────────────


class NoteType(str, enum.Enum):
    """Explicitly recognized note type tokens."""

    TAP = "TAP"
    CHR = "CHR"  # ExTap
    FLK = "FLK"  # Flick
    MNE = "MNE"  # Mine
    HLD = "HLD"  # Hold
    HXD = "HXD"  # ExTap-head hold
    SLD = "SLD"  # Slide
    SLC = "SLC"  # Slide control point
    SXD = "SXD"  # ExTap-head slide
    SXC = "SXC"  # ExTap-head slide control point
    AIR = "AIR"
    AUR = "AUR"  # Air Up-Right
    AUL = "AUL"  # Air Up-Left
    AHD = "AHD"  # Air hold
    ADW = "ADW"  # Air Down
    ADR = "ADR"  # Air Down-Right
    ADL = "ADL"  # Air Down-Left
    ALD = "ALD"  # Air trace/crush
    ASD = "ASD"  # Air slide head
    ASC = "ASC"  # Air slide control point
    AHX = "AHX"  # Air hold action
    ASX = "ASX"  # Air slide action
    ASO = "ASO"  # Air solid
    HHD = "HHD"  # Heaven Hold
    HHX = "HHX"  # Heaven ExHold


class Command(enum.Enum):
    """Header metadata and structural commands."""

    MET = "MET"
    MUSICID = "MUSICID"
    TITLE = "TITLE"
    ARTIST = "ARTIST"
    VERSION = "VERSION"
    VERS = "VERS"
    MUSIC = "MUSIC"
    SEQUENCEID = "SEQUENCEID"
    DIFFICULT = "DIFFICULT"
    LEVEL = "LEVEL"
    CREATOR = "CREATOR"
    RESOLUTION = "RESOLUTION"
    CLK_DEF = "CLK_DEF"
    BPM_DEF = "BPM_DEF"
    MET_DEF = "MET_DEF"
    BPM = "BPM"
    WENAME = "WENAME"
    WELEVEL = "WELEVEL"
    TUTORIAL = "TUTORIAL"
    PROGJUDGE_BPM = "PROGJUDGE_BPM"
    PROGJUDGE_AER = "PROGJUDGE_AER"


class AnimationType(enum.Enum):
    """Animation types for notes (e.g., ExTap, Slide)."""

    UP = "UP"
    DW = "DW"
    CE = "CE"
    LS = "LS"
    RS = "RS"
    LC = "LC"
    RC = "RC"
    BS = "BS"


class AirColor(enum.Enum):
    """Color types for AIR and DOWN modifier notes."""

    DEF = "DEF"
    PNK = "PNK"
    GRN = "GRN"


class AirTraceColor(enum.Enum):
    """Color types for ALD (Air Trace) notes."""

    GRY = "GRY"
    RED = "RED"
    ORN = "ORN"
    YEL = "YEL"
    AQA = "AQA"
    PPL = "PPL"
    PNK = "PNK"
    CYN = "CYN"
    BLK = "BLK"
    VLT = "VLT"
    LIM = "LIM"
    BLU = "BLU"
    GRN = "GRN"
    NON = "NON"
    DEF = "DEF"


class RenderRole(enum.Enum):
    """Structural roles for notes during rendering."""

    HEAD = "head"
    CONTROL = "control"
    TAP = "tap"


# ── Note-type groupings ──────────────────────────────────────────────────────

GROUND_NOTE_TYPES: frozenset[NoteType] = frozenset(
    {
        NoteType.TAP,
        NoteType.HLD,
        NoteType.HXD,
        NoteType.SLD,
        NoteType.SXD,
        NoteType.SLC,
        NoteType.SXC,
        NoteType.FLK,
        NoteType.MNE,
    }
)

CRUSH_NOTE_TYPES: frozenset[NoteType] = frozenset({NoteType.CHR})

AIR_ARROW_NOTES: frozenset[NoteType] = frozenset(
    [NoteType.AIR, NoteType.AUR, NoteType.AUL, NoteType.ADW, NoteType.ADR, NoteType.ADL]
)

AIR_HOLD_NOTES: frozenset[NoteType] = frozenset([NoteType.AHD, NoteType.AHX])

AIR_SLIDE_NOTES: frozenset[NoteType] = frozenset([NoteType.ASD, NoteType.ASC, NoteType.ASX])

AIR_ACTION_NOTES: frozenset[NoteType] = frozenset([NoteType.AHX, NoteType.ASX])

AIR_TRACE_NOTES: frozenset[NoteType] = frozenset({NoteType.ALD})

AIR_SOLID_NOTES: frozenset[NoteType] = frozenset({NoteType.ASO})

AIR_NOTE_TYPES: frozenset[NoteType] = frozenset(
    set(AIR_ARROW_NOTES)
    | set(AIR_HOLD_NOTES)
    | set(AIR_SLIDE_NOTES)
    | set(AIR_TRACE_NOTES)
    | set(AIR_SOLID_NOTES)
)

AIR_TRACE_COLORS: frozenset[str] = frozenset(
    {
        "DEF", "NON", "PNK", "GRY", "RED", "ORN", "YEL",
        "AQA", "PPL", "CYN", "BLK", "VLT", "LIM", "BLU", "GRN",
    }
)
