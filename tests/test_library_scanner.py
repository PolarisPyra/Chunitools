from __future__ import annotations

from pathlib import Path

from src.core.library_scanner import DataScanner
from src.core.metadata import DataScanner as MetadataDataScanner

MUSIC_XML = """<?xml version="1.0" encoding="utf-8"?>
<MusicData>
  <name>
    <id>1000</id>
    <str>Scanner Song</str>
  </name>
  <artistName>
    <str>Scanner Artist</str>
  </artistName>
  <jaketFile>
    <path>jacket.png</path>
  </jaketFile>
  <fumens>
    <MusicFumenData>
      <enable>true</enable>
      <file>
        <path>1000_03.c2s</path>
      </file>
      <type>
        <id>3</id>
        <str>MASTER</str>
      </type>
      <level>13</level>
      <levelDecimal>5</levelDecimal>
    </MusicFumenData>
    <MusicFumenData>
      <enable>false</enable>
      <file>
        <path>1000_00.c2s</path>
      </file>
      <type>
        <id>0</id>
        <str>BASIC</str>
      </type>
      <level>1</level>
      <levelDecimal>0</levelDecimal>
    </MusicFumenData>
  </fumens>
</MusicData>
"""


def test_data_scanner_parses_enabled_fumens(tmp_path: Path) -> None:
    music_dir = tmp_path / "A000" / "music" / "music0000"
    music_dir.mkdir(parents=True)
    (music_dir / "Music.xml").write_text(MUSIC_XML, encoding="utf-8")

    songs = DataScanner(str(tmp_path)).scan()

    assert len(songs) == 1
    assert songs[0].name == "Scanner Song"
    assert songs[0].artist == "Scanner Artist"
    assert songs[0].jacket_path == str(music_dir / "jacket.png")
    assert len(songs[0].fumens) == 1
    assert songs[0].fumens[0].file_path == str(music_dir / "1000_03.c2s")


def test_metadata_reexports_data_scanner() -> None:
    assert MetadataDataScanner is DataScanner
