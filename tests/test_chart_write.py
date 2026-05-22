from __future__ import annotations

from pathlib import Path

from src.core.const import NoteType
from src.core.editor import add_note, make_note, snap_abs_pos
from src.core.read import load_chart_file, parse_c2s
from src.core.write import create_blank_chart, save_chart_file, serialize_c2s, serialize_music_xml


def test_blank_chart_serializes_to_parseable_c2s() -> None:
    chart = create_blank_chart()
    chart.metadata.audio_path = "song.wav"
    text = serialize_c2s(chart)

    parsed = parse_c2s(text)

    assert "VERSION\t1.13.00\t1.13.00" in text
    assert "MUSIC\t0" in text
    assert "DIFFICULT\t03" in text
    assert "AUDIO\t" not in text
    assert "MUSICID\t" not in text
    assert "TITLE\t" not in text
    assert "ARTIST\t" not in text
    assert parsed.metadata.title == ""
    assert parsed.metadata.difficulty == "MASTER"
    assert parsed.metadata.level == "1"
    assert parsed.metadata.resolution == 384
    assert parsed.metadata.audio_path == ""
    assert parsed.bpms == [{"measure": 0, "offset": 0, "bpm": 120.0}]
    assert parsed.signatures == [{"measure": 0, "numerator": 4, "denominator": 4}]


def test_editor_note_placement_round_trips(tmp_path: Path) -> None:
    chart = create_blank_chart()
    measure, offset = snap_abs_pos(1.26, chart.metadata.resolution, 4)
    add_note(
        chart,
        make_note(
            NoteType.HLD,
            measure=measure,
            offset=offset,
            cell=3,
            width=2,
            duration=192,
        ),
    )
    output_path = tmp_path / "custom.c2s"

    save_chart_file(chart, output_path)
    parsed = parse_c2s(output_path.read_text(encoding="utf-8"))

    assert len(parsed.notes) == 1
    assert parsed.notes[0].note_type == NoteType.HLD
    assert parsed.notes[0].measure == 1
    assert parsed.notes[0].offset == 96
    assert parsed.notes[0].cell == 3
    assert parsed.notes[0].width == 2
    assert parsed.notes[0].duration == 192


def test_save_chart_file_writes_editor_metadata_sidecar(tmp_path: Path) -> None:
    chart = create_blank_chart()
    chart.metadata.audio_path = "song.flac"
    chart.metadata.jacket_path = "jacket.dds"
    chart.editor["option_folder"] = "A999"
    output_path = tmp_path / "custom.c2s"
    (tmp_path / "song.flac").write_bytes(b"fLaC")

    save_chart_file(chart, output_path)

    c2s_text = output_path.read_text(encoding="utf-8")
    editor_text = (tmp_path / "custom.json").read_text(encoding="utf-8")
    loaded = load_chart_file(output_path)

    assert "AUDIO\t" not in c2s_text
    assert not (tmp_path / "editor.json").exists()
    assert '"audio_path": "song.flac"' in editor_text
    assert '"jacket_path": "jacket.dds"' in editor_text
    assert '"option_folder": "A999"' in editor_text
    assert loaded.metadata.audio_path == str(tmp_path / "song.flac")
    assert loaded.metadata.jacket_path == "jacket.dds"
    assert loaded.editor["option_folder"] == "A999"


def test_save_chart_file_copies_external_assets_next_to_chart(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "saved"
    source_dir.mkdir()
    audio_path = source_dir / "song.wav"
    jacket_path = source_dir / "cover.png"
    audio_path.write_bytes(b"RIFF")
    jacket_path.write_bytes(b"PNG")
    chart = create_blank_chart()
    chart.metadata.audio_path = str(audio_path)
    chart.metadata.jacket_path = str(jacket_path)
    output_path = output_dir / "e.c2s"

    save_chart_file(chart, output_path)

    editor_text = (output_dir / "e.json").read_text(encoding="utf-8")
    assert (output_dir / "song.wav").read_bytes() == b"RIFF"
    assert (output_dir / "cover.png").read_bytes() == b"PNG"
    assert '"audio_path": "song.wav"' in editor_text
    assert '"jacket_path": "cover.png"' in editor_text
    assert chart.metadata.audio_path == "song.wav"
    assert chart.metadata.jacket_path == "cover.png"


def test_save_chart_file_copies_relative_assets_from_previous_chart_dir(tmp_path: Path) -> None:
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    audio_path = old_dir / "song.flac"
    jacket_path = old_dir / "jacket.jpg"
    audio_path.write_bytes(b"fLaC")
    jacket_path.write_bytes(b"JPEG")
    chart = create_blank_chart()
    chart.metadata.audio_path = "song.flac"
    chart.metadata.jacket_path = "jacket.jpg"

    save_chart_file(chart, new_dir / "renamed.c2s", source_chart_path=old_dir / "old.c2s")

    assert (new_dir / "renamed.json").exists()
    assert (new_dir / "song.flac").read_bytes() == b"fLaC"
    assert (new_dir / "jacket.jpg").read_bytes() == b"JPEG"


def test_music_xml_writer_uses_chart_metadata() -> None:
    chart = create_blank_chart()
    chart.metadata.music_id = "1234"
    chart.metadata.title = "Custom Song"
    chart.metadata.artist = "Custom Artist"
    chart.metadata.difficulty = "EXPERT"
    chart.metadata.difficulty_id = 2
    chart.metadata.level = "12+"
    chart.metadata.jacket_path = "/tmp/CHU_UI_Jacket_1234.dds"
    chart.metadata.audio_path = "custom.flac"

    xml_text = serialize_music_xml(chart, "1234_02.c2s")
    c2s_text = serialize_c2s(chart)

    assert "<id>1234</id>" in xml_text
    assert "<str>Custom Song</str>" in xml_text
    assert "<str>Custom Artist</str>" in xml_text
    assert "<path>1234_02.c2s</path>" in xml_text
    assert "<path>CHU_UI_Jacket_1234.dds</path>" in xml_text
    assert "<str>Expert</str>" in xml_text
    assert "<data>EXPERT</data>" in xml_text
    assert "<level>12</level>" in xml_text
    assert "<levelDecimal>50</levelDecimal>" in xml_text
    assert "AUDIO\tcustom.flac" not in c2s_text
