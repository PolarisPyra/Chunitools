"""Export editor-created charts into CHUNITHM-style option folders."""

from __future__ import annotations

import copy
import shutil
import tempfile
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from src.core.images import SUPPORTED_JACKET_SOURCE_SUFFIXES, convert_jacket_image_to_dds
from src.core.models import Chart
from src.core.read import parse_c2s
from src.core.write import save_chart_file, serialize_music_xml
from src.audio.codecs import (
    Afs2Entry,
    HcaEncodeError,
    build_afs2,
    encode_source_to_hca,
    extract_afs2_header,
    hca_encoder_available,
    read_hca_info,
    retarget_acb_template,
)


class AudioExportStrategy(ABC):
    """Abstract strategy for exporting audio into an option folder."""

    @abstractmethod
    def export(
        self, chart: Chart, cue_dir: Path, source: Path, hca_key: int
    ) -> tuple[Path, Path | None]:
        """Export audio and return (awb_path, acb_path)."""

    @abstractmethod
    def preflight(self, source: Path, hca_key: int) -> None:
        """Validate that export can proceed; raise OptionExportError if not."""


class DirectAwbStrategy(AudioExportStrategy):
    """Copies an existing .awb + .acb pair directly."""

    def preflight(self, source: Path, hca_key: int) -> None:
        acb_source = source.with_suffix(".acb")
        if not acb_source.exists() or not acb_source.is_file():
            raise OptionExportError("AWB option export requires a sibling .acb file")

    def export(
        self, chart: Chart, cue_dir: Path, source: Path, hca_key: int
    ) -> tuple[Path, Path | None]:
        awb_dest = cue_dir / f"music{chart.metadata.music_id}.awb"
        shutil.copy2(source, awb_dest)
        acb_source = source.with_suffix(".acb")
        acb_dest = cue_dir / f"music{chart.metadata.music_id}.acb"
        shutil.copy2(acb_source, acb_dest)
        return awb_dest, acb_dest


class EncodeAudioStrategy(AudioExportStrategy):
    """Encodes source audio (WAV/MP3/FLAC/HCA) into an AWB+ACB pair."""

    def preflight(self, source: Path, hca_key: int) -> None:
        if source.suffix.lower() != ".hca" and not hca_encoder_available():
            raise OptionExportError(
                "WAV/AIFF/MP3/FLAC option export requires PyCriCodecsEx for Python HCA "
                "encoding, or an already encoded .hca/.awb source"
            )
        needs_ffmpeg = source.suffix.lower() in {".mp3", ".flac", ".aif", ".aiff"}
        if needs_ffmpeg and shutil.which("ffmpeg") is None:
            raise OptionExportError("MP3/FLAC/AIFF option export requires ffmpeg and PyCriCodecsEx")
        if hca_key < 0:
            raise OptionExportError("HCA key must be zero or a positive integer")

    def export(
        self, chart: Chart, cue_dir: Path, source: Path, hca_key: int
    ) -> tuple[Path, Path | None]:
        awb_dest = cue_dir / f"music{chart.metadata.music_id}.awb"
        acb_dest = cue_dir / f"music{chart.metadata.music_id}.acb"
        template_acb = _resolve_audio_template_acb(None, source)
        with tempfile.TemporaryDirectory(prefix="chunitools-audio-") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            try:
                hca_path = encode_source_to_hca(
                    source, temp_dir / f"music{chart.metadata.music_id}.hca", key=hca_key,
                )
            except HcaEncodeError as exc:
                raise OptionExportError(str(exc)) from exc
            hca_info = read_hca_info(hca_path)
            awb_data = build_afs2([Afs2Entry(id=0, data=hca_path.read_bytes())])
            awb_dest.write_bytes(awb_data)
            retarget_acb_template(
                template_acb, acb_dest,
                music_id=chart.metadata.music_id,
                hca_info=hca_info,
                awb_data=awb_data,
                awb_header=extract_afs2_header(awb_data),
            )
        if not awb_dest.exists():
            raise OptionExportError("Python SonicAudioTools export did not produce an AWB file")
        if not acb_dest.exists():
            raise OptionExportError("Python SonicAudioTools export did not produce an ACB file")
        return awb_dest, acb_dest


@dataclass(frozen=True)
class OptionExportResult:
    option_root: Path
    music_dir: Path
    cue_dir: Path
    chart_path: Path
    music_xml_path: Path
    cue_file_xml_path: Path
    jacket_path: Path | None
    awb_path: Path
    acb_path: Path | None


class OptionExportError(ValueError):
    """Raised when a chart cannot be exported as a game option folder."""


@dataclass(frozen=True)
class OptionFolderValidation:
    option_root: Path
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def export_option_folder(
    chart: Chart,
    output_root: str | Path,
    *,
    option_folder_name: str = "",
    audio_path: str | Path | None = None,
    jacket_path: str | Path | None = None,
    atomcraft_project: str | Path | None = None,
    hca_key: str | int | None = None,
) -> OptionExportResult:
    """Create an option folder containing Music.xml, .c2s, CueFile.xml, and assets.

    The exporter can package an existing AWB/ACB pair directly. It can also
    encode WAV/MP3/FLAC/AIFF/HCA through the local Python SonicAudioTools layer,
    using an existing ACB as the cue-sheet template.
    """
    music_id_text = _music_id_text(chart)
    option_root = _resolve_option_root(output_root, option_folder_name)
    music_dir = option_root / "music" / f"music{music_id_text}"
    cue_dir = option_root / "cueFile" / f"cueFile{int(music_id_text):06d}"
    source_audio_path = audio_path or chart.metadata.audio_path
    parsed_hca_key = _parse_hca_key(hca_key)
    _preflight_audio_export(source_audio_path, atomcraft_project, parsed_hca_key)
    music_dir.mkdir(parents=True, exist_ok=True)
    cue_dir.mkdir(parents=True, exist_ok=True)

    export_chart = copy.deepcopy(chart)
    export_chart.metadata.music_id = music_id_text
    diff_id = _difficulty_id(export_chart)
    chart_filename = f"{music_id_text}_{diff_id:02d}.c2s"
    export_chart.metadata.sequence_id = f"{music_id_text}_{diff_id:02d}"
    export_chart.metadata.audio_path = ""

    jacket_output = _export_jacket(export_chart, music_dir, jacket_path)
    if jacket_output is not None:
        export_chart.metadata.jacket_path = jacket_output.name

    chart_path = music_dir / chart_filename
    save_chart_file(export_chart, chart_path)

    music_xml_path = music_dir / "Music.xml"
    jacket_filename = jacket_output.name if jacket_output else ""
    music_xml_path.write_text(
        serialize_music_xml(export_chart, chart_filename, jacket_filename),
        encoding="utf-8",
    )

    awb_path, acb_path = _export_audio(
        export_chart,
        cue_dir,
        source_audio_path,
        atomcraft_project,
        parsed_hca_key,
    )
    cue_file_xml_path = cue_dir / "CueFile.xml"
    acb_filename = acb_path.name if acb_path else ""
    cue_file_xml_path.write_text(
        serialize_cue_file_xml(music_id_text, awb_path.name, acb_filename),
        encoding="utf-8",
    )

    _write_data_conf(option_root)
    return OptionExportResult(
        option_root=option_root,
        music_dir=music_dir,
        cue_dir=cue_dir,
        chart_path=chart_path,
        music_xml_path=music_xml_path,
        cue_file_xml_path=cue_file_xml_path,
        jacket_path=jacket_output,
        awb_path=awb_path,
        acb_path=acb_path,
    )


def verify_option_folder(option_root: str | Path) -> OptionFolderValidation:
    """Validate the generated option-folder structure without launching the game."""
    root = Path(option_root).expanduser()
    errors: list[str] = []
    if not root.exists() or not root.is_dir():
        return OptionFolderValidation(root, (f"option folder does not exist: {root}",))

    music_xml_files = sorted(root.glob("music/music*/Music.xml"))
    cue_xml_files = sorted(root.glob("cueFile/cueFile*/CueFile.xml"))
    if not music_xml_files:
        errors.append("missing music/music*/Music.xml")
    if not cue_xml_files:
        errors.append("missing cueFile/cueFile*/CueFile.xml")

    for music_xml in music_xml_files:
        _validate_music_xml(root, music_xml, errors)
    for cue_xml in cue_xml_files:
        _validate_cue_file_xml(root, cue_xml, errors)

    return OptionFolderValidation(root, tuple(errors))


def serialize_cue_file_xml(music_id: str, awb_filename: str, acb_filename: str = "") -> str:
    """Serialize CueFile.xml so it matches the exported AWB name."""
    normalized_id = str(int(music_id))
    root = ET.Element(
        "CueFileData",
        {
            "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        },
    )
    _text_node(root, "dataName", f"cueFile{int(normalized_id):06d}")
    _string_id(root, "name", normalized_id, f"music{normalized_id}", "")
    if acb_filename:
        _text_node(root, "acbFile/path", acb_filename)
    _text_node(root, "awbFile/path", awb_filename)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(
        root,
        encoding="unicode",
        short_empty_elements=False,
    )


def _validate_music_xml(root: Path, music_xml: Path, errors: list[str]) -> None:
    try:
        music_root = ET.parse(music_xml).getroot()
    except (ET.ParseError, OSError) as exc:
        errors.append(f"invalid Music.xml: {music_xml.relative_to(root)} ({exc})")
        return

    jacket_path = (music_root.findtext("jaketFile/path") or "").strip()
    if jacket_path and not (music_xml.parent / jacket_path).is_file():
        errors.append(f"missing jacket file: {(music_xml.parent / jacket_path).relative_to(root)}")

    enabled_fumens = [
        fumen
        for fumen in music_root.findall("fumens/MusicFumenData")
        if (fumen.findtext("enable") or "").strip().lower() == "true"
    ]
    if not enabled_fumens:
        errors.append(f"Music.xml has no enabled fumen: {music_xml.relative_to(root)}")

    music_id = (music_root.findtext("name/id") or "").strip()
    for fumen in enabled_fumens:
        chart_name = (fumen.findtext("file/path") or "").strip()
        if not chart_name:
            errors.append(f"enabled fumen has no chart path: {music_xml.relative_to(root)}")
            continue

        chart_path = music_xml.parent / chart_name
        if not chart_path.is_file():
            errors.append(f"missing c2s chart: {chart_path.relative_to(root)}")
            continue

        try:
            chart = parse_c2s(chart_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            errors.append(f"invalid c2s chart: {chart_path.relative_to(root)} ({exc})")
            continue

        music_id_values = {music_id}
        if music_id.isdecimal():
            music_id_values.add(str(int(music_id)))
        if music_id and chart.metadata.music_id not in music_id_values:
            errors.append(f"chart music id mismatch: {chart_path.relative_to(root)}")


def _validate_cue_file_xml(root: Path, cue_xml: Path, errors: list[str]) -> None:
    try:
        cue_root = ET.parse(cue_xml).getroot()
    except (ET.ParseError, OSError) as exc:
        errors.append(f"invalid CueFile.xml: {cue_xml.relative_to(root)} ({exc})")
        return

    acb_name = (cue_root.findtext("acbFile/path") or "").strip()
    awb_name = (cue_root.findtext("awbFile/path") or "").strip()
    if not acb_name:
        errors.append(f"CueFile.xml has no acbFile/path: {cue_xml.relative_to(root)}")
    elif not (cue_xml.parent / acb_name).is_file():
        errors.append(f"missing ACB file: {(cue_xml.parent / acb_name).relative_to(root)}")

    if not awb_name:
        errors.append(f"CueFile.xml has no awbFile/path: {cue_xml.relative_to(root)}")
    elif not (cue_xml.parent / awb_name).is_file():
        errors.append(f"missing AWB file: {(cue_xml.parent / awb_name).relative_to(root)}")


def _music_id_text(chart: Chart) -> str:
    raw = (chart.metadata.music_id or "").strip()
    if not raw.isdecimal() or int(raw) <= 0:
        raise OptionExportError("set a positive numeric Music ID before exporting")
    return str(int(raw))


def _resolve_option_root(output_root: str | Path, option_folder_name: str) -> Path:
    root = Path(output_root).expanduser()
    folder_name = option_folder_name.strip()
    if folder_name:
        if any(part in {".", ".."} for part in Path(folder_name).parts):
            raise OptionExportError("option folder name must be a simple folder name")
        root = root / folder_name
    return root


def _difficulty_id(chart: Chart) -> int:
    if chart.metadata.difficulty_id:
        return int(chart.metadata.difficulty_id)
    difficulty_map = {
        "BASIC": 0,
        "ADVANCED": 1,
        "EXPERT": 2,
        "MASTER": 3,
        "WORLD'S END": 5,
        "ULTIMA": 4,
    }
    return difficulty_map.get(chart.metadata.difficulty.upper(), 3)


def _export_jacket(chart: Chart, music_dir: Path, jacket_path: str | Path | None) -> Path | None:
    source_value = str(jacket_path or chart.metadata.jacket_path or "").strip()
    if not source_value:
        return None

    source = Path(source_value).expanduser()
    if not source.exists():
        raise OptionExportError(f"jacket source does not exist: {source}")

    if source.suffix.lower() == ".dds":
        destination = music_dir / f"CHU_UI_Jacket_{chart.metadata.music_id}.dds"
        shutil.copy2(source, destination)
        return destination

    if source.suffix.lower() in SUPPORTED_JACKET_SOURCE_SUFFIXES:
        return convert_jacket_image_to_dds(source, music_dir, chart.metadata.music_id)

    raise OptionExportError("jacket source must be DDS, PNG, or JPEG")


def _resolve_audio_strategy(source: Path) -> AudioExportStrategy:
    """Return the appropriate export strategy for the source file."""
    if source.suffix.lower() == ".awb":
        return DirectAwbStrategy()
    return EncodeAudioStrategy()


def _export_audio(
    chart: Chart,
    cue_dir: Path,
    audio_path: str | Path | None,
    atomcraft_project: str | Path | None,
    hca_key: int,
) -> tuple[Path, Path | None]:
    source_value = str(audio_path or chart.metadata.audio_path or "").strip()
    if not source_value:
        raise OptionExportError("choose an existing AWB audio source before exporting")

    source = Path(source_value).expanduser()
    if not source.exists() or not source.is_file():
        raise OptionExportError(f"audio source does not exist: {source}")

    strategy = _resolve_audio_strategy(source)
    if isinstance(strategy, EncodeAudioStrategy) and atomcraft_project:
        _resolve_audio_template_acb(atomcraft_project, source)
    return strategy.export(chart, cue_dir, source, hca_key)


def _preflight_audio_export(
    audio_path: str | Path | None,
    atomcraft_project: str | Path | None,
    hca_key: int,
) -> None:
    source_value = str(audio_path or "").strip()
    if not source_value:
        raise OptionExportError("choose an existing AWB audio source before exporting")

    source = Path(source_value).expanduser()
    if not source.exists() or not source.is_file():
        raise OptionExportError(f"audio source does not exist: {source}")

    strategy = _resolve_audio_strategy(source)
    if isinstance(strategy, EncodeAudioStrategy):
        _resolve_audio_template_acb(atomcraft_project, source)
    strategy.preflight(source, hca_key)


def _resolve_audio_template_acb(
    atomcraft_project: str | Path | None,
    source: Path,
) -> Path:
    project_value = str(atomcraft_project or "").strip()
    if project_value:
        project_path = Path(project_value).expanduser()
        if not project_path.exists() or not project_path.is_file():
            raise OptionExportError(f"ACB template does not exist: {project_path}")
        if project_path.suffix.lower() != ".acb":
            raise OptionExportError("source-audio option export needs an existing .acb template")
        return project_path

    sibling_acb = source.with_suffix(".acb")
    if sibling_acb.is_file():
        return sibling_acb
    raise OptionExportError(
        "source-audio option export needs an existing .acb template because "
        "SonicAudioTools does not build ACB cue sheets from scratch"
    )


def _parse_hca_key(hca_key: str | int | None) -> int:
    if hca_key is None or hca_key == "":
        return 0
    if isinstance(hca_key, int):
        return hca_key
    try:
        return int(str(hca_key).strip(), 0)
    except ValueError as exc:
        raise OptionExportError("HCA key must be a decimal or 0x-prefixed integer") from exc


def _write_data_conf(option_root: Path) -> None:
    data_conf = option_root / "data.conf"
    if data_conf.exists():
        return
    data_conf.write_text(
        "\n".join(
            [
                "#-----------------------------------------------------------",
                "# data.conf AXXX option data",
                "#-----------------------------------------------------------",
                "",
                "[Version]",
                "Name = CHUNITHM",
                "VerMajor   = 2",
                "VerMinor   = 45",
                "VerRelease = 0",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _string_id(root: ET.Element, path: str, value_id: str, value_str: str, data: str) -> None:
    node = _ensure_path(root, path)
    _text_node(node, "id", value_id)
    _text_node(node, "str", value_str)
    _text_node(node, "data", data)


def _text_node(root: ET.Element, path: str, value: str) -> None:
    node = _ensure_path(root, path)
    node.text = value


def _ensure_path(root: ET.Element, path: str) -> ET.Element:
    current = root
    for part in path.split("/"):
        found = current.find(part)
        if found is None:
            found = ET.SubElement(current, part)
        current = found
    return current
