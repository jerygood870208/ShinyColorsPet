"""Weekly routine calendar visualization."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from shiny_pet.i18n import tr

_DAYS = ("星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六")
_HEADER_HEIGHT = 42
_HOUR_HEIGHT = 52
_GUTTER_WIDTH = 58


class WeeklyCalendarView(QWidget):
    """Render minute-accurate routine blocks on a seven-day, 24-hour grid."""

    edit_requested = Signal(str)
    create_requested = Signal(int, int)
    selection_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.routines: list[dict[str, Any]] = []
        self.event_rects: list[tuple[QRectF, str]] = []
        self.selected_id = ""
        self.setMinimumSize(820, _HEADER_HEIGHT + 24 * _HOUR_HEIGHT)
        self.setMouseTracking(True)
        self.setAccessibleName(tr("週作息表"))

    def set_routines(self, routines: list[dict[str, Any]]) -> None:
        self.routines = [dict(item) for item in routines]
        if self.selected_id and not any(
            item.get("id") == self.selected_id for item in self.routines
        ):
            self.selected_id = ""
            self.selection_changed.emit("")
        self.update()

    def _column_width(self) -> float:
        return max(1.0, (self.width() - _GUTTER_WIDTH) / 7)

    def _event_at(self, position: QPointF) -> str:
        for rectangle, identifier in reversed(self.event_rects):
            if rectangle.contains(position):
                return identifier
        return ""

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.selected_id = self._event_at(event.position())
        self.selection_changed.emit(self.selected_id)
        self.update()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        identifier = self._event_at(event.position())
        if identifier:
            self.edit_requested.emit(identifier)
        elif event.position().x() >= _GUTTER_WIDTH and event.position().y() >= _HEADER_HEIGHT:
            column = self._column_width()
            weekday = max(0, min(6, int((event.position().x() - _GUTTER_WIDTH) / column)))
            raw_minutes = int((event.position().y() - _HEADER_HEIGHT) * 60 / _HOUR_HEIGHT)
            minute = max(0, min(23 * 60 + 45, round(raw_minutes / 15) * 15))
            self.create_requested.emit(weekday, minute)
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        background = palette.color(palette.ColorRole.Base)
        text = palette.color(palette.ColorRole.Text)
        muted = palette.color(palette.ColorRole.Mid)
        grid = palette.color(palette.ColorRole.Midlight)
        painter.fillRect(self.rect(), background)
        column = self._column_width()

        today = (self._today_weekday() + 1) % 7
        painter.fillRect(
            QRectF(_GUTTER_WIDTH + today * column, 0, column, self.height()),
            QColor(66, 133, 244, 18),
        )
        painter.setPen(QPen(grid, 1))
        for day in range(8):
            x = _GUTTER_WIDTH + day * column
            painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        painter.drawLine(QPointF(0, _HEADER_HEIGHT), QPointF(self.width(), _HEADER_HEIGHT))
        for hour in range(25):
            y = _HEADER_HEIGHT + hour * _HOUR_HEIGHT
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(_GUTTER_WIDTH, y), QPointF(self.width(), y))
            if hour < 24:
                painter.setPen(muted)
                painter.drawText(
                    QRectF(0, y - 8, _GUTTER_WIDTH - 8, 18),
                    Qt.AlignmentFlag.AlignRight,
                    f"{hour:02}:00",
                )
        painter.setPen(text)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        for day, label in enumerate(_DAYS):
            painter.drawText(
                QRectF(_GUTTER_WIDTH + day * column, 0, column, _HEADER_HEIGHT),
                Qt.AlignmentFlag.AlignCenter,
                tr(label),
            )

        self.event_rects.clear()
        for routine in self.routines:
            self._paint_routine(painter, routine, column, text)
        now = datetime.now()
        current_day = (now.weekday() + 1) % 7
        current_y = _HEADER_HEIGHT + (now.hour * 60 + now.minute) * _HOUR_HEIGHT / 60
        current_x = _GUTTER_WIDTH + current_day * column
        painter.setPen(QPen(QColor(234, 67, 53), 2))
        painter.setBrush(QColor(234, 67, 53))
        painter.drawEllipse(QPointF(current_x, current_y), 4, 4)
        painter.drawLine(
            QPointF(current_x, current_y),
            QPointF(current_x + column, current_y),
        )

    @staticmethod
    def _today_weekday() -> int:
        return datetime.now().weekday()

    def _paint_routine(
        self,
        painter: QPainter,
        routine: dict[str, Any],
        column: float,
        text_color: QColor,
    ) -> None:
        try:
            weekday = int(routine.get("weekday", 0)) % 7
            start = int(routine.get("start_minute", 0))
            end = int(routine.get("end_minute", 60))
        except (TypeError, ValueError):
            return
        if not 0 <= start < end <= 24 * 60:
            return
        rectangle = QRectF(
            _GUTTER_WIDTH + weekday * column + 3,
            _HEADER_HEIGHT + start * _HOUR_HEIGHT / 60 + 2,
            column - 6,
            max(18, (end - start) * _HOUR_HEIGHT / 60 - 4),
        )
        identifier = str(routine.get("id", ""))
        self.event_rects.append((rectangle, identifier))
        hue = sum(ord(character) for character in identifier) % 360
        color = QColor.fromHsl(hue, 145, 115)
        if identifier == self.selected_id:
            painter.setPen(QPen(QColor(255, 255, 255), 3))
        else:
            painter.setPen(QPen(color.lighter(145), 1))
        painter.setBrush(color)
        painter.drawRoundedRect(rectangle, 6, 6)
        painter.setPen(QColor(255, 255, 255) if color.lightness() < 150 else text_color)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        title = str(routine.get("title", ""))
        start_text = f"{start // 60:02}:{start % 60:02}"
        end_text = f"{end // 60:02}:{end % 60:02}"
        label = title if rectangle.height() < 38 else f"{title}\n{start_text}–{end_text}"
        painter.drawText(
            rectangle.adjusted(6, 3, -4, -3),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            label,
        )
