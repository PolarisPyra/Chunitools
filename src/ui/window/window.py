from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeyEvent, QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.config import USER_CONFIG_DIR, get_sounds_dir, settings
from src.const import NoteType
from src.core.read import DataScanner, MetadataPreview, load_chart_file
from src.core.write import save_chart_file
from src.engine.playback import PlaybackController

if TYPE_CHECKING:
    from src.model import Chart
    from src.notes import Note
from src.services.playback import PlaybackCoordinator
from src.shell.status_bar import init_status_widgets
from src.ui import theme
from src.ui.components.fps_overlay import FpsOverlay
from src.ui.components.picker import ChartPicker
from src.ui.components.play_view import PlayView3D
from src.ui.components.radar import NoteDensityRadar
from src.ui.components.timeline_view import ChartViewport
from src.ui.theme.styles import get_main_stylesheet
from src.ui.view.timeline_widget import TimelineWidget
from src.ui.window import export as export_ops
from src.ui.window.editor_actions import NoteEditor
from src.ui.window.file_handler import FileHandler
from src.ui.window.inspectors import (
    format_notes_summary,
    format_render_behavior,
    resolve_warning_note,
)
from src.ui.window.key_handler import KeyHandler
from src.ui.window.metadata_editor import MetadataEditor
from src.ui.window.overlay_manager import OverlayManager
from src.ui.window.settings_handler import SettingsHandler
from src.ui.window.widgets import (
    make_inspector_text,
    make_section_label,
    make_status_label,
)
from src.workspace.menubar import MenuCursorFilter, create_menu_bar

LOGGER = logging.getLogger(__name__)

_LOGS_DIR_NAME = "logs"
_NOTE_RENDERING_DEBUG_LOG_NAME = "note_rendering_debug.log"


def _setup_note_rendering_debug_log(
    chart_title: str,
    chart_music_id: str,
    file_path: str,
) -> None:
    """Configure the note_rendering_debug logger with chart context.

    Called when a chart is loaded. Writes chart metadata as the first log
    entries so the log file is self-documenting.
    """
    log_dir = USER_CONFIG_DIR / _LOGS_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("note_rendering_debug")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = logging.FileHandler(
        log_dir / _NOTE_RENDERING_DEBUG_LOG_NAME, mode="w", encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    logger.info("Chart Title: %s", chart_title)
    logger.info("Chart Music ID: %s", chart_music_id)
    logger.info("Chart Path: %s", file_path)


class MainWindow(QMainWindow):
    """Main application window for the Chunithm Chart Viewer."""

    def _open_settings_dialog(self) -> None:
        """Open the full settings preferences dialog."""
        from src.dialogs.settings import open_settings

        old_root = settings.data_root
        open_settings(self)
        # If the data directory changed in settings, rescan and refresh the picker
        if settings.data_root != old_root:
            self._rescan_data_directory()

    def _rescan_data_directory(self) -> None:
        """Re-scan the configured data directory and refresh the picker."""
        path = settings.data_root
        if not path:
            return
        self.scanner = DataScanner(path)
        self.songs = self.scanner.scan()
        self.picker.songs = self.songs
        self.picker._populate_all_lists()
        self.playback_service.shutdown()
        sounds_path = get_sounds_dir(path)
        self.playback_service = PlaybackCoordinator(
            self.playback, str(sounds_path / "tap.wav"), path, self
        )
        self.playback_service.set_hitsound_volume(settings.hitsound_volume)
        self.playback_service.set_music_volume(settings.music_volume)
        self.visualizer.user_seeked.disconnect()
        self.visualizer.user_seeked.connect(self.playback_service.seek)
        self.play_view.user_seeked.disconnect()
        self.play_view.user_seeked.connect(self.playback_service.seek)
        self.statusBar().showMessage(f"Scanned data directory: {path}", 3000)

    def __init__(self) -> None:  # noqa: PLR0915
        super().__init__()
        self.setWindowTitle("Chunitools")
        self.resize(settings.window_width, settings.window_height)
        self.setStyleSheet(get_main_stylesheet())

        self.current_chart: Chart | None = None
        self.current_file_path: str | None = None
        self._chart_dirty = False
        self._chart_read_only = False
        self._editor_note_type = NoteType.TAP
        self._editor_note_width = 1
        self._warning_note_map: dict[str, Note | None] = {}
        self._undo_stack: list[tuple[str, list[Note]]] = []
        self._redo_stack: list[tuple[str, list[Note]]] = []
        self._show_warning_panel = False
        self._show_note_inspector = False
        self._show_editor_panel = False

        self._inspector_grouped = True
        self._current_inspector_notes: list[Note] = []
        self._last_export_root: str | None = None
        self._last_export_log: str | None = None
        self._export_cancel_requested = False

        self._menu_cursor_filter: MenuCursorFilter
        self.new_chart_action: QAction
        self.open_chart_action: QAction
        self.import_audio_action: QAction
        self.save_chart_action: QAction
        self.save_chart_as_action: QAction
        self.save_music_xml_action: QAction
        self.export_audio_action: QAction
        self.export_all_action: QAction
        self.rescan_data_action: QAction
        self.open_settings_action: QAction
        self.open_logs_action: QAction
        self.undo_action: QAction
        self.redo_action: QAction
        self.toggle_warnings_action: QAction
        self.toggle_radar_action: QAction
        self.toggle_fps_action: QAction
        self.toggle_note_debug_action: QAction
        self.toggle_inspector_action: QAction
        self.toggle_editor_action: QAction
        self.toggle_export_btn_action: QAction
        self.mode_2d_action: QAction
        self.mode_3d_action: QAction
        self.status_progress_host: QWidget
        self.status_progress_layout: QHBoxLayout
        self.status_eta_label: QLabel
        self.status_progress: QProgressBar
        self.status_cancel_button: QPushButton

        self.playback = PlaybackController(self)
        self.file_handler = FileHandler(self)
        self.key_handler = KeyHandler(self)
        self.overlay_manager = OverlayManager(self)

        data_path = settings.data_root

        sounds_path = get_sounds_dir(data_path)
        self.playback_service = PlaybackCoordinator(
            self.playback, str(sounds_path / "tap.wav"), data_path, self
        )
        self.playback_service.set_hitsound_volume(settings.hitsound_volume)
        self.playback_service.set_music_volume(settings.music_volume)

        self.scanner = DataScanner(data_path)
        self.songs = self.scanner.scan()
        self.note_editor = NoteEditor(self)
        self.settings_handler = SettingsHandler(self)
        self.metadata_editor: MetadataEditor

        self._init_ui()
        self.settings_handler.apply()
        create_menu_bar(self)
        init_status_widgets(self)
        self._setup_connections()
        # Set pointing-hand cursor on all interactive widgets (Qt stylesheets don't support
        # "cursor" for all widget types, generating "Unknown property cursor" warnings).
        hand = Qt.CursorShape.PointingHandCursor
        for w in self.findChildren(QPushButton):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            w.setCursor(hand)
        for w in self.findChildren(QComboBox):
            w.setCursor(hand)
        for w in self.findChildren(QSlider):
            w.setCursor(hand)
        for w in self.findChildren(QSpinBox):
            w.setCursor(hand)
        self.menuBar().setCursor(hand)
        self._view_stack.setCurrentIndex(0)
        self._switch_view_mode(0)
        self.overlay_manager.reposition()

    def _open_config_dir(self) -> None:
        if not USER_CONFIG_DIR.exists():
            USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(USER_CONFIG_DIR)))

    def _change_data_root(self) -> None:
        path = self.file_handler.prompt_data_root()
        if path:
            self.scanner = DataScanner(path)
            self.songs = self.scanner.scan()
            self.playback_service.shutdown()
            sounds_path = get_sounds_dir(path)
            self.playback_service = PlaybackCoordinator(
                self.playback, str(sounds_path / "tap.wav"), path, self
            )
            self.playback_service.set_hitsound_volume(settings.hitsound_volume)
            self.playback_service.set_music_volume(settings.music_volume)
            self.visualizer.user_seeked.disconnect()
            self.visualizer.user_seeked.connect(self.playback_service.seek)
            self.play_view.user_seeked.disconnect()
            self.play_view.user_seeked.connect(self.playback_service.seek)
            self.picker.songs = self.songs
            self.picker._populate_all_lists()

    def new_chart(self) -> None:
        self.file_handler.new()

    def open_chart_dialog(self) -> None:
        self.file_handler.open_dialog()

    def save_chart(self) -> bool:
        return self.file_handler.save()

    def save_chart_as(self) -> bool:
        return self.file_handler.save_as()

    def save_chart_with_asset_source(self, source_chart_path: str | None) -> bool:
        if self.current_chart is None or not self.current_file_path:
            return False
        self.metadata_editor._apply_fields()
        try:
            save_chart_file(self.current_chart, self.current_file_path, source_chart_path)
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return False
        self._chart_dirty = False
        self.metadata_editor.sync_fields()
        self._sync_file_actions()
        self.statusBar().showMessage(f"Saved {Path(self.current_file_path).name}.", 3000)
        return True

    def save_music_xml(self) -> None:
        self.file_handler.save_music_xml()

    # ── UI Layout ──

    def _init_ui(self) -> None:  # noqa: PLR0915
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setHandleWidth(1)
        main_layout.addWidget(self.content_splitter, stretch=1)

        left_panel = QFrame()
        left_panel.setFixedWidth(360)
        left_panel.setObjectName("LeftPanel")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        self.picker = ChartPicker(self.songs)
        left_layout.addWidget(self.picker, stretch=1)

        self.info_panel = QWidget()
        self.info_panel.setFixedHeight(30)
        self.info_panel.setObjectName("InfoPanel")
        self.info_panel.setStyleSheet(f"background: {theme.SURFACE_NAV}; border: none;")
        info_layout = QHBoxLayout(self.info_panel)
        info_layout.setContentsMargins(15, 0, 15, 0)
        info_layout.setSpacing(20)

        self.status_bpm_label = make_status_label("BPM: ---", muted=False)
        self.status_bpm_label.setStyleSheet(f"color: {theme.WHITE};")
        info_layout.addWidget(self.status_bpm_label)
        left_layout.addWidget(self.info_panel)
        self.content_splitter.addWidget(left_panel)

        viewport_container = QFrame()
        viewport_container.setObjectName("ViewportPanel")
        viewport_layout = QVBoxLayout(viewport_container)
        viewport_layout.setContentsMargins(0, 0, 0, 0)
        viewport_layout.setSpacing(0)
        self._view_stack = QStackedWidget()
        self.visualizer = ChartViewport(viewport_container, self.playback)
        self.visualizer.setObjectName("TimelineViewport")
        self._view_stack.addWidget(self.visualizer)
        self.play_view = PlayView3D(viewport_container, self.playback)
        self.play_view.setObjectName("GamePlayView")
        self._view_stack.addWidget(self.play_view)
        self.timeline_widget = TimelineWidget(viewport_container)
        self.timeline_widget.seek_requested.connect(self.playback_service.seek)
        viewport_layout.addWidget(self.timeline_widget)
        viewport_layout.addWidget(self._view_stack, stretch=1)
        self.radar = NoteDensityRadar(self.visualizer)
        self.radar.setFixedSize(220, 220)
        self.radar.raise_()
        self.fps_overlay = FpsOverlay(self.visualizer)
        self.fps_overlay.raise_()
        self.content_splitter.addWidget(viewport_container)

        self.inspector_panel = QFrame()
        self.inspector_panel.setMinimumWidth(480)
        self.inspector_panel.setObjectName("InspectorPanel")
        inspector_layout = QVBoxLayout(self.inspector_panel)
        inspector_layout.setContentsMargins(12, 12, 12, 12)
        inspector_layout.setSpacing(10)

        self.warning_section = QFrame()
        wl = QVBoxLayout(self.warning_section)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(10)
        self.warning_label = make_section_label("WARNINGS", warning=True)
        wl.addWidget(self.warning_label)
        self.warning_list = QListWidget()
        self.warning_list.setObjectName("WarningList")
        self.warning_list.itemClicked.connect(self._on_warning_clicked)
        wl.addWidget(self.warning_list, stretch=1)
        inspector_layout.addWidget(self.warning_section, stretch=1)

        self.note_section = QFrame()
        self.note_section.setObjectName("NoteSection")
        nl = QVBoxLayout(self.note_section)
        nl.setContentsMargins(0, 4, 0, 0)
        nl.setSpacing(8)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.inspector_label = make_section_label("NOTE INSPECTOR")
        self.inspector_label.setMinimumWidth(self.inspector_label.sizeHint().width())
        header_row.addWidget(self.inspector_label)
        header_row.addStretch()
        self.group_btn = QPushButton("Grouped")
        self.group_btn.setFixedHeight(24)
        self.group_btn.setFixedWidth(78)
        self.group_btn.setToolTip("Group notes by type")
        self.group_btn.setCheckable(True)
        self.group_btn.setChecked(True)
        self.group_btn.clicked.connect(lambda: self._set_inspector_grouping(True))
        header_row.addWidget(self.group_btn)
        self.chrono_btn = QPushButton("Timeline")
        self.chrono_btn.setFixedHeight(24)
        self.chrono_btn.setFixedWidth(78)
        self.chrono_btn.setToolTip("Show notes as a timeline of colored blocks")
        self.chrono_btn.setCheckable(True)
        self.chrono_btn.clicked.connect(lambda: self._set_inspector_grouping(False))
        header_row.addWidget(self.chrono_btn)
        self.export_inspector_btn = QPushButton("Export MD")
        self.export_inspector_btn.setFixedHeight(24)
        self.export_inspector_btn.setFixedWidth(90)
        self.export_inspector_btn.setToolTip("Export inspector content as Markdown")
        self.export_inspector_btn.clicked.connect(self._export_inspector_markdown)
        header_row.addWidget(self.export_inspector_btn)
        nl.addLayout(header_row)
        self.note_inspector = make_inspector_text()
        nl.addWidget(self.note_inspector, stretch=1)
        inspector_layout.addWidget(self.note_section, stretch=1)

        self.metadata_editor = MetadataEditor(self)
        inspector_layout.addWidget(self.metadata_editor)
        self.content_splitter.addWidget(self.inspector_panel)

        # ── Timeline toolbar (Rust-style, between scrubber and viewport) ──
        self._build_timeline_toolbar(viewport_layout)

        self.content_splitter.setStretchFactor(0, 0)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setStretchFactor(2, 0)
        self.content_splitter.setSizes([360, 1160, 480])

    def _build_timeline_toolbar(self, parent_layout: QVBoxLayout) -> None:
        """Build Rust-style compact toolbar between scrubber and viewport."""
        bar = QFrame()
        bar.setFixedHeight(34)
        bar.setObjectName("TimelineToolbar")
        bar.setStyleSheet(
            f"background: {theme.SURFACE_NAV};"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        btn_style = (
            f"QPushButton {{ background: transparent; color: {theme.WHITE}; "
            f"border: none; border-radius: 4px; padding: 4px; "
            f"min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; }}"
            f"QPushButton:hover {{ background: {theme.SURFACE_LIST_HOVER}; }}"
        )

        try:
            import qtawesome as qta
            self._qta = qta
        except ImportError:
            self._qta = None

        # ── Return to start ──
        self.btn_reset_timeline = QPushButton()
        self.btn_reset_timeline.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_reset_timeline.setStyleSheet(btn_style)
        self.btn_reset_timeline.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_timeline.setToolTip("Return to start")
        if self._qta:
            self.btn_reset_timeline.setIcon(self._qta.icon("fa5s.undo", color=theme.WHITE))
            self.btn_reset_timeline.setIconSize(QSize(14, 14))
        else:
            self.btn_reset_timeline.setText("⟲")
        self.btn_reset_timeline.clicked.connect(self._reset_timeline)
        layout.addWidget(self.btn_reset_timeline, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── Play / Pause ──
        self.btn_play = QPushButton()
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.setStyleSheet(btn_style)
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.setToolTip("Play / Pause")
        if self._qta:
            self.btn_play.setIcon(self._qta.icon("fa5s.play", color=theme.WHITE))
            self.btn_play.setIconSize(QSize(16, 16))
        else:
            self.btn_play.setText("▶")
        self.btn_play.clicked.connect(self.toggle_playback)
        layout.addWidget(self.btn_play)

        # Track last known play state so we only update the icon when it changes.
        self._last_play_state: bool | None = None

        layout.addSpacing(8)

        layout.addStretch()

        # ── Measure label ──
        measure_lbl = QLabel("Measure")
        measure_lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px; background: transparent;")
        measure_lbl.setFixedHeight(22)
        layout.addWidget(measure_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        self.measure_display = QLineEdit()
        self.measure_display.setReadOnly(True)
        self.measure_display.setFrame(False)
        self.measure_display.setFixedWidth(52)
        self.measure_display.setFixedHeight(22)
        self.measure_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.measure_display.setStyleSheet(
            f"QLineEdit {{ background: {theme.SURFACE_ELEVATED}; color: {theme.WHITE}; "
            f"border: none; border-radius: 4px; "
            f"font-size: 12px; font-family: monospace; padding: 0 4px; }}"
        )
        self.measure_display.setText("001")
        self.measure_display.mouseDoubleClickEvent = lambda e: self._start_measure_edit()
        layout.addWidget(self.measure_display, 0, Qt.AlignmentFlag.AlignVCenter)

        self.measure_edit = QLineEdit()
        self.measure_edit.setFrame(False)
        self.measure_edit.setFixedWidth(52)
        self.measure_edit.setFixedHeight(22)
        self.measure_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.measure_edit.setStyleSheet(
            f"QLineEdit {{ background: {theme.SURFACE_ELEVATED}; color: {theme.WHITE}; "
            f"border: 1px solid {theme.ACCENT}; border-radius: 4px; "
            f"font-size: 12px; font-family: monospace; padding: 0 4px; }}"
        )
        self.measure_edit.hide()
        self.measure_edit.returnPressed.connect(self._commit_measure_edit)
        layout.addWidget(self.measure_edit)

        # ── Open chart location ──
        self.btn_open_location = QPushButton()
        self.btn_open_location.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_open_location.setStyleSheet(btn_style)
        self.btn_open_location.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_location.setToolTip("Open chart file location")
        if self._qta:
            self.btn_open_location.setIcon(self._qta.icon("fa5s.external-link-alt", color=theme.WHITE))
            self.btn_open_location.setIconSize(QSize(14, 14))
        else:
            self.btn_open_location.setText("\u2197")
        self.btn_open_location.clicked.connect(self._open_chart_location)
        layout.addWidget(self.btn_open_location)

        parent_layout.addWidget(bar)
        self._timeline_toolbar = bar

    def _start_measure_edit(self) -> None:
        self.measure_display.hide()
        self.measure_edit.setText(self.measure_display.text())
        self.measure_edit.show()
        self.measure_edit.setFocus()
        self.measure_edit.selectAll()

    def _open_chart_location(self) -> None:
        path = self.current_file_path
        if not path:
            self.statusBar().showMessage("No chart file is loaded.", 2000)
            return
        url = QUrl.fromLocalFile(str(Path(path).parent))
        QDesktopServices.openUrl(url)

    def _commit_measure_edit(self) -> None:
        try:
            target = float(self.measure_edit.text())
            if self.current_chart:
                self.playback_service.seek(target)
        except ValueError:
            pass
        self.measure_edit.hide()
        self.measure_display.show()

    def _reset_timeline(self) -> None:
        if self.current_chart:
            # Stop playback first so the button returns to the play state
            if self.playback.is_playing:
                self.playback_service.toggle_playback()
            self.playback_service.seek(0.0)
        self._sync_play_button()

    # ── View ──

    def _switch_view_mode(self, mode: int) -> None:
        self._view_stack.setCurrentIndex(mode)
        is_t = mode == 0
        self.timeline_widget.setVisible(is_t)
        self.radar.setVisible(is_t and settings.show_radar)
        self.radar.setParent(self.visualizer if is_t else self.play_view)
        self.fps_overlay.setParent(self.visualizer if is_t else self.play_view)
        if is_t:
            self.play_view.set_playback_active(False)
            self.visualizer.set_playback_active(self.playback.is_playing)
        else:
            self.visualizer.set_playback_active(False)
            self.play_view.set_playback_active(self.playback.is_playing)
        if hasattr(self, "mode_2d_action"):
            self.mode_2d_action.setChecked(is_t)
        if hasattr(self, "mode_3d_action"):
            self.mode_3d_action.setChecked(not is_t)
        QTimer.singleShot(0, self.overlay_manager.reposition)

    # ── Connections ──

    def _setup_connections(self) -> None:
        self.picker.chart_selected.connect(self.load_chart_file)
        self.visualizer.frame_rendered.connect(self.fps_overlay.record_frame)
        self.visualizer.user_seeked.connect(self.playback_service.seek)
        self.visualizer.current_pos_changed.connect(self.timeline_widget.set_playhead_measure)
        self.play_view.user_seeked.connect(self.playback_service.seek)
        self.play_view.current_pos_changed.connect(self.timeline_widget.set_playhead_measure)
        self.visualizer.note_selected.connect(self._on_note_selected)
        self.visualizer.notes_selected.connect(self._on_notes_selected)
        self.visualizer.note_context_requested.connect(self.note_editor.show_note_context_menu)
        self.visualizer.note_place_requested.connect(self.note_editor.place_note_at)
        self.visualizer.note_size_drag_place_requested.connect(self.note_editor.place_note_at)
        self.visualizer.note_drag_place_requested.connect(self.note_editor.place_note_drag)
        self.visualizer.resized.connect(self.overlay_manager.reposition)
        self.playback.pos_changed.connect(self._on_playhead_moved)

    # ── Chart loading / display ──

    def load_chart_file(self, path: str) -> None:
        try:
            self.statusBar().showMessage("Loading chart...", 0)
            chart = load_chart_file(path)
            self.current_chart = chart
            self.current_file_path = path
            if settings.log_note_rendering:
                _setup_note_rendering_debug_log(
                    chart.metadata.title,
                    chart.metadata.music_id,
                    path,
                )
            self._chart_dirty = False
            self._chart_read_only = self._path_is_from_data_root(path)
            self.note_editor.clear_history()
            self.playback.set_chart(chart)
            self.playback_service.set_chart_audio(chart, path)
            self._sync_file_actions()
            self._display_chart(chart)
            self._update_chart_metadata(chart)
            self.metadata_editor.sync_fields()
            msg = (
                "Chart loaded."
                if self.playback_service.has_music_source
                else "Data-folder chart loaded read-only. No music source found."
                if self._chart_read_only
                else "Chart loaded. No music source found; set data directory or choose Audio."
            )
            self.statusBar().showMessage(msg, 5000)
            QTimer.singleShot(10, lambda: self._update_chart_warnings(chart))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            self.statusBar().showMessage(f"Error: {exc}", 5000)
            LOGGER.warning("Failed to load chart from %s: %s", path, exc)

    def _path_is_from_data_root(self, path: str | Path) -> bool:
        try:
            Path(path).resolve().relative_to(self.scanner.data_root.resolve())
        except ValueError:
            return False
        return True

    def _update_chart_warnings(self, chart: Chart) -> None:
        self.warning_list.clear()
        self._warning_note_map = {}
        warnings = chart.timeline.chart.warnings
        if not warnings:
            self.warning_section.hide()
            self.settings_handler.sync_inspector_visibility()
            return
        self.warning_section.show()
        for w in warnings:
            item = QListWidgetItem(w)
            self.warning_list.addItem(item)
            self._warning_note_map[w] = resolve_warning_note(chart, w)
        self.settings_handler.sync_inspector_visibility()

    def _update_chart_metadata(self, chart: Chart) -> None:
        self.update_metadata_display(
            {
                "bpm_def": chart.metadata.bpm_def,
                "creator": chart.metadata.creator,
                "version": chart.metadata.version,
            }
        )
        if not chart.metadata.bpm_def and chart.bpms:
            self._set_bpm_text(sorted({b["bpm"] for b in chart.bpms}))

    def _display_chart(self, chart: Chart) -> None:
        self.visualizer.draw_chart(chart)
        self.play_view.draw_chart(chart)
        self.timeline_widget.set_chart(chart)
        self._sync_timeline_extent(chart)
        self.visualizer.show_judgment = True
        self.visualizer.setFocus(Qt.FocusReason.OtherFocusReason)
        self.radar.update_chart(chart)
        self.note_inspector.setPlainText("Click a note to inspect it.")
        self.overlay_manager.reposition()
        self.visualizer.update()
        self.play_view.update()

    def _sync_timeline_extent(self, chart: Chart) -> None:
        total = None
        dur = self.playback.playback_end_seconds
        if dur > 0:
            total = max(
                float(chart.timeline.calculate_max_measure()),
                chart.timeline.pos_at_time(dur),
            )
        self.timeline_widget.set_total_measures(total)
        self.visualizer.set_total_measures(total)
        self.play_view.set_total_measures(total)

    # ── Info display ──

    def _on_playhead_moved(self, pos: float) -> None:
        self.visualizer.set_current_pos(pos)
        self.play_view.set_current_pos(pos)
        self.timeline_widget.set_playhead_measure(pos)
        # Update toolbar measure display
        if hasattr(self, "measure_display") and not self.measure_edit.isVisible():
            self.measure_display.setText(f"{int(pos):03d}")
        # Sync button icon when playback ends naturally (is_playing -> False)
        self._sync_play_button()


    def _on_note_selected(self, note: Note | None) -> None:
        if note is None:
            html = '<span style="color:#888;font-size:12px;">Click a note to inspect it.</span>'
            if self.current_chart:
                flat_total = 0
                counts: dict[str, int] = {}
                for n in self.current_chart.notes:
                    steps = getattr(n, "steps", None)
                    if steps is not None:
                        flat_total += len(steps)
                        for s in steps:
                            counts[s.note_type.value] = counts.get(s.note_type.value, 0) + 1
                    else:
                        flat_total += 1
                        counts[n.note_type.value] = counts.get(n.note_type.value, 0) + 1
                html += "<br><br>"
                html += (
                    f'<span style="color:#aaa;font-size:12px;">Total notes: '
                    f'<b style="color:#fff;">{flat_total}</b></span><br>'
                )
                for nt in sorted(counts):
                    html += (
                        f'<span style="color:#666;font-size:11px;">&nbsp;&nbsp;{nt}: '
                        f'{counts[nt]}</span><br>'
                    )
            self.note_inspector.setHtml(html)
            return
        self.note_inspector.setHtml(format_render_behavior(note, self.current_chart))
        if self._show_note_inspector or self._chart_read_only:
            self.settings_handler.toggle_inspector(True)

    def _on_notes_selected(self, notes: list[Note]) -> None:
        self._current_inspector_notes = notes
        if not notes:
            self._on_note_selected(None)
        elif len(notes) == 1:
            self._on_note_selected(notes[0])
        else:
            self._render_inspector_summary()
            if self._show_note_inspector or self._chart_read_only:
                self.settings_handler.toggle_inspector(True)

    def _set_inspector_grouping(self, grouped: bool) -> None:
        self._inspector_grouped = grouped
        self.group_btn.setChecked(grouped)
        self.chrono_btn.setChecked(not grouped)
        if len(self._current_inspector_notes) > 1:
            self._render_inspector_summary()

    def _render_inspector_summary(self) -> None:
        notes = self._current_inspector_notes
        if len(notes) <= 1:
            return
        self.note_inspector.setHtml(
            format_notes_summary(notes, self.current_chart, grouped=self._inspector_grouped)
        )

    def _export_inspector_markdown(self) -> None:
        text = self.note_inspector.toPlainText().strip()
        if not text:
            self.statusBar().showMessage("Nothing to export — inspector is empty.", 2000)
            return
        if self.current_chart:
            title = self.current_chart.metadata.title or "Untitled"
            diff = self.current_chart.metadata.difficulty or ""
            level = self.current_chart.metadata.level or ""
            chart_name = f"{title} — {diff} {level}".strip()
        else:
            chart_name = "Note Inspector Export"
        mode_tag = "grouped" if self._inspector_grouped else "timeline"
        default_name = (
            f"{Path(self.current_file_path).stem}_notes_{mode_tag}.md"
            if self.current_file_path
            else f"inspector_export_{mode_tag}.md"
        )
        md = f"# {chart_name}\n\n```\n{text}\n```\n"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Inspector as Markdown", default_name, "Markdown (*.md)"
        )
        if not path:
            return
        Path(path).write_text(md, encoding="utf-8")
        self.statusBar().showMessage(f"Exported inspector to {path}", 3000)

    def _on_warning_clicked(self, item: QListWidgetItem) -> None:
        note = self._warning_note_map.get(item.text())
        if note and self.current_chart:
            self.playback_service.seek(self.current_chart.timeline.note_abs_pos(note))
            self._on_note_selected(note)

    def _set_bpm_text(self, values: list[float] | None) -> None:
        if not values:
            self.status_bpm_label.setText("BPM: ---")
            return
        lo, hi = min(values), max(values)
        self.status_bpm_label.setText(f"BPM: {lo:g}" if lo == hi else f"BPM: {lo:g} - {hi:g}")

    def update_metadata_display(self, meta: MetadataPreview) -> None:
        bpm_def = meta.get("bpm_def")
        if bpm_def:
            try:
                self._set_bpm_text([float(x) for x in bpm_def[1:3]])
            except (ValueError, IndexError, TypeError):
                self._set_bpm_text(None)
        else:
            self._set_bpm_text(None)

    # ── Sync ──

    def _sync_file_actions(self) -> None:
        has = self.current_chart is not None
        can = has and not self._chart_read_only
        for attr in ("save_chart_action", "save_chart_as_action", "save_music_xml_action"):
            if hasattr(self, attr):
                getattr(self, attr).setEnabled(can)
        if hasattr(self, "export_audio_action"):
            self.export_audio_action.setEnabled(has and self._chart_read_only)
        export_chart = getattr(self, "export_chart_action", None)
        if export_chart is not None:
            export_chart.setEnabled(has)
        self.note_editor._sync_history_actions()
        if self.metadata_editor:
            self.metadata_editor._sync_editor_enabled()
        self._sync_place_mode()

        suffix = "*" if self._chart_dirty else ""
        path = self.current_file_path
        if path:
            self.setWindowTitle(f"Chunitools - {Path(path).name}{suffix}")
        elif has:
            self.setWindowTitle(f"Chunitools - Untitled{suffix}")
        else:
            self.setWindowTitle("Chunitools")

    def _sync_place_mode(self) -> None:
        if hasattr(self, "visualizer"):
            self.visualizer.set_editor_place_mode(
                not self._chart_read_only, self._editor_note_width, self._editor_note_type
            )

    # ── Metadata editor delegation ──

    def import_audio_dialog(self) -> None:
        if self.metadata_editor:
            self.metadata_editor._browse_path("audio_path")

    def create_option_folder_dialog(self) -> None:
        if self.metadata_editor:
            self.metadata_editor._create_option_folder()

    def convert_image_to_dds_dialog(self) -> None:
        if self.metadata_editor:
            self.metadata_editor.convert_image_to_dds()

    # ── Playback ──

    def _sync_play_button(self) -> None:
        """Update the play/pause button icon to match actual playback state."""
        is_p = self.playback.is_playing
        if is_p == self._last_play_state:
            return
        self._last_play_state = is_p
        if self._qta:
            icon_name = "fa5s.pause" if is_p else "fa5s.play"
            self.btn_play.setIcon(self._qta.icon(icon_name, color=theme.WHITE))
        else:
            self.btn_play.setText("⏸" if is_p else "▶")

    def toggle_playback(self) -> None:
        if not self.current_chart:
            return
        self.playback_service.toggle_playback()
        is_p = self.playback.is_playing
        self.visualizer.set_playback_active(is_p)
        self.play_view.set_playback_active(is_p)
        self._sync_play_button()

    # ── Events ──

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self.overlay_manager.reposition)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.file_handler.confirm_discard():
            event.ignore()
            return
        self.playback_service.shutdown()
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: ANN401
        if not self.key_handler.handle_key(event):
            super().keyPressEvent(event)

    # ── Settings delegates (connected via menus.py) ──

    def _sync_menu_states(self) -> None:
        self.settings_handler.sync_menu_states()

    def _sync_inspector_panel_visibility(self) -> None:
        self.settings_handler.sync_inspector_visibility()

    # ── Export delegates ──

    def export_current_chart_image(self) -> None:
        if self.current_chart:
            export_ops.export_current_chart_image(self)

    def export_all_charts(self) -> None:
        export_ops.export_all_charts(self)

    def export_current_audio(self) -> None:
        if self.current_chart and self._chart_read_only:
            export_ops.export_current_audio(self)

    def cancel_export_all(self) -> None:
        export_ops.cancel_export_all(self)

    def open_last_export_folder(self) -> None:
        export_ops.open_last_export_folder(self)

    def open_logs_folder(self) -> None:
        export_ops.open_logs_folder(self)

    def open_last_export_log(self) -> None:
        export_ops.open_last_export_log(self)
