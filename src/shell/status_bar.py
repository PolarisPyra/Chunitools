"""Status bar widgets for the main window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from src.ui import theme

if TYPE_CHECKING:
    from src.workspace.layout import MainWindow


def init_status_widgets(window: MainWindow) -> None:
    window.status_progress_host = QWidget(window)
    window.status_progress_host.setAttribute(
        Qt.WidgetAttribute.WA_StyledBackground, True
    )
    window.status_progress_host.setStyleSheet(f"background: {theme.TRANSPARENT};")

    window.status_progress_layout = QHBoxLayout(window.status_progress_host)
    window.status_progress_layout.setContentsMargins(0, 0, 18, 0)
    window.status_progress_layout.setSpacing(12)

    window.status_eta_label = QLabel("ETA --:--", window.status_progress_host)
    window.status_eta_label.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    window.status_eta_label.setStyleSheet(
        f"color: {theme.TEXT_STATUS_MUTED}; "
        f"background: {theme.TRANSPARENT}; "
        "padding-bottom: 1px;"
    )
    window.status_eta_label.setFixedWidth(88)
    window.status_progress_layout.addWidget(
        window.status_eta_label, 0, Qt.AlignmentFlag.AlignVCenter,
    )

    window.status_progress = QProgressBar(window.status_progress_host)
    window.status_progress.setFixedWidth(220)
    window.status_progress.setFixedHeight(14)
    window.status_progress.setTextVisible(False)
    window.status_progress_layout.addWidget(
        window.status_progress, 0, Qt.AlignmentFlag.AlignVCenter,
    )

    button_style = (
        f"QPushButton {{ background: {theme.SURFACE_STATUS_BUTTON}; "
        f"color: {theme.WHITE}; "
        f"border: 1px solid {theme.BORDER_CONTROL}; "
        "border-radius: 4px; padding: 2px 8px; min-height: 20px; }}"
        f"QPushButton:hover {{ background: {theme.SURFACE_STATUS_BUTTON_HOVER}; }}"
    )

    window.status_cancel_button = QPushButton("Cancel", window.status_progress_host)
    window.status_cancel_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    window.status_cancel_button.setStyleSheet(button_style)
    window.status_cancel_button.clicked.connect(window.cancel_export_all)
    window.status_progress_layout.addWidget(
        window.status_cancel_button, 0, Qt.AlignmentFlag.AlignVCenter,
    )

    window.status_progress_layout.addStretch(1)

    window.status_eta_label.hide()
    window.status_progress.hide()
    window.status_cancel_button.hide()

    window.status_progress_host.setFixedWidth(350)
    window.status_progress_host.setFixedHeight(30)
    window.status_progress_host.show()

    window.statusBar().addPermanentWidget(window.status_progress_host)
    window.statusBar().setSizeGripEnabled(False)
