from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from PySide6.QtCore import QObject, Signal

from src.audio.engine import AudioEngine
from src.audio.music import MusicStreamPlayer
from src.core.editor import add_note
from src.core.enums import NoteType
from src.core.models import Chart, ChartMetadata
from src.engine.playback import PlaybackController
from src.engine.timeline import ChartTimeline
from src.notes import Tap
from src.services.playback import PlaybackCoordinator


@dataclass
class FakeTimeline:
    resolution: int = 384
    seen_ticks: list[int] = field(default_factory=list)

    def time_at(self, tick: int) -> float:
        self.seen_ticks.append(tick)
        return tick / self.resolution + 1.25

    def pos_at_time(self, seconds: float) -> float:
        return (seconds - 1.25) * self.resolution / self.resolution

    def calculate_max_measure(self) -> int:
        return 10


@dataclass
class FakeChart:
    timeline: FakeTimeline = field(default_factory=FakeTimeline)


class FakeController(QObject):
    triggered = Signal(int)
    pos_changed = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.chart = FakeChart()
        self.current_pos = 1.0
        self.is_playing = False
        self.sync_to_calls: list[float] = []
        self.playback_duration_seconds = 0.0
        self.refresh_chart_count = 0

    def toggle_playback(self) -> bool:
        self.is_playing = not self.is_playing
        return self.is_playing

    def refresh_chart(self) -> None:
        self.refresh_chart_count += 1

    def seek(self, pos: float) -> None:
        self.current_pos = pos
        self.pos_changed.emit(pos)

    def sync_to(self, pos: float) -> None:
        self.current_pos = pos
        self.sync_to_calls.append(pos)
        self.pos_changed.emit(pos)

    def set_playback_duration(self, duration_seconds: float) -> None:
        self.playback_duration_seconds = duration_seconds


class FakeHitsoundEngine:
    def __init__(self) -> None:
        self.play_count = 0
        self.stop_count = 0
        self.volume = 0.0

    def play_hit(self) -> None:
        self.play_count += 1

    def stop_all(self) -> None:
        self.stop_count += 1

    def set_volume(self, volume: float) -> None:
        self.volume = volume


class FakeMusicPlayer:
    def __init__(self) -> None:
        self.resume_count = 0
        self.pause_count = 0
        self.duration_seconds = 100.0
        self.position_seconds = 0.0
        self.volume = 0.0
        self.source_path = None
        self.play_from_calls: list[float] = []
        self.seek_calls: list[float] = []

    @property
    def has_loaded_source(self) -> bool:
        return self.source_path is not None

    def set_source(self, path) -> None:
        self.source_path = path

    def resume(self) -> None:
        self.resume_count += 1

    def pause(self) -> None:
        self.pause_count += 1

    def play_from(self, seconds: float) -> None:
        self.play_from_calls.append(seconds)

    def seek(self, seconds: float) -> None:
        self.seek_calls.append(seconds)

    def set_volume(self, volume: float) -> None:
        self.volume = volume


def test_toggle_playback_resumes_music_without_reseeking(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, FakeHitsoundEngine())
    coordinator.music_player = cast(MusicStreamPlayer, music_player)

    assert coordinator.toggle_playback()
    assert not coordinator.toggle_playback()
    assert coordinator.toggle_playback()

    assert music_player.resume_count == 2
    assert music_player.pause_count == 1
    assert music_player.play_from_calls == []


def test_volume_controls_delegate_to_audio_players(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    hitsound_engine = FakeHitsoundEngine()
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, hitsound_engine)
    coordinator.music_player = cast(MusicStreamPlayer, music_player)

    coordinator.set_hitsound_volume(0.8)
    coordinator.set_music_volume(0.35)

    assert hitsound_engine.volume == 0.8
    assert music_player.volume == 0.35


def test_set_chart_audio_loads_custom_audio_relative_to_chart_path(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, FakeHitsoundEngine())
    coordinator.music_player = cast(MusicStreamPlayer, music_player)
    chart_dir = tmp_path / "custom"
    chart_dir.mkdir()
    audio_path = chart_dir / "song.wav"
    audio_path.write_bytes(b"RIFF")
    chart_path = chart_dir / "custom.c2s"
    chart_path.write_text("MUSIC\t0\n", encoding="utf-8")
    chart = Chart(metadata=ChartMetadata(audio_path="song.wav"))

    coordinator.set_chart_audio(chart, chart_path)
    assert coordinator.toggle_playback()

    assert music_player.source_path == audio_path
    assert music_player.resume_count == 1
    assert controller.playback_duration_seconds == 100.0
    assert coordinator.has_music_source


def test_loading_chart_while_playing_does_not_emit_old_clock_hitsounds(tmp_path) -> None:
    old_chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    new_chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    new_chart.notes = [
        Tap(
            note_type=NoteType.TAP,
            measure=measure,
            offset=0,
            cell=0,
            width=4,
        )
        for measure in range(4)
    ]
    controller = PlaybackController()
    controller.set_chart(old_chart)
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    hitsound_engine = FakeHitsoundEngine()
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, hitsound_engine)
    coordinator.music_player = cast(MusicStreamPlayer, music_player)
    controller.is_playing = True
    controller._start_pos_seconds = 0.0
    controller._start_time = FakeElapsedTimer(0.0)
    music_player.position_seconds = 8.0

    controller.set_chart(new_chart)
    coordinator.set_chart_audio(new_chart)

    assert hitsound_engine.play_count == 0
    assert controller.current_pos == 0.0
    assert music_player.play_from_calls == [0.0]


def test_refresh_chart_after_edit_releases_seek_debounce_for_fresh_notes(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    hitsound_engine = FakeHitsoundEngine()
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, hitsound_engine)
    coordinator.music_player = cast(MusicStreamPlayer, music_player)

    coordinator.seek(1.0)
    coordinator.refresh_chart_after_edit()
    controller.triggered.emit(1)

    assert controller.refresh_chart_count == 1
    assert music_player.seek_calls == [2.25]
    assert hitsound_engine.play_count == 1


def test_seek_while_playing_moves_music_to_chart_time_without_restarting(
    tmp_path,
) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, FakeHitsoundEngine())
    coordinator.music_player = cast(MusicStreamPlayer, music_player)
    controller.is_playing = True

    coordinator.seek(2.5)
    coordinator._perform_deferred_audio_seek()

    assert music_player.seek_calls == [3.75]
    assert music_player.play_from_calls == []
    assert controller.chart.timeline.seen_ticks == [960]


def test_seek_while_paused_moves_music_without_playing(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, FakeHitsoundEngine())
    coordinator.music_player = cast(MusicStreamPlayer, music_player)

    coordinator.seek(2.5)
    coordinator._perform_deferred_audio_seek()

    assert music_player.seek_calls == [3.75]
    assert music_player.play_from_calls == []
    assert controller.chart.timeline.seen_ticks == [960]


def test_rapid_seek_debounces_music_to_last_requested_position(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, FakeHitsoundEngine())
    coordinator.music_player = cast(MusicStreamPlayer, music_player)

    coordinator.seek(2.0)
    coordinator.seek(3.0)

    assert music_player.seek_calls == []

    coordinator._perform_deferred_audio_seek()

    assert music_player.seek_calls == [4.25]


def test_rapid_seek_stops_audio_once_until_debounce_finishes(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    hitsound_engine = FakeHitsoundEngine()
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, hitsound_engine)
    coordinator.music_player = cast(MusicStreamPlayer, music_player)

    coordinator.seek(2.0)
    coordinator.seek(3.0)
    coordinator.seek(4.0)

    assert hitsound_engine.stop_count == 1

    coordinator._perform_deferred_audio_seek()
    coordinator.seek(5.0)

    assert hitsound_engine.stop_count == 2


def test_hitsounds_are_muted_while_seek_debounce_is_active(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    hitsound_engine = FakeHitsoundEngine()
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, hitsound_engine)
    coordinator.music_player = cast(MusicStreamPlayer, music_player)

    coordinator.seek(2.0)
    controller.triggered.emit(1)

    assert hitsound_engine.play_count == 0

    coordinator._perform_deferred_audio_seek()
    controller.triggered.emit(1)

    assert hitsound_engine.play_count == 1


def test_seek_debounce_blocks_music_clock_sync(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, FakeHitsoundEngine())
    coordinator.music_player = cast(MusicStreamPlayer, music_player)
    controller.is_playing = True
    music_player.position_seconds = 4.25

    coordinator.seek(2.0)
    controller.pos_changed.emit(2.1)
    coordinator._sync_chart_to_music_clock(2.1)

    assert controller.sync_to_calls == []


def test_coordinator_forward_seek_to_note_stays_silent_after_debounce(tmp_path) -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.notes = [
        Tap(
            note_type=NoteType.TAP,
            measure=10,
            offset=0,
            cell=0,
            width=4,
        )
    ]
    controller = PlaybackController()
    controller.set_chart(chart)
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    hitsound_engine = FakeHitsoundEngine()
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, hitsound_engine)
    coordinator.music_player = cast(MusicStreamPlayer, music_player)
    controller.is_playing = True

    coordinator.seek(10.0)
    coordinator._perform_deferred_audio_seek()
    music_player.position_seconds = music_player.seek_calls[-1]
    controller._start_time = FakeElapsedTimer(0.0)
    controller._update_playback()

    assert hitsound_engine.play_count == 0


def test_timeline_time_at_uses_resolution_as_ticks_per_measure() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    timeline = ChartTimeline(chart)

    assert timeline.time_at(384) == 2.0
    assert timeline.time_at(960) == 5.0


def test_timeline_time_at_handles_bpm_changes() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.bpms = [{"measure": 1, "offset": 0, "bpm": 240.0}]
    timeline = ChartTimeline(chart)

    assert timeline.time_at(384) == 2.0
    assert timeline.time_at(768) == 3.0


def test_playback_position_follows_music_clock_instead_of_seeking_music(
    tmp_path,
) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, FakeHitsoundEngine())
    coordinator.music_player = cast(MusicStreamPlayer, music_player)
    controller.is_playing = True
    music_player.position_seconds = 3.75

    controller.pos_changed.emit(2.0)

    assert music_player.seek_calls == []
    assert controller.sync_to_calls == [2.5]


def test_playback_position_does_not_resync_without_loaded_music(tmp_path) -> None:
    controller = FakeController()
    coordinator = PlaybackCoordinator(controller, "", str(tmp_path))
    music_player = FakeMusicPlayer()
    coordinator.engine = cast(AudioEngine, FakeHitsoundEngine())
    coordinator.music_player = cast(MusicStreamPlayer, music_player)
    controller.is_playing = True
    music_player.duration_seconds = 0.0
    music_player.position_seconds = 3.75

    controller.pos_changed.emit(2.0)

    assert controller.sync_to_calls == []


def test_timeline_pos_at_time_is_inverse_of_time_at() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.bpms = [{"measure": 1, "offset": 0, "bpm": 240.0}]
    timeline = ChartTimeline(chart)

    assert timeline.pos_at_time(2.0) == 1.0
    assert timeline.pos_at_time(3.0) == 2.0


def test_refresh_chart_rebuilds_hitsounds_after_editor_mutation() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    controller = PlaybackController()
    controller.set_chart(chart)

    assert controller.audible_triggers == []

    add_note(
        chart,
        Tap(
            note_type=NoteType.TAP,
            measure=1,
            offset=0,
            cell=0,
            width=4,
        ),
    )
    controller.refresh_chart()

    assert controller.audible_trigger_count_at(1.0) == 1


def test_freshly_placed_note_at_seek_landing_is_not_suppressed() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    controller = PlaybackController()
    controller.set_chart(chart)
    controller.seek(1.0)

    add_note(
        chart,
        Tap(
            note_type=NoteType.TAP,
            measure=1,
            offset=0,
            cell=0,
            width=4,
        ),
    )
    controller.refresh_chart()
    emitted: list[int] = []
    controller.triggered.connect(emitted.append)
    controller.is_playing = True
    controller._start_pos_seconds = chart.timeline.time_at_measure(1.0)
    controller._start_time = FakeElapsedTimer(0.0)

    controller._update_playback()

    assert emitted == [1]


def test_music_clock_sync_emits_hitsound_when_visible_playhead_crosses_note() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.notes = [
        Tap(
            note_type=NoteType.TAP,
            measure=2,
            offset=0,
            cell=0,
            width=4,
        )
    ]
    controller = PlaybackController()
    controller.set_chart(chart)
    controller.seek(1.9)
    controller.is_playing = True
    controller._start_pos_seconds = chart.timeline.time_at_measure(1.9)
    controller._start_time = FakeElapsedTimer(0.0)
    emitted: list[int] = []
    controller.triggered.connect(emitted.append)

    controller.sync_to(2.1)

    assert emitted == [1]


def test_seek_to_note_during_playback_does_not_emit_landing_hitsound() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.notes = [
        Tap(
            note_type=NoteType.TAP,
            measure=2,
            offset=0,
            cell=0,
            width=4,
        )
    ]
    controller = PlaybackController()
    controller.set_chart(chart)
    emitted: list[int] = []
    controller.triggered.connect(emitted.append)
    controller.is_playing = True
    controller.seek(2.0)

    controller._start_time = FakeElapsedTimer(0.0)
    controller._update_playback()

    assert emitted == []


def test_seek_suppression_does_not_mute_earlier_notes_after_seeking_back() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.notes = [
        Tap(
            note_type=NoteType.TAP,
            measure=2,
            offset=0,
            cell=0,
            width=4,
        ),
        Tap(
            note_type=NoteType.TAP,
            measure=10,
            offset=0,
            cell=0,
            width=4,
        ),
    ]
    controller = PlaybackController()
    controller.set_chart(chart)
    emitted: list[int] = []
    controller.triggered.connect(emitted.append)

    controller.is_playing = True
    controller.seek(10.0)
    controller._start_time = FakeElapsedTimer(0.0)
    controller._update_playback()
    assert emitted == []

    controller.seek(1.9)
    controller._start_pos_seconds = chart.timeline.time_at_measure(1.9)
    controller._start_time = FakeElapsedTimer(0.0)
    controller.sync_to(2.1)

    assert emitted == [1]


def test_music_clock_sync_backwards_resyncs_hitsound_index() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.notes = [
        Tap(
            note_type=NoteType.TAP,
            measure=2,
            offset=0,
            cell=0,
            width=4,
        ),
        Tap(
            note_type=NoteType.TAP,
            measure=10,
            offset=0,
            cell=0,
            width=4,
        ),
    ]
    controller = PlaybackController()
    controller.set_chart(chart)
    emitted: list[int] = []
    controller.triggered.connect(emitted.append)

    controller.seek(10.1)
    assert controller.trigger_index == len(controller.audible_triggers)

    controller.is_playing = True
    controller._start_pos_seconds = chart.timeline.time_at_measure(10.1)
    controller._start_time = FakeElapsedTimer(0.0)
    controller.sync_to(1.9)
    controller._start_pos_seconds = chart.timeline.time_at_measure(1.9)
    controller._start_time = FakeElapsedTimer(0.0)
    controller.sync_to(2.1)

    assert emitted == [1]


def test_backward_sync_does_not_emit_notes_while_slew_is_rewinding() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.notes = [
        Tap(
            note_type=NoteType.TAP,
            measure=2,
            offset=0,
            cell=0,
            width=4,
        ),
        Tap(
            note_type=NoteType.TAP,
            measure=4,
            offset=0,
            cell=0,
            width=4,
        ),
        Tap(
            note_type=NoteType.TAP,
            measure=6,
            offset=0,
            cell=0,
            width=4,
        ),
        Tap(
            note_type=NoteType.TAP,
            measure=10,
            offset=0,
            cell=0,
            width=4,
        ),
    ]
    controller = PlaybackController()
    controller.set_chart(chart)
    controller.set_playback_duration(30.0)
    emitted: list[int] = []
    controller.triggered.connect(emitted.append)

    controller.seek(10.1)
    assert controller.trigger_index == len(controller.audible_triggers)

    controller.is_playing = True
    controller._start_pos_seconds = chart.timeline.time_at_measure(10.1)
    controller._start_time = FakeElapsedTimer(0.0)
    controller.sync_to(1.9)
    controller._update_playback()

    assert emitted == []


def test_backward_sync_to_note_suppresses_landing_hitsound() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.notes = [
        Tap(
            note_type=NoteType.TAP,
            measure=2,
            offset=0,
            cell=0,
            width=4,
        ),
        Tap(
            note_type=NoteType.TAP,
            measure=10,
            offset=0,
            cell=0,
            width=4,
        ),
    ]
    controller = PlaybackController()
    controller.set_chart(chart)
    emitted: list[int] = []
    controller.triggered.connect(emitted.append)

    controller.seek(10.1)
    controller.is_playing = True
    controller._start_pos_seconds = chart.timeline.time_at_measure(10.1)
    controller._start_time = FakeElapsedTimer(0.0)
    controller.sync_to(2.0)
    controller._update_playback()

    assert emitted == []


class FakeElapsedTimer:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def nsecsElapsed(self) -> int:  # noqa: N802 - mirrors QElapsedTimer.
        return round(self.seconds * 1_000_000_000)

    def start(self) -> None:
        return None


def test_music_duration_keeps_short_chart_preview_playing_until_song_end() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    chart.notes = [
        Tap(
            note_type=NoteType.TAP,
            measure=0,
            offset=0,
            cell=0,
            width=4,
        )
    ]
    controller = PlaybackController()
    controller.set_chart(chart)
    controller.set_playback_duration(6.0)
    controller.is_playing = True

    controller._start_time = FakeElapsedTimer(3.0)
    controller._update_playback()

    assert controller.is_playing
    assert controller.current_pos == 1.5

    controller._start_time = FakeElapsedTimer(6.1)
    controller._update_playback()

    assert not controller.is_playing
    assert controller.current_pos == 0.0
