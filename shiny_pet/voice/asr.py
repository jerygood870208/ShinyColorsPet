"""OpenAI-compatible ASR request with explicit cancellation checks."""

from __future__ import annotations

import importlib
import io
import json
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True, slots=True)
class MicrophoneTestResult:
    rms: float
    peak: float

    @property
    def level_percent(self) -> int:
        return round(min(1.0, self.rms * 8.0) * 100)


def input_devices() -> tuple[tuple[int, str], ...]:
    """Return available recording devices without requiring voice extras at startup."""
    try:
        sd = importlib.import_module("sounddevice")
        devices = sd.query_devices()
    except Exception:
        return ()
    result: list[tuple[int, str]] = []
    for index, device in enumerate(devices):
        try:
            channels = int(device["max_input_channels"])
            name = str(device["name"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if channels > 0 and name:
            result.append((index, name))
    return tuple(result)


def resolve_input_device(device: int) -> int:
    """Keep the saved microphone when available; otherwise use the system default."""
    if device < 0:
        return -1
    available = input_devices()
    if not available or any(index == device for index, _label in available):
        return device
    return -1


def test_input_device(device: int = -1, *, seconds: float = 2.0) -> MicrophoneTestResult:
    """Capture a short sample and report its RMS/peak without retaining audio."""
    try:
        np = importlib.import_module("numpy")
        sd = importlib.import_module("sounddevice")
    except ImportError as exc:
        raise RuntimeError("麥克風測試需要 voice 錄音元件") from exc
    chunks: list[object] = []

    def callback(data: object, _frames: object, _time: object, _status: object) -> None:
        chunks.append(data.copy())  # type: ignore[attr-defined]

    resolved = resolve_input_device(device)
    selected = None if resolved < 0 else resolved
    try:
        with sd.InputStream(
            device=selected, samplerate=16000, channels=1, dtype="float32", callback=callback,
        ):
            threading.Event().wait(max(0.25, min(5.0, float(seconds))))
    except Exception as exc:
        raise RuntimeError(f"無法使用選取的麥克風：{exc}") from exc
    if not chunks:
        raise RuntimeError("麥克風沒有傳回任何音訊")
    samples = np.concatenate(chunks, axis=0)
    rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    return MicrophoneTestResult(rms=max(0.0, rms), peak=max(0.0, peak))


def is_connection_reset_error(exc: BaseException) -> bool:
    """Recognize Windows/native-server connection resets through wrapped exceptions."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ConnectionResetError) or getattr(current, "winerror", None) == 10054:
            return True
        current = current.__cause__ or current.__context__
    return "WinError 10054" in str(exc)


def normalize_asr_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("ASR API URL is empty")
    parts = urlsplit(raw if "://" in raw else "http://" + raw)
    path = parts.path.rstrip("/")
    if not path.endswith("/audio/transcriptions"):
        path += "/audio/transcriptions" if path.endswith("/v1") else "/v1/audio/transcriptions"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


@dataclass(frozen=True, slots=True)
class ASRConfig:
    api_url: str
    api_key: str = ""
    model: str = "whisper-1"
    language: str = ""
    timeout_seconds: float = 60.0


class OpenAIASRClient:
    def __init__(self, config: ASRConfig) -> None:
        self.config = config

    def transcribe(self, audio: bytes, media_type: str,
                   cancel: threading.Event) -> str:
        if not audio:
            raise ValueError("ASR requires recorded audio")
        if cancel.is_set():
            raise RuntimeError("ASR cancelled")
        boundary = "----ShinyPet" + uuid.uuid4().hex
        fields = {"model": self.config.model}
        if self.config.language:
            fields["language"] = self.config.language
        chunks: list[bytes] = []
        for key, value in fields.items():
            chunks.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\""
                           f"\r\n\r\n{value}\r\n").encode())
        chunks.append(
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
             "filename=\"speech.wav\"\r\nContent-Type: " + media_type + "\r\n\r\n").encode()
        )
        chunks.extend((audio, f"\r\n--{boundary}--\r\n".encode()))
        headers = {"Content-Type": "multipart/form-data; boundary=" + boundary,
                   "User-Agent": "ShinyColorsPet/0.0.1"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        request = urllib.request.Request(normalize_asr_url(self.config.api_url),
                                         b"".join(chunks), headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"ASR HTTP {exc.code}: " +
                               exc.read(512).decode(errors="replace")) from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"ASR request failed: {exc}") from exc
        if cancel.is_set():
            raise RuntimeError("ASR cancelled")
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("ASR returned no transcript")
        return text.strip()


class SoundDeviceRecorder:
    """Cancelable mono recorder. Cancellation returns captured WAV instead of hanging."""

    def __init__(self, device: int = -1) -> None:
        resolved = resolve_input_device(device)
        self.device = None if resolved < 0 else resolved

    def record(self, cancel: threading.Event, *, sample_rate: int = 16000,
               max_seconds: float = 60.0) -> tuple[bytes, str]:
        try:
            np = importlib.import_module("numpy")
            sd = importlib.import_module("sounddevice")
            sf = importlib.import_module("soundfile")
        except ImportError as exc:
            raise RuntimeError(
                "Voice recording requires the 'voice' optional dependencies"
            ) from exc
        chunks: list[object] = []
        def callback(data: object, _frames: object, _time: object, _status: object) -> None:
            chunks.append(data.copy())  # type: ignore[attr-defined]

        with sd.InputStream(
            device=self.device, samplerate=sample_rate, channels=1,
            dtype="float32", callback=callback,
        ):
            cancel.wait(max(1.0, min(300.0, float(max_seconds))))
        if not chunks:
            raise RuntimeError("No audio was recorded")
        samples = np.concatenate(chunks, axis=0)
        output = io.BytesIO()
        sf.write(output, samples, sample_rate, format="WAV", subtype="PCM_16")
        return output.getvalue(), "audio/wav"
