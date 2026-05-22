"""Low-latency audio engine for hitsound playback using QSoundEffect."""

import os
from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QSoundEffect

from src.core.config import DEFAULT_HITSOUND_VOLUME

# A pool of effects allows for simultaneous note playback with zero mixing overhead
POOL_SIZE = 16

class AudioEngine(QObject):
    """Manages a pool of QSoundEffect objects for ultra-low latency hitsounds."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self.effects: list[QSoundEffect] = []
        self._current_index = 0
        self.volume = DEFAULT_HITSOUND_VOLUME
        self.path = path

        if os.path.exists(path):
            url = QUrl.fromLocalFile(os.path.abspath(path))
            for _ in range(POOL_SIZE):
                effect = QSoundEffect(self)
                effect.setSource(url)
                effect.setVolume(self.volume)
                self.effects.append(effect)

    def set_volume(self, volume: float) -> None:
        """Update the volume for all effects in the pool."""
        self.volume = max(0.0, min(1.0, float(volume)))
        for effect in self.effects:
            effect.setVolume(self.volume)

    def play_hit(self, volume: float | None = None) -> None:
        """Play a hitsound using the next available effect in the pool."""
        if not self.effects:
            return

        # Simple round-robin pooling
        effect = self.effects[self._current_index]
        
        # If the user provided a specific volume for this hit, apply it
        if volume is not None:
            effect.setVolume(max(0.0, min(1.0, float(volume))))
        elif effect.volume() != self.volume:
            effect.setVolume(self.volume)

        effect.play()
        
        self._current_index = (self._current_index + 1) % POOL_SIZE

    def stop_all(self) -> None:
        """Stop all currently playing hitsounds."""
        for effect in self.effects:
            effect.stop()
