from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import cast

from PIL import Image
from PySide6.QtCore import QEvent, QModelIndex, QPoint, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from src.core.read import SongInfo
from src.core.read import fast_get_metadata, MetadataPreview
from src.ui import theme

LOGGER = logging.getLogger(__name__)

# Maps each view mode to the set of difficulty indices that should be displayed.
_VISIBLE_DIFFICULTIES: dict[str, frozenset[int]] = {
    "standard": frozenset({0, 1, 2, 3}),
    "ultima": frozenset({4}),
    "worlds_end": frozenset({5}),
}
_DIFFICULTY_COLORS = {
    0: QColor("#22ac38"),  # BASIC
    1: QColor("#f39800"),  # ADVANCED
    2: QColor("#eb6100"),  # EXPERT
    3: QColor("#920783"),  # MASTER
    4: QColor("#222222"),  # ULTIMA
    5: QColor("#ffffff"),  # WORLDS_END
}
_LEVEL_CHIP_BACKGROUND = theme.SURFACE_CHIP
_LEVEL_CHIP_RADIUS = 10
_LEVEL_CHIP_HEIGHT = 20
_LEVEL_CHIP_MIN_WIDTH = 40
_LEVEL_CHIP_HORIZONTAL_PADDING = 12
_LEVEL_CHIP_GAP = 6


@lru_cache(maxsize=1024)
def load_chart_metadata_cached(path: str) -> MetadataPreview:
    """Load metadata with caching to prevent repeated disk I/O during paint."""
    return fast_get_metadata(path)


@lru_cache(maxsize=2048)
def load_dds_to_pixmap(path: str) -> QPixmap:
    """Load a DDS file with Pillow and convert it to ``QPixmap``.

    Args:
        path: DDS image path.

    Returns:
        Pixmap for Qt display, or an empty pixmap if loading fails.
    """
    if not os.path.exists(path):
        return QPixmap()

    try:
        with Image.open(path) as source:
            # Scale down immediately to save massive amounts of RAM.
            source.thumbnail((64, 64), Image.Resampling.LANCZOS)
            image = source.convert("RGBA")
            data = image.tobytes("raw", "RGBA")
            qimg = QImage(
                data, image.size[0], image.size[1], QImage.Format.Format_RGBA8888
            )
            return QPixmap.fromImage(qimg)
    except (OSError, ValueError) as exc:
        LOGGER.warning("Failed to load DDS %s: %s", path, exc)
        return QPixmap()


class SongDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._name_font = QFont(theme.FONT_UI, 12, QFont.Weight.Bold)
        self._artist_font = QFont(theme.FONT_UI, 10, QFont.Weight.Normal)
        self._id_font = QFont(theme.FONT_MONO, 9, QFont.Weight.Normal)
        self._level_font = QFont(theme.FONT_MONO, 10, QFont.Weight.Medium)

    def editorEvent(
        self, event: QEvent, model, option: QStyleOptionViewItem, index: QModelIndex
    ) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            mevent = cast(QMouseEvent, event)
            if mevent.button() == Qt.MouseButton.LeftButton:
                song = index.data(Qt.ItemDataRole.UserRole)
                if not isinstance(song, SongInfo):
                    return False

                rect = option.rect.adjusted(12, 16, -12, -16)
                text_x = rect.x() + 88 + 16
                marker_y = rect.y() + 100
                marker_x = text_x

                metrics = QFontMetrics(self._level_font)
                view_mode = (
                    option.widget.property("view_mode") if option.widget else "standard"
                )
                visible = _VISIBLE_DIFFICULTIES.get(view_mode, frozenset({0, 1, 2, 3}))
                for fumen in song.fumens:
                    if fumen.difficulty not in visible:
                        marker_x += 0  # position not advanced for hidden badges
                        continue
                    label = str(fumen.level)
                    if fumen.level_decimal >= 50:
                        label += "+"

                    text_rect = metrics.boundingRect(label)
                    box_w = max(
                        _LEVEL_CHIP_MIN_WIDTH,
                        text_rect.width() + _LEVEL_CHIP_HORIZONTAL_PADDING,
                    )
                    box_rect = QRectF(marker_x, marker_y, box_w, _LEVEL_CHIP_HEIGHT)

                    if box_rect.contains(mevent.position()):
                        view = option.widget
                        if hasattr(view, "on_difficulty_clicked"):
                            view.on_difficulty_clicked(fumen.file_path, song)
                        return True

                    marker_x += box_w + _LEVEL_CHIP_GAP
        return super().editorEvent(event, model, option, index)

    def hit_test_difficulty(
        self, option: QStyleOptionViewItem, index: QModelIndex, pos: QPoint
    ) -> bool:
        song = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(song, SongInfo):
            return False

        view_mode = option.widget.property("view_mode") if option.widget else "standard"
        visible = _VISIBLE_DIFFICULTIES.get(view_mode, frozenset({0, 1, 2, 3}))

        rect = option.rect.adjusted(12, 16, -12, -16)
        text_x = rect.x() + 88 + 16
        marker_y = rect.y() + 100
        marker_x = text_x

        metrics = QFontMetrics(self._level_font)
        for fumen in song.fumens:
            if fumen.difficulty not in visible:
                continue

            label = str(fumen.level)
            if fumen.level_decimal >= 50:
                label += "+"

            text_rect = metrics.boundingRect(label)
            box_w = max(
                _LEVEL_CHIP_MIN_WIDTH,
                text_rect.width() + _LEVEL_CHIP_HORIZONTAL_PADDING,
            )
            box_rect = QRectF(marker_x, marker_y, box_w, _LEVEL_CHIP_HEIGHT)

            if box_rect.contains(pos):
                return True
            marker_x += box_w + _LEVEL_CHIP_GAP
        return False

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ):
        song = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(song, SongInfo):
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(theme.SURFACE_LIST_SELECTED))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(theme.SURFACE_ELEVATED))

        # Padding adjustment: 16px vertical padding for more breathing room
        rect = option.rect.adjusted(12, 16, -12, -16)

        # Jacket
        jacket_size = 88
        jacket_rect = QRectF(rect.x(), rect.y(), jacket_size, jacket_size)

        # Subtle shadow/border for jacket
        painter.setPen(QPen(QColor(theme.BORDER_PANEL), 1))
        painter.setBrush(QColor(theme.SURFACE_ELEVATED))
        painter.drawRect(jacket_rect.adjusted(-0.5, -0.5, 0.5, 0.5))

        pixmap = load_dds_to_pixmap(song.jacket_path)
        if not pixmap.isNull():
            painter.drawPixmap(jacket_rect.toRect(), pixmap)
        else:
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(jacket_rect, Qt.AlignCenter, "?")

        # Text stack
        text_x = rect.x() + jacket_size + 16
        text_w = rect.width() - jacket_size - 16

        # Title
        painter.setFont(self._name_font)
        painter.setPen(QColor(theme.TEXT_PRIMARY))
        title_rect = QRectF(text_x, rect.y(), text_w, 28)
        painter.drawText(
            title_rect,
            Qt.AlignLeft | Qt.AlignTop,
            painter.fontMetrics().elidedText(song.name, Qt.ElideRight, int(text_w)),
        )

        # Artist
        painter.setFont(self._artist_font)
        painter.setPen(QColor(theme.TEXT_SOFT))
        artist_rect = QRectF(text_x, rect.y() + 28, text_w, 20)
        painter.drawText(
            artist_rect,
            Qt.TextSingleLine,
            painter.fontMetrics().elidedText(song.artist, Qt.ElideRight, int(text_w)),
        )

        # Metadata Pass
        painter.setFont(self._id_font)

        charter = "---"
        if song.fumens:
            # Use last fumen as it's usually the highest difficulty (MASTER/ULT/WE)
            preview = load_chart_metadata_cached(song.fumens[-1].file_path)
            charter = preview.get("creator") or "---"

        # Charter line
        painter.setPen(QColor(theme.TEXT_MUTED))
        charter_text = f"CHARTER: {charter}"
        charter_rect = QRectF(text_x, rect.y() + 52, text_w, 16)
        painter.drawText(
            charter_rect,
            Qt.TextSingleLine,
            painter.fontMetrics().elidedText(charter_text, Qt.ElideRight, int(text_w)),
        )

        # ID line
        version = preview.get("version") or "---"
        painter.setPen(QColor(theme.TEXT_DIM))
        id_text = f"ID {song.song_id}  •  {version}"
        id_rect = QRectF(text_x, rect.y() + 72, text_w, 16)
        painter.drawText(id_rect, Qt.TextSingleLine, id_text)

        # Difficulty Markers (shown in all view modes)
        marker_y = rect.y() + 100
        marker_x = text_x
        painter.setFont(self._level_font)

        view_mode = option.widget.property("view_mode") if option.widget else "standard"
        visible = _VISIBLE_DIFFICULTIES.get(view_mode, frozenset({0, 1, 2, 3}))
        for fumen in song.fumens:
            if fumen.difficulty not in visible:
                continue
            label = str(fumen.level)
            if fumen.level_decimal >= 50:
                label += "+"

            text_rect = painter.fontMetrics().boundingRect(label)
            box_w = max(
                _LEVEL_CHIP_MIN_WIDTH,
                text_rect.width() + _LEVEL_CHIP_HORIZONTAL_PADDING,
            )
            box_rect = QRectF(marker_x, marker_y, box_w, _LEVEL_CHIP_HEIGHT)

            diff_color = _DIFFICULTY_COLORS.get(fumen.difficulty, QColor(theme.WHITE))
            
            painter.save()
            # Draw Pill Background
            painter.setPen(QPen(QColor(theme.BORDER_CHIP), 1.0))
            painter.setBrush(QColor(_LEVEL_CHIP_BACKGROUND))
            painter.drawRoundedRect(
                box_rect,
                box_rect.height() / 2,
                box_rect.height() / 2,
            )
            
            # Draw Text
            painter.setFont(self._level_font)
            painter.setPen(QColor(theme.TEXT_SUBTLE))
            painter.drawText(box_rect, Qt.AlignmentFlag.AlignCenter, label)
            painter.restore()

            marker_x += box_w + _LEVEL_CHIP_GAP

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        return QSize(200, 150)
