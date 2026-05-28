"""Settings dialog — Qt-based modal window for application preferences.

Uses the same theme tokens as the rest of the application for consistent styling.
"""

from __future__ import annotations

import logging
from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.config import settings as global_settings
from src.dialogs.settings.shared import find_file_named, is_valid_directory, setting_path_display
from src.ui.theme.ui import (
    APP_BACKGROUND,
    BORDER_CONTROL,
    BORDER_PANEL,
    SURFACE_LIST_HOVER,
    SURFACE_LIST_SELECTED,
    SURFACE_NAV,
    TEXT_DIM,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SOFT,
    TRANSPARENT,
)
from src.utils.audio import VgmstreamValidation, validate_vgmstream_path

LOGGER = logging.getLogger(__name__)

_DATA_EXECUTABLE_NAMES: tuple[str, ...] = ("chusanApp", "chusanApp.exe")


def open_settings(parent: QWidget | None = None) -> SettingsDialog:
    """Open the settings dialog as a modal window."""
    dialog = SettingsDialog(parent)
    dialog.exec()
    return dialog


class SettingsDialog(QDialog):
    """Application settings dialog with tabbed layout."""

    settings_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chunitools — Settings")
        self.setMinimumSize(840, 560)
        self.resize(960, 640)
        self.setModal(True)

        self._settings = global_settings
        self._data_valid: bool = False
        self._vgmstream_validation: str = VgmstreamValidation.NOT_FOUND
        self._vgmstream_detail: str = ""

        self._build_ui()
        self._refresh_validation()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(
            f"background: {SURFACE_NAV}; border-right: 1px solid {BORDER_PANEL};"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 8, 0, 0)

        self._nav_list = QListWidget()
        self._nav_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self._nav_list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; color: {TEXT_MUTED}; font-size: 13px; }}"
            f"QListWidget::item {{ padding: 10px 20px; }}"
            f"QListWidget::item:selected {{ background: {SURFACE_LIST_SELECTED}; color: {TEXT_PRIMARY}; }}"
            f"QListWidget::item:hover {{ background: {SURFACE_LIST_HOVER}; color: {TEXT_SOFT}; }}"
        )
        self._nav_list.addItem("General")
        self._nav_list.addItem("Audio")
        self._nav_list.addItem("Appearance")
        self._nav_list.setCurrentRow(0)
        self._nav_list.currentRowChanged.connect(self._on_tab_changed)
        sidebar_layout.addWidget(self._nav_list)
        layout.addWidget(sidebar)

        right = QWidget()
        right.setStyleSheet(f"background: {APP_BACKGROUND};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(32, 20, 32, 20)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._stack.addWidget(self._build_general_page())
        self._stack.addWidget(self._build_audio_page())
        self._stack.addWidget(self._build_appearance_page())
        right_layout.addWidget(self._stack, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        right_layout.addLayout(btn_layout)

        layout.addWidget(right)

    # ── General page ─────────────────────────────────────────────────────

    def _build_general_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)

        title = QLabel("General")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        desc = QLabel("Application-wide preferences.")
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(desc)

        layout.addWidget(self._build_path_row(
            "Data Directory",
            "CHUNITHM data files used by the browser and editor.",
            "data_root",
        ))

        layout.addWidget(self._build_path_row(
            "vgmstream-cli Directory",
            "Directory containing vgmstream-cli for audio decoding.",
            "vgstreamcli_path",
        ))

        layout.addWidget(self._build_panel_widths())
        layout.addWidget(self._build_scroll_speed())

        layout.addStretch()
        return page

    def _build_path_row(self, title: str, description: str, field_name: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(16)

        label_col = QVBoxLayout()
        label_col.setSpacing(2)
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color: {TEXT_SOFT}; font-size: 13px; font-weight: 500;")
        label_col.addWidget(lbl)
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        desc_lbl.setWordWrap(True)
        label_col.addWidget(desc_lbl)

        valid_lbl = QLabel("")
        valid_lbl.setStyleSheet("color: #32d74b; font-size: 11px;")
        valid_lbl.hide()
        label_col.addWidget(valid_lbl)
        self.__dict__[f"{field_name}_valid_lbl"] = valid_lbl

        row_layout.addLayout(label_col, 1)

        path_display = QLineEdit()
        path_display.setReadOnly(True)
        path_display.setCursor(Qt.CursorShape.IBeamCursor)
        path_display.setMinimumWidth(320)
        path_display.setPlaceholderText("Not set")
        raw = getattr(self._settings, field_name, "")
        path_display.setText(setting_path_display(str(raw)))
        self.__dict__[f"{field_name}_display"] = path_display
        row_layout.addWidget(path_display)

        choose_btn = QPushButton("Choose…")
        choose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        choose_btn.clicked.connect(partial(self._pick_folder, field_name))
        row_layout.addSpacing(8)
        row_layout.addWidget(choose_btn)

        return row

    def _build_panel_widths(self) -> QWidget:
        group = QGroupBox("Panel Widths")
        group.setStyleSheet(
            f"QGroupBox {{ color: {TEXT_MUTED}; font-size: 12px; border: 1px solid {BORDER_CONTROL}; "
            f"border-radius: 6px; margin-top: 8px; padding-top: 16px; background: {TRANSPARENT}; }}"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        for side, attr in [("Left", "left_panel_min_width"), ("Right", "right_panel_min_width")]:
            row = QHBoxLayout()
            lbl = QLabel(f"{side} Panel Min Width:")
            lbl.setStyleSheet(f"color: {TEXT_SOFT}; font-size: 12px;")
            row.addWidget(lbl)
            spin = QSpinBox()
            spin.setCursor(Qt.CursorShape.PointingHandCursor)
            spin.setRange(0, 1200)
            spin.setValue(getattr(self._settings, attr, 350))
            spin.setSuffix(" px")
            spin.valueChanged.connect(partial(self._update_spin, attr))
            row.addWidget(spin)
            row.addStretch()
            layout.addLayout(row)

        return group

    def _update_spin(self, attr: str, value: int) -> None:
        self._update_setting(attr, value)

    def _build_scroll_speed(self) -> QWidget:
        group = QGroupBox("Scroll Speed")
        group.setStyleSheet(
            f"QGroupBox {{ color: {TEXT_MUTED}; font-size: 12px; border: 1px solid {BORDER_CONTROL}; "
            f"border-radius: 6px; margin-top: 8px; padding-top: 16px; background: {TRANSPARENT}; }}"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        layout = QHBoxLayout(group)

        lbl = QLabel("Default Scroll Speed:")
        lbl.setStyleSheet(f"color: {TEXT_SOFT}; font-size: 12px;")
        layout.addWidget(lbl)

        self._scroll_slider = QSlider(Qt.Orientation.Horizontal)
        self._scroll_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scroll_slider.setRange(10, 300)
        self._scroll_slider.setValue(int(self._settings.scroll_speed * 10))
        self._scroll_slider.valueChanged.connect(self._on_scroll_speed_changed)
        layout.addWidget(self._scroll_slider, 1)

        self._scroll_label = QLabel(f"{self._settings.scroll_speed:.1f}")
        self._scroll_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; min-width: 36px;")
        layout.addWidget(self._scroll_label)

        return group

    # ── Audio page ───────────────────────────────────────────────────────

    def _build_audio_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)

        title = QLabel("Audio")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        desc = QLabel("Volume preferences for playback.")
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(desc)

        layout.addWidget(self._build_volume_slider(
            "Hitsound Volume", "hitsound_volume",
        ))
        layout.addWidget(self._build_volume_slider(
            "Music Volume", "music_volume",
        ))

        layout.addStretch()
        return page

    def _build_volume_slider(self, title: str, field_name: str) -> QWidget:
        group = QGroupBox(title)
        group.setStyleSheet(
            f"QGroupBox {{ color: {TEXT_MUTED}; font-size: 12px; border: 1px solid {BORDER_CONTROL}; "
            f"border-radius: 6px; margin-top: 8px; padding-top: 16px; background: {TRANSPARENT}; }}"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        glayout = QHBoxLayout(group)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setCursor(Qt.CursorShape.PointingHandCursor)
        slider.setRange(0, 100)
        current_val = getattr(self._settings, field_name, 0.75)
        slider.setValue(round(current_val * 100))
        self.__dict__[f"_{field_name}_slider"] = slider
        glayout.addWidget(slider, 1)

        label = QLabel(f"{int(current_val * 100)}%")
        label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; min-width: 40px;")
        self.__dict__[f"_{field_name}_label"] = label
        glayout.addWidget(label)

        slider.valueChanged.connect(partial(self._on_volume_changed, field_name, label))
        return group

    def _on_volume_changed(self, field_name: str, label: QLabel, value: int) -> None:
        volume = value / 100.0
        label.setText(f"{value}%")
        self._update_setting(field_name, volume)

    # ── Appearance page ───────────────────────────────────────────────────

    def _build_appearance_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(20)

        title = QLabel("Appearance")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        desc = QLabel("Visual preferences for the application.")
        desc.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(desc)

        theme_group = QGroupBox("Theme")
        theme_group.setStyleSheet(
            f"QGroupBox {{ color: {TEXT_MUTED}; font-size: 12px; border: 1px solid {BORDER_CONTROL}; "
            f"border-radius: 6px; margin-top: 8px; padding-top: 16px; background: {TRANSPARENT}; }}"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        theme_layout = QHBoxLayout(theme_group)

        theme_lbl = QLabel("Application Theme:")
        theme_lbl.setStyleSheet(f"color: {TEXT_SOFT}; font-size: 12px;")
        theme_layout.addWidget(theme_lbl)

        self._theme_combo = QComboBox()
        self._theme_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_combo.addItems(["Dark", "Light"])
        self._theme_combo.setCurrentText("Dark")
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        theme_layout.addWidget(self._theme_combo)
        theme_layout.addStretch()
        layout.addWidget(theme_group)

        layout.addStretch()
        return page

    # ── Actions ───────────────────────────────────────────────────────────

    def _pick_folder(self, field_name: str) -> None:
        current = str(getattr(self._settings, field_name, ""))
        start_dir = current if is_valid_directory(current) else ""
        path = QFileDialog.getExistingDirectory(self, "Choose Directory", start_dir)
        if not path:
            return
        self._update_setting(field_name, path)
        display = self.__dict__.get(f"{field_name}_display")
        if display is not None:
            display.setText(path)
        self._refresh_validation()

    def _update_setting(self, name: str, value: object) -> None:
        setattr(self._settings, name, value)
        self._settings.save()
        self.settings_changed.emit()

    def _refresh_validation(self) -> None:
        data_path = str(getattr(self._settings, "data_root", ""))
        self._data_valid = is_valid_directory(data_path)
        data_exe = find_file_named(data_path, _DATA_EXECUTABLE_NAMES) if self._data_valid else None

        data_valid_lbl = self.__dict__.get("data_root_valid_lbl")
        if data_valid_lbl is not None:
            if data_exe:
                data_valid_lbl.setText(f"✓ Found: {data_exe}")
                data_valid_lbl.setStyleSheet("color: #32d74b; font-size: 11px;")
                data_valid_lbl.show()
            else:
                data_valid_lbl.hide()

        vg_path = str(getattr(self._settings, "vgstreamcli_path", ""))
        result = validate_vgmstream_path(vg_path)
        self._vgmstream_validation = result.status
        self._vgmstream_detail = result.detail

        vg_valid_lbl = self.__dict__.get("vgstreamcli_path_valid_lbl")
        if vg_valid_lbl is not None:
            if result.status == VgmstreamValidation.READY:
                vg_valid_lbl.setText(f"✓ {result.detail}")
                vg_valid_lbl.setStyleSheet("color: #32d74b; font-size: 11px;")
                vg_valid_lbl.show()
            elif result.status == VgmstreamValidation.LIBRARY_ONLY:
                vg_valid_lbl.setText(f"⚠ {result.detail}")
                vg_valid_lbl.setStyleSheet("color: #f0a030; font-size: 11px;")
                vg_valid_lbl.show()
            else:
                vg_valid_lbl.hide()

    def _on_tab_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    def _on_theme_changed(self, text: str) -> None:
        LOGGER.info("Theme changed to: %s", text)

    def _on_scroll_speed_changed(self, value: int) -> None:
        speed = value / 10.0
        self._scroll_label.setText(f"{speed:.1f}")
        self._update_setting("scroll_speed", speed)
