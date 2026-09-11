"""Renderer-neutral normalized geometry for synchronous fallback hit tests."""

from __future__ import annotations

from dataclasses import dataclass

from .base import HitResult


@dataclass(frozen=True)
class HitPolygon:
    name: str
    points: tuple[tuple[float, float], ...]

    def contains(self, x: float, y: float) -> bool:
        inside = False
        for i, (ax, ay) in enumerate(self.points):
            bx, by = self.points[i - 1]
            cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
            if (
                abs(cross) < 1e-9
                and min(ax, bx) <= x <= max(ax, bx)
                and min(ay, by) <= y <= max(ay, by)
            ):
                return True
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
                inside = not inside
        return inside


@dataclass(frozen=True)
class HitGeometry:
    attachments: tuple[HitPolygon, ...] = ()
    model: HitPolygon | None = None

    def hit_test(self, x: float, y: float, *, model_only: bool = False) -> HitResult:
        if self.attachments and not model_only:
            for polygon in reversed(self.attachments):
                if polygon.contains(x, y):
                    return HitResult(True, polygon.name, "attachment")
            return HitResult(False, source="attachment")
        if self.model is not None:
            return HitResult(self.model.contains(x, y), source="model-bounds")
        return HitResult(False, source="none")
