"""Debug overlay is a sibling of the renderer, so it cannot contaminate alpha grabs."""

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from shiny_pet.renderer.webengine_spine36 import WebEngineSpine36Renderer


class HitOverlay(QWidget):
    def __init__(self, parent: QWidget, renderer: WebEngineSpine36Renderer) -> None:
        super().__init__(parent)
        self._renderer = renderer
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def refresh(self) -> None:
        self.setGeometry(self._renderer.geometry())
        self.raise_()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        geometry = self._renderer.hit_geometry
        polygons = [(p, "#00ff80") for p in geometry.attachments]
        if geometry.model is not None:
            polygons.append((geometry.model, "#ffb000"))
        for polygon, color in polygons:
            painter.setPen(QPen(QColor(color), 2))
            points = [QPointF(x * self.width(), y * self.height()) for x, y in polygon.points]
            painter.drawPolygon(QPolygonF(points))
            painter.drawText(points[0], polygon.name)
        painter.setPen(QColor("#ff4040"))
        painter.drawText(10, 20, f"Hit mode: {self._renderer.hit_test_mode}")
        painter.end()
