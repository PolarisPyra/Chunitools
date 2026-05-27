from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QElapsedTimer, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeyEvent, QResizeEvent
from PySide6.QtWidgets import (
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
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.config import USER_CONFIG_DIR, get_sounds_dir, resolve_startup_data_root, settings
from src.const import NoteType
from src.core.read import DataScanner, MetadataPreview, load_chart_file
from src.core.write import save_chart_file
from src.engine.playback import PlaybackController

if TYPE_CHECKING:
    from src.model import Chart
    from src.notes import Note
from src.services.playback import PlaybackCoordinator
from src.ui import theme
from src.ui.components.fps_overlay import FpsOverlay
from src.ui.components.picker import ChartPicker
from src.ui.components.play_view import PlayView3D
from src.ui.components.radar import NoteDensityRadar
from src.ui.components.viewport import ChartViewport
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
from src.workspace.menubar import MenuCursorFilter, create_menu_bar
from src.ui.window.metadata_editor import MetadataEditor
from src.ui.window.overlay_manager import OverlayManager
from src.ui.window.settings_handler import SettingsHandler
from src.shell.status_bar import init_status_widgets
from src.ui.window.widgets import (
    make_command_button,
    make_inspector_text,
    make_section_label,
    make_status_label,
)

LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window for the Chunithm Chart Viewer."""

    def _open_settings_dialog(self) -> None:
        """Open the full settings preferences dialog."""
        from src.dialogs.settings import open_settings

        open_settings(self)

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
        self._last_status_measure_text = "MEASURE: 0.00"
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
        self.change_data_dir_action: QAction
        self.open_settings_action: QAction
        self.open_config_dir_action: QAction
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

        startup_data_root = resolve_startup_data_root(settings)
        data_path = startup_data_root.path
        if startup_data_root.should_prompt:
            prompted_path = self.file_handler.prompt_data_root()
            if prompted_path:
                data_path = prompted_path

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
        for w in self.findChildren(QPushButton):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        self.status_measure_label = make_status_label("MEASURE: 0.00")
        self.status_measure_label.setStyleSheet(f"color: {theme.WHITE}; font-weight: bold;")
        info_layout.addWidget(self.status_measure_label)
        info_layout.addStretch()
        self.status_bpm_label = make_status_label("BPM: ---", muted=False)
        self.status_bpm_label.setStyleSheet(f"color: {theme.WHITE};")
        info_layout.addWidget(self.status_bpm_label)
        left_layout.addWidget(self.info_panel)

        self.left_controls_panel = QFrame()
        self.left_controls_panel.setObjectName("LeftControlsPanel")
        self.left_controls_panel.setStyleSheet(f"background: {theme.SURFACE_NAV}; border: none;")
        left_controls_layout = QVBoxLayout(self.left_controls_panel)
        left_controls_layout.setContentsMargins(12, 8, 12, 8)
        left_controls_layout.setSpacing(8)

        slider_style = (
            "QSlider::groove:horizontal { height: 4px; "
            f"background: {theme.BASE_GRAY_900}; border-radius: 2px; }}"
            "QSlider::handle:horizontal { width: 10px; margin: -4px 0; "
            f"background: {theme.ACCENT}; border-radius: 5px; }}"
            f"QSlider::sub-page:horizontal {{ background: {theme.ACCENT_PROGRESS}; border-radius: 2px; }}"
        )
        volume_label_style = f"color: {theme.WHITE}; font-size: 10px;"

        hitsound_row = QHBoxLayout()
        hitsound_row.setSpacing(8)
        self.hitsound_volume_label = QLabel("Hit sound")
        self.hitsound_volume_label.setStyleSheet(volume_label_style)
        hitsound_row.addWidget(self.hitsound_volume_label)
        self.hitsound_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.hitsound_volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hitsound_volume_slider.setRange(0, 100)
        self.hitsound_volume_slider.setStyleSheet(slider_style)
        self.hitsound_volume_slider.setValue(round(settings.hitsound_volume * 100))
        self.hitsound_volume_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        hitsound_row.addWidget(self.hitsound_volume_slider)
        left_controls_layout.addLayout(hitsound_row)

        music_row = QHBoxLayout()
        music_row.setSpacing(8)
        self.music_volume_label = QLabel("Music")
        self.music_volume_label.setStyleSheet(volume_label_style)
        music_row.addWidget(self.music_volume_label)
        self.music_volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.music_volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.music_volume_slider.setRange(0, 100)
        self.music_volume_slider.setStyleSheet(slider_style)
        self.music_volume_slider.setValue(round(settings.music_volume * 100))
        self.music_volume_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        music_row.addWidget(self.music_volume_slider)
        left_controls_layout.addLayout(music_row)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        try:
            import qtawesome as qta  # noqa: PLC0415
        except ImportError:
            qta = None
        icon_button_style = (
            f"QPushButton {{ background: {theme.TRANSPARENT}; "
            f"color: {theme.WHITE}; "
            f"border: 1px solid {theme.BORDER_CONTROL}; border-radius: 4px; padding: 0px; "
            "min-width: 24px; max-width: 24px; "
            "min-height: 24px; max-height: 24px; }}"
            f"QPushButton:hover {{ background: {theme.SURFACE_STATUS_BUTTON_HOVER}; }}"
        )
        self.open_folder_btn = QPushButton()
        self.open_folder_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.open_folder_btn.setStyleSheet(icon_button_style)
        self.open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_folder_btn.setToolTip("Open export folder")
        if qta:
            self.open_folder_btn.setIcon(qta.icon("fa5s.folder", color=theme.WHITE))
            self.open_folder_btn.setIconSize(QSize(14, 14))
        self.open_folder_btn.setFixedSize(24, 24)
        self.open_folder_btn.clicked.connect(export_ops.open_last_export_folder)
        self.open_folder_btn.setVisible(settings.show_export_button)
        folder_row.addWidget(self.open_folder_btn)

        self.open_logs_btn = QPushButton()
        self.open_logs_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.open_logs_btn.setStyleSheet(icon_button_style)
        self.open_logs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_logs_btn.setToolTip("Open logs folder")
        if qta:
            self.open_logs_btn.setIcon(qta.icon("fa5s.folder-open", color=theme.WHITE))
            self.open_logs_btn.setIconSize(QSize(14, 14))
            self.open_logs_btn.setFixedSize(24, 24)
        else:
            self.open_logs_btn.setText("Logs")
            self.open_logs_btn.setFixedHeight(24)
            self.open_logs_btn.setMinimumWidth(48)
        self.open_logs_btn.clicked.connect(export_ops.open_logs_folder)
        self.open_logs_btn.setVisible(settings.show_export_button)
        folder_row.addWidget(self.open_logs_btn)
        folder_row.addStretch()
        left_controls_layout.addLayout(folder_row)

        left_layout.addWidget(self.left_controls_panel)
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
        self.chrono_btn = QPushButton("Chrono")
        self.chrono_btn.setFixedHeight(24)
        self.chrono_btn.setFixedWidth(78)
        self.chrono_btn.setToolTip("Sort notes chronologically")
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

        self.bottom_bar = QFrame()
        self.bottom_bar.setFixedHeight(36)
        self.bottom_bar.setObjectName("BottomControlBar")
        self.bottom_layout = QHBoxLayout(self.bottom_bar)
        self.bottom_layout.setContentsMargins(12, 0, 12, 0)
        self.bottom_layout.setSpacing(12)

        self.btn_play = make_command_button("PLAY", width=100)
        self.btn_play.setObjectName("CommandButton")
        self.btn_play.setFixedHeight(22)
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.clicked.connect(self.toggle_playback)
        self.bottom_layout.addWidget(self.btn_play, 0, Qt.AlignmentFlag.AlignVCenter)
        self.bottom_layout.addStretch()
        self.jump_input = QLineEdit()
        self.jump_input.setPlaceholderText("Measure...")
        self.jump_input.setFixedWidth(100)
        self.jump_input.setFixedHeight(22)
        self.jump_input.returnPressed.connect(self._jump_to_position)
        self.bottom_layout.addWidget(self.jump_input, 0, Qt.AlignmentFlag.AlignVCenter)
        self.btn_jump = make_command_button("JUMP", width=64)
        self.btn_jump.setObjectName("CommandButton")
        self.btn_jump.setFixedHeight(22)
        self.btn_jump.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_jump.clicked.connect(self._jump_to_position)
        self.bottom_layout.addWidget(self.btn_jump, 0, Qt.AlignmentFlag.AlignVCenter)
        main_layout.addWidget(self.bottom_bar)
        self.content_splitter.setStretchFactor(0, 0)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setStretchFactor(2, 0)
        self.content_splitter.setSizes([360, 1160, 480])

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
        self.hitsound_volume_slider.valueChanged.connect(self.settings_handler.on_hitsound_volume)
        self.music_volume_slider.valueChanged.connect(self.settings_handler.on_music_volume)
        self.playback.pos_changed.connect(self._on_playhead_moved)

    # ── Chart loading / display ──

    def load_chart_file(self, path: str) -> None:
        try:
            self.statusBar().showMessage("Loading chart...", 0)
            chart = load_chart_file(path)
            self.current_chart = chart
            self.current_file_path = path
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
        if not hasattr(self, "_label_update_timer"):
            self._label_update_timer = QElapsedTimer()
            self._label_update_timer.start()
        if self._label_update_timer.elapsed() > 100:
            text = f"MEASURE: {pos:.2f}"
            if text != self._last_status_measure_text:
                self._last_status_measure_text = text
                self.status_measure_label.setText(text)
            self._label_update_timer.restart()

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
        mode_tag = "grouped" if self._inspector_grouped else "chrono"
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

    def toggle_playback(self) -> None:
        if not self.current_chart:
            return
        self.playback_service.toggle_playback()
        is_p = self.playback.is_playing
        self.visualizer.set_playback_active(is_p)
        self.play_view.set_playback_active(is_p)
        self.btn_play.setText("PAUSE" if is_p else "PLAY CHART")

    def _jump_to_position(self) -> None:
        if self.current_chart:
              with contextlib.suppress(ValueError):
                  self.playback_service.seek(float(self.jump_input.text()))

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
