"""Domain constants and enums for the CHUNITHM chart parser."""

import enum


class NoteType(str, enum.Enum):
    """Explicitly recognized note type tokens."""

    TAP = "TAP"
    """Standard tap note."""

    CHR = "CHR"
    """ExTap note (yellow/gold tap)."""

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
    """Air Hold."""

    ADW = "ADW"
    """Air Downwards."""

    ADR = "ADR"
    """Air Down-Right."""

    ADL = "ADL"
    """Air Down-Left."""

    ALD = "ALD"
    """Air trace/effect; NON creates AIR-ACTION/AIR CRUSH objects."""

    ASD = "ASD"
    """Air slide wrapper."""

    ASC = "ASC"
    """Air slide control/wrapper."""

    AHX = "AHX"
    """Purple air-action note attached to an air hold."""

    ASX = "ASX"
    """Air slide action/end (no terminal, like AHX for air slides)."""

    ASO = "ASO"
    """Air Solid."""

    HHD = "HHD"
    """Heaven Hold."""

    HHX = "HHX"
    """Heaven ExHold."""


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


GROUND_NOTE_TYPES: frozenset[NoteType] = frozenset(
    {
        NoteType.TAP, NoteType.CHR, NoteType.HLD, NoteType.HXD,
        NoteType.SLD, NoteType.SXD, NoteType.SLC, NoteType.SXC,
        NoteType.FLK, NoteType.MNE,
    }
)

AIR_TRACE_COLORS: frozenset[str] = frozenset(
    {
        "DEF", "NON", "PNK", "GRY", "RED", "ORN", "YEL", "AQA",
        "PPL", "CYN", "BLK", "VLT", "LIM", "BLU", "GRN",
    }
)

# Groupings for easier logic dispatch
AIR_NOTE_TYPES: frozenset[NoteType] = frozenset(
    [
        NoteType.AIR,
        NoteType.AUR,
        NoteType.AUL,
        NoteType.AHD,
        NoteType.ADW,
        NoteType.ADR,
        NoteType.ADL,
        NoteType.ALD,
        NoteType.ASD,
        NoteType.ASC,
        NoteType.ASX,
        NoteType.AHX,
    ]
)

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

AIR_SUSTAIN_NOTES: frozenset[NoteType] = frozenset(
    [
        NoteType.AHD,
        NoteType.AHX,
        NoteType.ALD,
        NoteType.ASD,
        NoteType.ASC,
        NoteType.ASX,
    ]
)
