"""Service for coordinating playback timing and hitsound audio."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer

from src.audio.engine import AudioEngine
from src.audio.music import MusicStreamPlayer
from src.core.audio_assets import resolve_chart_audio_path

LOGGER = logging.getLogger(__name__)

MUSIC_MASTER_POSITION_EPSILON = 1 / 128  # Increased from 1/384 to reduce jitter

if TYPE_CHECKING:
    from src.core.models import Chart
    from src.engine.playback import PlaybackController


class PlaybackCoordinator(QObject):
    """Coordinates between the timing controller and the audio engine."""

    def __init__(
        self,
        controller: PlaybackController,
        hitsound_path: str,
        data_root: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.engine = AudioEngine(hitsound_path)
        self.data_root = Path(data_root)
        self.music_player = MusicStreamPlayer(self)
        self._manual_seek_in_progress = False
        self._music_clock_sync_in_progress = False
        self._seek_debounce_active = False

        # Debounce timer for expensive audio seeking during rapid scrolling
        self._audio_seek_timer = QTimer(self)
        self._audio_seek_timer.setSingleShot(True)
        self._audio_seek_timer.setInterval(50)  # 50ms debounce
        self._audio_seek_timer.timeout.connect(self._perform_deferred_audio_seek)
        self._deferred_seek_pos = 0.0

        # Wire up the hitsound trigger
        self.controller.triggered.connect(self._on_triggered)

        # Stop sounds on seek/pos change to prevent 'smearing'
        self.controller.pos_changed.connect(self._on_pos_changed)

        # Dedicated timer for audio synchronization to avoid high-frequency slew resets
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(500)  # Sync every 500ms
        self._sync_timer.timeout.connect(
            lambda: self._sync_chart_to_music_clock(self.controller.current_pos)
        )

    def set_chart_audio(self, chart: Chart, chart_path: str | Path | None = None) -> bool:
        """Load chart audio, return True if audio loaded successfully."""
        audio_path = resolve_chart_audio_path(chart, self.data_root, chart_path)
        LOGGER.debug("set_chart_audio: resolved path=%s", audio_path)
        self.music_player.set_source(audio_path)
        loaded = self.music_player.has_loaded_source
        LOGGER.debug("set_chart_audio: loaded=%s duration=%.2f", loaded, self.music_player.duration_seconds)
        self.controller.set_playback_duration(self.music_player.duration_seconds)
        if loaded and self.controller.is_playing:
            self.music_player.play_from(self._chart_seconds_at_pos(self.controller.current_pos))
            self._sync_timer.start()
        return loaded

    def refresh_chart_after_edit(self) -> None:
        """Rebuild hitsound triggers after chart edits and clear stale seek debounce."""
        self.controller.refresh_chart()
        if self._seek_debounce_active:
            self._perform_deferred_audio_seek()

    @property
    def has_music_source(self) -> bool:
        """Return whether chart music is ready to play."""
        return self.music_player.has_loaded_source

    def set_hitsound_volume(self, volume: float) -> None:
        """Set hitsound preview volume."""
        self.engine.set_volume(volume)

    def set_music_volume(self, volume: float) -> None:
        """Set song preview volume."""
        self.music_player.set_volume(volume)

    def _on_triggered(self, count: int) -> None:
        """Route a chart tick trigger to the audio engine.

        Ched's preview deduplicates simultaneous note ticks before playing the
        clap. Keep the count for diagnostics/UI, but play one mixed-safe hit.
        """
        if self._manual_seek_in_progress or self._seek_debounce_active:
            return
        self.engine.play_hit()

    def _on_pos_changed(self, pos: float) -> None:
        """Silence audio when the playhead moves significantly (non-playback)."""
        if self._manual_seek_in_progress:
            return
        if self._music_clock_sync_in_progress:
            return
        if self._seek_debounce_active:
            return

        if not self.controller.is_playing:
            self.engine.stop_all()
            self.music_player.seek(self._chart_seconds_at_pos(pos))
            return

        self._sync_chart_to_music_clock(pos)

    def toggle_playback(self) -> bool:
        """Start or stop playback and sync audio state."""
        state = self.controller.toggle_playback()
        if state:
            self.music_player.resume()
            self._sync_timer.start()
        else:
            self.engine.stop_all()
            self.music_player.pause()
            self._sync_timer.stop()
        return state

    def seek(self, pos: float) -> None:
        """Seek to a position and silence audio. Debounces the expensive music seek."""
        if not self._seek_debounce_active:
            self.engine.stop_all()
        self._manual_seek_in_progress = True
        try:
            self.controller.seek(pos)
        finally:
            self._manual_seek_in_progress = False

        self._deferred_seek_pos = pos
        self._seek_debounce_active = True
        self._audio_seek_timer.stop()
        self._audio_seek_timer.start()

    def _perform_deferred_audio_seek(self) -> None:
        """Actually execute the music seek after the debounce interval."""
        self._audio_seek_timer.stop()
        seconds = self._chart_seconds_at_pos(self._deferred_seek_pos)
        try:
            self.music_player.seek(seconds)
        finally:
            self._seek_debounce_active = False

    def shutdown(self) -> None:
        """Stop all audio owned by this playback coordinator."""
        self.engine.stop_all()
        self.music_player.shutdown()
        self._sync_timer.stop()

    def _chart_seconds_at_pos(self, pos: float) -> float:
        chart = self.controller.chart
        if chart is None:
            return 0.0

        timeline = chart.timeline
        if hasattr(timeline, "time_at_measure"):
            return timeline.time_at_measure(pos)
        tick = round(pos * timeline.resolution)
        return timeline.time_at(tick)

    def _sync_chart_to_music_clock(self, pos: float) -> None:
        chart = self.controller.chart
        if (
            chart is None
            or self.music_player.duration_seconds <= 0.0
            or not self.controller.is_playing
            or self._seek_debounce_active
        ):
            return

        music_pos = chart.timeline.pos_at_time(self.music_player.position_seconds)
        if abs(music_pos - pos) <= MUSIC_MASTER_POSITION_EPSILON:
            return

        self._music_clock_sync_in_progress = True
        try:
            self.controller.sync_to(music_pos)
        finally:
            self._music_clock_sync_in_progress = False
