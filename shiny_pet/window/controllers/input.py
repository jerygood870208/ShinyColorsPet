"""Mouse gestures kept separate from the renderer and top-level window."""

from __future__ import annotations

from typing import Any, Protocol

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from shiny_pet.renderer.base import HitResult


class HitTester(Protocol):
    def hit_test(self, x: float, y: float) -> HitResult: ...


class InputController(QObject):
    clicked = Signal()
    double_clicked = Signal()
    context_requested = Signal(object)
    drag_started = Signal()
    drag_finished = Signal()

    def __init__(self, window: QWidget, renderer_widget: QWidget, renderer: HitTester) -> None:
        super().__init__(window)
        self._window = window
        self._renderer = renderer
        self._drag_offset = QPoint()
        self._dragging = False
        self._moved = False
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(250)
        self._click_timer.timeout.connect(self.clicked)
        renderer_widget.installEventFilter(self)

    def install_tree(self, root: QWidget) -> None:
        root.installEventFilter(self)
        for child in root.findChildren(QWidget):
            child.installEventFilter(self)

    def accepts_input_at(self, x: float, y: float) -> bool:
        return self._renderer.hit_test(x, y).hit

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        del watched
        if not isinstance(event, QMouseEvent):
            return False
        position = event.position()
        event_type = event.type()
        if event_type == QEvent.Type.MouseButtonPress:
            if not self.accepts_input_at(position.x(), position.y()):
                return False
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = event.globalPosition().toPoint() - self._window.pos()
                self._dragging = True
                self._moved = False
                return True
            if event.button() == Qt.MouseButton.RightButton:
                self.context_requested.emit(event.globalPosition().toPoint())
                return True
        elif event_type == QEvent.Type.MouseMove and self._dragging:
            if not self._moved:
                self.drag_started.emit()
            self._moved = True
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            return True
        elif event_type == QEvent.Type.MouseButtonRelease and self._dragging:
            self._dragging = False
            if event.button() == Qt.MouseButton.LeftButton and not self._moved:
                self._click_timer.start()
            elif event.button() == Qt.MouseButton.LeftButton and self._moved:
                self.drag_finished.emit()
            return True
        elif event_type == QEvent.Type.MouseButtonDblClick:
            self._dragging = False
            self._click_timer.stop()
            self.double_clicked.emit()
            return True
        return False

    def event(self, event: Any) -> bool:
        return super().event(event)
