"""Song library scanning from CHUNITHM Music.xml files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from src.core.library_models import FumenInfo, SongInfo

__all__ = ["DataScanner"]

DEFAULT_SONG_NAME = "Unknown"
DEFAULT_ARTIST_NAME = "Unknown"
MUSIC_XML_PATTERN = "A*/music/*/Music.xml"
TRUE_TEXT = "true"


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


class DataScanner:
    """Scan CHUNITHM data folders and parse song metadata."""

    def __init__(self, data_root: str) -> None:
        self.data_root = Path(data_root)

    def scan(self) -> list[SongInfo]:
        """
        Scan the data root for Music.xml files and parse song metadata.
        
        Returns:
            A list of SongInfo objects discovered under the configured data root.
        """
        if not self.data_root.exists() or not self.data_root.is_dir():
            return []

        xml_paths = sorted(self.data_root.glob(MUSIC_XML_PATTERN))
        if not xml_paths:
            return []
        
        # Parallelize XML parsing to speed up large library scans
        from concurrent.futures import ThreadPoolExecutor
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
