"""Python HCA encoding adapter for the option exporter."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

try:  # pragma: no cover - availability is exercised through the adapter seams.
    from PyCriCodecsEx.hca import HCACodec
except ImportError:  # pragma: no cover
    HCACodec = None


class HcaEncodeError(ValueError):
    """Raised when source audio cannot be encoded to HCA."""


@dataclass(frozen=True)
class HcaInfo:
    channels: int
    sample_rate: int
    sample_count: int


def hca_encoder_available() -> bool:
    return HCACodec is not None


def encode_source_to_hca(
    source: str | Path,
    destination: str | Path,
    *,
    key: int = 0,
    subkey: int = 0,
) -> Path:
    """Encode or copy source audio into an HCA file without CRI executables."""
    source_path = Path(source).expanduser()
    destination_path = Path(destination)
    if not source_path.is_file():
        raise HcaEncodeError(f"audio source does not exist: {source_path}")

    if source_path.suffix.lower() == ".hca":
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        return destination_path

    wav_path = source_path
    with tempfile.TemporaryDirectory(prefix="chunitools-hca-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        if source_path.suffix.lower() != ".wav":
            wav_path = _convert_to_wav(source_path, temp_dir / "source.wav")
        _encode_wav(wav_path, destination_path, key=key, subkey=subkey)
    return destination_path


def read_hca_info(source: str | Path) -> HcaInfo:
    source_path = Path(source).expanduser()
    if HCACodec is None:
        raise HcaEncodeError("reading HCA metadata requires PyCriCodecsEx")
    try:
        codec = HCACodec(str(source_path))
    except Exception as exc:
        raise HcaEncodeError(f"could not read HCA metadata: {exc}") from exc
    frame_count = int(codec.hca.get("FrameCount", 0))
    delay = int(codec.hca.get("EncoderDelay", 0))
    padding = int(codec.hca.get("EncoderPadding", 0))
    sample_count = max(0, frame_count * 1024 - delay - padding)
    return HcaInfo(
        channels=int(codec.chnls),
        sample_rate=int(codec.sampling_rate),
        sample_count=sample_count,
    )


def read_wav_info(source: str | Path) -> HcaInfo:
    with wave.open(str(Path(source).expanduser()), "rb") as wav_file:
        return HcaInfo(
            channels=wav_file.getnchannels(),
            sample_rate=wav_file.getframerate(),
            sample_count=wav_file.getnframes(),
        )


def _encode_wav(wav_path: Path, destination_path: Path, *, key: int, subkey: int) -> None:
    if HCACodec is None:
        raise HcaEncodeError(
            "WAV/MP3/FLAC option export requires PyCriCodecsEx for Python HCA encoding, "
            "or an already encoded .hca/.awb source"
        )
    try:
        codec = HCACodec(str(wav_path), filename=destination_path.name, key=key, subkey=subkey)
        encoded = codec.get_encoded()
    except Exception as exc:
        raise HcaEncodeError(f"Python HCA encoder failed: {exc}") from exc

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(encoded)


def _convert_to_wav(source_path: Path, destination_path: Path) -> Path:
    if source_path.suffix.lower() not in {".mp3", ".flac", ".aif", ".aiff"}:
        raise HcaEncodeError("audio source must be AWB, HCA, WAV, AIFF, MP3, or FLAC")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise HcaEncodeError("MP3/FLAC/AIFF option export requires ffmpeg and PyCriCodecsEx")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source_path),
                "-acodec",
                "pcm_s16le",
                str(destination_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise HcaEncodeError(f"ffmpeg could not prepare WAV material: {exc}") from exc
    return destination_path
