"""Song playback for CHUNITHM AWB/HCA music banks."""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import wave
from array import array
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from types import TracebackType

from PySide6.QtCore import QIODevice, QObject, QTimer
from PySide6.QtMultimedia import QAudioFormat, QAudioSink

from src.core.config import DEFAULT_MUSIC_VOLUME

__all__ = ["MusicStreamPlayer"]

LOGGER = logging.getLogger(__name__)
DECODE_CHUNK_FRAMES = 4096
PUSH_INTERVAL_MILLISECONDS = 10
PCM16_BYTES_PER_SAMPLE = 2
MINIMUM_WRITE_BYTES = 1024
BUNDLED_CLI_DIR_NAME = "vgmstream"
FLAC_SUFFIX = ".flac"
WAV_SUFFIX = ".wav"
MP3_SUFFIX = ".mp3"
VGMSTREAM_SUFFIXES = {".awb", MP3_SUFFIX}


class VgmstreamError(RuntimeError):
    """Raised when vgmstream-cli cannot decode a music asset."""


class AudioSourceError(RuntimeError):
    """Raised when a custom chart audio source cannot be decoded."""


class _PcmAudioStream(Protocol):
    sample_rate: int
    channels: int
    play_samples: int

    def read_pcm16(self, frame_count: int) -> bytes:
        """Decode up to frame_count PCM16 frames from the current position."""
        ...

    def seek_samples(self, position: int) -> None:
        """Seek to an absolute sample position."""

    def close(self) -> None:
        """Release decoder resources."""

    def __enter__(self) -> _PcmAudioStream: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


# ---------------------------------------------------------------------------
# vgmstream-cli based decoder
# ---------------------------------------------------------------------------


def _vgmstream_cli_path() -> Path | None:
    """Return the configured vgmstream-cli path, or None if not found."""
    from src.config import settings
    from src.utils.audio import find_vgmstream_cli

    configured = getattr(settings, "vgstreamcli_path", "")
    if configured:
        cli = find_vgmstream_cli(configured)
        if cli is not None:
            return cli

    # Legacy fallback: bundled binary (PyInstaller or vendor/)
    exe_name = "vgmstream-cli.exe" if sys.platform == "win32" else "vgmstream-cli"
    bundle_root = Path(getattr(sys, "_MEIPASS", ""))
    if bundle_root:
        candidate = bundle_root / BUNDLED_CLI_DIR_NAME / exe_name
        if candidate.exists():
            return candidate

    platform_name = _platform_dir_name()
    candidate = (
        Path(__file__).resolve().parents[2]
        / "vendor"
        / BUNDLED_CLI_DIR_NAME
        / platform_name
        / exe_name
    )
    if candidate.exists():
        return candidate

    return None


class _VgmstreamCliStream:
    """Decode an AWB/MP3 file via vgmstream-cli into a temporary WAV, then stream it."""

    def __init__(self, source_path: Path) -> None:
        cli = _vgmstream_cli_path()
        if cli is None:
            raise VgmstreamError(
                "could not find vgmstream-cli; set vgstreamcli_path in Settings (Ctrl+,)"
            )

        # Decode to a temporary WAV file. We keep the temp file open so
        # _WavePcmStream can read it; it gets cleaned up in close().
        self._tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)  # noqa: SIM115
        tmp_path = Path(self._tmp.name)
        self._tmp.close()

        try:
            subprocess.run(
                [str(cli), "-o", str(tmp_path), str(source_path)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            tmp_path.unlink(missing_ok=True)
            stderr = exc.stderr.decode(errors="replace").strip()
            raise VgmstreamError(f"vgmstream-cli failed to decode {source_path}: {stderr}") from exc

        self._tmp_path = tmp_path
        self._wav = _WavePcmStream(tmp_path)
        self.sample_rate = self._wav.sample_rate
        self.channels = self._wav.channels
        self.play_samples = self._wav.play_samples

    def read_pcm16(self, frame_count: int) -> bytes:
        return self._wav.read_pcm16(frame_count)

    def seek_samples(self, position: int) -> None:
        self._wav.seek_samples(position)

    def close(self) -> None:
        self._wav.close()
        self._tmp_path.unlink(missing_ok=True)

    def __enter__(self) -> _VgmstreamCliStream:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


# ---------------------------------------------------------------------------
# WAV decoder
# ---------------------------------------------------------------------------


class _WavePcmStream:
    """Decode PCM WAV files into interleaved signed 16-bit frames."""

    def __init__(self, source_path: Path) -> None:
        try:
            self._wave = wave.open(str(source_path), "rb")  # noqa: SIM115
        except wave.Error as exc:
            raise AudioSourceError(f"could not read WAV file {source_path}: {exc}") from exc

        self._source_path = source_path
        self.sample_rate = self._wave.getframerate()
        self.channels = self._wave.getnchannels()
        self.play_samples = self._wave.getnframes()
        self._sample_width = self._wave.getsampwidth()
        if self._wave.getcomptype() != "NONE":
            raise AudioSourceError(
                f"could not read compressed WAV {source_path}; expected PCM WAV audio"
            )
        if self.sample_rate <= 0 or self.channels <= 0 or self.play_samples < 0:
            raise AudioSourceError(f"invalid WAV stream metadata for {source_path}")
        if self._sample_width not in {1, 2, 3, 4}:
            raise AudioSourceError(
                f"unsupported WAV sample width {self._sample_width}; expected 8/16/24/32-bit PCM"
            )

    def read_pcm16(self, frame_count: int) -> bytes:
        if frame_count <= 0:
            return b""
        raw = self._wave.readframes(frame_count)
        if not raw:
            return b""
        if self._sample_width == PCM16_BYTES_PER_SAMPLE:
            return raw
        return _pcm_bytes_to_int16(raw, self._sample_width)

    def seek_samples(self, position: int) -> None:
        clamped_position = max(0, min(position, self.play_samples))
        self._wave.setpos(clamped_position)

    def close(self) -> None:
        self._wave.close()

    def __enter__(self) -> _WavePcmStream:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


# ---------------------------------------------------------------------------
# FLAC decoder
# ---------------------------------------------------------------------------


class _FlacPcmStream:
    """Decode FLAC files with pyFLAC into seekable interleaved signed 16-bit frames."""

    def __init__(self, source_path: Path) -> None:
        try:
            import numpy as np  # noqa: PLC0415
            import pyflac  # noqa: PLC0415
            import soundfile as sf  # noqa: PLC0415
        except ImportError as exc:
            raise AudioSourceError(
                "could not import pyFLAC; install pyflac to play FLAC custom audio"
            ) from exc

        try:
            info = sf.info(source_path)
            if info.subtype in {"PCM_16", "PCM_32"}:
                audio, sample_rate = pyflac.FileDecoder(source_path).process()
            else:
                audio, sample_rate = sf.read(source_path, always_2d=True, dtype="float64")
        except Exception as exc:
            raise AudioSourceError(f"could not read FLAC file {source_path}: {exc}") from exc

        samples = np.asarray(audio)
        if samples.ndim == 1:
            samples = samples.reshape(-1, 1)
        if samples.ndim != 2:
            raise AudioSourceError(f"invalid FLAC stream shape for {source_path}: {samples.shape}")

        if samples.dtype.kind not in {"i", "u", "f"}:
            raise AudioSourceError(
                f"unsupported FLAC sample type {samples.dtype}; expected PCM samples"
            )

        self.sample_rate = int(sample_rate)
        self.channels = int(samples.shape[1])
        self.play_samples = int(samples.shape[0])
        self._samples = _numpy_audio_to_int16(samples)
        self._position = 0

        if self.sample_rate <= 0 or self.channels <= 0:
            raise AudioSourceError(f"invalid FLAC stream metadata for {source_path}")

    def read_pcm16(self, frame_count: int) -> bytes:
        if frame_count <= 0:
            return b""
        end_position = min(self.play_samples, self._position + frame_count)
        if end_position <= self._position:
            return b""
        chunk = self._samples[self._position : end_position]
        self._position = end_position
        return cast("bytes", chunk.tobytes())

    def seek_samples(self, position: int) -> None:
        self._position = max(0, min(position, self.play_samples))

    def close(self) -> None:
        return None

    def __enter__(self) -> _FlacPcmStream:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pcm_bytes_to_int16(raw: bytes, sample_width: int) -> bytes:
    output = array("h")
    if sample_width == 1:
        output.extend((sample - 128) << 8 for sample in raw)
    elif sample_width == 3:
        for index in range(0, len(raw), 3):
            value = int.from_bytes(raw[index : index + 3], "little", signed=True)
            output.append(_clamp_int16(value >> 8))
    elif sample_width == 4:
        for index in range(0, len(raw), 4):
            value = int.from_bytes(raw[index : index + 4], "little", signed=True)
            output.append(_clamp_int16(value >> 16))
    else:
        raise AudioSourceError(f"unsupported PCM sample width: {sample_width}")
    return output.tobytes()


def _numpy_audio_to_int16(samples: Any) -> Any:
    import numpy as np  # noqa: PLC0415

    if samples.dtype == np.int16:
        return np.ascontiguousarray(samples)
    if samples.dtype.kind == "f":
        scaled = np.clip(samples, -1.0, 1.0) * 32767.0
        return np.ascontiguousarray(scaled.astype(np.int16))
    info = np.iinfo(samples.dtype)
    if info.bits > 16:
        scaled = samples >> (info.bits - 16)
    elif info.bits < 16:
        scaled = samples << (16 - info.bits)
    else:
        scaled = samples
    return np.ascontiguousarray(np.clip(scaled, -32768, 32767).astype(np.int16))


def _clamp_int16(sample: int) -> int:
    return max(-32768, min(32767, sample))


def _platform_dir_name() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


# ---------------------------------------------------------------------------
# Public player
# ---------------------------------------------------------------------------


class MusicStreamPlayer(QObject):
    """Stream decoded song PCM directly into Qt audio output."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._duration_seconds = 0.0
        self._source_path: Path | None = None
        self._stream: _PcmAudioStream | None = None
        self._sink: QAudioSink | None = None
        self._io_device: QIODevice | None = None
        self._sample_rate = 0
        self._channels = 0
        self._current_sample = 0
        self._sink_start_sample = 0
        self._is_playing = False
        self._volume = DEFAULT_MUSIC_VOLUME
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._push_audio)

    def set_source(self, path: Path | None) -> None:
        """Load a supported song source, or clear song playback."""
        self.shutdown()
        self._source_path = path
        if path is None:
            return

        try:
            self._stream = self._open_stream(path)
            self._sample_rate = self._stream.sample_rate
            self._channels = self._stream.channels
            play_samples = self._stream.play_samples
        except (OSError, AudioSourceError, VgmstreamError) as exc:
            LOGGER.warning("Failed to prepare song audio from %s: %s", path, exc)
            if self._stream is not None:
                self._stream.close()
            self._clear_stream_state()
            return

        self._duration_seconds = play_samples / self._sample_rate
        self._sink = self._create_sink()

    @property
    def duration_seconds(self) -> float:
        """Return decoded song duration for seek-bar style timeline mapping."""
        return self._duration_seconds

    @property
    def has_loaded_source(self) -> bool:
        """Return whether a source decoded successfully and can be played."""
        return self._stream is not None and self._sink is not None

    @property
    def volume(self) -> float:
        """Return the current music output volume."""
        return self._volume

    def set_volume(self, volume: float) -> None:
        """Set music output volume for current and future sinks."""
        self._volume = max(0.0, min(1.0, volume))
        if self._sink is not None:
            self._sink.setVolume(self._volume)

    @property
    def position_seconds(self) -> float:
        """Return the audio position currently processed by Qt output."""
        if self._sample_rate <= 0:
            return 0.0

        if self._sink is None:
            return self._current_sample / self._sample_rate

        processed_seconds = self._sink.processedUSecs() / 1_000_000.0
        return self._sink_start_sample / self._sample_rate + processed_seconds

    def export_wav(self, destination_path: Path) -> None:
        """Decode the current source to a WAV file."""
        if self._source_path is None:
            raise VgmstreamError("cannot export audio; expected a loaded music source")

        with self._open_stream(self._source_path) as stream:
            with wave.open(str(destination_path), "wb") as wave_file:
                wave_file.setnchannels(stream.channels)
                wave_file.setsampwidth(PCM16_BYTES_PER_SAMPLE)
                wave_file.setframerate(stream.sample_rate)
                while True:
                    chunk = stream.read_pcm16(DECODE_CHUNK_FRAMES)
                    if not chunk:
                        break
                    wave_file.writeframes(chunk)

    def play_from(self, seconds: float) -> None:
        """Start playback at a song position."""
        self.seek(seconds)
        self.resume()

    def resume(self) -> None:
        """Resume music from the current decoded sample position."""
        if self._stream is None or self._sink is None:
            return

        if self._io_device is None:
            self._sink_start_sample = self._current_sample
            self._io_device = self._sink.start()
        else:
            self._sink.resume()

        self._is_playing = True
        if not self._timer.isActive():
            self._timer.start(PUSH_INTERVAL_MILLISECONDS)

    def pause(self) -> None:
        """Pause music without changing the decoded sample position."""
        if self._sink is not None:
            self._sink.suspend()
        self._is_playing = False
        self._timer.stop()

    def stop(self) -> None:
        """Stop current music output."""
        self._timer.stop()
        if self._sink is not None:
            self._sink.stop()
        self._is_playing = False
        self._io_device = None

    def shutdown(self) -> None:
        """Stop playback and detach the current source."""
        self.stop()
        if self._stream is not None:
            self._stream.close()
        self._clear_stream_state()

    def seek(self, seconds: float) -> None:
        """Move the decoder to an audio position like a normal seek bar."""
        stream = self._stream
        if stream is None:
            return

        clamped_seconds = max(0.0, min(seconds, self._duration_seconds))
        sample_position = round(clamped_seconds * self._sample_rate)
        stream.seek_samples(sample_position)
        self._current_sample = sample_position
        self._sink_start_sample = sample_position

        if self._sink is not None:
            self._sink.reset()
            self._io_device = None
            if self._is_playing:
                self._io_device = self._sink.start()

    def _clear_stream_state(self) -> None:
        self._stream = None
        self._sink = None
        self._io_device = None
        self._duration_seconds = 0.0
        self._sample_rate = 0
        self._channels = 0
        self._current_sample = 0
        self._sink_start_sample = 0
        self._is_playing = False

    def _open_stream(self, path: Path) -> _PcmAudioStream:
        suffix = path.suffix.lower()
        if suffix == WAV_SUFFIX:
            return _WavePcmStream(path)
        if suffix == FLAC_SUFFIX:
            return _FlacPcmStream(path)
        if suffix in VGMSTREAM_SUFFIXES:
            return _VgmstreamCliStream(path)
        raise AudioSourceError(
            f"unsupported audio format {suffix or '<none>'}; expected FLAC, WAV, MP3, or AWB"
        )

    def _create_sink(self) -> QAudioSink:
        audio_format = QAudioFormat()
        audio_format.setSampleRate(self._sample_rate)
        audio_format.setChannelCount(self._channels)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        sink = QAudioSink(audio_format, self)
        sink.setBufferFrameCount(DECODE_CHUNK_FRAMES * 2)
        sink.setVolume(self._volume)
        return sink

    def _push_audio(self) -> None:
        if self._stream is None or self._sink is None or self._io_device is None:
            self._timer.stop()
            return

        bytes_free = self._sink.bytesFree()
        if bytes_free < MINIMUM_WRITE_BYTES:
            return

        bytes_per_frame = self._channels * PCM16_BYTES_PER_SAMPLE
        frame_count = min(bytes_free // bytes_per_frame, DECODE_CHUNK_FRAMES)
        if frame_count <= 0:
            return

        chunk = self._stream.read_pcm16(frame_count)
        if not chunk:
            self.stop()
            return

        self._io_device.write(chunk)
        self._current_sample += len(chunk) // bytes_per_frame
