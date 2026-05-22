"""Library metadata types shared by scanning and picker modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

__all__ = [
    "DirectoryParseResult",
    "FumenInfo",
    "MetadataPreview",
    "SongInfo",
]


@dataclass(slots=True)
class FumenInfo:
    """Detailed information about a single chart file in the song library."""

    fumen_type: str
    difficulty: int
    level: int
    level_decimal: int
    file_path: str
    enabled: bool


@dataclass(slots=True)
class SongInfo:
    """Metadata for a song discovered in the CHUNITHM data folders."""

    song_id: str
    name: str
    artist: str
    folder_name: str
    jacket_path: str
    base_dir: str
    fumens: list[FumenInfo] = field(default_factory=list)


@dataclass(slots=True)
class DirectoryParseResult:
    """Stats for a bulk chart parsing operation."""

    total_files: int = 0
    parsed_files: int = 0
    failed_files: list[tuple[Path, str]] = field(default_factory=list)
    total_notes: int = 0
    total_warnings: int = 0


class MetadataPreview(TypedDict):
    """Small metadata subset used by the chart picker preview."""

    bpm_def: list[str] | None
    creator: str | None
    version: str | None
