"""Play the current idol's local touch recordings without overlapping audio."""

from __future__ import annotations

import logging
import random
import re
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from shiny_pet.models.runtime_catalog import application_root

DEFAULT_TOUCH_VOICE_ROOT = application_root() / "audio_reference" / "touch_voices"
_CHARACTER_ID = re.compile(r"(?:idol-)?([0-9]{1,3})")
_LOG = logging.getLogger(__name__)


def touch_voice_files(character_id: str, root: Path) -> tuple[Path, ...]:
    """Resolve only breast_01 through breast_03 for this character."""
    match = _CHARACTER_ID.fullmatch(character_id)
    if match is None:
        return ()
    idol_id = f"{int(match.group(1)):03d}"
    candidates = (
        root / idol_id / f"mypage_{idol_id}_breast_{number:02d}.m4a"
        for number in range(1, 4)
    )
    return tuple(path for path in candidates if path.is_file())


class TouchVoiceController(QObject):
    def __init__(
        self, parent: QObject, character_id: str, *,
        root: Path = DEFAULT_TOUCH_VOICE_ROOT, rng: random.Random | None = None,
    ) -> None:
        super().__init__(parent)
        self.files = touch_voice_files(character_id, root)
        self._rng = rng or random.Random()
        self._audio = QAudioOutput(self)
        self._audio.setVolume(1.0)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio)
        self._player.errorOccurred.connect(self._on_error)

    def play(self) -> Path | None:
        # Recheck in case an external recording was removed since startup.
        available = tuple(path for path in self.files if path.is_file())
        if not available:
            return None
        selected = self._rng.choice(available)
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(selected.resolve())))
        self._player.play()
        return selected

    def stop(self) -> None:
        self._player.stop()

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        _LOG.warning("Touch voice playback failed (%s): %s", error, message)
