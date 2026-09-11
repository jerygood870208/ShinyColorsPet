"""Windows layered-window input policy, independent of native hit-test messages."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any, Protocol

from PySide6.QtCore import QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

from .input import HitTester


class InputSurface(HitTester, Protocol):
    @property
    def is_ready(self) -> bool: ...

    @property
    def failed(self) -> Any: ...

    def mapFromGlobal(self, point: QPoint, /) -> QPoint: ...  # noqa: N802


def input_style(style: int, passthrough: bool) -> int:
    """Preserve all other window flags, including the existing layered style."""
    return style | 0x20 if passthrough else style & ~0x20


class WindowsPassthrough(QObject):
    def __init__(self, window: QWidget, renderer: InputSurface) -> None:
        super().__init__(window)
        self._window = window
        self._renderer = renderer
        self._enabled = False
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self.refresh)
        if QApplication.platformName() in ("windows", "cocoa", "xcb"):
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def refresh(self) -> None:
        if not self._window.isVisible() or not self._renderer.is_ready:
            return
        # Keep the existing policy throughout a drag or an underlying application's click.
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        local = self._renderer.mapFromGlobal(QCursor.pos())
        enabled = not self._renderer.hit_test(local.x(), local.y()).hit
        if enabled == self._enabled:
            return
        if sys.platform != "win32":
            # Qt maps this to the platform input policy. Real macOS/X11 QA is
            # required; Wayland intentionally leaves the timer disabled.
            handle = self._window.windowHandle()
            if handle is not None:
                handle.setFlag(Qt.WindowType.WindowTransparentForInput, enabled)
                self._enabled = enabled
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        get_style = user32.GetWindowLongPtrW
        set_style = user32.SetWindowLongPtrW
        get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_style.restype = ctypes.c_ssize_t
        hwnd = int(self._window.winId())
        style = get_style(hwnd, -20)  # GWL_EXSTYLE
        ctypes.set_last_error(0)
        previous = set_style(hwnd, -20, input_style(style, enabled))
        error = ctypes.get_last_error()
        if previous == 0 and error:
            self._timer.stop()
            self._renderer.failed.emit(f"Cannot update Windows input policy: error {error}")
            return
        self._enabled = enabled
