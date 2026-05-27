"""Settings dialog — shared utilities and validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


def _walk_files(root: Path) -> Iterator[Path]:
    """Yield all regular files under *root*, depth-first."""
    if not root.is_dir():
        return
    for entry in root.rglob("*"):
        if entry.is_file():
            yield entry


def find_file_named(path: str, expected_names: tuple[str, ...]) -> Path | None:
    """Return the first file under *path* whose name is in *expected_names*."""
    root = Path(path)
    if not root.is_dir():
        return None
    for file_path in _walk_files(root):
        if file_path.name in expected_names:
            return file_path
    return None


def is_valid_directory(path: str) -> bool:
    """Return True if *path* is a non-empty string pointing to an existing directory."""
    return bool(path) and Path(path).is_dir()


def setting_path_display(path: str) -> str:
    """Return a display string for a path setting (or 'Not set' if empty)."""
    return path if path else "Not set"
