"""Single, atomically replaced reference recording per catalog character."""

from __future__ import annotations

import os
import re
import tempfile
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

from shiny_pet.ai.persona import character_asset_key
from shiny_pet.i18n import tr, trf

MAX_REFERENCE_SECONDS = 120
REFERENCE_EXTENSIONS = (".wav", ".flac", ".ogg", ".m4a", ".mp3")


def custom_reference_path(root: Path, character: str) -> Path:
    key = character_asset_key(character)
    if not re.fullmatch(r"[0-9]{2}", key):
        raise ValueError(tr("此角色不支援自訂參考音檔。"))
    return root / f"{key}.wav"


def default_reference_path(root: Path, character: str) -> Path | None:
    key = character_asset_key(character)
    if not re.fullmatch(r"[0-9]{2}", key):
        return None
    for extension in REFERENCE_EXTENSIONS:
        candidate = root / f"{key}{extension}"
        if candidate.is_file():
            return candidate
    return None


class ReferenceAudioImporter(QObject):
    """Decode asynchronously to one PCM WAV; keep the old file on any failure."""

    imported = Signal(str, float)
    failed = Signal(str)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._decoder = QAudioDecoder(self)
        audio_format = QAudioFormat()
        audio_format.setSampleRate(48000)
        audio_format.setChannelCount(1)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self._decoder.setAudioFormat(audio_format)
        self._decoder.bufferReady.connect(self._read_buffer)
        self._decoder.finished.connect(self._finish)
        self._decoder.error.connect(lambda *_args: self._fail(
            tr("無法讀取音檔：") + self._decoder.errorString()
        ))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._fail(tr("讀取音檔逾時，請換一個檔案。")))
        self._temporary: Path | None = None
        self._destination: Path | None = None
        self._writer: wave.Wave_write | None = None
        self._frames = 0

    def start(self, source: Path, destination: Path) -> None:
        if self._temporary is not None:
            raise RuntimeError("Reference import already in progress")
        try:
            self._decoder.stop()
            self._decoder.setSource(QUrl())
            if source.suffix.lower() not in REFERENCE_EXTENSIONS or not source.is_file():
                raise ValueError(tr("請選擇有效的 WAV、FLAC、OGG、M4A 或 MP3 音檔。"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=".reference-", suffix=".wav", dir=destination.parent)
            os.close(fd)
            self._temporary = Path(name)
            self._destination = destination
            self._frames = 0
            self._writer = wave.open(name, "wb")
            self._writer.setnchannels(1)
            self._writer.setsampwidth(2)
            self._writer.setframerate(48000)
            self._timer.start(30000)
            self._decoder.setSource(QUrl.fromLocalFile(str(source.resolve())))
            self._decoder.start()
        except (OSError, ValueError, wave.Error) as exc:
            self._fail(str(exc))

    def _read_buffer(self) -> None:
        if self._writer is None:
            return
        buffer = self._decoder.read()
        if not buffer.isValid():
            return
        fmt = buffer.format()
        if (fmt.sampleRate() != 48000 or fmt.channelCount() != 1
                or fmt.sampleFormat() != QAudioFormat.SampleFormat.Int16):
            self._fail(tr("無法將音檔轉換為支援的參考音訊格式。"))
            return
        self._frames += buffer.frameCount()
        if self._frames > MAX_REFERENCE_SECONDS * 48000:
            self._fail(trf("參考音檔長度上限為 {seconds} 秒，請先裁剪後再匯入。",
                           seconds=MAX_REFERENCE_SECONDS))
            return
        try:
            self._writer.writeframes(bytes(buffer.data()))
        except (OSError, wave.Error) as exc:
            self._fail(str(exc))

    def _finish(self) -> None:
        if self._temporary is None or self._destination is None:
            return
        if not self._frames:
            self._fail(tr("音檔沒有可讀取的聲音內容。"))
            return
        try:
            self._close_writer()
            os.replace(self._temporary, self._destination)
        except (OSError, wave.Error) as exc:
            self._fail(str(exc))
            return
        path, duration = str(self._destination), self._frames / 48000
        self._temporary = None
        self._destination = None
        self.imported.emit(path, duration)

    def _close_writer(self) -> None:
        self._timer.stop()
        if self._writer is not None:
            writer, self._writer = self._writer, None
            writer.close()

    def cancel(self) -> None:
        temporary, self._temporary = self._temporary, None
        self._destination = None
        self._close_writer()
        self._decoder.stop()
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    def _fail(self, message: str) -> None:
        try:
            self.cancel()
        except OSError:
            pass
        self.failed.emit(message)
