"""Deterministic renderer for controller and contract tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .base import AlphaMask, EventSource, HitResult, ModelCapabilities, PlaybackToken, RendererEvent


class NullRenderer:
    def __init__(self, capabilities: ModelCapabilities | None = None) -> None:
        self._capabilities = capabilities or ModelCapabilities()
        self._loaded = False
        self._next_token = 1
        self._active: dict[str, PlaybackToken] = {}
        self._finished: set[PlaybackToken] = set()
        self.frame_policy = (60, True, "balanced")
        self.scale = 1.0
        self.events = EventSource()

    def subscribe_events(self, callback: Callable[[RendererEvent], None]) -> Callable[[], None]:
        return self.events.subscribe(callback)

    def load_model(self, manifest_path: Path) -> ModelCapabilities:
        if not isinstance(manifest_path, Path):
            raise TypeError("manifest_path must be a pathlib.Path")
        self._loaded = True
        return self._capabilities

    def unload(self) -> None:
        self.clear()
        self._loaded = False

    def set_frame_policy(self, fps: int, vsync: bool, quality: str) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        if not quality.strip():
            raise ValueError("quality must not be empty")
        self.frame_policy = (fps, vsync, quality)

    def set_scale(self, scale: float) -> None:
        if scale <= 0:
            raise ValueError("scale must be positive")
        self.scale = scale

    def play(
        self,
        channel: str,
        animation: str,
        *,
        loop: bool,
        mix_seconds: float = 0.0,
    ) -> PlaybackToken:
        del loop
        self._require_loaded()
        if not channel or not animation:
            raise ValueError("channel and animation must not be empty")
        if mix_seconds < 0:
            raise ValueError("mix_seconds must not be negative")
        previous = self._active.get(channel)
        if previous is not None:
            self._finished.add(previous)
        token = PlaybackToken(self._next_token)
        self._next_token += 1
        self._active[channel] = token
        return token

    def clear(self, channel: str | None = None) -> None:
        channels = list(self._active) if channel is None else [channel]
        for name in channels:
            token = self._active.pop(name, None)
            if token is not None:
                self._finished.add(token)

    def is_finished(self, token: PlaybackToken) -> bool:
        return token in self._finished

    def set_expression(self, semantic_name: str) -> bool:
        self._require_loaded()
        return bool(semantic_name) and self._capabilities.expressions

    def set_mouth(self, openness: float, form: float = 0.0) -> bool:
        self._require_loaded()
        if not 0.0 <= openness <= 1.0 or not -1.0 <= form <= 1.0:
            raise ValueError("mouth values are outside their normalized ranges")
        return self._capabilities.lip_sync

    def set_gaze(self, x: float, y: float) -> bool:
        self._require_loaded()
        if not -1.0 <= x <= 1.0 or not -1.0 <= y <= 1.0:
            raise ValueError("gaze values are outside the normalized range")
        return self._capabilities.gaze

    def hit_test(self, x: float, y: float) -> HitResult:
        del x, y
        self._require_loaded()
        return HitResult(False)

    def snapshot_alpha_mask(self) -> AlphaMask | None:
        self._require_loaded()
        return None

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("no model is loaded")
