from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, Qt

_DEFAULT_MODEL_INDEX = QModelIndex()

if TYPE_CHECKING:
    from src.core.read import SongInfo


class SongModel(QAbstractListModel):
    def __init__(self, songs: list[SongInfo], parent: Any = None) -> None:
        super().__init__(parent)
        self._all_songs = songs
        self._visible_songs = songs

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _DEFAULT_MODEL_INDEX) -> int:
        _ = parent
        return len(self._visible_songs)

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if not index.isValid() or index.row() >= len(self._visible_songs):
            return None

        song = self._visible_songs[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return song
        if role == Qt.ItemDataRole.DisplayRole:
            return song.name
        return None

    def filter(self, needle: str) -> None:
        self.beginResetModel()
        needle = needle.strip().lower()
        if not needle:
            self._visible_songs = self._all_songs
        else:
            self._visible_songs = [
                s for s in self._all_songs if needle in s.name.lower() or needle in s.artist.lower()
            ]
        self.endResetModel()

    def sort_by_id(self, ascending: bool) -> None:
        self.beginResetModel()
        self._all_songs.sort(key=lambda s: s.folder_name, reverse=not ascending)
        self.endResetModel()
