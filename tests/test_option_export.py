from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image
from PyCriCodecsEx.utf import UTF

from src.core.audio_assets import resolve_chart_awb_path
from src.core.option_export import OptionExportError, export_option_folder, verify_option_folder
from src.core.read import parse_c2s
from src.core.write import create_blank_chart, serialize_music_xml
from src.lib.sonic_audio_tools import extract_afs2_header, parse_afs2


def test_option_folder_export_writes_official_style_layout(tmp_path: Path) -> None:
    chart = create_blank_chart()
    chart.metadata.music_id = "2821"
    chart.metadata.title = "Export Song"
    chart.metadata.artist = "Export Artist"
    chart.metadata.difficulty = "EXPERT"
    chart.metadata.difficulty_id = 2
    chart.metadata.level = "12+"
    chart.metadata.audio_path = str(tmp_path / "source.awb")
    chart.metadata.jacket_path = str(tmp_path / "jacket.png")
    Path(chart.metadata.audio_path).write_bytes(b"AFS2")
    Path(chart.metadata.audio_path).with_suffix(".acb").write_bytes(b"ACB")
    Image.new("RGB", (32, 48), "blue").save(chart.metadata.jacket_path)

    result = export_option_folder(chart, tmp_path / "exports", option_folder_name="A999")

    assert result.option_root == tmp_path / "exports" / "A999"
    assert result.chart_path == result.music_dir / "2821_02.c2s"
    assert result.music_xml_path == result.music_dir / "Music.xml"
    assert result.jacket_path == result.music_dir / "CHU_UI_Jacket_2821.dds"
    assert result.cue_file_xml_path == result.cue_dir / "CueFile.xml"
    assert result.awb_path == result.cue_dir / "music2821.awb"
    assert result.acb_path == result.cue_dir / "music2821.acb"
    assert (result.option_root / "data.conf").exists()

    parsed = parse_c2s(result.chart_path.read_text(encoding="utf-8"))
    assert parsed.metadata.music_id == "2821"
    assert parsed.metadata.sequence_id == "2821_02"
    assert parsed.metadata.audio_path == ""
    assert resolve_chart_awb_path(parsed, tmp_path / "exports") == result.awb_path

    music_xml = result.music_xml_path.read_text(encoding="utf-8")
    cue_xml = result.cue_file_xml_path.read_text(encoding="utf-8")
    assert "<dataName>music2821</dataName>" in music_xml
    assert "<path>2821_02.c2s</path>" in music_xml
    assert "<path>CHU_UI_Jacket_2821.dds</path>" in music_xml
    assert "<path>music2821.awb</path>" in cue_xml
    assert "<path>music2821.acb</path>" in cue_xml
    assert verify_option_folder(result.option_root).ok


def test_option_folder_export_rejects_non_awb_audio_without_python_hca_encoder(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import src.core.option_export as option_export

    chart = create_blank_chart()
    chart.metadata.music_id = "2822"
    chart.metadata.audio_path = str(tmp_path / "song.wav")
    Path(chart.metadata.audio_path).write_bytes(b"RIFF")
    monkeypatch.setattr(option_export, "hca_encoder_available", lambda: False)

    with pytest.raises(OptionExportError, match="requires PyCriCodecsEx"):
        export_option_folder(chart, tmp_path / "exports", option_folder_name="A999")
    assert not (tmp_path / "exports" / "A999").exists()


def test_option_folder_export_rejects_awb_without_acb(tmp_path: Path) -> None:
    chart = create_blank_chart()
    chart.metadata.music_id = "2826"
    chart.metadata.audio_path = str(tmp_path / "source.awb")
    Path(chart.metadata.audio_path).write_bytes(b"AFS2")

    with pytest.raises(OptionExportError, match="sibling .acb"):
        export_option_folder(chart, tmp_path / "exports", option_folder_name="A999")


def test_option_folder_verifier_reports_missing_cue_assets(tmp_path: Path) -> None:
    chart = create_blank_chart()
    chart.metadata.music_id = "2828"
    chart.metadata.audio_path = str(tmp_path / "source.awb")
    Path(chart.metadata.audio_path).write_bytes(b"AFS2")
    Path(chart.metadata.audio_path).with_suffix(".acb").write_bytes(b"ACB")
    result = export_option_folder(chart, tmp_path / "exports", option_folder_name="A999")
    result.awb_path.unlink()

    validation = verify_option_folder(result.option_root)

    assert not validation.ok
    assert any("missing AWB file" in error for error in validation.errors)


def test_option_folder_export_uses_python_sonic_audio_tools_for_hca_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    template_acb = next(
        Path("/home/polaris/Documents/Projects/Arcade/resources/chunithm/charts").glob(
            "A*/cueFile/cueFile*/music*.acb"
        )
    )
    chart = create_blank_chart()
    chart.metadata.music_id = "2824"
    chart.metadata.audio_path = str(tmp_path / "song.hca")
    real_hca = next(
        Path("/home/polaris/Documents/Projects/Arcade/resources/chunithm/charts").glob(
            "A*/cueFile/cueFile*/music*.awb"
        )
    )
    awb = parse_afs2(real_hca.read_bytes())
    Path(chart.metadata.audio_path).write_bytes(awb.entries[0].data)

    result = export_option_folder(
        chart,
        tmp_path / "exports",
        option_folder_name="A999",
        atomcraft_project=template_acb,
    )

    assert result.awb_path == result.cue_dir / "music2824.awb"
    assert result.acb_path == result.cue_dir / "music2824.acb"
    awb = parse_afs2(result.awb_path.read_bytes())
    assert awb.version == 1
    assert awb.align == 32
    assert awb.entries[0].id == 0
    acb = UTF(str(result.acb_path), recursive=True)
    row = acb.dictarray[0]
    assert row["Name"][1] == "music2824"
    assert row["StreamAwbHash"][1][0]["Name"][1] == "music2824"
    assert row["StreamAwbHash"][1][0]["Hash"][1] == hashlib.md5(
        result.awb_path.read_bytes()
    ).digest()
    assert row["StreamAwbAfs2Header"][1][0]["Header"][1] == extract_afs2_header(
        result.awb_path.read_bytes()
    )
    waveform = row["WaveformTable"][1][0]
    assert waveform["EncodeType"][1] == 2
    assert waveform["Streaming"][1] == 1
    assert waveform["StreamAwbId"][1] == 0


def test_source_audio_export_requires_acb_template(tmp_path: Path) -> None:
    chart = create_blank_chart()
    chart.metadata.music_id = "2825"
    chart.metadata.audio_path = str(tmp_path / "song.hca")
    Path(chart.metadata.audio_path).write_bytes(b"HCA\x00payload")

    with pytest.raises(OptionExportError, match="ACB"):
        export_option_folder(chart, tmp_path / "exports", option_folder_name="A999")


def test_music_xml_writer_emits_all_official_fumen_slots() -> None:
    chart = create_blank_chart()
    chart.metadata.music_id = "2823"
    chart.metadata.difficulty = "ULTIMA"
    chart.metadata.difficulty_id = 4

    xml_text = serialize_music_xml(chart, "2823_04.c2s", "CHU_UI_Jacket_2823.dds")

    assert xml_text.count("<MusicFumenData>") == 6
    assert "<dataName>music2823</dataName>" in xml_text
    assert "<path>2823_04.c2s</path>" in xml_text
    assert "<str>Ultima</str>" in xml_text
    assert "<data>ULTIMA</data>" in xml_text
