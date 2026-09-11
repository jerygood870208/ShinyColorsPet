"""Sprite-only pet; does not import or start Qt WebEngine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from shiny_pet.renderer.chibi import ChibiPetWidget

from .controllers.input import InputController
from .controllers.lifecycle import ModelLifecycleManager
from .controllers.passthrough import WindowsPassthrough


class ChibiWindow(QWidget):
    closed = Signal()
    context_requested = Signal(object)

    def __init__(self, image: Path, frames: Path, scale: float = 1.0) -> None:
        super().__init__()
        self.setWindowTitle(image.stem)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.renderer = ChibiPetWidget(image, frames, scale)
        layout.addWidget(self.renderer)
        self.input = InputController(self, self.renderer, self.renderer)
        self.input.clicked.connect(lambda: self.renderer.play("waving"))
        self.input.context_requested.connect(self.context_requested)
        self.passthrough = WindowsPassthrough(self, self.renderer)
        self.lifecycle = ModelLifecycleManager(self.passthrough.stop, self.renderer.unload)
        self.adjustSize()

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        self.lifecycle.close()
        super().closeEvent(event)
        self.closed.emit()
