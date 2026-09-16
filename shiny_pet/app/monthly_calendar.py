"""Month view for dated character events."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

from shiny_pet.i18n import tr, trf

_DAYS = ("星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六")
_HEADER_HEIGHT = 34
_DAY_NUMBER_HEIGHT = 28
_EVENT_HEIGHT = 22


class MonthlyCalendarView(QWidget):
    """Render a six-week month grid with selectable dated event chips."""

    edit_requested = Signal(str)
    create_requested = Signal(object)
    selection_changed = Signal(str)
    month_changed = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        today = date.today()
        self.year = today.year
        self.month = today.month
        self.events: list[dict[str, Any]] = []
        self.selected_id = ""
        self.event_rects: list[tuple[QRectF, str]] = []
        self.day_rects: list[tuple[QRectF, date]] = []
        self.setMinimumSize(820, 620)
        self.setAccessibleName(tr("角色月曆"))

    @property
    def month_title(self) -> str:
        return trf("{year} 年 {month} 月", year=self.year, month=self.month)

    def set_events(self, events: list[dict[str, Any]]) -> None:
        self.events = [dict(item) for item in events]
        if self.selected_id and not any(item.get("id") == self.selected_id for item in self.events):
            self.selected_id = ""
            self.selection_changed.emit("")
        self.update()

    def set_month(self, year: int, month: int) -> None:
        absolute = year * 12 + month - 1
        self.year, zero_month = divmod(absolute, 12)
        self.month = zero_month + 1
        self.month_changed.emit(self.year, self.month)
        self.update()

    def previous_month(self) -> None:
        self.set_month(self.year, self.month - 1)

    def next_month(self) -> None:
        self.set_month(self.year, self.month + 1)

    def show_today(self) -> None:
        today = date.today()
        self.set_month(today.year, today.month)

    def _weeks(self) -> list[list[date]]:
        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(self.year, self.month)
        while len(weeks) < 6:
            start = weeks[-1][-1] + timedelta(days=1)
            weeks.append([start + timedelta(days=offset) for offset in range(7)])
        return weeks[:6]

    def _event_at(self, position: QPointF) -> str:
        for rectangle, identifier in reversed(self.event_rects):
            if rectangle.contains(position):
                return identifier
        return ""

    def _date_at(self, position: QPointF) -> date | None:
        for rectangle, value in self.day_rects:
            if rectangle.contains(position):
                return value
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.selected_id = self._event_at(event.position())
        self.selection_changed.emit(self.selected_id)
        self.update()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        identifier = self._event_at(event.position())
        if identifier:
            self.edit_requested.emit(identifier)
        else:
            selected_date = self._date_at(event.position())
            if selected_date is not None:
                self.create_requested.emit(selected_date)
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QColor(255, 255, 255)
        text = QColor(60, 64, 67)
        muted = QColor(154, 160, 166)
        grid = QColor(218, 220, 224)
        painter.fillRect(self.rect(), base)
        column = self.width() / 7
        row_height = (self.height() - _HEADER_HEIGHT) / 6
        today = date.today()

        painter.setPen(text)
        header_font = painter.font()
        header_font.setBold(True)
        painter.setFont(header_font)
        for weekday, label in enumerate(_DAYS):
            painter.drawText(
                QRectF(weekday * column, 0, column, _HEADER_HEIGHT),
                Qt.AlignmentFlag.AlignCenter,
                tr(label),
            )

        self.day_rects.clear()
        self.event_rects.clear()
        weeks = self._weeks()
        for row, week in enumerate(weeks):
            for weekday, day in enumerate(week):
                rectangle = QRectF(
                    weekday * column,
                    _HEADER_HEIGHT + row * row_height,
                    column,
                    row_height,
                )
                self.day_rects.append((rectangle, day))
                # QPainter keeps the brush used by the preceding day number or event chip.
                # Paint every cell explicitly so that color can never leak into later days.
                painter.fillRect(rectangle, base)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(grid, 1))
                painter.drawRect(rectangle)
                self._paint_day_number(
                    painter,
                    rectangle,
                    day,
                    today,
                    day.year == self.year and day.month == self.month,
                    text,
                    muted,
                )
                self._paint_day_events(painter, rectangle, day, text)

    @staticmethod
    def _paint_day_number(
        painter: QPainter,
        rectangle: QRectF,
        day: date,
        today: date,
        in_current_month: bool,
        text: QColor,
        muted: QColor,
    ) -> None:
        number_rect = QRectF(rectangle.right() - 31, rectangle.top() + 3, 27, 24)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(text if in_current_month else muted)
        font = painter.font()
        font.setBold(day == today)
        painter.setFont(font)
        painter.drawText(number_rect, Qt.AlignmentFlag.AlignCenter, str(day.day))

    def _paint_day_events(
        self, painter: QPainter, cell: QRectF, day: date, text_color: QColor
    ) -> None:
        matching = [event for event in self.events if self._event_covers(event, day)]
        visible_slots = max(1, int((cell.height() - _DAY_NUMBER_HEIGHT - 5) / _EVENT_HEIGHT))
        for index, event in enumerate(matching[:visible_slots]):
            rectangle = QRectF(
                cell.left() + 4,
                cell.top() + _DAY_NUMBER_HEIGHT + index * _EVENT_HEIGHT,
                cell.width() - 8,
                _EVENT_HEIGHT - 3,
            )
            identifier = str(event.get("id", ""))
            self.event_rects.append((rectangle, identifier))
            hue = sum(ord(character) for character in identifier) % 360
            color = QColor.fromHsl(hue, 145, 115)
            painter.setPen(
                QPen(QColor(255, 255, 255), 2)
                if identifier == self.selected_id
                else QPen(color.lighter(145), 1)
            )
            painter.setBrush(color)
            painter.drawRoundedRect(rectangle, 4, 4)
            painter.setPen(QColor(255, 255, 255) if color.lightness() < 150 else text_color)
            title = str(event.get("title", ""))
            start_text = str(event.get("start_at", ""))
            try:
                start = datetime.fromisoformat(start_text).astimezone()
                prefix = (
                    start.strftime("%H:%M ")
                    if not bool(event.get("all_day", False)) and start.date() == day
                    else ""
                )
            except ValueError:
                prefix = ""
            painter.drawText(
                rectangle.adjusted(5, 0, -3, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                prefix + title,
            )
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        hidden = len(matching) - visible_slots
        if hidden > 0:
            painter.setPen(text_color)
            painter.drawText(
                QRectF(
                    cell.left() + 7,
                    cell.bottom() - 20,
                    cell.width() - 14,
                    17,
                ),
                Qt.AlignmentFlag.AlignLeft,
                tr("另有 {count} 項").format(count=hidden),
            )

    @staticmethod
    def _event_covers(event: dict[str, Any], day: date) -> bool:
        try:
            start = datetime.fromisoformat(str(event.get("start_at", ""))).astimezone()
            end = datetime.fromisoformat(str(event.get("end_at", ""))).astimezone()
        except ValueError:
            return False
        effective_end = end - timedelta(microseconds=1) if end > start else start
        return start.date() <= day <= effective_end.date()
