"""Application dialogs — settings, export, and other modal windows.

Mirrors the Rust ``dialogs/`` module.
"""

from src.dialogs.settings import SettingsDialog, open_settings

__all__ = ["SettingsDialog", "open_settings"]
