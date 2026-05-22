from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from src.core.const import NoteType
from src.ui.window.menus import _make_note_tool_icon


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_down_air_toolbar_icons_face_down() -> None:
    _app()

    for note_type in (NoteType.ADW, NoteType.ADL, NoteType.ADR):
        image = _make_note_tool_icon(note_type).pixmap(QSize(24, 24)).toImage()

        assert image.pixelColor(5, 8).alpha() > 0
        assert image.pixelColor(5, 16).alpha() == 0
