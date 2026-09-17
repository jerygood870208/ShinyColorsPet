"""Thin transparent top-level pet window."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QVBoxLayout, QWidget

from shiny_pet.models import Manifest, load_manifest
from shiny_pet.models.abilities import resolve_abilities
from shiny_pet.renderer.webengine_spine36 import WebEngineSpine36Renderer

from .controllers import AnimationController, GazeController, InputController, LipSyncController
from .controllers.lifecycle import ModelLifecycleManager
from .controllers.passthrough import WindowsPassthrough
from .hit_overlay import HitOverlay


class PetWindow(QWidget):
    closed = Signal()
    renderer_failed = Signal(str)
    context_requested = Signal(object)
    double_clicked = Signal()

    def __init__(
        self,
        manifest_path: Path,
        *,
        runtime_root: Path | None = None,
        fps: int = 60,
        vsync: bool = True,
        quality: str = "balanced",
        scale: float = 1.0,
        hit_test_mode: str = "auto",
        debug_hit_areas: bool = False,
        gaze_enabled: bool = True,
        idle_enabled: bool = True,
        random_enabled: bool = True,
        random_interval_seconds: int = 30,
        standard_animation_policy: str = "all",
    ) -> None:
        super().__init__()
        self.manifest: Manifest = resolve_abilities(load_manifest(manifest_path)).manifest
        self.setWindowTitle(self.manifest.display_name)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.renderer = WebEngineSpine36Renderer(runtime_root, hit_test_mode=hit_test_mode)
        layout.addWidget(self.renderer)
        self.hit_overlay = HitOverlay(self, self.renderer) if debug_hit_areas else None
        self.renderer.set_frame_policy(fps, vsync, quality)
        self.renderer.set_scale(scale)
        capabilities = self.renderer.load_model(manifest_path)
        self.animation = AnimationController(
            self.renderer, self.manifest,
            idle_enabled=idle_enabled, random_enabled=random_enabled,
            standard_animation_policy=standard_animation_policy,
        )
        self.lipsync = LipSyncController(self.renderer, self.renderer.capabilities)
        self.gaze = GazeController(self.renderer, capabilities)
        self.gaze.enabled = gaze_enabled and capabilities.gaze
        self.gaze_timer = QTimer(self)
        self.gaze_timer.setInterval(33)
        self.gaze_timer.timeout.connect(self._update_gaze)
        if gaze_enabled:
            self.gaze_timer.start()
        self.random_timer = QTimer(self)
        self.random_timer.setInterval(random_interval_seconds * 1000)
        self.random_timer.timeout.connect(self.animation.play_random)
        if random_enabled:
            self.random_timer.start()
        self.input = InputController(self, self.renderer, self.renderer)
        self.passthrough = WindowsPassthrough(self, self.renderer)
        self.lifecycle = ModelLifecycleManager(
            self._stop_interactions, self.passthrough.stop, self.animation.stop,
            self.renderer.unload,
        )
        self.renderer.loadFinished.connect(lambda _ok: self.input.install_tree(self.renderer))
        self.input.clicked.connect(lambda: self.animation.play_gesture("click"))
        self.input.drag_started.connect(self.animation.start_drag)
        self.input.drag_finished.connect(self.animation.finish_drag)
        self.input.double_clicked.connect(self.double_clicked)
        self.input.context_requested.connect(self.context_requested)
        self.renderer.playback_finished.connect(self.animation.playback_finished)
        self.renderer.ready.connect(lambda _payload: self.animation.start_idle())
        self.renderer.failed.connect(self.renderer_failed)
        window = self.manifest.raw.get("window", {})
        self.resize(int(window.get("width", 640)), int(window.get("height", 960)))

    def _update_gaze(self) -> None:
        if not self.isVisible() or not self.gaze.enabled:
            return
        screen = self.screen()
        if screen is None:
            return
        center = self.mapToGlobal(self.rect().center())
        cursor = QCursor.pos()
        geometry = screen.availableGeometry()
        x = (cursor.x() - center.x()) / max(1.0, geometry.width() / 2.0)
        y = (cursor.y() - center.y()) / max(1.0, geometry.height() / 2.0)
        self.gaze.update(x, y, self.gaze_timer.interval() / 1000.0)

    def apply_interaction_settings(
        self, *, hit_test_mode: str, debug_hit_areas: bool, gaze_enabled: bool,
        idle_enabled: bool, random_enabled: bool, random_interval_seconds: int,
    ) -> None:
        self.renderer.set_hit_test_mode(hit_test_mode)
        if debug_hit_areas and self.hit_overlay is None:
            self.hit_overlay = HitOverlay(self, self.renderer)
            self.hit_overlay.show()
        elif not debug_hit_areas and self.hit_overlay is not None:
            self.hit_overlay.hide()
            self.hit_overlay.deleteLater()
            self.hit_overlay = None
        if not gaze_enabled and self.gaze.enabled:
            self.gaze.stop()
        self.gaze.enabled = gaze_enabled and self.renderer.capabilities.gaze
        if gaze_enabled:
            self.gaze_timer.start()
        else:
            self.gaze_timer.stop()
        self.animation.set_behavior(
            idle_enabled=idle_enabled, random_enabled=random_enabled,
        )
        if idle_enabled and self.renderer.is_ready:
            self.animation.ensure_idle()
        self.random_timer.setInterval(random_interval_seconds * 1000)
        if random_enabled:
            self.random_timer.start()
        else:
            self.random_timer.stop()

    def _stop_interactions(self) -> None:
        self.gaze_timer.stop()
        self.random_timer.stop()
        self.gaze.stop()

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        self.lifecycle.close()
        super().closeEvent(event)
        self.closed.emit()
