"""Undo/redo history for note editing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.editor import add_note, remove_notes
from src.notes import Note

if TYPE_CHECKING:
    from src.ui.window.window import MainWindow


class NoteHistory:
    """Manages the undo/redo stack for note edits."""

    def __init__(self, window: MainWindow) -> None:
        self.w = window

    @property
    def _chart(self):
        return self.w.current_chart

    @property
    def _read_only(self):
        return self.w._chart_read_only

    # ── Stack access ──

    @property
    def _undo(self) -> list[tuple[str, list[Note]]]:
        return self.w._undo_stack

    @property
    def _redo(self) -> list[tuple[str, list[Note]]]:
        return self.w._redo_stack

    def push(self, operation: str, notes: list[Note]) -> None:
        self._undo.append((operation, list(notes)))
        self._redo.clear()
        self._sync()

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._sync()

    def undo(self) -> tuple[str, list[Note]] | None:
        if not self._undo or self._read_only:
            return None
        operation, notes = self._undo.pop()
        if operation == "add":
            removed = remove_notes(self._chart, notes)
            if not removed:
                self._sync()
                return None
            self._redo.append((operation, notes))
            return "undo_add", []
        if operation == "replace" and len(notes) == 2:
            original, replacement = notes
            self._replace(replacement, original)
            self._redo.append((operation, notes))
            return "undo_replace", [original]
        return None

    def redo(self) -> tuple[str, list[Note]] | None:
        if not self._redo or self._read_only:
            return None
        operation, notes = self._redo.pop()
        if operation == "add":
            for n in notes:
                add_note(self._chart, n)
            self._undo.append((operation, notes))
            return "redo_add", [notes[-1]]
        if operation == "replace" and len(notes) == 2:
            original, replacement = notes
            self._replace(original, replacement)
            self._undo.append((operation, notes))
            return "redo_replace", [replacement]
        return None

    def _replace(self, original: Note, replacement: Note) -> None:
        chart = self._chart
        if chart is None:
            return
        for i, n in enumerate(chart.notes):
            if n is original:
                chart.notes[i] = replacement
                chart.invalidate_timeline()
                return

    def _sync(self) -> None:
        w = self.w
        can_edit = self._chart is not None and not self._read_only
        if hasattr(w, "undo_action"):
            w.undo_action.setEnabled(can_edit and bool(self._undo))
        if hasattr(w, "redo_action"):
            w.redo_action.setEnabled(can_edit and bool(self._redo))
