from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPointF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from src.ui import theme


class HoverOnlyComboDelegate(QStyledItemDelegate):
    """Popup delegate that does not treat the current value as hovered."""

    def __init__(self, combo: GridComboBox) -> None:
        super().__init__(combo)
        self._combo = combo

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        # Check if this item is currently hovered by comparing rows
        is_hovered = (self._combo.hovered_popup_index.isValid() and
                      index.row() == self._combo.hovered_popup_index.row())

        # Always fill background to prevent transparency
        painter.fillRect(option.rect, QColor(theme.SURFACE_MENU))

        if is_hovered:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            # Create a slightly inset highlight with rounded corners to match menus
            highlight_rect = option.rect.adjusted(2, 1, -2, -1)
            painter.setBrush(QColor(theme.ACCENT))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(highlight_rect, 4, 4)

        # Prepare option for standard text drawing (without selection highlight)
        new_option = QStyleOptionViewItem(option)
        new_option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, new_option, index)


class GridComboBox(QComboBox):
    """Compact combo box with stable popup highlighting and a drawn chevron."""

    def __init__(self) -> None:
        super().__init__()
        self._previous_focus: QWidget | None = None
        self.hovered_popup_index = QModelIndex()
        self.setItemDelegate(HoverOnlyComboDelegate(self))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMaxVisibleItems(15)
        self.view().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view().setMouseTracking(True)
        self.view().setCursor(Qt.CursorShape.PointingHandCursor)
        self.view().viewport().setMouseTracking(True)
        self.view().viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.view().viewport().setStyleSheet(f"background-color: {theme.SURFACE_MENU};")

        # Connect to entered signal for reliable hover tracking
        self.view().entered.connect(self._on_item_entered)

    def _on_item_entered(self, index: QModelIndex) -> None:
        self.hovered_popup_index = index
        self.view().viewport().update()

    def showPopup(self) -> None:
        self._previous_focus = QApplication.focusWidget()
        super().showPopup()
        self._clear_popup_current_item()
        self.hovered_popup_index = QModelIndex()
        QTimer.singleShot(0, self._restore_previous_focus)

    def hidePopup(self) -> None:
        super().hidePopup()
        self._clear_popup_current_item()
        self.hovered_popup_index = QModelIndex()
        QTimer.singleShot(0, self._restore_previous_focus)

    def _clear_popup_current_item(self) -> None:
        view = self.view()
        selection_model = view.selectionModel()
        if selection_model is not None:
            selection_model.clearSelection()

    def _restore_previous_focus(self) -> None:
        if self._previous_focus is None:
            return
        if not self._previous_focus.isVisible() or not self._previous_focus.isEnabled():
            return
        self._previous_focus.setFocus(Qt.FocusReason.OtherFocusReason)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(theme.qt(theme.BORDER_CONTROL_SOFT), 1))
        painter.setBrush(theme.qt(theme.GUNMETAL))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)

        text_rect = self.rect().adjusted(8, 0, -24, 0)
        text = QFontMetrics(self.font()).elidedText(
            self.currentText(),
            Qt.TextElideMode.ElideRight,
            text_rect.width(),
        )
        painter.setPen(theme.qt(theme.TEXT_PRIMARY))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        painter.setPen(QPen(theme.qt(theme.TEXT_SOFT), 1.6))
        center_x = self.width() - 14
        center_y = self.height() / 2
        chevron = QPolygonF(
            [
                QPointF(center_x - 4, center_y - 2),
                QPointF(center_x, center_y + 2),
                QPointF(center_x + 4, center_y - 2),
            ]
        )
        painter.drawPolyline(chevron)
        painter.end()
