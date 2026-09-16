"""TTS request and renderer-neutral lip synchronization lifecycle."""

from __future__ import annotations

import importlib
import io
import json
import math
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from array import array
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from shiny_pet.ai.actions import ActionDirective
from shiny_pet.ai.persona import character_asset_key

_ACTION_TAG = re.compile(r"\[\s*(?:(?:action|expression)\s*:\s*)?[a-z0-9_.-]+\s*\]", re.I)
_JA_JP = re.compile(r"<ja-jp>\s*(.*?)\s*</ja-jp>", re.I | re.S)
_LANGUAGE_BLOCK = re.compile(r"<zh-tw>.*?</zh-tw>|</?(?:zh-tw|ja-jp)>", re.I | re.S)

_IRODORI_EMOTION_CAPTIONS = {
    "greeting": "親しみを込めて、歓迎するように話す。",
    "happy": "明るく嬉しそうに、楽しげに話す。",
    "smile": "笑顔で、柔らかく楽しそうに話す。",
    "sad": "悲しそうに、静かに話す。",
    "angry": "怒りを込めて、強くはっきり話す。",
    "angry_strong": "強い怒りを込めて、鋭くはっきり話す。",
    "surprised": "驚いた様子で、勢いよく話す。",
    "neutral": "落ち着いて、自然に話す。",
    "crying": "涙をこらえながら、声を震わせて話す。",
    "shy": "照れくさそうに、控えめに話す。",
    "serious": "真剣に、落ち着いた調子で話す。",
    "troubled": "困ったように、ためらいながら話す。",
    "afraid": "不安そうに、少し緊張して話す。",
    "panicked": "慌てた様子で、少し早口に話す。",
    "excited": "わくわくした様子で、弾むように話す。",
    "smug": "得意げに、少し自信を込めて話す。",
    "mischievous": "いたずらっぽく、軽やかに話す。",
    "cool": "少し冷ややかに、抑えた調子で話す。",
    "sleepy": "眠そうに、ゆっくり柔らかく話す。",
    "thinking": "考え込みながら、ゆっくり話す。",
    "agree": "うなずくように、穏やかに話す。",
    "disagree": "きっぱりと、しかし自然に話す。",
}

# Generated manifests retain raw face animation names as well as semantic aliases.
# ChatService advertises every available expression key to the LLM, so both forms
# need a speech cue. Non-emotional eye/idle poses intentionally use neutral delivery.
_IRODORI_EMOTION_ALIASES = {
    alias: emotion
    for emotion, aliases in {
        "neutral": (
            "wait", "wait2", "wait3", "wait4", "nothing", "left", "right",
            "close", "close2", "close3", "close4", "close5", "close6",
            "close7", "close8", "close9",
        ),
        "happy": ("joy",),
        "smile": ("smile1", "smile2", "smile3", "smile4"),
        "sad": ("sad2", "sad3", "down"),
        "angry": ("anger", "anger1", "anger2", "anger3", "anger4", "rebellion1", "rebellion2"),
        "angry_strong": ("anger_strong",),
        "surprised": ("surp", "surp2", "shy_surp"),
        "crying": ("cry", "cry2", "tear", "tear1", "tear2"),
        "shy": ("shy2", "shy3", "red"),
        "troubled": ("awkward", "bad", "bitter_smile", "bitter_smile2", "puzzle", "trouble"),
        "afraid": ("fear", "fear2"),
        "panicked": ("panic",),
        "excited": ("excite",),
        "smug": ("doya",),
        "mischievous": ("cheat",),
        "cool": ("jito", "jito2"),
        "sleepy": ("sleep",),
    }.items()
    for alias in aliases
}


def clean_spoken_text(text: str) -> str:
    value = str(text or "")
    japanese = _JA_JP.search(value)
    if japanese:
        value = japanese.group(1)
    value = _LANGUAGE_BLOCK.sub("", value)
    return _ACTION_TAG.sub("", value).strip()


def irodori_voice_id(character: str, fallback: str = "") -> str:
    """Resolve a catalog character id to the matching Irodori server voice alias."""
    key = character_asset_key(character)
    if re.fullmatch(r"[0-9]{2}", key):
        return f"person_{key}"
    return str(fallback or "").strip()


def irodori_emotion_caption(directives: Iterable[ActionDirective]) -> str:
    """Describe only emotional delivery, leaving identity to the reference voice."""
    parts: list[str] = []
    seen: set[str] = set()
    for directive in directives:
        emotion = _IRODORI_EMOTION_ALIASES.get(directive.key, directive.key)
        caption = _IRODORI_EMOTION_CAPTIONS.get(emotion, "")
        if caption and caption not in seen:
            parts.append(caption)
            seen.add(caption)
    return "".join(parts)


def emotion_category(key: str) -> str:
    """Reduce a manifest expression or gesture to an LLM-facing emotion."""
    category = _IRODORI_EMOTION_ALIASES.get(key, key)
    return category if category in _IRODORI_EMOTION_CAPTIONS else ""


def expression_choices(keys: Iterable[str], category: str) -> list[str]:
    """Available manifest expression keys for one emotion on the current outfit."""
    return sorted(key for key in keys if emotion_category(key) == category)


@dataclass(frozen=True, slots=True)
class TTSConfig:
    api_url: str
    voice: str = ""
    api_key: str = ""
    model: str = "tts-1"
    timeout_seconds: float = 60.0
    caption: str = ""


class Synthesizer(Protocol):
    def synthesize(self, text: str, cancel: threading.Event) -> tuple[bytes, str]: ...


class AudioPlayer(Protocol):
    def play(self, audio: bytes, media_type: str, level: Callable[[float], None],
             cancel: threading.Event) -> None: ...


class HttpTTSClient:
    """OpenAI speech-compatible endpoint; alternate servers can adapt this protocol."""

    def __init__(self, config: TTSConfig) -> None:
        self.config = config

    def build_payload(self, text: str) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.config.model,
            "voice": self.config.voice or "alloy",
            "input": clean_spoken_text(text),
            "response_format": "wav",
        }
        caption = self.config.caption.strip()
        if self.config.model.strip().casefold() == "irodori-tts" and caption:
            payload["irodori"] = {"caption": caption}
        return payload

    def synthesize(self, text: str, cancel: threading.Event) -> tuple[bytes, str]:
        if cancel.is_set():
            raise RuntimeError("TTS cancelled")
        url = self.config.api_url.strip().rstrip("/")
        if not url:
            raise ValueError("TTS API URL is empty")
        if not url.endswith("/audio/speech"):
            url += "/audio/speech" if url.endswith("/v1") else "/v1/audio/speech"
        payload = self.build_payload(text)
        headers = {"Content-Type": "application/json", "User-Agent": "ShinyColorsPet/0.0.1"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        request = urllib.request.Request(url, json.dumps(payload).encode(), headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                audio = response.read()
                media_type = response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"TTS HTTP {exc.code}: " +
                               exc.read(512).decode(errors="replace")) from exc
        except OSError as exc:
            raise RuntimeError(f"TTS request failed: {exc}") from exc
        if cancel.is_set():
            raise RuntimeError("TTS cancelled")
        if not audio:
            raise RuntimeError("TTS returned empty audio")
        return audio, media_type


class PlatformAudioPlayer:
    """Dependency-free WAV playback on Windows; SoundDevice fallback elsewhere."""

    def play(self, audio: bytes, media_type: str, level: Callable[[float], None],
             cancel: threading.Event) -> None:
        if os.name != "nt":
            SoundDeviceAudioPlayer().play(audio, media_type, level, cancel)
            return
        import winsound

        try:
            with wave.open(io.BytesIO(audio), "rb") as stream:
                rate = stream.getframerate()
                width = stream.getsampwidth()
                channels = stream.getnchannels()
                frames = stream.readframes(stream.getnframes())
        except (EOFError, wave.Error) as exc:
            raise RuntimeError(f"TTS returned invalid WAV: {exc}") from exc
        if width != 2 or rate <= 0 or channels <= 0:
            raise RuntimeError("TTS WAV must use 16-bit PCM")
        fd, temporary = tempfile.mkstemp(prefix="shiny-tts-", suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(audio)
            winsound.PlaySound(temporary, winsound.SND_FILENAME | winsound.SND_ASYNC)
            samples = array("h")
            samples.frombytes(frames)
            per_tick = max(channels, int(rate * channels / 30))
            maximum = 32768.0
            for start in range(0, len(samples), per_tick):
                if cancel.is_set():
                    break
                chunk = samples[start:start + per_tick]
                rms = math.sqrt(sum(value * value for value in chunk) / max(1, len(chunk)))
                level(min(1.0, rms / maximum * 8.0))
                time.sleep(len(chunk) / (rate * channels))
        finally:
            winsound.PlaySound(None, 0)
            level(0.0)
            Path(temporary).unlink(missing_ok=True)


class SoundDeviceAudioPlayer:
    """Optional local player that derives mouth openness from real PCM blocks."""

    def play(self, audio: bytes, media_type: str, level: Callable[[float], None],
             cancel: threading.Event) -> None:
        del media_type
        try:
            np = importlib.import_module("numpy")
            sd = importlib.import_module("sounddevice")
            sf = importlib.import_module("soundfile")
        except ImportError as exc:
            raise RuntimeError("Voice playback requires the 'voice' optional dependencies") from exc
        samples, rate = sf.read(io.BytesIO(audio), dtype="float32", always_2d=True)
        block = max(256, int(rate / 30))
        with sd.OutputStream(samplerate=rate, channels=samples.shape[1], dtype="float32") as stream:
            for start in range(0, len(samples), block):
                if cancel.is_set():
                    return
                chunk = samples[start:start + block]
                amplitude = float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0
                level(min(1.0, amplitude * 8.0))
                stream.write(chunk)
        level(0.0)


class VoiceCoordinator:
    """Guarantees mouth reset on success, cancellation, playback error, or no capability."""

    def __init__(self, synth: Synthesizer, player: AudioPlayer,
                 mouth: Callable[[float, float], bool]) -> None:
        self.synth, self.player, self.mouth = synth, player, mouth
        self.cancel_event = threading.Event()

    def speak(
        self,
        text: str,
        cancel: threading.Event | None = None,
        on_playback_start: Callable[[], None] | None = None,
        on_audio_ready: Callable[[bytes, str], None] | None = None,
    ) -> None:
        if cancel is None:
            self.cancel()
            self.cancel_event = threading.Event()
        else:
            self.cancel_event = cancel
        try:
            audio, media_type = self.synth.synthesize(clean_spoken_text(text), self.cancel_event)
            if self.cancel_event.is_set():
                raise RuntimeError("TTS cancelled")
            if on_audio_ready is not None:
                on_audio_ready(audio, media_type)
            if on_playback_start is not None:
                on_playback_start()
            if self.cancel_event.is_set():
                raise RuntimeError("TTS cancelled")
            self.player.play(audio, media_type, self._level, self.cancel_event)
        finally:
            self.mouth(0.0, 0.0)

    def _level(self, value: float) -> None:
        if not math.isfinite(value):
            value = 0.0
        normalized = max(0.0, min(1.0, value))
        # Spine lip animations need a visible minimum mix weight once speech is audible.
        if normalized > 0.01:
            normalized = max(0.35, normalized)
        self.mouth(normalized, 0.0)

    def cancel(self) -> None:
        self.cancel_event.set()
        self.mouth(0.0, 0.0)
