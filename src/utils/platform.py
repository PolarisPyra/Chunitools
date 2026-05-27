"""Platform detection utilities."""

from __future__ import annotations

import platform
import sys

__all__ = ["current_os", "is_linux", "is_macos", "is_windows"]


def current_os() -> str:
    """Return a lowercase OS name: 'linux', 'macos', or 'windows'."""
    system = platform.system()
    if system == "Linux":
        return "linux"
    if system == "Darwin":
        return "macos"
    if system == "Windows":
        return "windows"
    return system.lower()


def is_linux() -> bool:
    return sys.platform == "linux"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform == "win32"
