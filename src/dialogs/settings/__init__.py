"""Settings dialog — Qt-based modal for application preferences.

Mirrors the Rust ``dialogs/settings/`` module.
"""

from src.dialogs.settings.content import SettingsDialog, open_settings

__all__ = ["SettingsDialog", "open_settings"]
