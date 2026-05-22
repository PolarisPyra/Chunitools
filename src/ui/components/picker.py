from __future__ import annotations

import os
import subprocess
from typing import Literal

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.core.read import SongInfo
from src.core.read import MetadataPreview, fast_get_metadata
from src.ui import theme
from src.ui.components.picker_model import SongModel
from src.ui.components.picker_delegate import SongDelegate

ViewMode = Literal["standard", "ultima", "worlds_end"]

_LIST_STYLESHEET = f"""
    QListView {{
        background: {theme.SURFACE_RAISED};
        border: none;
        outline: none;
        color: {theme.TEXT_PRIMARY};
    }}
    QScrollBar:vertical {{
        background: {theme.SURFACE_SCROLLBAR};
        width: 12px;
        margin: 0;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {theme.SURFACE_SCROLLBAR_HANDLE};
        border-radius: 6px;
        min-height: 40px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {theme.SURFACE_SCROLLBAR_HANDLE_HOVER};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: {theme.TRANSPARENT};
    }}
"""

_MENU_STYLESHEET = (
    f"QMenu {{ background: {theme.SURFACE_MENU}; color: {theme.TEXT_SOFT}; "
    "border: 1px solid rgba(255, 255, 255, 0.10); border-radius: 8px; }}"
    f"QMenu::item {{ padding: 8px 18px; background: {theme.TRANSPARENT}; }}"
    f"QMenu::item:selected {{ background: {theme.SURFACE_MENU_HOVER}; color: {theme.TEXT_PRIMARY}; }}"
)

_MODE_BUTTON_STYLESHEET = f"""
    QPushButton#ModeToggle {{
        background: rgba(255, 255, 255, 0.03);
        color: {theme.TEXT_MUTED};
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 8px;
        padding: 0 10px;
        min-height: 28px;
        font-size: 11px;
        font-weight: 600;
    }}
    QPushButton#ModeToggle:hover {{
        background: rgba(255, 255, 255, 0.05);
        color: {theme.TEXT_SOFT};
        border-color: rgba(255, 255, 255, 0.10);
    }}
    QPushButton#ModeToggle:checked {{
        background: {theme.SURFACE_ELEVATED};
        color: {theme.TEXT_PRIMARY};
        border-color: rgba(255, 255, 255, 0.18);
    }}
    QPushButton#ModeToggle:checked:hover {{
        background: {theme.SURFACE_ELEVATED};
        color: {theme.TEXT_PRIMARY};
        border-color: rgba(255, 255, 255, 0.24);
    }}
"""


class PickerListView(QListView):
    """Custom list view to handle dynamic cursor changes on difficulty markers."""

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if index.isValid():
            delegate = self.itemDelegate()
            if hasattr(delegate, "hit_test_difficulty"):
                from PySide6.QtWidgets import QStyleOptionViewItem

                option = QStyleOptionViewItem()
                option.widget = self
                option.rect = self.visualRect(index)
                if delegate.hit_test_difficulty(option, index, pos):
                    self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                    return
        self.viewport().unsetCursor()


class ChartPicker(QWidget):
    """Sidebar widget for selecting songs and difficulties."""

    chart_selected = Signal(str)
    song_previewed = Signal(dict)

    def __init__(self, songs: list[SongInfo], parent: QWidget | None = None) -> None:
        """Create picker for *songs*."""
        super().__init__(parent)
        self.songs = songs
        self.ascending = True
        self.view_mode: ViewMode = "standard"
        self.search_text: str = ""
        self.setObjectName("ChartPicker")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._apply_search_filter)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self.btn_sort = QPushButton("ID ↑")
        self.btn_std = QPushButton("STANDARD")
        self.btn_ult = QPushButton("ULTIMA")
        self.btn_we = QPushButton("WORLD'S END")
        self.search_input = QLineEdit()

        # Models
        self.model_std = SongModel([])
        self.model_ult = SongModel([])
        self.model_we = SongModel([])

        # Views
        self.view_std = PickerListView()
        self.view_ult = PickerListView()
        self.view_we = PickerListView()

        self._build_header()
        self._build_song_lists()
        self._populate_all_lists()
        self._update_toggle_styles()

    def _on_song_selected(self) -> None:
        """Handle song selection after filtering or sorting."""
        model = self._active_view().model()
        if model.rowCount() > 0:
            first_song_index = model.index(0, 0)
            first_song = model.data(first_song_index, Qt.ItemDataRole.UserRole)
            if isinstance(first_song, SongInfo):
                self.song_previewed.emit(self._metadata_preview(first_song))

    def _build_header(self) -> None:
        """Build title, sort button, and mode toggles."""
        header_container = QFrame()
        header_container.setObjectName("PickerHeader")
        header_layout = QVBoxLayout(header_container)
        header_layout.setContentsMargins(14, 14, 14, 12)
        header_layout.setSpacing(12)

        top_row = QHBoxLayout()
        header = QLabel("LIBRARY")
        header.setObjectName("PickerTitle")
        header_font = QFont(theme.FONT_UI, 11, QFont.Weight.DemiBold)
        header_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        header.setFont(header_font)
        top_row.addWidget(header)
        top_row.addStretch()

        self.btn_sort.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_sort.clicked.connect(self.toggle_sort)
        top_row.addWidget(
            self.btn_sort,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        header_layout.addLayout(top_row)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(12)
        toggle_row.setContentsMargins(0, 0, 0, 4)
        toggle_row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for button in (self.btn_std, self.btn_ult, self.btn_we):
            button.setObjectName("ModeToggle")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(28)
            button.setStyleSheet(_MODE_BUTTON_STYLESHEET)

        self.btn_std.clicked.connect(
            lambda _checked=False: self.set_view_mode("standard")
        )
        self.btn_ult.clicked.connect(
            lambda _checked=False: self.set_view_mode("ultima")
        )
        self.btn_we.clicked.connect(
            lambda _checked=False: self.set_view_mode("worlds_end")
        )

        toggle_row.addWidget(self.btn_std)
        toggle_row.addWidget(self.btn_ult)
        toggle_row.addWidget(self.btn_we)
        header_layout.addLayout(toggle_row)

        self.search_input.setPlaceholderText("Search title...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.set_search_text)
        header_layout.addWidget(self.search_input)
        self.root_layout.addWidget(header_container)

    def _build_song_lists(self) -> None:
        """Create standard, ULTIMA and WORLD'S END song lists."""
        lists = [
            (self.view_std, self.model_std, "standard"),
            (self.view_ult, self.model_ult, "ultima"),
            (self.view_we, self.model_we, "worlds_end"),
        ]
        for view, model, mode in lists:
            view.setModel(model)
            view.setProperty("view_mode", mode)
            view.setItemDelegate(SongDelegate(view))
            # Attach the callback to the view itself so the delegate can find it
            view.on_difficulty_clicked = self.on_difficulty_clicked
            view.setMouseTracking(True)
            view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
            view.setStyleSheet(_LIST_STYLESHEET)
            view.setUniformItemSizes(True)
            view.setSelectionMode(QListView.SelectionMode.NoSelection)

            view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(self._show_context_menu)

            self.root_layout.addWidget(view, stretch=1)

    def _show_context_menu(self, pos: QPoint) -> None:
        view = self._active_view()
        index = view.indexAt(pos)
        if not index.isValid():
            return
        song = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(song, SongInfo):
            return

        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLESHEET)
        
        copy_action = QAction("Copy Song Name", self)
        copy_action.triggered.connect(lambda: self._copy_to_clipboard(song.name))
        menu.addAction(copy_action)
        
        action = QAction("Open File Location", self)
        action.triggered.connect(lambda: self._open_song_location(song))
        menu.addAction(action)
        
        menu.exec(view.viewport().mapToGlobal(pos))

    @staticmethod
    def _copy_to_clipboard(text: str) -> None:
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        if cb:
            cb.setText(text)

    @staticmethod
    def _open_song_location(song: SongInfo) -> None:
        if song.fumens:
            folder = os.path.dirname(song.fumens[0].file_path)
        else:
            folder = song.base_dir
        if os.path.isdir(folder):
            subprocess.Popen(["xdg-open", folder])

    def _populate_all_lists(self) -> None:
        """Populate models from song list."""
        # 1. World's End: Specialized folders
        worlds_end = [
            song for song in self.songs if song.folder_name.startswith("music8")
        ]

        # 2. Ultima: Standard folders that contain an ULTIMA difficulty chart
        # These are moved out of the standard list into their own dedicated tab.
        ultima = [
            song
            for song in self.songs
            if not song.folder_name.startswith("music8")
            and any(f.difficulty == 4 for f in song.fumens)
        ]

        # 3. Standard: All standard folders (non-music8), including those with Ultima charts.
        standard = [
            song for song in self.songs if not song.folder_name.startswith("music8")
        ]

        self.model_std._all_songs = standard
        self.model_std.filter("")

        self.model_ult._all_songs = ultima
        self.model_ult.filter("")

        self.model_we._all_songs = worlds_end
        self.model_we.filter("")

        self.update_view()

    def update_view(self) -> None:
        """Show active list and hide inactive lists."""
        self.view_std.setVisible(self.view_mode == "standard")
        self.view_ult.setVisible(self.view_mode == "ultima")
        self.view_we.setVisible(self.view_mode == "worlds_end")

    def set_view_mode(self, mode: ViewMode) -> None:
        """Switch between standard, ULTIMA and WORLD'S END lists."""
        self.view_mode = mode
        self.btn_std.setChecked(mode == "standard")
        self.btn_ult.setChecked(mode == "ultima")
        self.btn_we.setChecked(mode == "worlds_end")
        self._update_toggle_styles()
        self.update_view()

    def _update_toggle_styles(self) -> None:
        """Refresh mode toggle appearance using standard checked state."""
        self.btn_std.setChecked(self.view_mode == "standard")
        self.btn_ult.setChecked(self.view_mode == "ultima")
        self.btn_we.setChecked(self.view_mode == "worlds_end")

    def _active_view(self) -> QListView:
        if self.view_mode == "standard":
            return self.view_std
        elif self.view_mode == "ultima":
            return self.view_ult
        return self.view_we

    def toggle_sort(self) -> None:
        """Toggle sort order."""
        self.ascending = not self.ascending
        self.btn_sort.setText("ID ↑" if self.ascending else "ID ↓")
        self.model_std.sort_by_id(self.ascending)
        self.model_ult.sort_by_id(self.ascending)
        self.model_we.sort_by_id(self.ascending)
        self._apply_search_filter()

    def set_search_text(self, text: str) -> None:
        """Filter songs by title."""
        self.search_text = text
        self._search_timer.start()

    def _apply_search_filter(self) -> None:
        self.model_std.filter(self.search_text)
        self.model_ult.filter(self.search_text)
        self.model_we.filter(self.search_text)
        self._on_song_selected()

    def on_difficulty_clicked(self, file_path: str, song: SongInfo) -> None:
        """Called by delegate when a difficulty marker is clicked."""
        self.chart_selected.emit(file_path)
        self.song_previewed.emit(self._metadata_preview(song))

    @staticmethod
    def _metadata_preview(song: SongInfo) -> MetadataPreview:
        """Read preview metadata from first available chart."""
        if not song.fumens:
            return {"bpm_def": None, "creator": None}
        return fast_get_metadata(song.fumens[0].file_path)
