"""Workspace layout — main window, menubar, panels, and timeline.

Mirrors the Rust ``workspace/`` module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.ui.window.window import MainWindow

__all__ = ["MainWindow"]


def __getattr__(name: str):
    """Lazy re-export to avoid circular imports with ``src.ui.window.window``."""
    if name == "MainWindow":
        from src.ui.window.window import MainWindow  # noqa: PLC0415

        return MainWindow
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
