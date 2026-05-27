"""Settings dialog — Qt-based modal window for application preferences.

Mirrors the Rust ``dialogs/settings/content.rs`` layout: tabbed interface
with General and Appearance pages, data directory and vgmstream-cli path
pickers with live validation, panel width adjusters, and theme selection.
"""

from __future__ import annotations

import logging

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
from src.dialogs.settings.shared import (
    find_file_named,
    is_valid_directory,
    setting_path_display,
)
from src.utils.audio import VgmstreamValidation, validate_vgmstream_path

LOGGER = logging.getLogger(__name__)

# Linux: look for chusanApp in the data directory
_DATA_EXECUTABLE_NAMES: tuple[str, ...] = ("chusanApp",)


def open_settings(parent: QWidget | None = None) -> SettingsDialog:
    """Open the settings dialog as a modal window."""
    dialog = SettingsDialog(parent)
    dialog.exec()
    return dialog


class SettingsDialog(QDialog):
    """Application settings dialog with tabbed layout.

    Tabs:
      - General: data paths, vgmstream CLI, panel widths
      - Appearance: theme selection
    """

    settings_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chunitools — Settings")
        self.setMinimumSize(720, 480)
        self.resize(880, 560)
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

        # Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(
            "background: #1a1a2e; border-right: 1px solid #2a2a4a;"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        self._nav_list = QListWidget()
        self._nav_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; color: #888; font-size: 13px; }"
            "QListWidget::item { padding: 10px 16px; }"
            "QListWidget::item:selected { background: #2a2a4a; color: #e0e0ff; }"
            "QListWidget::item:hover { background: #222240; color: #ccc; }"
        )
        self._nav_list.addItem("General")
        self._nav_list.addItem("Appearance")
        self._nav_list.setCurrentRow(0)
        self._nav_list.currentRowChanged.connect(self._on_tab_changed)
        sidebar_layout.addWidget(self._nav_list)

        layout.addWidget(sidebar)

        # Content area
        right = QWidget()
        right.setStyleSheet("background: #16162a;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 16, 24, 16)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        self._stack.addWidget(self._build_general_page())
        self._stack.addWidget(self._build_appearance_page())
        right_layout.addWidget(self._stack, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self._btn_style())
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        right_layout.addLayout(btn_layout)

        layout.addWidget(right)

    # ── General page ─────────────────────────────────────────────────────

    def _build_general_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        title = QLabel("General")
        title.setStyleSheet("color: #e0e0ff; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel("Application-wide preferences.")
        desc.setStyleSheet("color: #777; font-size: 12px;")
        layout.addWidget(desc)

        # Data Directory
        layout.addWidget(self._build_path_row(
            "Data Directory",
            "CHUNITHM data files used by the browser and editor.",
            "data_dir_path",
            "data_dir_choose",
        ))

        # vgmstream-cli Directory
        layout.addWidget(self._build_path_row(
            "vgmstream-cli Directory",
            "Directory containing vgmstream-cli for audio decoding.",
            "vgmstreamcli_path",
            "vgmstreamcli_choose",
        ))

        # Panel widths
        layout.addWidget(self._build_panel_widths())

        # Scroll speed
        layout.addWidget(self._build_scroll_speed())

        layout.addStretch()
        return page

    def _build_path_row(
        self,
        title: str,
        description: str,
        field_name: str,
        btn_name: str,
    ) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        # Label side
        label_col = QVBoxLayout()
        label_col.setSpacing(2)
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #ccc; font-size: 13px; font-weight: 500;")
        label_col.addWidget(lbl)
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("color: #666; font-size: 11px;")
        desc_lbl.setWordWrap(True)
        label_col.addWidget(desc_lbl)

        # Validation label (hidden by default, shown on validation)
        self.__dict__[f"{field_name}_valid_lbl"] = valid_lbl = QLabel("")
        valid_lbl.setStyleSheet("color: #4f4; font-size: 11px;")
        valid_lbl.hide()
        label_col.addWidget(valid_lbl)

        row_layout.addLayout(label_col, 1)

        # Path display + button
        path_display = QLineEdit()
        path_display.setReadOnly(True)
        path_display.setStyleSheet(
            "QLineEdit { background: #1e1e3a; border: 1px solid #333; border-radius: 4px; "
            "color: #aaa; padding: 4px 8px; font-size: 12px; }"
        )
        path_display.setMinimumWidth(280)
        path_display.setPlaceholderText("Not set")
        val = getattr(self._settings, field_name, "")
        path_display.setText(setting_path_display(val))
        self.__dict__[f"{field_name}_display"] = path_display
        row_layout.addWidget(path_display)

        choose_btn = QPushButton("Choose…")
        choose_btn.setStyleSheet(self._btn_style())
        choose_btn.clicked.connect(lambda: self._pick_folder(field_name))
        self.__dict__[f"{field_name}_btn"] = choose_btn
        row_layout.addWidget(choose_btn)

        return row

    def _build_panel_widths(self) -> QWidget:
        group = QGroupBox("Panel Widths")
        group.setStyleSheet(
            "QGroupBox { color: #999; font-size: 12px; border: 1px solid #2a2a4a; "
            "border-radius: 6px; margin-top: 8px; padding-top: 16px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        layout = QVBoxLayout(group)

        # Left panel width
        left_row = QHBoxLayout()
        left_lbl = QLabel("Left Panel Min Width:")
        left_lbl.setStyleSheet("color: #aaa; font-size: 12px;")
        left_row.addWidget(left_lbl)
        left_spin = QSpinBox()
        left_spin.setRange(0, 1200)
        left_spin.setValue(getattr(self._settings, "left_panel_min_width", 350))
        left_spin.setSuffix(" px")
        left_spin.setStyleSheet(self._spin_style())
        left_spin.valueChanged.connect(lambda v: self._update_setting("left_panel_min_width", v))
        left_row.addWidget(left_spin)
        left_row.addStretch()
        layout.addLayout(left_row)

        # Right panel width
        right_row = QHBoxLayout()
        right_lbl = QLabel("Right Panel Min Width:")
        right_lbl.setStyleSheet("color: #aaa; font-size: 12px;")
        right_row.addWidget(right_lbl)
        right_spin = QSpinBox()
        right_spin.setRange(0, 1200)
        right_spin.setValue(getattr(self._settings, "right_panel_min_width", 350))
        right_spin.setSuffix(" px")
        right_spin.setStyleSheet(self._spin_style())
        right_spin.valueChanged.connect(lambda v: self._update_setting("right_panel_min_width", v))
        right_row.addWidget(right_spin)
        right_row.addStretch()
        layout.addLayout(right_row)

        return group

    def _build_scroll_speed(self) -> QWidget:
        group = QGroupBox("Scroll Speed")
        group.setStyleSheet(
            "QGroupBox { color: #999; font-size: 12px; border: 1px solid #2a2a4a; "
            "border-radius: 6px; margin-top: 8px; padding-top: 16px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        layout = QHBoxLayout(group)

        lbl = QLabel("Default Scroll Speed:")
        lbl.setStyleSheet("color: #aaa; font-size: 12px;")
        layout.addWidget(lbl)

        self._scroll_slider = QSlider(Qt.Orientation.Horizontal)
        self._scroll_slider.setRange(10, 300)
        self._scroll_slider.setValue(int(self._settings.scroll_speed * 10))
        self._scroll_slider.setStyleSheet(self._slider_style())
        self._scroll_slider.valueChanged.connect(self._on_scroll_speed_changed)
        layout.addWidget(self._scroll_slider, 1)

        self._scroll_label = QLabel(f"{self._settings.scroll_speed:.1f}")
        self._scroll_label.setStyleSheet("color: #ccc; font-size: 12px; min-width: 40px;")
        layout.addWidget(self._scroll_label)

        return group

    # ── Appearance page ───────────────────────────────────────────────────

    def _build_appearance_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        title = QLabel("Appearance")
        title.setStyleSheet("color: #e0e0ff; font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel("Visual preferences for the application.")
        desc.setStyleSheet("color: #777; font-size: 12px;")
        layout.addWidget(desc)

        theme_group = QGroupBox("Theme")
        theme_group.setStyleSheet(
            "QGroupBox { color: #999; font-size: 12px; border: 1px solid #2a2a4a; "
            "border-radius: 6px; margin-top: 8px; padding-top: 16px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        theme_layout = QHBoxLayout(theme_group)

        theme_lbl = QLabel("Application Theme:")
        theme_lbl.setStyleSheet("color: #aaa; font-size: 12px;")
        theme_layout.addWidget(theme_lbl)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Dark", "Light"])
        self._theme_combo.setCurrentText("Dark")
        self._theme_combo.setStyleSheet(
            "QComboBox { background: #1e1e3a; color: #ccc; border: 1px solid #333; "
            "border-radius: 4px; padding: 4px 8px; font-size: 12px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background: #1e1e3a; color: #ccc; selection-background-color: #2a2a4a; }"
        )
        self._theme_combo.currentTextChanged.connect(self._on_theme_changed)
        theme_layout.addWidget(self._theme_combo)
        theme_layout.addStretch()
        layout.addWidget(theme_group)

        layout.addStretch()
        return page

    # ── Actions ───────────────────────────────────────────────────────────

    def _pick_folder(self, field_name: str) -> None:
        current = getattr(self._settings, field_name, "")
        start_dir = current if is_valid_directory(current) else ""
        path = QFileDialog.getExistingDirectory(
            self, "Choose Directory", start_dir,
        )
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
        """Update validation indicators for data and vgmstream paths."""
        # Data directory validation
        data_path = self._settings.data_root
        self._data_valid = is_valid_directory(data_path)
        data_exe = find_file_named(data_path, _DATA_EXECUTABLE_NAMES) if self._data_valid else None

        data_valid_lbl = self.__dict__.get("data_dir_path_valid_lbl")
        if data_valid_lbl is not None:
            if data_exe:
                data_valid_lbl.setText(f"✓ Found: {data_exe}")
                data_valid_lbl.setStyleSheet("color: #4f4; font-size: 11px;")
                data_valid_lbl.show()
            elif self._data_valid:
                data_valid_lbl.setText("✓ Valid directory (no chusanApp found)")
                data_valid_lbl.setStyleSheet("color: #fa0; font-size: 11px;")
                data_valid_lbl.show()
            else:
                data_valid_lbl.hide()

        # vgmstream validation
        vg_path = getattr(self._settings, "vgstreamcli_path", "")
        result = validate_vgmstream_path(vg_path)
        self._vgmstream_validation = result.status
        self._vgmstream_detail = result.detail

        vg_valid_lbl = self.__dict__.get("vgmstreamcli_path_valid_lbl")
        if vg_valid_lbl is not None:
            if result.status == VgmstreamValidation.READY:
                vg_valid_lbl.setText(f"✓ {result.detail}")
                vg_valid_lbl.setStyleSheet("color: #4f4; font-size: 11px;")
                vg_valid_lbl.show()
            elif result.status == VgmstreamValidation.LIBRARY_ONLY:
                vg_valid_lbl.setText(f"⚠ {result.detail}")
                vg_valid_lbl.setStyleSheet("color: #fa0; font-size: 11px;")
                vg_valid_lbl.show()
            else:
                vg_valid_lbl.hide()

    def _on_tab_changed(self, index: int) -> None:
        self._stack.setCurrentIndex(index)

    def _on_theme_changed(self, text: str) -> None:
        # Theme changes are applied on next restart or via stylesheet reload
        LOGGER.info("Theme changed to: %s", text)

    def _on_scroll_speed_changed(self, value: int) -> None:
        speed = value / 10.0
        self._scroll_label.setText(f"{speed:.1f}")
        self._update_setting("scroll_speed", speed)

    # ── Styles ────────────────────────────────────────────────────────────

    @staticmethod
    def _btn_style() -> str:
        return (
            "QPushButton { background: #2a2a4a; color: #ccc; border: 1px solid #444; "
            "border-radius: 4px; padding: 4px 12px; font-size: 12px; }"
            "QPushButton:hover { background: #3a3a5a; }"
        )

    @staticmethod
    def _spin_style() -> str:
        return (
            "QSpinBox { background: #1e1e3a; color: #ccc; border: 1px solid #333; "
            "border-radius: 4px; padding: 2px 6px; font-size: 12px; }"
        )

    @staticmethod
    def _slider_style() -> str:
        return (
            "QSlider::groove:horizontal { background: #2a2a4a; height: 6px; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #5a5a8a; width: 14px; height: 14px; "
            "margin: -4px 0; border-radius: 7px; }"
            "QSlider::handle:horizontal:hover { background: #7a7aaa; }"
        )
