"""Independent sprite mode adapted from BANDORI-PET-REV PixelPetWidget, GPL-3.0.

Retains the spriteSheet/animations layout and three-beat frame timing. Input
and window ownership live in controllers instead of the sprite painter.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

from .base import HitResult


class ChibiPetWidget(QWidget):
    failed = Signal(str)
    frame_changed = Signal()

    def __init__(self, image_path: Path, frames_path: Path, scale: float = 1.0) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.sheet = QImage(str(image_path))
        if self.sheet.isNull():
            raise ValueError(f"Cannot decode sprite: {image_path}")
        data = json.loads(frames_path.read_text(encoding="utf-8-sig"))
        sheet = data.get("spriteSheet", {})
        cols, rows = sheet.get("totalCols"), sheet.get("totalRows")
        if (type(cols) is not int or type(rows) is not int or cols <= 0 or rows <= 0
                or self.sheet.width() % cols or self.sheet.height() % rows):
            raise ValueError("Invalid spriteSheet grid")
        self.frame_width = self.sheet.width() // cols
        self.frame_height = self.sheet.height() // rows
        self.animations = data.get("animations", {})
        if not isinstance(self.animations, dict) or "idle" not in self.animations:
            raise ValueError("Sprite needs an idle animation")
        for name, animation in self.animations.items():
            if not isinstance(animation, dict):
                raise ValueError(f"Invalid sprite animation: {name}")
            row, count = animation.get("row"), animation.get("frames")
            fps = animation.get("fps", 8)
            if (type(row) is not int or not 0 <= row < rows or type(count) is not int
                    or not 1 <= count <= cols or type(fps) is not int or not 1 <= fps <= 120
                    or type(animation.get("loop", True)) is not bool):
                raise ValueError(f"Invalid sprite animation: {name}")
        self.animation = "idle"
        self.frame = 0
        self.is_ready = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.set_scale(scale)
        self.play("idle")

    def set_scale(self, scale: float) -> None:
        if not math.isfinite(scale) or not 0.1 <= scale <= 4:
            raise ValueError("scale must be 0.1–4")
        self.setFixedSize(max(1, round(self.frame_width * scale)),
                          max(1, round(self.frame_height * scale)))

    def play(self, name: str) -> bool:
        if name not in self.animations:
            return False
        self.animation, self.frame = name, 0
        self.timer.start(round(3000 / self.animations[name].get("fps", 8)))
        self.update()
        self.frame_changed.emit()
        return True

    def advance(self) -> None:
        animation = self.animations[self.animation]
        self.frame += 1
        if self.frame >= animation["frames"]:
            if animation.get("loop", True):
                self.frame = 0
            else:
                self.play("idle")
        self.update()
        self.frame_changed.emit()

    def source(self) -> QRect:
        return QRect(self.frame * self.frame_width,
                     self.animations[self.animation]["row"] * self.frame_height,
                     self.frame_width, self.frame_height)

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        if not self.is_ready:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(self.rect(), self.sheet, self.source())
        painter.end()

    def hit_test(self, x: float, y: float) -> HitResult:
        if not self.is_ready or not (0 <= x < self.width() and 0 <= y < self.height()):
            return HitResult(False)
        source = self.source()
        sx = source.x() + int(x * self.frame_width / self.width())
        sy = source.y() + int(y * self.frame_height / self.height())
        return HitResult(self.sheet.pixelColor(sx, sy).alpha() > 8, source="sprite-alpha")

    def unload(self) -> None:
        self.timer.stop()
        self.is_ready = False
        self.sheet = QImage()
        self.update()
