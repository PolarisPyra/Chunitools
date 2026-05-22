from __future__ import annotations

import wave
from array import array
from pathlib import Path

import pyflac
import soundfile as sf

from src.audio.music import MusicStreamPlayer, _FlacPcmStream, _WavePcmStream


def test_wave_stream_reads_pcm16(tmp_path: Path) -> None:
    wav_path = tmp_path / "song.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(array("h", [100, -100, 200, -200]).tobytes())

    stream = _WavePcmStream(wav_path)

    assert stream.sample_rate == 44100
    assert stream.channels == 2
    assert stream.play_samples == 2
    assert stream.read_pcm16(2) == array("h", [100, -100, 200, -200]).tobytes()


def test_flac_stream_uses_pyflac_decoder(tmp_path: Path) -> None:
    wav_path = tmp_path / "song.wav"
    flac_path = tmp_path / "song.flac"
    pcm = array("h", [1000, -1000, 2000, -2000])
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(pcm.tobytes())
    pyflac.FileEncoder(wav_path, flac_path).process()

    stream = _FlacPcmStream(flac_path)
    stream.seek_samples(1)

    assert stream.sample_rate == 48000
    assert stream.channels == 2
    assert stream.play_samples == 2
    assert stream.read_pcm16(1) == array("h", [1999, -1999]).tobytes()


def test_flac_stream_falls_back_for_24_bit_flac_without_pyflac_callback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    flac_path = tmp_path / "song24.flac"
    sf.write(
        flac_path,
        [[0.25, -0.25], [0.5, -0.5]],
        44100,
        format="FLAC",
        subtype="PCM_24",
    )

    def fail_if_pyflac_file_decoder_is_used(path):
        raise AssertionError(f"pyFLAC should not decode unsupported subtype: {path}")

    monkeypatch.setattr(pyflac, "FileDecoder", fail_if_pyflac_file_decoder_is_used)

    stream = _FlacPcmStream(flac_path)

    assert stream.sample_rate == 44100
    assert stream.channels == 2
    assert stream.play_samples == 2
    assert stream.read_pcm16(1) == array("h", [8191, -8191]).tobytes()


def test_music_player_routes_mp3_to_vgmstream_backend(tmp_path: Path) -> None:
    mp3_path = tmp_path / "song.mp3"
    mp3_path.write_bytes(b"ID3")

    class FakeLibrary:
        def __init__(self) -> None:
            self.opened_path: Path | None = None

        def open_stream(self, path: Path):
            self.opened_path = path
            return object()

    player = MusicStreamPlayer()
    fake_library = FakeLibrary()
    player._library = fake_library

    assert player._open_stream(mp3_path) is not None
    assert fake_library.opened_path == mp3_path
