from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QMenu, QMenuBar

from src.core.config import settings
from src.core.const import NoteType
from src.ui.theme.notes import get_note_color

if TYPE_CHECKING:
    from src.ui.window.window import MainWindow


class MenuCursorFilter(QObject):
    """Event filter that provides a pointer cursor for menu items and menu bar titles."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override.
        if isinstance(watched, (QMenu, QMenuBar)) and event.type() == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
                action = watched.actionAt(event.pos())
                if action and not action.isSeparator() and action.isEnabled():
                    if watched.cursor().shape() != Qt.CursorShape.PointingHandCursor:
                        watched.setCursor(Qt.CursorShape.PointingHandCursor)
                elif watched.cursor().shape() != Qt.CursorShape.ArrowCursor:
                    watched.setCursor(Qt.CursorShape.ArrowCursor)
        return super().eventFilter(watched, event)


def _make_note_tool_icon(note_type: NoteType, size: int = 24) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    try:
        color = get_note_color(note_type)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)

        if note_type in {NoteType.ADW, NoteType.ADL, NoteType.ADR}:
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(2, 6),
                        QPointF(size - 2, 6),
                        QPointF(size / 2, 14),
                    ]
                )
            )
        else:
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 220))
            painter.drawRoundedRect(3, 6, size - 6, size - 12, 3, 3)
    finally:
        painter.end()

    return QIcon(pixmap)


def create_menu_bar(window: MainWindow) -> None:  # noqa: PLR0915
    # 1. The actual menu bar
    menu_bar = QMenuBar(window)
    menu_bar.setNativeMenuBar(False)
    menu_bar.setMouseTracking(True)
    window.setMenuBar(menu_bar)

    # Helper filter for cursor behavior
    window._menu_cursor_filter = MenuCursorFilter(window)
    menu_bar.installEventFilter(window._menu_cursor_filter)

    file_menu = menu_bar.addMenu("File")
    edit_menu = menu_bar.addMenu("Edit")
    view_menu = menu_bar.addMenu("View")
    mode_menu = menu_bar.addMenu("Mode")
    notes_menu = menu_bar.addMenu("Note Visibility")

    for m in [file_menu, edit_menu, view_menu, mode_menu, notes_menu]:
        m.setMouseTracking(True)
        m.installEventFilter(window._menu_cursor_filter)

    # --- File Menu ---
    window.new_chart_action = QAction("New File", window)
    window.new_chart_action.setShortcut("Ctrl+N")
    window.new_chart_action.triggered.connect(window.new_chart)
    file_menu.addAction(window.new_chart_action)

    window.open_chart_action = QAction("Open .c2s...", window)
    window.open_chart_action.setShortcut("Ctrl+O")
    window.open_chart_action.triggered.connect(window.open_chart_dialog)
    file_menu.addAction(window.open_chart_action)

    window.import_audio_action = QAction("Import Audio...", window)
    window.import_audio_action.triggered.connect(window.import_audio_dialog)
    file_menu.addAction(window.import_audio_action)

    file_menu.addSeparator()

    window.save_chart_action = QAction("Save", window)
    window.save_chart_action.setShortcut("Ctrl+S")
    window.save_chart_action.setEnabled(False)
    window.save_chart_action.triggered.connect(window.save_chart)
    file_menu.addAction(window.save_chart_action)

    window.save_chart_as_action = QAction("Save As...", window)
    window.save_chart_as_action.setShortcut("Ctrl+Shift+S")
    window.save_chart_as_action.setEnabled(False)
    window.save_chart_as_action.triggered.connect(window.save_chart_as)
    file_menu.addAction(window.save_chart_as_action)

    window.save_music_xml_action = QAction("Save Music.xml", window)
    window.save_music_xml_action.setEnabled(False)
    window.save_music_xml_action.triggered.connect(window.save_music_xml)
    file_menu.addAction(window.save_music_xml_action)

    file_menu.addSeparator()

    export_menu = file_menu.addMenu("Export")
    export_menu.setMouseTracking(True)
    export_menu.installEventFilter(window._menu_cursor_filter)

    window.export_audio_action = QAction("Audio (WAV)", window)
    window.export_audio_action.setEnabled(False)
    window.export_audio_action.triggered.connect(window.export_current_audio)
    export_menu.addAction(window.export_audio_action)

    window.export_all_action = QAction("All Charts", window)
    window.export_all_action.triggered.connect(window.export_all_charts)
    export_menu.addAction(window.export_all_action)

    settings_menu = file_menu.addMenu("Settings")
    settings_menu.setMouseTracking(True)
    settings_menu.installEventFilter(window._menu_cursor_filter)

    window.change_data_dir_action = QAction("Set Data Directory...", window)
    window.change_data_dir_action.triggered.connect(window._change_data_root)
    settings_menu.addAction(window.change_data_dir_action)

    window.open_config_dir_action = QAction("Open Config Directory", window)
    window.open_config_dir_action.triggered.connect(window._open_config_dir)
    settings_menu.addAction(window.open_config_dir_action)

    file_menu.addSeparator()

    close_action = QAction("Quit", window)
    close_action.setShortcut("Ctrl+Q")
    close_action.triggered.connect(window.close)
    file_menu.addAction(close_action)

    # --- Edit Menu ---
    window.undo_action = QAction("Undo Note Placement", window)
    window.undo_action.setShortcuts([QKeySequence("Ctrl+Z")])
    window.undo_action.setEnabled(False)
    window.undo_action.triggered.connect(window.note_editor.undo)
    edit_menu.addAction(window.undo_action)

    window.redo_action = QAction("Redo Note Placement", window)
    window.redo_action.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
    window.redo_action.setEnabled(False)
    window.redo_action.triggered.connect(window.note_editor.redo)
    edit_menu.addAction(window.redo_action)

    # --- View Menu ---
    window.toggle_warnings_action = QAction("Show Warnings", window, checkable=True)
    window.toggle_warnings_action.setChecked(settings.show_warnings)
    window.toggle_warnings_action.triggered.connect(window.settings_handler.toggle_warnings)
    view_menu.addAction(window.toggle_warnings_action)

    window.toggle_radar_action = QAction("Show Note Radar", window, checkable=True)
    window.toggle_radar_action.setChecked(settings.show_radar)
    window.toggle_radar_action.triggered.connect(window.settings_handler.toggle_radar)
    view_menu.addAction(window.toggle_radar_action)

    window.toggle_fps_action = QAction("Show FPS Overlay", window, checkable=True)
    window.toggle_fps_action.setChecked(settings.show_fps)
    window.toggle_fps_action.triggered.connect(window.settings_handler.toggle_fps)
    view_menu.addAction(window.toggle_fps_action)

    window.toggle_note_debug_action = QAction("Show Note Debug Overlay", window, checkable=True)
    window.toggle_note_debug_action.setChecked(settings.show_note_debug_overlay)
    window.toggle_note_debug_action.triggered.connect(window.settings_handler.toggle_note_debug_overlay)
    view_menu.addAction(window.toggle_note_debug_action)

    view_menu.addSeparator()

    window.toggle_inspector_action = QAction("Show Note Inspector", window, checkable=True)
    window.toggle_inspector_action.setChecked(settings.show_inspector)
    window.toggle_inspector_action.triggered.connect(window.settings_handler.toggle_inspector)
    view_menu.addAction(window.toggle_inspector_action)

    window.toggle_editor_action = QAction("Show Option Editor", window, checkable=True)
    window.toggle_editor_action.setChecked(False)
    window.toggle_editor_action.triggered.connect(window.settings_handler.toggle_editor_panel)
    view_menu.addAction(window.toggle_editor_action)

    window.toggle_export_btn_action = QAction("Show Export Button", window, checkable=True)
    window.toggle_export_btn_action.setChecked(settings.show_export_button)
    window.toggle_export_btn_action.triggered.connect(window.settings_handler.toggle_export_button)
    view_menu.addAction(window.toggle_export_btn_action)

    reset_zoom_action = QAction("Reset Zoom", window)
    reset_zoom_action.triggered.connect(window.settings_handler.reset_zoom)
    view_menu.addAction(reset_zoom_action)

    # --- Mode Menu ---
    window.mode_2d_action = QAction("2D (Timeline)", window, checkable=True)
    window.mode_2d_action.setChecked(True)
    window.mode_2d_action.setShortcut("Ctrl+1")
    window.mode_2d_action.triggered.connect(lambda: window._switch_view_mode(0))
    mode_menu.addAction(window.mode_2d_action)

    window.mode_3d_action = QAction("3D (Game)", window, checkable=True)
    window.mode_3d_action.setShortcut("Ctrl+2")
    window.mode_3d_action.triggered.connect(lambda: window._switch_view_mode(1))
    mode_menu.addAction(window.mode_3d_action)

    mode_group = QActionGroup(window)
    mode_group.setExclusive(True)
    mode_group.addAction(window.mode_2d_action)
    mode_group.addAction(window.mode_3d_action)

    # --- Note Visibility Menu (Categorized) ---
    categories = {
        "Ground Notes": {
            NoteType.TAP: "Tap",
            NoteType.CHR: "Ex-Tap",
            NoteType.FLK: "Flick",
            NoteType.MNE: "Mine",
        },
        "Hold Notes": {
            NoteType.HLD: "Hold",
            NoteType.HXD: "Ex-Hold",
        },
        "Slide Notes": {
            NoteType.SLD: "Slide",
            NoteType.SLC: "Slide Control",
            NoteType.SXD: "Ex-Slide",
            NoteType.SXC: "Ex-Slide Control",
        },
        "Air Arrows": {
            NoteType.AIR: "Air",
            NoteType.AUR: "Air Up-Right",
            NoteType.AUL: "Air Up-Left",
            NoteType.ADW: "Air Down",
            NoteType.ADR: "Air Down-Right",
            NoteType.ADL: "Air Down-Left",
        },
        "Air Holds": {
            NoteType.AHD: "Air Hold",
            NoteType.AHX: "Air Hold Action",
        },
        "Air Slides": {
            NoteType.ASD: "Air Slide",
            NoteType.ASC: "Air Slide Control",
        },
        "Air Trace": {
            NoteType.ALD: "Air Trace and Action",
            NoteType.ASO: "Air Solid",
        },
        "Effects": {
            NoteType.HHD: "Heaven Hold",
            NoteType.HHX: "Heaven ExHold",
        },
    }

    for cat_name, notes in categories.items():
        cat_menu = notes_menu.addMenu(cat_name)
        for nt_enum, label in notes.items():
            nt_value = nt_enum.value
            visible = settings.visible_note_types.get(nt_value, True)

            action = QAction(f"Show {label}", window, checkable=True)
            action.setChecked(visible)
            action.triggered.connect(
                lambda checked, val=nt_value: window.settings_handler.toggle_note_visibility(val, checked)
            )
            cat_menu.addAction(action)

        cat_menu.setMouseTracking(True)
        cat_menu.installEventFilter(window._menu_cursor_filter)
