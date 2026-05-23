"""Global Qt stylesheets driven by theme tokens."""

from .ui import (
    ACCENT,
    APP_BACKGROUND,
    BASE_GRAY_900,
    BORDER_CONTROL,
    BORDER_PANEL,
    FONT_MONO,
    FONT_UI,
    SURFACE_ELEVATED,
    SURFACE_LIST_HOVER,
    SURFACE_MENU,
    SURFACE_NAV,
    SURFACE_RAISED,
    SURFACE_SCROLLBAR,
    SURFACE_SCROLLBAR_HANDLE,
    SURFACE_SCROLLBAR_HANDLE_HOVER,
    SURFACE_SELECTED,
    TEXT_DISABLED,
    TEXT_EDITOR,
    TEXT_PRIMARY,
    TEXT_SOFT,
    TRANSPARENT,
    WHITE,
)


def get_main_stylesheet() -> str:
    return f"""
QMainWindow, QWidget {{
    background-color: {APP_BACKGROUND};
    color: {TEXT_PRIMARY};
    font-family: {FONT_UI};
    font-size: 13px;
    font-weight: 400;
}}

QFrame#LeftPanel {{
    background-color: {SURFACE_RAISED};
    border-right: 1px solid {BORDER_PANEL};
}}

QFrame#InspectorPanel {{
    background-color: {SURFACE_RAISED};
    border-left: 1px solid {BORDER_PANEL};
}}

QFrame#InfoPanel {{
    background-color: {SURFACE_RAISED};
    border-top: 1px solid {BORDER_PANEL};
}}

QFrame#BottomControlBar {{
    background-color: {SURFACE_NAV};
    border-top: 1px solid {BORDER_PANEL};
    border-bottom: none;
}}



QSplitter::handle {{
    background-color: {BORDER_PANEL};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QFrame#PickerHeader,
QFrame#MetaPanel,
QFrame#ControlPanel,
QFrame#DiffContainer {{
    background-color: {SURFACE_RAISED};
    border-top: 1px solid {BORDER_PANEL};
}}

QFrame#PickerHeader {{
    border-bottom: 1px solid {BORDER_PANEL};
    border-top: none;
}}

QLabel#PickerTitle {{
    color: {TEXT_PRIMARY};
    font-weight: 600;
    background-color: transparent;
}}

QFrame#ViewportPanel {{
    background-color: {APP_BACKGROUND};
    border: none;
}}

QLabel {{
    background-color: {TRANSPARENT};
}}

/* --- BUTTONS --- */
QPushButton {{
    background-color: {SURFACE_ELEVATED};
    color: {WHITE};
    border: 1px solid {BORDER_CONTROL};
    border-radius: 4px;
    padding: 2px 10px;
    font-weight: 500;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: {SURFACE_LIST_HOVER};
    border-color: {ACCENT};
    color: {TEXT_PRIMARY};
}}

QPushButton:pressed {{
    background-color: {SURFACE_SELECTED};
    color: {TEXT_PRIMARY};
}}

QPushButton:checked {{
    background-color: {ACCENT};
    color: {WHITE};
    font-weight: 600;
    border-color: {ACCENT};
}}

QPushButton#CommandButton {{
    background-color: {SURFACE_ELEVATED};
    color: {WHITE};
    border: 1px solid {BORDER_CONTROL};
    border-radius: 4px;
    font-weight: 500;
    padding: 2px 12px;
    min-height: 18px;
    height: 22px;
}}

QPushButton#CommandButton:hover {{
    background-color: {SURFACE_LIST_HOVER};
    border-color: {ACCENT};
}}

QPushButton#CommandButton:pressed {{
    background-color: {SURFACE_SELECTED};
}}

/* --- INPUTS --- */
QLineEdit, QTextEdit {{
    background-color: {BASE_GRAY_900};
    color: {WHITE};
    border: 1px solid {BORDER_CONTROL};
    border-radius: 4px;
    padding: 2px 8px;
    selection-background-color: {ACCENT};
    selection-color: {WHITE};
    font-family: {FONT_MONO};
    font-size: 12px;
    min-height: 18px;
    height: 22px;
    margin: 4px 0;
}}

QLineEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT};
}}

QFrame#NoteSection {{
    background-color: {TRANSPARENT};
}}

QTextEdit#InspectorText {{
    background-color: {TRANSPARENT};
    color: {TEXT_EDITOR};
    border: 1px solid {BORDER_PANEL};
    border-radius: 4px;
    padding: 10px;
}}

QListWidget#WarningList {{
    background: {SURFACE_ELEVATED};
    color: {TEXT_EDITOR};
    border: 1px solid {BORDER_PANEL};
    border-radius: 4px;
    padding: 4px;
}}

QListWidget#WarningList::item {{
    padding: 4px 8px;
    border-radius: 2px;
}}

QListWidget#WarningList::item:selected {{
    background: {ACCENT};
    color: {APP_BACKGROUND};
}}

/* --- SCROLLBARS --- */
QScrollBar:vertical {{
    background: {SURFACE_SCROLLBAR};
    width: 12px;
    margin: 0;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {SURFACE_SCROLLBAR_HANDLE};
    border-radius: 6px;
    min-height: 30px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: {SURFACE_SCROLLBAR_HANDLE_HOVER};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: {TRANSPARENT};
}}

/* --- MENUS & COMBOS --- */
QComboBox {{
    background-color: {SURFACE_ELEVATED};
    color: {TEXT_SOFT};
    border: 1px solid {BORDER_CONTROL};
    border-radius: 4px;
    padding: 2px 8px;
    min-width: 80px;
}}

QComboBox::drop-down {{
    border: none;
}}

QComboBox QAbstractItemView {{
    background-color: {SURFACE_MENU};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
    selection-color: {WHITE};
    border: 1px solid {BORDER_PANEL};
    outline: none;
}}

QComboBox QListView {{
    background-color: {SURFACE_MENU};
    border: 1px solid {BORDER_PANEL};
}}

QComboBox QListView::item {{
    background-color: {SURFACE_MENU};
    padding: 4px;
}}

QComboBox QListView::item:selected {{
    background-color: {ACCENT};
    color: {WHITE};
}}

QToolTip {{
    background-color: {SURFACE_MENU};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_PANEL};
    border-radius: 4px;
    padding: 4px;
}}

QStatusBar {{
    background-color: {SURFACE_NAV};
    color: {WHITE};
    border-top: 1px solid {BORDER_PANEL};
}}

QStatusBar::item {{
    border: none;
}}

QMenuBar {{
    background-color: {SURFACE_NAV};
    color: {WHITE};
    border-bottom: 1px solid {BORDER_PANEL};
    font-weight: 500;
    min-height: 36px;
    padding: 0 12px;
}}

QMenuBar::item {{
    padding: 0px 12px;
    margin: 6px 2px;
    background-color: transparent;
    color: {WHITE};
    border-radius: 4px;
    height: 22px;
}}

QMenuBar::item:selected {{
    background-color: {SURFACE_LIST_HOVER};
}}

QMenu {{
    background-color: {SURFACE_MENU};
    color: {WHITE};
    border: 1px solid {BORDER_PANEL};
    border-radius: 6px;
    padding: 4px;
    margin: 0px;
}}

QMenu::item {{
    padding: 4px 24px;
    margin: 2px 4px;
    border-radius: 4px;
    color: {WHITE};
}}

QMenu::item:selected, QMenu::item:hover {{
    background-color: {ACCENT};
    color: {WHITE};
}}

QMenu::item:disabled {{
    color: {TEXT_DISABLED};
    background-color: transparent;
}}

QMenu::separator {{
    height: 1px;
    background: {BORDER_PANEL};
    margin: 4px 8px;
}}
"""
