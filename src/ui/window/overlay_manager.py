"""Overlay positioning for FPS counter and radar.

Extracted from MainWindow._position_overlays to keep the window class
focused on orchestration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer

if TYPE_CHECKING:
    from src.workspace.layout import MainWindow


class OverlayManager:
    """Positions FPS and radar overlays on the active viewport."""

    OVERLAY_MARGIN = 20

    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self._pending = False

    def reposition(self) -> None:
        """Position overlays on the currently visible viewport."""
        if self._pending:
            return

        if not self._can_position():
            self._pending = True
            QTimer.singleShot(100, self._deferred_reposition)
            return

        is_t = self.window._view_stack.currentIndex() == 0
        ref = self.window.visualizer if is_t else self.window.play_view

        if hasattr(self.window, "fps_overlay"):
            self.window.fps_overlay.setParent(ref)
            self.window.fps_overlay.move(self.OVERLAY_MARGIN, self.OVERLAY_MARGIN)
            self.window.fps_overlay.raise_()

        if hasattr(self.window, "radar"):
            r = self.window.radar
            r.setParent(ref)
            r.move(ref.width() - r.width() - self.OVERLAY_MARGIN, self.OVERLAY_MARGIN)
            r.raise_()

        self._pending = False

    def _can_position(self) -> bool:
        vis = getattr(self.window, "visualizer", None)
        pv = getattr(self.window, "play_view", None)
        return bool(
            (vis and vis.isVisible() and vis.width() >= 100)
            or (pv and pv.isVisible() and pv.width() >= 100)
        )

    def _deferred_reposition(self) -> None:
        self._pending = False
        self.reposition()
