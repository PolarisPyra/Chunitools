from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from PySide6.QtCore import QElapsedTimer, QObject, Qt, QTimer, Signal

if TYPE_CHECKING:
    from src.core.models import Chart

MAX_PLAYBACK_FPS = 120
PLAYBACK_TIMER_INTERVAL_MS = max(1, round(1000 / MAX_PLAYBACK_FPS))
PLAYBACK_POSITION_SIGNAL_FPS = 30
PLAYBACK_POSITION_SIGNAL_INTERVAL_MS = max(1, round(1000 / PLAYBACK_POSITION_SIGNAL_FPS))
TRIGGER_EPSILON_SECONDS = 0.001


class PlaybackController(QObject):
    """Handles the timing, hitsound triggering, and playback state of a chart."""

    pos_changed = Signal(float)
    triggered = Signal(int)  # Emitted with the number of hitsounds to play.

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.chart: Chart | None = None
        self.current_pos = 0.0
        self.is_playing = False

        self.audible_triggers: list[tuple[float, int]] = []
        self.trigger_index = 0
        self.playback_end_seconds = 0.0
        self._suppressed_landing_trigger_time_s: float | None = None

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._update_playback)

        self.elapsed = QElapsedTimer()
        self._start_time = QElapsedTimer()
        self._slew_timer = QElapsedTimer()
        self._last_position_emit_timer = QElapsedTimer()
        self._last_position_emit_timer.start()
        self._start_pos_seconds = 0.0
        self._sync_offset_s = 0.0
        self._target_sync_offset_s = 0.0
        self._slew_start_offset = 0.0
        self._slew_duration = 0.2  # 200ms to smoothly reach the sync target

    def set_chart(self, chart: Chart) -> None:
        """Initialize the controller with a new chart."""
        was_playing = self.is_playing
        self.chart = chart
        self.current_pos = 0.0
        self._suppressed_landing_trigger_time_s = None
        self.generate_triggers()
        if was_playing:
            self._start_pos_seconds = 0.0
            self._start_time.start()
            self._slew_timer.start()
            self._last_position_emit_timer.start()
            self._sync_offset_s = 0.0
            self._target_sync_offset_s = 0.0
            self._slew_start_offset = 0.0
            self.elapsed.start()
            if not self.timer.isActive():
                self.timer.start(PLAYBACK_TIMER_INTERVAL_MS)
            return

        self._emit_position_changed(force=True)  # Ensure UI resets to start.

    def _bpm_at_pos(self, pos: float) -> float:
        if not self.chart:
            return 120.0
        # Optimization: ChartTimeline already has BPM segments.
        # We can look up by absolute position (measures) directly.
        return self.chart.timeline.bpm_at_pos(pos)

    def generate_triggers(self) -> None:
        """Pre-calculate the absolute times (seconds) where hitsounds should fire."""
        if not self.chart:
            return

        timeline = self.chart.timeline

        # Calculate pass/judgement times for each audible note. Air notes use
        # Render's separate jdgTimingAir pass offset.
        trigger_times = [
            timeline.time_at(event.tick) + event.delay_seconds
            for event in timeline.audible_events()
        ]

        # Group simultaneous hitsounds
        trigger_counts = Counter(trigger_times)
        self.audible_triggers = sorted(trigger_counts.items())
        self.resync_index()

    def refresh_chart(self) -> None:
        """Refresh cached trigger timing after in-place chart edits."""
        if not self.chart:
            return
        self._suppressed_landing_trigger_time_s = None
        self.generate_triggers()

    def set_playback_duration(self, duration_seconds: float) -> None:
        """Set the song-backed playback duration, or 0 to use chart length."""
        self.playback_end_seconds = max(0.0, float(duration_seconds))

    def audible_trigger_count_at(self, pos: float) -> int:
        """Return how many chart notes contribute to a playback position."""
        if not self.chart:
            return 0
        tick = round(pos * self.chart.timeline.resolution)
        return self.chart.timeline.audible_ticks.count(tick)

    def resync_index(self) -> None:
        """Find the next trigger index based on the current wall-clock time."""
        if not self.chart:
            return

        current_time_s = self.chart.timeline.time_at_measure(self.current_pos)
        self._resync_index_at_time(current_time_s)

    def _resync_index_at_time(self, current_time_s: float) -> None:
        self.trigger_index = 0
        while (
            self.trigger_index < len(self.audible_triggers)
            and self.audible_triggers[self.trigger_index][0] < current_time_s - 0.0001
        ):
            self.trigger_index += 1

    def seek(self, pos: float, *, suppress_landing_hitsound: bool = True) -> None:
        """Move the playhead to absolute position *pos*."""
        self.current_pos = pos
        self.resync_index()
        if self.is_playing and self.chart:
            self._start_pos_seconds = self.chart.timeline.time_at_measure(pos)
            self._start_time.start()
        if self.chart and suppress_landing_hitsound:
            self._suppressed_landing_trigger_time_s = self.chart.timeline.time_at_measure(pos)
        elif not suppress_landing_hitsound:
            self._suppressed_landing_trigger_time_s = None
        self._emit_position_changed(force=True)

    def sync_to(self, pos: float) -> None:
        """Gradually align playback to an external clock position using a time-based lerp."""
        if not self.is_playing or not self.chart:
            self.seek(pos)
            return

        # Record the start of a new slew transition
        self._slew_start_offset = self._sync_offset_s
        self._slew_timer.start()

        # Calculate the new target offset based on the external clock
        target_time_s = self.chart.timeline.time_at_measure(pos)
        internal_time_s = (
            self._start_pos_seconds
            + self._start_time.nsecsElapsed() / 1_000_000_000.0
        )
        if target_time_s > internal_time_s:
            self._emit_due_triggers(target_time_s)
        elif target_time_s < internal_time_s - TRIGGER_EPSILON_SECONDS:
            self._reset_clock_to_time(target_time_s)
            self._resync_index_at_time(target_time_s)
            self._suppressed_landing_trigger_time_s = target_time_s
            return
        self._target_sync_offset_s = target_time_s - internal_time_s

    def _reset_clock_to_time(self, time_s: float) -> None:
        self._start_pos_seconds = time_s
        self._start_time.start()
        self._sync_offset_s = 0.0
        self._target_sync_offset_s = 0.0
        self._slew_start_offset = 0.0
        self._slew_timer.start()

    def toggle_playback(self) -> bool:
        """Start or stop playback. Returns the new is_playing state."""
        if not self.chart:
            return False

        if self.is_playing:
            self.current_pos = self.get_clock_pos()
            self.is_playing = False
            self.timer.stop()
            self._emit_position_changed(force=True)
            return self.is_playing

        self.is_playing = True
        self.resync_index()
        self._start_pos_seconds = self.chart.timeline.time_at_measure(self.current_pos)
        self._start_time.start()
        self._slew_timer.start()
        self._last_position_emit_timer.start()
        self._sync_offset_s = 0.0
        self._target_sync_offset_s = 0.0
        self._slew_start_offset = 0.0
        self.elapsed.start()
        self.timer.start(PLAYBACK_TIMER_INTERVAL_MS)
        self._emit_position_changed(force=True)

        return self.is_playing

    def get_clock_pos(self) -> float:
        """Return the precise absolute position (measures) based on the current wall-clock."""
        if not self.is_playing or not self.chart:
            return self.current_pos

        elapsed_s = self._start_time.nsecsElapsed() / 1_000_000_000.0
        # Combine the linear clock with the smoothed sync offset calculated dynamically
        current_time_s = self._start_pos_seconds + elapsed_s + self._current_sync_offset()
        return self.chart.timeline.pos_at_time(current_time_s)

    def _current_sync_offset(self) -> float:
        """Calculate the current interpolated sync offset based on the slew timer."""
        if not self._slew_timer.isValid():
            return self._target_sync_offset_s

        slew_elapsed = self._slew_timer.nsecsElapsed() / 1_000_000_000.0
        if slew_elapsed < self._slew_duration:
            t = slew_elapsed / self._slew_duration
            return (
                self._slew_start_offset
                + (self._target_sync_offset_s - self._slew_start_offset) * t
            )
        return self._target_sync_offset_s

    def _update_playback(self) -> None:
        """Core playback loop called by timer."""
        if not self.chart:
            return

        # Update the linear ground truth
        self._sync_offset_s = self._current_sync_offset()

        elapsed_s = self._start_time.nsecsElapsed() / 1_000_000_000.0
        current_time_s = self._start_pos_seconds + elapsed_s + self._sync_offset_s

        # End of preview check. With music loaded, the song duration is the source
        # of truth; otherwise fall back to the authored chart length.
        if current_time_s >= self._playback_end_time_seconds():
            self.current_pos = 0.0
            self.resync_index()
            self._suppressed_landing_trigger_time_s = None
            self.is_playing = False
            self.timer.stop()
            self._emit_position_changed(force=True)
            return

        self.current_pos = self.chart.timeline.pos_at_time(current_time_s)
        self._emit_due_triggers(current_time_s)
        self._emit_position_changed()

    def _emit_position_changed(self, *, force: bool = False) -> None:
        """Emit lower-rate UI position updates while the renderer uses the live clock."""
        if (
            not force
            and self._last_position_emit_timer.isValid()
            and self._last_position_emit_timer.elapsed() < PLAYBACK_POSITION_SIGNAL_INTERVAL_MS
        ):
            return
        self._last_position_emit_timer.restart()
        self.pos_changed.emit(self.current_pos)

    def _playback_end_time_seconds(self) -> float:
        if self.playback_end_seconds > 0.0:
            return self.playback_end_seconds
        if not self.chart:
            return 0.0
        return self.chart.timeline.time_at(
            self.chart.timeline.calculate_max_measure() * self.chart.timeline.resolution
        )

    def _emit_due_triggers(self, current_time_s: float) -> None:
        """Emit hitsounds at trigger times reached by the wall-clock."""
        self._skip_suppressed_landing_trigger()
        while (
            self.trigger_index < len(self.audible_triggers)
            and self.audible_triggers[self.trigger_index][0]
            <= current_time_s + TRIGGER_EPSILON_SECONDS
        ):
            _, count = self.audible_triggers[self.trigger_index]
            self.triggered.emit(count)
            self.trigger_index += 1

    def _skip_suppressed_landing_trigger(self) -> None:
        if self._suppressed_landing_trigger_time_s is None:
            return
        while self.trigger_index < len(self.audible_triggers):
            trigger_time = self.audible_triggers[self.trigger_index][0]
            if (
                abs(trigger_time - self._suppressed_landing_trigger_time_s)
                > TRIGGER_EPSILON_SECONDS
            ):
                break
            self.trigger_index += 1
        self._suppressed_landing_trigger_time_s = None
