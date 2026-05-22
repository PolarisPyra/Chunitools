from PySide6.QtGui import QColor
from src.core.const import NoteType

NOTE_TAP = "#ff4040"
NOTE_CHR = "#ffcc00"
NOTE_HOLD = "#ff9000"
NOTE_SLIDE = "#0090ff"
NOTE_AIR = "#33ff55"
NOTE_DOWN_AIR = "#ff33cc"
NOTE_AIR_TRACE = "#33ff55"
NOTE_AIR_SLIDE = "#34c759"
NOTE_FLICK = "#d0d0d0"
NOTE_MINE = "#af52de"
NOTE_HOLD_EX_HEAD = "#ff9f1a"
NOTE_SLIDE_HEAD = "#00ccff"
NOTE_AIR_ACTION = "#d13bff"
NOTE_CYAN = "#00d5ff"
NOTE_AIR_SOLID = "#45c4ff"
NOTE_HEAVEN_HOLD = "#fff4a3"

NOTE_COLORS = {
    NoteType.TAP: (NOTE_TAP, NOTE_TAP),
    NoteType.CHR: (NOTE_CHR, NOTE_CHR),
    NoteType.HLD: (NOTE_HOLD, NOTE_HOLD_EX_HEAD),
    NoteType.HXD: (NOTE_HOLD, NOTE_CHR),
    NoteType.SLD: (NOTE_SLIDE, NOTE_SLIDE_HEAD),
    NoteType.SLC: (NOTE_SLIDE, NOTE_SLIDE_HEAD),
    NoteType.SXD: (NOTE_SLIDE, NOTE_CHR),
    NoteType.SXC: (NOTE_SLIDE, NOTE_CHR),
    NoteType.AIR: (NOTE_AIR, NOTE_AIR),
    NoteType.AUR: (NOTE_AIR, NOTE_AIR),
    NoteType.AUL: (NOTE_AIR, NOTE_AIR),
    NoteType.AHD: (NOTE_AIR, NOTE_AIR),
    NoteType.ADW: (NOTE_DOWN_AIR, NOTE_DOWN_AIR),
    NoteType.ADR: (NOTE_DOWN_AIR, NOTE_DOWN_AIR),
    NoteType.ADL: (NOTE_DOWN_AIR, NOTE_DOWN_AIR),
    NoteType.ALD: (NOTE_AIR_TRACE, NOTE_AIR_TRACE),
    NoteType.ASD: (NOTE_AIR_SLIDE, NOTE_AIR_SLIDE),
    NoteType.ASC: (NOTE_AIR_SLIDE, NOTE_AIR_SLIDE),
    NoteType.ASX: (NOTE_AIR_ACTION, NOTE_AIR_ACTION),
    NoteType.AHX: (NOTE_AIR_ACTION, NOTE_AIR_ACTION),
    NoteType.ASO: (NOTE_AIR_SOLID, NOTE_AIR_SOLID),
    NoteType.HHD: (NOTE_HEAVEN_HOLD, NOTE_HEAVEN_HOLD),
    NoteType.HHX: (NOTE_HEAVEN_HOLD, NOTE_CHR),
    NoteType.FLK: (NOTE_FLICK, NOTE_FLICK),
    NoteType.MNE: (NOTE_MINE, NOTE_MINE),
}

TRACE_COLORS = {
    "DEF": NOTE_AIR_SLIDE, "NON": NOTE_AIR_ACTION, "PNK": NOTE_DOWN_AIR, "GRY": "#808080",
    "YEL": NOTE_CHR, "BLK": "#000000", "CYN": NOTE_CYAN, "AQA": "#00ffff",
    "LIM": "#99ff33", "VLT": "#8a5cff", "ORN": NOTE_HOLD, "RED": NOTE_TAP,
    "BLU": NOTE_SLIDE, "GRN": NOTE_AIR,
}

def get_note_color(t: NoteType, mod: str | None = None) -> QColor:
    if t in (NoteType.ALD, NoteType.ASD, NoteType.ASC, NoteType.ASX, NoteType.ASO) and mod in TRACE_COLORS and mod != "DEF":
        return QColor(TRACE_COLORS[mod])
    return QColor(NOTE_COLORS.get(t, ("#ffffff", "#ffffff"))[0])

def get_head_color(t: NoteType) -> QColor:
    return QColor(NOTE_COLORS.get(t, ("#ffffff", "#ffffff"))[1])

def get_action_bar_color() -> QColor:
    return QColor(NOTE_AIR_ACTION)
