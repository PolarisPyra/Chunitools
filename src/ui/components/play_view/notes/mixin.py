from __future__ import annotations

from src.ui.components.play_view.notes.air import PlayViewAirNotesMixin
from src.ui.components.play_view.notes.dispatch import PlayViewNoteDispatchMixin
from src.ui.components.play_view.notes.ground import PlayViewGroundNotesMixin
from src.ui.components.play_view.notes.sustain import PlayViewSustainNotesMixin


class PlayViewNotesMixin(
    PlayViewNoteDispatchMixin,
    PlayViewAirNotesMixin,
    PlayViewSustainNotesMixin,
    PlayViewGroundNotesMixin,
):
    pass
