"""Renderer-neutral contracts used by pet controllers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class PlaybackToken:
    """Opaque identity for one playback request."""

    value: int


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Features that callers may use without renderer-specific assumptions."""

    expressions: bool = False
    lip_sync: bool = False
    gaze: bool = False
    semantic_hit_areas: bool = False
    alpha_mask: bool = False
    skins: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    lip_sync_driver: str = "disabled"
    gaze_driver: str = "disabled"
    expression_drivers: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RendererEvent:
    name: str
    channel: str
    token: PlaybackToken | None
    time: float
    int_value: int = 0
    float_value: float = 0.0
    string_value: str = ""


class EventSource:
    """Synchronous callbacks; subscribe returns an idempotent unsubscribe function."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[RendererEvent], None]] = []

    def subscribe(self, callback: Callable[[RendererEvent], None]) -> Callable[[], None]:
        self._callbacks.append(callback)

        def unsubscribe() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return unsubscribe

    def emit(self, event: RendererEvent) -> None:
        for callback in tuple(self._callbacks):
            callback(event)


@dataclass(frozen=True, slots=True)
class HitResult:
    hit: bool
    area: str | None = None
    source: str = "none"


@dataclass(frozen=True, slots=True)
class AlphaMask:
    width: int
    height: int
    pixels: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("alpha mask dimensions must be positive")
        if len(self.pixels) != self.width * self.height:
            raise ValueError("alpha mask must contain one byte per pixel")

    def alpha_at(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return 0
        return self.pixels[y * self.width + x]


@runtime_checkable
class PetRenderer(Protocol):
    def subscribe_events(self, callback: Callable[[RendererEvent], None]) -> Callable[[], None]: ...

    def load_model(self, manifest_path: Path) -> ModelCapabilities: ...

    def unload(self) -> None: ...

    def set_frame_policy(self, fps: int, vsync: bool, quality: str) -> None: ...

    def set_scale(self, scale: float) -> None: ...

    def play(
        self,
        channel: str,
        animation: str,
        *,
        loop: bool,
        mix_seconds: float = 0.0,
    ) -> PlaybackToken: ...

    def clear(self, channel: str | None = None) -> None: ...

    def is_finished(self, token: PlaybackToken) -> bool: ...

    def set_expression(self, semantic_name: str) -> bool: ...

    def set_mouth(self, openness: float, form: float = 0.0) -> bool: ...

    def set_gaze(self, x: float, y: float) -> bool: ...

    def hit_test(self, x: float, y: float) -> HitResult: ...

    def snapshot_alpha_mask(self) -> AlphaMask | None: ...
