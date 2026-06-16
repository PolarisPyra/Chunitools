from __future__ import annotations

from src.ui.components.play_view.notes.air import PlayViewAirNotesMixin
from src.ui.components.play_view.notes.damage import PlayViewDamageNotesMixin
from src.ui.components.play_view.notes.flick import PlayViewFlickNotesMixin
from src.ui.components.play_view.notes.hold import PlayViewHoldNotesMixin
from src.ui.components.play_view.notes.slide import PlayViewSlideNotesMixin
from src.ui.components.play_view.notes.support import PlayViewSupportNotesMixin


class PlayViewNotesMixin(
    PlayViewSupportNotesMixin,
    PlayViewAirNotesMixin,
    PlayViewHoldNotesMixin,
    PlayViewSlideNotesMixin,
    PlayViewDamageNotesMixin,
    PlayViewFlickNotesMixin,
):
    pass


__all__ = ["PlayViewNotesMixin"]
