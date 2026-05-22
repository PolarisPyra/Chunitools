from __future__ import annotations

from src.core.audio_assets import resolve_chart_audio_path, resolve_chart_awb_path
from src.core.editor_metadata import save_editor_metadata
from src.core.metadata import load_chart_file
from src.core.models import Chart, ChartMetadata


def test_resolve_chart_awb_path_uses_cue_file_metadata(tmp_path) -> None:
    cue_dir = tmp_path / "A283" / "cueFile" / "cueFile002963"
    cue_dir.mkdir(parents=True)
    awb_path = cue_dir / "music2963.awb"
    awb_path.write_bytes(b"AFS2")
    (cue_dir / "CueFile.xml").write_text(
        """
        <CueFileData>
          <awbFile>
            <path>music2963.awb</path>
          </awbFile>
        </CueFileData>
        """,
        encoding="utf-8",
    )
    chart = Chart(metadata=ChartMetadata(music_id="2963"))

    assert resolve_chart_awb_path(chart, tmp_path) == awb_path


def test_resolve_chart_awb_path_returns_none_for_missing_music_id(tmp_path) -> None:
    chart = Chart(metadata=ChartMetadata(music_id=""))

    assert resolve_chart_awb_path(chart, tmp_path) is None


def test_resolve_chart_audio_path_prefers_custom_audio_relative_to_chart(tmp_path) -> None:
    chart_dir = tmp_path / "custom"
    chart_dir.mkdir()
    audio_path = chart_dir / "song.flac"
    audio_path.write_bytes(b"fLaC")
    chart_path = chart_dir / "custom.c2s"
    chart = Chart(metadata=ChartMetadata(music_id="2963", audio_path="song.flac"))
    chart_path.write_text("MUSIC\t2963\n", encoding="utf-8")
    save_editor_metadata(chart, chart_path)

    assert resolve_chart_audio_path(chart, tmp_path, chart_path) == audio_path


def test_load_chart_file_infers_music_id_when_header_uses_zero(tmp_path) -> None:
    chart_path = tmp_path / "2963_03.c2s"
    chart_path.write_text(
        "\n".join(
            [
                "MUSIC\t0",
                "BPM_DEF\t120.000\t120.000\t120.000\t120.000",
                "RESOLUTION\t384",
            ]
        ),
        encoding="utf-8",
    )

    chart = load_chart_file(chart_path)

    assert chart.metadata.music_id == "2963"
