from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit

from src.ui import theme


def make_section_label(text: str, *, warning: bool = False) -> QLabel:
    label = QLabel(text)
    font = QFont(theme.FONT_UI, 10, QFont.Weight.DemiBold)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
    label.setFont(font)
    label.setStyleSheet(
        f"color: {theme.WARNING_RED if warning else theme.WHITE};"
        f"background: {theme.TRANSPARENT};"
    )
    return label


def make_status_label(text: str, *, muted: bool = False) -> QLabel:
    label = QLabel(text)
    font = QFont(theme.FONT_MONO, 10, QFont.Weight.Medium)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)
    label.setFont(font)
    label.setStyleSheet(
        f"color: {theme.WHITE if muted else theme.TEXT_PRIMARY};"
        f"background: {theme.TRANSPARENT};"
    )
    return label


def make_command_button(text: str, *, width: int) -> QPushButton:
    button = QPushButton(text)
    button.setFixedWidth(width)
    button.setFixedHeight(22)
    button.setFont(QFont(theme.FONT_UI, 9, QFont.Weight.Bold))
    return button


def make_inspector_text() -> QTextEdit:
    editor = QTextEdit()
    editor.setReadOnly(True)
    font = QFont(theme.FONT_MONO, 9)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    editor.setFont(font)
    editor.setObjectName("InspectorText")
    return editor
