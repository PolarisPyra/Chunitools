"""Keyboard input handler for the main window.

Extracted from MainWindow.keyPressEvent to keep the window class focused
on orchestration rather than key mapping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent  # noqa: TC002

if TYPE_CHECKING:
    from src.workspace.layout import MainWindow


class KeyHandler:
    """Handles keyboard shortcuts for the main window."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window

    def handle_key(self, event: QKeyEvent) -> bool:  # noqa: PLR0911
        """Process a key press. Return True if handled."""
        k = event.key()
        mods = event.modifiers()

        if k in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            self.window.note_editor.delete_selected()
            return True

        if k == Qt.Key.Key_Space:
            self.window.toggle_playback()
            return True

        if k == Qt.Key.Key_C:
            v = self.window.visualizer
            v.column_mode ^= True
            v.update()
            self.window.statusBar().showMessage(
                f"Column Mode: {'ON' if v.column_mode else 'OFF'}", 2000
            )
            return True

        if k == Qt.Key.Key_BracketLeft:
            v = self.window.visualizer
            v.measures_per_column = max(1, v.measures_per_column - 1)
            v.update()
            self.window.statusBar().showMessage(
                f"Measures per Column: {v.measures_per_column}", 2000
            )
            return True

        if k == Qt.Key.Key_BracketRight:
            v = self.window.visualizer
            v.measures_per_column = min(32, v.measures_per_column + 1)
            v.update()
            self.window.statusBar().showMessage(
                f"Measures per Column: {v.measures_per_column}", 2000
            )
            return True

        if k == Qt.Key.Key_A and mods & Qt.KeyboardModifier.ControlModifier:
            self._select_all_notes()
            return True

        if k == Qt.Key.Key_Escape:
            self.window.visualizer._clear_selection()
            return True

        return False

    def _select_all_notes(self) -> None:
        chart = self.window.current_chart
        if not chart:
            return
        notes = list(chart.notes)
        if not notes:
            return
        v = self.window.visualizer
        v.selected_notes = notes
        v.selected_note = notes[0]
        v.notes_selected.emit(notes)
        v.update()
        self.window.statusBar().showMessage(f"Selected {len(notes)} note(s).", 2000)
