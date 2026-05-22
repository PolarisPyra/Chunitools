from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.core.images import convert_jacket_image_to_dds
from src.core.option_export import OptionExportError, export_option_folder, verify_option_folder
from src.ui.window.widgets import make_command_button, make_section_label

if TYPE_CHECKING:
    from src.ui.window.window import MainWindow

AUDIO_FILE_FILTER = (
    "Supported Audio (*.flac *.wav *.mp3 *.awb);;"
    "FLAC (*.flac);;WAV (*.wav);;MP3 (*.mp3);;AWB (*.awb);;All Files (*)"
)
JACKET_IMAGE_FILTER = "Jacket Images (*.png *.jpg *.jpeg);;PNG (*.png);;JPEG (*.jpg *.jpeg)"
ACB_TEMPLATE_FILTER = "ACB Template (*.acb);;All Files (*)"
DESKTOP_DIR = Path.home() / "Desktop"


class MetadataEditor(QFrame):
    """Chart metadata / asset editor panel (Song / Assets / Option tabs)."""

    def __init__(self, window: MainWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.w = window
        self._syncing_editor_fields = False
        self.metadata_fields: dict[str, QLineEdit] = {}
        self.editor_stack: QStackedWidget | None = None
        self._editor_segment_group = None
        self.create_option_folder_button: QPushButton | None = None
        self._init_ui()

    # ── Quick-access helpers ──

    @property
    def _chart(self):
        return self.w.current_chart

    @property
    def _read_only(self):
        return self.w._chart_read_only

    # ── Init ──

    def _init_ui(self) -> None:
        self.setObjectName("MetadataEditor")
        editor_layout = QVBoxLayout(self)
        editor_layout.setContentsMargins(10, 8, 10, 8)
        editor_layout.setSpacing(12)
        editor_layout.addWidget(make_section_label("OPTION EDITOR"))

        segment_row = QWidget()
        segment_layout = QHBoxLayout(segment_row)
        segment_layout.setContentsMargins(0, 0, 0, 0)
        segment_layout.setSpacing(4)
        self.editor_stack = QStackedWidget()
        from PySide6.QtWidgets import QButtonGroup

        self._editor_segment_group = QButtonGroup(self)
        self._editor_segment_group.setExclusive(True)

        pages = [
            ("Song", [
                ("title", "Title"), ("artist", "Artist"), ("music_id", "Music ID"),
                ("sequence_id", "Sequence"), ("difficulty", "Difficulty"),
                ("level", "Level"), ("creator", "Creator"), ("version", "Version"),
                ("bpm", "BPM"),
            ]),
            ("Assets", [("jacket_path", "Jacket"), ("audio_path", "Audio Source")]),
            ("Option", [("option_folder", "Folder"), ("atomcraft_project", "ACB Template"), ("hca_key", "HCA Key")]),
        ]

        for page_idx, (page_label, fields) in enumerate(pages):
            btn = QPushButton(page_label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, idx=page_idx: self.editor_stack.setCurrentIndex(idx))
            self._editor_segment_group.addButton(btn)
            segment_layout.addWidget(btn)
            if page_idx == 0:
                btn.setChecked(True)

            page = QWidget()
            form = QFormLayout(page)
            form.setContentsMargins(0, 0, 0, 0)
            form.setSpacing(6)
            for key, label_text in fields:
                field = QLineEdit()
                field.setObjectName("EditorField")
                field.editingFinished.connect(self._on_field_changed)
                self.metadata_fields[key] = field
                if key in {"jacket_path", "audio_path", "atomcraft_project"}:
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(4)
                    row_layout.addWidget(field, stretch=1)
                    browse_btn = QPushButton("...")
                    browse_btn.setFixedWidth(32)
                    browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    browse_btn.clicked.connect(lambda checked=False, fk=key: self._browse_path(fk))
                    row_layout.addWidget(browse_btn)
                    form.addRow(label_text, row)
                else:
                    form.addRow(label_text, field)
            self.editor_stack.addWidget(page)

        editor_layout.addWidget(segment_row)
        editor_layout.addWidget(self.editor_stack)

        self.create_option_folder_button = make_command_button("CREATE OPTION FOLDER", width=220)
        self.create_option_folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_option_folder_button.clicked.connect(self._create_option_folder)
        editor_layout.addWidget(self.create_option_folder_button, 0, Qt.AlignmentFlag.AlignHCenter)

    # ── Sync fields from chart ──

    def sync_fields(self) -> None:
        chart = self._chart
        if chart is None:
            return
        self._syncing_editor_fields = True
        try:
            meta = chart.metadata
            values = {
                "title": meta.title,
                "artist": meta.artist,
                "music_id": meta.music_id,
                "sequence_id": meta.sequence_id,
                "difficulty": meta.difficulty,
                "level": meta.level,
                "creator": meta.creator,
                "version": meta.version,
                "bpm": self._metadata_bpm_text(chart),
                "jacket_path": meta.jacket_path,
                "audio_path": meta.audio_path,
                "option_folder": chart.editor.get("option_folder", self._suggest_option_folder_name()),
                "atomcraft_project": chart.editor.get("atomcraft_project", ""),
                "hca_key": chart.editor.get("hca_key", ""),
            }
            for key, value in values.items():
                if key in self.metadata_fields:
                    self.metadata_fields[key].setText(str(value or ""))
        finally:
            self._syncing_editor_fields = False
        self._sync_editor_enabled()

    def _sync_editor_enabled(self) -> None:
        readonly = self._read_only
        for field in self.metadata_fields.values():
            field.setReadOnly(readonly)
            field.setEnabled(not readonly)
        if self.create_option_folder_button:
            self.create_option_folder_button.setEnabled(not readonly and self._chart is not None)

    # ── Apply fields to chart ──

    def _on_field_changed(self) -> None:
        if self._syncing_editor_fields:
            return
        self._apply_fields()

    def _apply_fields(self) -> None:
        if self._chart is None or self._syncing_editor_fields:
            return
        if self._read_only:
            return
        chart = self._chart
        meta = chart.metadata
        meta.title = self.metadata_fields["title"].text().strip()
        meta.artist = self.metadata_fields["artist"].text().strip()
        meta.music_id = self.metadata_fields["music_id"].text().strip()
        meta.sequence_id = self.metadata_fields["sequence_id"].text().strip()
        meta.difficulty = self.metadata_fields["difficulty"].text().strip()
        meta.level = self.metadata_fields["level"].text().strip()
        meta.creator = self.metadata_fields["creator"].text().strip()
        meta.version = self.metadata_fields["version"].text().strip()
        meta.jacket_path = self.metadata_fields["jacket_path"].text().strip()
        meta.audio_path = self.metadata_fields["audio_path"].text().strip()
        chart.editor["option_folder"] = self.metadata_fields["option_folder"].text().strip()
        chart.editor["atomcraft_project"] = self.metadata_fields["atomcraft_project"].text().strip()
        chart.editor["hca_key"] = self.metadata_fields["hca_key"].text().strip()
        if meta.difficulty:
            diff_map = {
                "BASIC": 0, "ADVANCED": 1, "EXPERT": 2,
                "MASTER": 3, "ULTIMA": 4, "WORLD'S END": 5,
            }
            meta.difficulty_id = diff_map.get(meta.difficulty.upper(), meta.difficulty_id)
        bpm_text = self.metadata_fields["bpm"].text().strip()
        try:
            bpm = float(bpm_text)
        except ValueError:
            bpm = None
        if bpm and bpm > 0:
            meta.bpm_def = [f"{bpm:.3f}"] * 4
            if chart.bpms:
                chart.bpms[0] = {"measure": 0, "offset": 0, "bpm": bpm}
            else:
                chart.bpms.append({"measure": 0, "offset": 0, "bpm": bpm})
        chart.signatures = [{"measure": 0, "numerator": meta.met_def[0], "denominator": meta.met_def[1]}]
        chart.invalidate_timeline()
        self.w._chart_dirty = True
        self.w._update_chart_metadata(chart)
        self.w._sync_file_actions()
        self.w.visualizer.update()

    # ── Browse paths ──

    def _browse_path(self, field_key: str) -> None:
        if self._chart is None:
            self.w.new_chart()
        if self._chart is None:
            return
        if self._read_only:
            QMessageBox.information(self.w, "Read-only chart", "Charts loaded from the data folder cannot be edited.")
            return

        if field_key == "audio_path":
            title = "Select Chart Audio"
            file_filter = AUDIO_FILE_FILTER
        elif field_key == "jacket_path":
            title = "Select Jacket Image"
            file_filter = JACKET_IMAGE_FILTER
        elif field_key == "atomcraft_project":
            title = "Select ACB Template"
            file_filter = ACB_TEMPLATE_FILTER
        else:
            return

        path, _ = QFileDialog.getOpenFileName(self.w, title, os.path.expanduser("~"), file_filter)
        if not path:
            return

        stored = self._stored_path(path)
        self.metadata_fields[field_key].setText(stored)
        self._apply_fields()
        if field_key == "audio_path":
            self.w.playback_service.set_chart_audio(self._chart, self.w.current_file_path)
            self.w._sync_timeline_extent(self._chart)
            self.w.statusBar().showMessage(f"Imported audio: {Path(path).name}", 3000)
        elif field_key == "jacket_path":
            self.w.statusBar().showMessage(f"Selected jacket image: {Path(path).name}", 3000)

    # ── Create option folder ──

    def _create_option_folder(self) -> None:
        if self._chart is None:
            QMessageBox.warning(self.w, "Export failed", "No chart is currently loaded.")
            return
        if self._read_only:
            QMessageBox.information(self.w, "Read-only chart", "Loaded data-folder charts are already in option-folder format.")
            return

        self._apply_fields()
        export_root = QFileDialog.getExistingDirectory(self.w, "Select option export parent folder", str(Path.home() / "Desktop"))
        if not export_root:
            return

        option_name = self.metadata_fields.get("option_folder")
        option_folder_name = option_name.text().strip() if option_name else ""
        hca_key_field = self.metadata_fields.get("hca_key")
        hca_key = hca_key_field.text().strip() if hca_key_field else ""

        try:
            result = export_option_folder(
                self._chart, export_root,
                option_folder_name=option_folder_name,
                audio_path=self._resolved_path("audio_path"),
                jacket_path=self._resolved_path("jacket_path"),
                atomcraft_project=self._resolved_path("atomcraft_project"),
                hca_key=hca_key,
            )
        except (OSError, OptionExportError, ValueError) as exc:
            QMessageBox.warning(self.w, "Export failed", f"Could not create option folder:\n{exc}")
            return

        validation = verify_option_folder(result.option_root)
        if not validation.ok:
            QMessageBox.warning(self.w, "Export failed", "Created option folder did not pass validation:\n" + "\n".join(validation.errors))
            return

        self.w._last_export_root = str(result.option_root)
        self.w._last_export_log = None
        self.w.statusBar().showMessage(f"Created option folder: {result.option_root}", 5000)

    # ── Path helpers ──

    def _resolved_path(self, field_key: str) -> str:
        field = self.metadata_fields.get(field_key)
        value = field.text().strip() if field else ""
        if not value:
            return ""
        path = Path(value).expanduser()
        if path.is_absolute():
            return str(path)
        if self.w.current_file_path:
            cand = Path(self.w.current_file_path).parent / path
            if cand.exists():
                return str(cand)
        return str(path)

    def _stored_path(self, asset_path: str) -> str:
        path = Path(asset_path)
        if self.w.current_file_path:
            try:
                return str(path.relative_to(Path(self.w.current_file_path).parent))
            except ValueError:
                pass
        return str(path)

    def convert_image_to_dds(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self.w, "Convert Jacket Image to DDS", os.path.expanduser("~"), JACKET_IMAGE_FILTER)
        if not path:
            return
        music_id = self.w.current_chart.metadata.music_id if self.w.current_chart else ""
        try:
            dds = convert_jacket_image_to_dds(path, DESKTOP_DIR, music_id)
        except ValueError as exc:
            QMessageBox.warning(self.w, "Convert failed", str(exc))
            return
        if self.w.current_chart is not None and not self._read_only:
            stored = self._stored_path(str(dds))
            self.w.current_chart.metadata.jacket_path = stored
            self.metadata_fields["jacket_path"].setText(stored)
            self.w._chart_dirty = True
            self.w._sync_file_actions()
        self.w.statusBar().showMessage(f"Exported {dds.name} to Desktop.", 5000)

    # ── Helpers ──

    def _suggest_option_folder_name(self) -> str:
        if self._chart is None:
            return ""
        meta = self._chart.metadata
        base = f"{meta.music_id}_{meta.difficulty}_{meta.level}" if meta.difficulty else f"{meta.music_id}"
        return base.replace(" ", "_")

    def _metadata_bpm_text(self, chart) -> str:
        if chart.metadata.bpm_def:
            return chart.metadata.bpm_def[0].strip().rstrip(".")
        if chart.bpms and chart.bpms[0].get("bpm"):
            return f'{chart.bpms[0]["bpm"]:.3f}'
        return ""
