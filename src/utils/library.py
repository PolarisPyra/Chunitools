"""Song library scanning and indexing from CHUNITHM data directories."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from src.core.read import discover_chart_files, load_chart_file

__all__ = [
    "ChartIndexEntry",
    "ChartIndex",
    "DataScanner",
    "DirectoryParseResult",
    "FumenInfo",
    "MetadataPreview",
    "SongInfo",
    "build_index",
]

DEFAULT_SONG_NAME = "Unknown"
DEFAULT_ARTIST_NAME = "Unknown"
MUSIC_XML_PATTERN = "**/Music.xml"
TRUE_TEXT = "true"


# ── Library models ────────────────────────────────────────────────────────────


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


class MetadataPreview(dict):
    """Small metadata subset used by the chart picker preview."""

    def __init__(
        self,
        bpm_def: list[str] | None = None,
        creator: str | None = None,
        version: str | None = None,
    ) -> None:
        super().__init__(
            bpm_def=bpm_def,
            creator=creator,
            version=version,
        )


# ── XML helpers ───────────────────────────────────────────────────────────────


def _node_text(parent: ET.Element, path: str, default: str = "") -> str:
    node = parent.find(path)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _node_int(parent: ET.Element, path: str, default: int = 0) -> int:
    value = _node_text(parent, path)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


# ── DataScanner ───────────────────────────────────────────────────────────────


class DataScanner:
    """Scan CHUNITHM data folders and parse song metadata from Music.xml files."""

    def __init__(self, data_root: str) -> None:
        self.data_root = Path(data_root)

    def scan(self) -> list[SongInfo]:
        """Scan the data root for Music.xml files and parse song metadata."""
        if not self.data_root.exists() or not self.data_root.is_dir():
            return []

        xml_paths = sorted(self.data_root.glob(MUSIC_XML_PATTERN))
        if not xml_paths:
            return []

        with ThreadPoolExecutor() as executor:
            songs = list(executor.map(self._parse_music_xml, xml_paths))

        return [s for s in songs if s is not None]

    def _parse_music_xml(self, xml_path: Path) -> SongInfo | None:
        try:
            root = ET.parse(xml_path).getroot()
        except (ET.ParseError, OSError):
            return None

        base_dir = xml_path.parent
        jacket_file = _node_text(root, "jaketFile/path")
        song = SongInfo(
            song_id=_node_text(root, "name/id"),
            name=_node_text(root, "name/str", DEFAULT_SONG_NAME),
            artist=_node_text(root, "artistName/str", DEFAULT_ARTIST_NAME),
            folder_name=base_dir.name,
            jacket_path=str(base_dir / jacket_file) if jacket_file else "",
            base_dir=str(base_dir),
        )

        fumens_node = root.find("fumens")
        if fumens_node is not None:
            for fumen_node in fumens_node.findall("MusicFumenData"):
                fumen = self._parse_fumen(fumen_node, base_dir)
                if fumen is not None:
                    song.fumens.append(fumen)

        song.fumens.sort(key=lambda fumen: fumen.difficulty)
        return song

    def _parse_fumen(self, fumen_node: ET.Element, base_dir: Path) -> FumenInfo | None:
        enabled = _node_text(fumen_node, "enable") == TRUE_TEXT
        file_path = _node_text(fumen_node, "file/path")
        if not enabled or not file_path:
            return None

        return FumenInfo(
            fumen_type=_node_text(fumen_node, "type/str"),
            difficulty=_node_int(fumen_node, "type/id"),
            level=_node_int(fumen_node, "level"),
            level_decimal=_node_int(fumen_node, "levelDecimal"),
            file_path=str(base_dir / file_path),
            enabled=enabled,
        )


# ── Chart indexing ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class ChartIndexEntry:
    path: Path
    music_id: str
    title: str
    difficulty: str
    notes: int
    warnings: int


@dataclass(slots=True)
class ChartIndex:
    entries: list[ChartIndexEntry]
    failures: list[tuple[Path, str]]


def build_index(
    data_dir: str | Path,
    *,
    parse_metadata: bool = True,
    suffixes: tuple[str, ...] = (".c2s",),
) -> ChartIndex:
    """Build a chart index from candidates in *data_dir*."""
    entries: list[ChartIndexEntry] = []
    failures: list[tuple[Path, str]] = []
    for path in discover_chart_files(data_dir, suffixes=suffixes):
        if not parse_metadata:
            entries.append(
                ChartIndexEntry(
                    path=path,
                    music_id="",
                    title=path.stem,
                    difficulty="",
                    notes=0,
                    warnings=0,
                )
            )
            continue
        try:
            chart = load_chart_file(path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            failures.append((path, str(exc)))
            continue
        entries.append(
            ChartIndexEntry(
                path=path,
                music_id=getattr(chart.metadata, "music_id", ""),
                title=getattr(chart.metadata, "title", "") or path.stem,
                difficulty=getattr(chart.metadata, "difficulty", ""),
                notes=len(chart.notes),
                warnings=len(chart.warnings),
            )
        )
    return ChartIndex(entries=entries, failures=failures)
