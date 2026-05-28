"""Main window package — re-exports for compatibility."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .window import MainWindow

__all__ = ["MainWindow"]


def __getattr__(name: str):
    """Lazy re-export to avoid circular imports with ``src.workspace``."""
    if name == "MainWindow":
        from .window import MainWindow  # noqa: PLC0415

        return MainWindow
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
