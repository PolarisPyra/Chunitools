"""Audio asset resolution, vgmstream CLI discovery, and validation.

Matches the Rust ``utils/audio.rs`` module: resolve audio paths, find
vgmstream-cli executables, and validate vgmstream directories.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "VgmstreamValidation",
    "find_executable_in_dir",
    "find_vgmstream_cli",
    "validate_vgmstream_path",
]

# Executable and library names for vgmstream on every platform.
# We search ALL names regardless of host OS so that cross-platform
# installations (e.g. WSL, Wine, downloaded archives) still work.
_VGMSTREAM_CLI_NAMES: tuple[str, ...] = (
    "vgmstream-cli",
    "vgmstream-cli.exe",
    "vgstream-cli.exe",
)
_VGMSTREAM_LIB_NAMES: tuple[str, ...] = (
    "libvgmstream.so",
    "libvgmstream.dylib",
    "vgmstream.dll",
)


class VgmstreamValidation:
    """Result of validating a vgmstream directory.

    Mirrors the Rust ``VgmstreamValidation`` enum.
    """

    READY = "ready"
    LIBRARY_ONLY = "library_only"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class _VgmstreamResult:
    status: str
    path: str = ""
    detail: str = ""


def _walk_files(root: Path) -> Iterator[Path]:
    """Yield all regular files under *root*, depth-first."""
    if not root.is_dir():
        return
    for entry in root.rglob("*"):
        if entry.is_file():
            yield entry


def find_executable_in_dir(path: str, expected_names: tuple[str, ...]) -> Path | None:
    """Return the first file under *path* whose name matches *expected_names*."""
    root = Path(path)
    if not root.is_dir():
        return None
    for file_path in _walk_files(root):
        if file_path.name in expected_names:
            return file_path
    return None


def find_vgmstream_cli(vgmstream_path: str) -> Path | None:
    """Find the vgmstream CLI executable in the configured directory.

    Only searches for CLI binaries — shared libraries (``libvgmstream.so``, etc.)
    cannot be executed directly.
    """
    return find_executable_in_dir(vgmstream_path, _VGMSTREAM_CLI_NAMES)


def validate_vgmstream_path(vgmstream_path: str) -> _VgmstreamResult:
    """Validate a vgmstream directory, returning one of READY, LIBRARY_ONLY, or NOT_FOUND."""
    if not vgmstream_path or not Path(vgmstream_path).is_dir():
        return _VgmstreamResult(status=VgmstreamValidation.NOT_FOUND)

    # First, look for the CLI executable
    cli_path = find_executable_in_dir(vgmstream_path, _VGMSTREAM_CLI_NAMES)
    if cli_path is not None:
        return _VgmstreamResult(
            status=VgmstreamValidation.READY,
            path=str(cli_path),
            detail=f"Ready: {cli_path}",
        )

    # Fall back: check for shared library (validates the directory
    # but user needs CLI for actual playback)
    lib_path = find_executable_in_dir(vgmstream_path, _VGMSTREAM_LIB_NAMES)
    if lib_path is not None:
        parent = lib_path.parent
        return _VgmstreamResult(
            status=VgmstreamValidation.LIBRARY_ONLY,
            path=str(lib_path),
            detail=f"Found shared library, need vgmstream-cli executable in: {parent}",
        )

    return _VgmstreamResult(status=VgmstreamValidation.NOT_FOUND)
