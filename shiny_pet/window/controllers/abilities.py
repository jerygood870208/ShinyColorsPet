"""Normalized input controllers for future voice and cursor integrations."""

from __future__ import annotations

import math

from shiny_pet.renderer.base import ModelCapabilities, PetRenderer


class LipSyncController:
    def __init__(self, renderer: PetRenderer, capabilities: ModelCapabilities) -> None:
        self.renderer = renderer
        self.enabled = capabilities.lip_sync

    def update(self, openness: float, form: float = 0.0) -> bool:
        if not math.isfinite(openness) or not math.isfinite(form):
            raise ValueError("mouth input must be finite")
        return self.enabled and self.renderer.set_mouth(
            max(0.0, min(1.0, openness)), max(-1.0, min(1.0, form))
        )

    def stop(self) -> bool:
        return self.update(0.0)


class GazeController:
    def __init__(self, renderer: PetRenderer, capabilities: ModelCapabilities) -> None:
        self.renderer = renderer
        self.enabled = capabilities.gaze
        self.position = (0.0, 0.0)
        self._elapsed = 0.0

    def update(self, x: float, y: float, dt: float) -> bool:
        if not all(math.isfinite(v) for v in (x, y, dt)) or dt < 0:
            raise ValueError("gaze input must be finite; dt must be non-negative")
        if not self.enabled:
            return False
        alpha = 1.0 - math.exp(-dt / 0.08)
        self.position = tuple(  # type: ignore[assignment]
            old + (max(-1.0, min(1.0, value)) - old) * alpha
            for old, value in zip(self.position, (x, y), strict=True)
        )
        self._elapsed += dt
        if self._elapsed < 1 / 30:
            return False
        self._elapsed = 0.0
        return self.renderer.set_gaze(*self.position)

    def stop(self) -> bool:
        self.position = (0.0, 0.0)
        self._elapsed = 0.0
        return self.enabled and self.renderer.set_gaze(0.0, 0.0)
