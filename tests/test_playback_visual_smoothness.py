from __future__ import annotations

from PySide6.QtCore import Qt

from src.core.models import Chart, ChartMetadata
from src.engine.playback import (
    MAX_PLAYBACK_FPS,
    PLAYBACK_POSITION_SIGNAL_FPS,
    PLAYBACK_POSITION_SIGNAL_INTERVAL_MS,
    PLAYBACK_TIMER_INTERVAL_MS,
    PlaybackController,
)
from src.ui.components.viewport import (
    PLAYBACK_REPAINT_INTERVAL_MS,
    TARGET_PLAYBACK_FPS,
)


def test_playback_timer_uses_precise_120hz_class_interval() -> None:
    controller = PlaybackController()

    assert MAX_PLAYBACK_FPS == 120
    assert PLAYBACK_TIMER_INTERVAL_MS <= 9
    assert controller.timer.timerType() == Qt.TimerType.PreciseTimer


def test_viewport_repaint_cadence_matches_playback_timer() -> None:
    assert TARGET_PLAYBACK_FPS == 120
    assert PLAYBACK_REPAINT_INTERVAL_MS == PLAYBACK_TIMER_INTERVAL_MS


class FakeElapsedTimer:
    def __init__(self, seconds: float = 0.0, milliseconds: int = 0) -> None:
        self.seconds = seconds
        self.milliseconds = milliseconds
        self.restart_count = 0

    def nsecsElapsed(self) -> int:  # noqa: N802 - mirrors QElapsedTimer.
        return round(self.seconds * 1_000_000_000)

    def elapsed(self) -> int:
        return self.milliseconds

    def isValid(self) -> bool:  # noqa: N802 - mirrors QElapsedTimer.
        return True

    def start(self) -> None:
        self.restart()

    def restart(self) -> None:
        self.restart_count += 1
        self.milliseconds = 0


def test_playback_position_signal_is_throttled_below_render_cadence() -> None:
    chart = Chart(metadata=ChartMetadata(resolution=384, bpm_def=["120.0"]))
    controller = PlaybackController()
    controller.set_chart(chart)
    controller.set_playback_duration(10.0)
    controller.is_playing = True
    emitted: list[float] = []
    controller.pos_changed.connect(emitted.append)

    controller._start_pos_seconds = 0.0
    controller._start_time = FakeElapsedTimer(seconds=0.005)
    controller._last_position_emit_timer = FakeElapsedTimer(milliseconds=0)
    controller._update_playback()

    controller._start_time = FakeElapsedTimer(seconds=0.040)
    controller._last_position_emit_timer = FakeElapsedTimer(
        milliseconds=PLAYBACK_POSITION_SIGNAL_INTERVAL_MS
    )
    controller._update_playback()

    assert PLAYBACK_POSITION_SIGNAL_FPS < MAX_PLAYBACK_FPS
    assert len(emitted) == 1
    assert emitted[0] > 0.0
