from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class GradientColor:
    dark: QColor
    light: QColor

def argb(a: int, r: int, g: int, b: int) -> QColor:
    return QColor(r, g, b, a)

def rgb(r: int, g: int, b: int) -> QColor:
    return QColor(r, g, b, 255)

@dataclass(frozen=True)
class ColorProfile:
    border: GradientColor
    tap: GradientColor
    ex_tap: GradientColor
    flick_base: GradientColor
    flick_foreground: GradientColor
    damage: GradientColor
    hold: GradientColor
    hold_background: GradientColor
    slide: GradientColor
    slide_curve: GradientColor
    slide_line: QColor
    slide_background: GradientColor
    air_up: QColor
    air_down: QColor
    air_action: GradientColor
    air_hold_line: QColor
    air_step: GradientColor

# Extracted from Ched/Ched/UI/NoteView.cs
DEFAULT_COLOR_PROFILE = ColorProfile(
    border=GradientColor(rgb(160, 160, 160), rgb(208, 208, 208)),
    tap=GradientColor(rgb(138, 0, 0), rgb(255, 128, 128)),
    ex_tap=GradientColor(rgb(204, 192, 0), rgb(255, 236, 68)),
    flick_base=GradientColor(rgb(68, 68, 68), rgb(186, 186, 186)),
    flick_foreground=GradientColor(rgb(0, 96, 138), rgb(122, 216, 252)),
    damage=GradientColor(rgb(8, 8, 116), rgb(22, 40, 180)),
    hold=GradientColor(rgb(196, 86, 0), rgb(244, 156, 102)),
    hold_background=GradientColor(argb(196, 166, 44, 168), argb(196, 216, 216, 0)),
    slide=GradientColor(rgb(0, 16, 138), rgb(86, 106, 255)),
    slide_curve=GradientColor(rgb(179, 0, 223), rgb(138, 71, 155)),
    slide_line=argb(196, 0, 214, 192),
    slide_background=GradientColor(argb(196, 166, 44, 168), argb(196, 0, 164, 146)),
    air_up=rgb(28, 206, 22),
    air_down=rgb(192, 21, 216),
    air_action=GradientColor(rgb(146, 0, 192), rgb(212, 92, 255)),
    air_hold_line=argb(216, 0, 196, 0),
    air_step=GradientColor(rgb(6, 180, 10), rgb(80, 224, 64))
)
