"""Domain constants and enums for the CHUNITHM chart parser."""

import enum


class NoteType(str, enum.Enum):
    """Explicitly recognized note type tokens."""

    TAP = "TAP"
    """Standard tap note."""

    CHR = "CHR"
    """ExTap / TapEx note."""

    FLK = "FLK"
    """Flick note."""

    MNE = "MNE"
    """Damage mine note."""

    HLD = "HLD"
    """Standard hold note."""

    HXD = "HXD"
    """Hold note with ExTap head."""

    SLD = "SLD"
    """Standard slide note."""

    SLC = "SLC"
    """Slide control point."""

    SXD = "SXD"
    """Slide note with ExTap head."""

    SXC = "SXC"
    """Slide control point with ExTap head."""

    AIR = "AIR"
    """Air."""

    AUR = "AUR"
    """Air Up-Right."""

    AUL = "AUL"
    """Air Up-Left."""

    AHD = "AHD"
    """Air hold — sustained position in the air."""

    ADW = "ADW"
    """Air Downwards."""

    ADR = "ADR"
    """Air Down-Right."""

    ADL = "ADL"
    """Air Down-Left."""

    ALD = "ALD"
    """Air slide pattern/effect carrier. Color NON creates AIR-ACTION bars."""

    ASD = "ASD"
    """Air slide head — start of a sliding path in the air."""

    ASC = "ASC"
    """Air slide control point — intermediate point along an air slide path."""

    AHX = "AHX"
    """Air hold action / alternate air-hold endpoint."""


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
    BS = "BS"  # Slide animation for SXC/SXD


class AirColor(enum.Enum):
    """Color types for AIR and DOWN modifier notes."""

    DEF = "DEF"
    PNK = "PNK"
    GRN = "GRN"


class AirTraceColor(enum.Enum):
    """Color/effect types for ALD air slide pattern notes."""

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


# ── Note-type groupings matching the supported CHUNITHM C2S categories ─────

# Ground-level notes that occupy the 16-lane playfield
GROUND_NOTE_TYPES: frozenset[NoteType] = frozenset(
    {
        NoteType.TAP,
        NoteType.CHR,
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

# ExTap / TapEx notes.
EXTAP_NOTE_TYPES: frozenset[NoteType] = frozenset({NoteType.CHR})

# ── Air system groupings ───────────────────────────────────────────────────

AIR_ARROW_NOTES: frozenset[NoteType] = frozenset(
    [
        NoteType.AIR,
        NoteType.AUR,
        NoteType.AUL,
        NoteType.ADW,
        NoteType.ADR,
        NoteType.ADL,
    ]
)
"""Air arrow modifiers that create a hit above the ground note."""

AIR_HOLD_NOTES: frozenset[NoteType] = frozenset([NoteType.AHD, NoteType.AHX])
"""Air hold chain — a sustained position in the air + optional action bar."""

AIR_SLIDE_NOTES: frozenset[NoteType] = frozenset([NoteType.ASD, NoteType.ASC])
"""Air slide chain — a sliding path in the air."""

AIR_ACTION_NOTES: frozenset[NoteType] = frozenset([NoteType.AHX])
"""Air action notes represented directly by supported C2S."""

AIR_SLIDE_PATTERN_NOTES: frozenset[NoteType] = frozenset({NoteType.ALD})
"""Air slide pattern/effect carrier notes represented by ALD."""

# All air-related notes combined (useful for broad "is this air?" checks)
AIR_NOTE_TYPES: frozenset[NoteType] = frozenset(
    set(AIR_ARROW_NOTES)
    | set(AIR_HOLD_NOTES)
    | set(AIR_SLIDE_NOTES)
    | set(AIR_SLIDE_PATTERN_NOTES)
)

# ── Other constants ────────────────────────────────────────────────────────

AIR_SLIDE_PATTERN_COLORS: frozenset[str] = frozenset(
    {
        "DEF",
        "NON",
        "PNK",
        "GRY",
        "RED",
        "ORN",
        "YEL",
        "AQA",
        "PPL",
        "CYN",
        "BLK",
        "VLT",
        "LIM",
        "BLU",
        "GRN",
    }
)
