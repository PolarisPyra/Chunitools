from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QMessageBox

from src.config import settings
from src.core.write import create_blank_chart, save_chart_file, save_music_xml as write_music_xml

if TYPE_CHECKING:
    from src.core.models import Chart
    from src.workspace.layout import MainWindow


class FileHandler:
    """Handles chart file operations (new, open, save, load, display)."""

    def __init__(self, window: MainWindow) -> None:
        self.w = window

    @property
    def _chart(self) -> Chart | None:
        return self.w.current_chart

    @_chart.setter
    def _chart(self, v: Chart | None) -> None:
        self.w.current_chart = v

    # ── Confirm discard ──

    def confirm_discard(self) -> bool:
        if not self.w._chart_dirty:
            return True
        result = QMessageBox.question(
            self.w,
            "Discard unsaved changes?",
            "The current chart has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Discard

    def suggest_filename(self) -> str:
        if self.w.current_file_path:
            return self.w.current_file_path
        if self._chart:
            meta = self._chart.metadata
            music_id = meta.music_id or "0000"
            diff_id = meta.difficulty_id or 0
            return str(Path.home() / f"{music_id}_{diff_id:02d}.c2s")
        return str(Path.home() / "new_chart.c2s")

    # ── New ──

    def new(self) -> None:
        if not self.confirm_discard():
            return
        chart = create_blank_chart()
        self._chart = chart
        self.w.current_file_path = None
        self.w._chart_dirty = True
        self.w._chart_read_only = False
        self.w.note_editor.clear_history()
        self.w.playback.set_chart(chart)
        self.w.playback_service.set_chart_audio(chart, None)
        self.w._display_chart(chart)
        self.w._update_chart_metadata(chart)
        self.w.metadata_editor.sync_fields()
        self.w._sync_file_actions()
        self.w.statusBar().showMessage("New blank chart created.", 3000)

    # ── Open ──

    def open_dialog(self) -> None:
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self.w, "Open .c2s Chart", os.path.expanduser("~"),
            "CHUNITHM Charts (*.c2s);;All Files (*)",
        )
        if path:
            self.w.load_chart_file(path)

    # ── Save ──

    def save(self) -> bool:
        if self._chart is None:
            return False
        if self.w._chart_read_only:
            QMessageBox.information(self.w, "Read-only chart", "Charts loaded from the data folder cannot be edited.")
            return False
        self.w.metadata_editor._apply_fields()
        if not self.w.current_file_path:
            return self.save_as()
        try:
            save_chart_file(self._chart, self.w.current_file_path)
        except OSError as exc:
            QMessageBox.warning(self.w, "Save failed", f"Could not save chart:\n{exc}")
            return False
        self.w._chart_dirty = False
        self.w._sync_file_actions()
        self.w.statusBar().showMessage(f"Saved {Path(self.w.current_file_path).name}.", 3000)
        return True

    def save_as(self) -> bool:
        if self._chart is None:
            return False
        if self.w._chart_read_only:
            QMessageBox.information(self.w, "Read-only chart", "Charts loaded from the data folder cannot be edited.")
            return False
        suggested = self.suggest_filename()
        path, _ = QFileDialog.getSaveFileName(
            self.w, "Save .c2s Chart", suggested, "CHUNITHM Charts (*.c2s);;All Files (*)",
        )
        if not path:
            return False
        if not path.lower().endswith(".c2s"):
            path += ".c2s"
        prev = self.w.current_file_path
        self.w.current_file_path = path
        ok = self._save_with_source(prev)
        if not ok:
            self.w.current_file_path = prev
        return ok

    def _save_with_source(self, source: str | None) -> bool:
        if self._chart is None or not self.w.current_file_path:
            return False
        self.w.metadata_editor._apply_fields()
        try:
            save_chart_file(self._chart, self.w.current_file_path, source)
        except OSError as exc:
            QMessageBox.warning(self.w, "Save failed", f"Could not save chart:\n{exc}")
            return False
        self.w._chart_dirty = False
        self.w.metadata_editor.sync_fields()
        self.w._sync_file_actions()
        self.w.statusBar().showMessage(f"Saved {Path(self.w.current_file_path).name}.", 3000)
        return True

    def save_music_xml(self) -> None:
        if self._chart is None:
            return
        if self.w._chart_read_only:
            QMessageBox.information(self.w, "Read-only chart", "Charts loaded from the data folder cannot be edited.")
            return
        self.w.metadata_editor._apply_fields()
        if not self.w.current_file_path and not self.save_as():
            return
        assert self.w.current_file_path is not None
        chart_path = Path(self.w.current_file_path)
        try:
            write_music_xml(self._chart, chart_path.with_name("Music.xml"), chart_path.name)
        except OSError as exc:
            QMessageBox.warning(self.w, "Save failed", f"Could not save Music.xml:\n{exc}")
            return
        self.w.statusBar().showMessage("Saved Music.xml.", 3000)

    # ── Data root ──

    def prompt_data_root(self) -> str | None:
        path = QFileDialog.getExistingDirectory(
            self.w, "Select CHUNITM Data Directory (containing 'A***' folders)",
            os.path.expanduser("~"),
        )
        if path:
            settings.data_root = path
            settings.save()
            return path
        return None
