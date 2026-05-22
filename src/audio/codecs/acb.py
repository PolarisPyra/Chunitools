"""ACB template retargeting for CHUNITHM option exports."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path

from PyCriCodecsEx.utf import UTF, UTFBuilder

from src.audio.codecs.hca import HcaInfo


def retarget_acb_template(
    template_path: str | Path,
    destination_path: str | Path,
    *,
    music_id: str,
    hca_info: HcaInfo,
    awb_data: bytes,
    awb_header: bytes,
) -> Path:
    """Rewrite a known-good ACB template to point at the generated AWB.

    SonicAudioTools does not build ACB cue sheets from scratch. This keeps the
    original table shape and only updates fields tied to the new waveform.
    """
    template = UTF(str(Path(template_path).expanduser()), recursive=True)
    payload = deepcopy(template.dictarray)
    if not payload:
        raise ValueError("ACB template has no rows")

    row = payload[0]
    music_name = f"music{int(music_id):04d}"
    _set(row, "Name", music_name)
    _set_stream_awb_hash(row, music_name, awb_data)
    _set_stream_awb_header(row, awb_header)
    _set_waveform(row, hca_info)
    _set_cue_lengths(row, hca_info)

    rebuilt = UTFBuilder(
        payload,
        encoding=template.encoding,
        table_name=template.table_name,
    ).bytes()
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(bytes(rebuilt))
    return destination


def _set(row: dict, key: str, value: object) -> None:
    value_type, _old_value = row[key]
    row[key] = (value_type, value)


def _set_stream_awb_header(row: dict, awb_header: bytes) -> None:
    table_name, rows = row["StreamAwbAfs2Header"]
    if not rows:
        return
    header_type, _old_header = rows[0]["Header"]
    rows[0]["Header"] = (header_type, awb_header)
    row["StreamAwbAfs2Header"] = (table_name, rows)


def _set_stream_awb_hash(row: dict, music_name: str, awb_data: bytes) -> None:
    if "StreamAwbHash" not in row:
        return
    table_name, rows = row["StreamAwbHash"]
    if not rows:
        return
    if "Name" in rows[0]:
        _set(rows[0], "Name", music_name)
    if "Hash" in rows[0]:
        _set(rows[0], "Hash", hashlib.md5(awb_data).digest())
    row["StreamAwbHash"] = (table_name, rows)


def _set_waveform(row: dict, hca_info: HcaInfo) -> None:
    table_name, waveforms = row["WaveformTable"]
    if not waveforms:
        raise ValueError("ACB template has no waveform rows")
    waveform = waveforms[0]
    _set(waveform, "MemoryAwbId", 0xFFFF)
    _set(waveform, "EncodeType", 2)
    _set(waveform, "Streaming", 1)
    _set(waveform, "NumChannels", hca_info.channels)
    _set(waveform, "LoopFlag", 0)
    _set(waveform, "SamplingRate", hca_info.sample_rate)
    _set(waveform, "NumSamples", hca_info.sample_count)
    if "StreamAwbPortNo" in waveform:
        _set(waveform, "StreamAwbPortNo", 0)
    if "StreamAwbId" in waveform:
        _set(waveform, "StreamAwbId", 0)
    row["WaveformTable"] = (table_name, [waveform])


def _set_cue_lengths(row: dict, hca_info: HcaInfo) -> None:
    if hca_info.sample_rate <= 0 or "CueTable" not in row:
        return
    length_ms = round(hca_info.sample_count / hca_info.sample_rate * 1000)
    table_name, cues = row["CueTable"]
    if cues:
        length_type, _old_length = cues[0]["Length"]
        cues[0]["Length"] = (length_type, length_ms)
    row["CueTable"] = (table_name, cues)
