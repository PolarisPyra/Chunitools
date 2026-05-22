"""Open the source chart file at a note's line in an external editor."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from src.notes import AirSlideStart, Note, Slide

if TYPE_CHECKING:
    from src.ui.window.window import MainWindow

LOGGER = logging.getLogger(__name__)
EDITOR_ENV_VAR = "CHUNITOOLS_EDITOR"

_VSCODE_LIKE = {"code", "code-insiders", "codium", "cursor", "windsurf"}
_SUBLIME_LIKE = {"subl", "sublime_text"}
_KATE_LIKE = {"kate", "kwrite"}
_GEDIT = {"gedit"}


class SourceFileOpener:
    """Finds a note's source line and opens it in an external editor."""

    def __init__(self, window: MainWindow) -> None:
        self.w = window

    def open(self, note: Note) -> None:
        location = self._locate(note)
        if location is None:
            self.w.statusBar().showMessage("No chart file is loaded for this note.", 3000)
            return
        path, line_number = location
        if line_number is None:
            self.w.statusBar().showMessage(
                "Could not find that note in the chart file. Save the chart and try again.",
                4000,
            )
            return
        if self._launch(path, line_number):
            self.w.statusBar().showMessage(f"Opened {path.name}:{line_number}.", 3000)
        else:
            self.w.statusBar().showMessage(f"Could not open {path.name}:{line_number}.", 4000)

    def _locate(self, note: Note) -> tuple[Path, int | None] | None:
        file_path = getattr(self.w, "current_file_path", None)
        if not file_path:
            return None
        path = Path(file_path)
        source = self._source_note(note)
        target = self._source_line(source)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return path, None
        for line_number, raw_line in enumerate(lines, start=1):
            if raw_line.strip() == target:
                return path, line_number
        return path, None

    @staticmethod
    def _source_note(note: Note) -> Note:
        if isinstance(note, (Slide, AirSlideStart)) and note.steps:
            return note.steps[0]
        return note

    def _source_line(self, note: Note) -> str:
        chart = self.w.current_chart
        if chart is not None:
            return chart.find_note_line(note)
        return note.serialize()

    def _launch(self, path: Path, line_number: int) -> bool:
        configured = os.environ.get(EDITOR_ENV_VAR)
        if configured and self._exec(configured, path, line_number):
            return True
        for cmd in _VSCODE_LIKE | _SUBLIME_LIKE | _KATE_LIKE | _GEDIT:
            if shutil.which(cmd) and self._exec(cmd, path, line_number):
                return True
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @staticmethod
    def _exec(command: str, path: Path, line_number: int) -> bool:
        try:
            base_args = shlex.split(command)
        except ValueError:
            LOGGER.warning("Invalid %s command: %s", EDITOR_ENV_VAR, command)
            return False
        if not base_args:
            return False
        exe = Path(base_args[0]).name
        if exe in _VSCODE_LIKE:
            args = [*base_args, "-g", f"{path}:{line_number}"]
        elif exe in _SUBLIME_LIKE:
            args = [*base_args, f"{path}:{line_number}"]
        elif exe in _KATE_LIKE:
            args = [*base_args, "--line", str(line_number), str(path)]
        elif exe in _GEDIT:
            args = [*base_args, f"+{line_number}", str(path)]
        else:
            args = [*base_args, str(path)]
        try:
            subprocess.Popen(args)
        except OSError as exc:
            LOGGER.warning("Failed to launch editor command %s: %s", args, exc)
            return False
        return True
