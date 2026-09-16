"""Manage visual weekly routines, dated character events, and diaries."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any, cast

from PySide6.QtCore import QDateTime, Qt, QTime, QTimer
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from shiny_pet.i18n import tr

from ..monthly_calendar import MonthlyCalendarView
from ..weekly_calendar import WeeklyCalendarView
from ._shared import _card, _character_combo, _heading

_DAYS = ("星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六")


class _WrappingListWidget(QListWidget):
    """A single-column list whose rows reflow when the viewport width changes."""

    def __init__(self) -> None:
        super().__init__()
        self.setWordWrap(True)
        self.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.setUniformItemSizes(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, self.doItemsLayout)


def _routine_minutes(item: dict[str, Any]) -> tuple[int, int]:
    start = int(item.get("start_minute", int(item.get("start_hour", 0)) * 60))
    end = int(item.get("end_minute", int(item.get("end_hour", 1)) * 60))
    return start, end


class _RoutineDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        record: dict[str, Any] | None = None,
        *,
        weekday: int = 0,
        start_minute: int = 9 * 60,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("編輯週作息" if record else "新增週作息"))
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.weekday = QComboBox()
        self.weekday.addItems([tr(day) for day in _DAYS])
        self.start = QTimeEdit()
        self.end = QTimeEdit()
        for editor in (self.start, self.end):
            editor.setDisplayFormat("HH:mm")
            editor.setKeyboardTracking(False)
        self.midnight = QCheckBox(tr("結束於隔日 00:00"))
        self.title = QLineEdit()
        self.title.setPlaceholderText(tr("例如：上課、練習、休息"))
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(90)
        form.addRow(tr("星期"), self.weekday)
        form.addRow(tr("開始時間"), self.start)
        form.addRow(tr("結束時間"), self.end)
        form.addRow("", self.midnight)
        form.addRow(tr("行程名稱"), self.title)
        form.addRow(tr("備註"), self.notes)
        layout.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("ErrorText")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.midnight.toggled.connect(lambda checked: self.end.setEnabled(not checked))

        if record:
            start, end = _routine_minutes(record)
            weekday = int(record.get("weekday", 0)) % 7
            self.title.setText(str(record.get("title", "")))
            self.notes.setPlainText(str(record.get("notes", "")))
        else:
            start = max(0, min(23 * 60 + 45, start_minute))
            end = min(24 * 60, start + 60)
        self.weekday.setCurrentIndex(weekday)
        self.start.setTime(QTime(start // 60, start % 60))
        self.midnight.setChecked(end == 24 * 60)
        shown_end = min(end, 23 * 60 + 59)
        self.end.setTime(QTime(shown_end // 60, shown_end % 60))

    def values(self) -> dict[str, Any]:
        start = self.start.time().hour() * 60 + self.start.time().minute()
        end = (
            24 * 60
            if self.midnight.isChecked()
            else self.end.time().hour() * 60 + self.end.time().minute()
        )
        return {
            "weekday": self.weekday.currentIndex(),
            "start_minute": start,
            "end_minute": end,
            "title": " ".join(self.title.text().split())[:300],
            "notes": self.notes.toPlainText().strip()[:1500],
        }

    def _accept_if_valid(self) -> None:
        values = self.values()
        if not values["title"]:
            self.error.setText(tr("請輸入行程名稱"))
            return
        if int(values["end_minute"]) <= int(values["start_minute"]):
            self.error.setText(tr("結束時間必須晚於開始時間"))
            return
        self.accept()


class _CalendarDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        record: dict[str, Any] | None = None,
        *,
        selected_date: date | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("編輯月曆行程" if record else "新增月曆行程"))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit()
        self.title.setPlaceholderText(tr("行程名稱"))
        self.all_day = QCheckBox(tr("整天"))
        self.start = QDateTimeEdit()
        self.end = QDateTimeEdit()
        for editor in (self.start, self.end):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("yyyy-MM-dd HH:mm")
            editor.setKeyboardTracking(False)
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(100)
        form.addRow(tr("行程名稱"), self.title)
        form.addRow("", self.all_day)
        form.addRow(tr("開始時間"), self.start)
        self.end_label = QLabel(tr("結束時間"))
        form.addRow(self.end_label, self.end)
        form.addRow(tr("備註"), self.notes)
        layout.addLayout(form)
        self.error = QLabel("")
        self.error.setObjectName("ErrorText")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.all_day.toggled.connect(self._set_all_day)

        if record:
            self.title.setText(str(record.get("title", "")))
            self.notes.setPlainText(str(record.get("notes", "")))
            start = datetime.fromisoformat(str(record.get("start_at", ""))).astimezone()
            end = datetime.fromisoformat(str(record.get("end_at", ""))).astimezone()
            all_day = bool(record.get("all_day", False))
        else:
            day = selected_date or date.today()
            start = (
                datetime.combine(day, datetime.now().time())
                .astimezone()
                .replace(minute=0, second=0, microsecond=0)
            )
            if start <= datetime.now().astimezone():
                start += timedelta(hours=1)
            end = start + timedelta(hours=1)
            all_day = False
        self.start.setDateTime(QDateTime.fromSecsSinceEpoch(int(start.timestamp())))
        self.end.setDateTime(QDateTime.fromSecsSinceEpoch(int(end.timestamp())))
        self.all_day.setChecked(all_day)
        self._set_all_day(all_day)

    def _set_all_day(self, checked: bool) -> None:
        self.start.setDisplayFormat("yyyy-MM-dd" if checked else "yyyy-MM-dd HH:mm")
        self.end.setVisible(not checked)
        self.end_label.setVisible(not checked)
        if checked:
            start = cast(datetime, self.start.dateTime().toPython()).astimezone()
            midnight = start.replace(hour=0, minute=0, second=0, microsecond=0)
            self.start.setDateTime(QDateTime.fromSecsSinceEpoch(int(midnight.timestamp())))

    def values(self) -> dict[str, Any]:
        start = cast(datetime, self.start.dateTime().toPython()).astimezone()
        all_day = self.all_day.isChecked()
        if all_day:
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        else:
            end = cast(datetime, self.end.dateTime().toPython()).astimezone()
        return {
            "title": " ".join(self.title.text().split())[:300],
            "start_at": start.isoformat(timespec="minutes"),
            "end_at": end.isoformat(timespec="minutes"),
            "all_day": all_day,
            "notes": self.notes.toPlainText().strip()[:1500],
        }

    def _accept_if_valid(self) -> None:
        values = self.values()
        if not values["title"]:
            self.error.setText(tr("請輸入行程名稱"))
            return
        if datetime.fromisoformat(str(values["end_at"])) <= datetime.fromisoformat(
            str(values["start_at"])
        ):
            self.error.setText(tr("結束時間必須晚於開始時間"))
            return
        self.accept()


def _install_agent_planner(panel: Any) -> None:
    page = panel.add_navigation_page(
        "agent_planner",
        "reminders",
        "角色行事曆與日記",
        "角色行事曆與日記",
        "管理角色的週作息表、月曆行程與日記",
    )
    _, layout = _card(page)
    character = _character_combo(panel)
    layout.addWidget(character)
    tabs = QTabWidget()
    layout.addWidget(tabs)

    weekly_tab = QWidget()
    weekly_layout = QVBoxLayout(weekly_tab)
    _heading(
        weekly_layout,
        "週作息表",
        "雙擊空白時間新增作息；雙擊行程區塊即可編輯，可精確設定至分鐘",
    )
    weekly_actions = QHBoxLayout()
    weekly_add = QPushButton("新增作息")
    weekly_add.setObjectName("PrimaryButton")
    weekly_edit = QPushButton("編輯選取")
    weekly_delete = QPushButton("刪除選取")
    weekly_edit.setEnabled(False)
    weekly_delete.setEnabled(False)
    weekly_actions.addWidget(weekly_add)
    weekly_actions.addWidget(weekly_edit)
    weekly_actions.addWidget(weekly_delete)
    weekly_actions.addStretch()
    weekly_layout.addLayout(weekly_actions)
    weekly_scroll = QScrollArea()
    weekly_scroll.setWidgetResizable(True)
    weekly_scroll.setMinimumHeight(520)
    weekly_view = WeeklyCalendarView()
    weekly_scroll.setWidget(weekly_view)
    weekly_layout.addWidget(weekly_scroll)
    tabs.addTab(weekly_tab, tr("週作息表"))

    calendar_tab = QWidget()
    calendar_layout = QVBoxLayout(calendar_tab)
    _heading(
        calendar_layout,
        "角色月曆",
        "雙擊日期新增行程；聊天可記住日期明確的共同約會，指定日期行程優先於週作息表",
    )
    calendar_toolbar = QHBoxLayout()
    calendar_previous = QPushButton("‹")
    calendar_today = QPushButton("今天")
    calendar_next = QPushButton("›")
    calendar_month = QLabel("")
    calendar_month.setObjectName("SectionTitle")
    calendar_add = QPushButton("新增月曆行程")
    calendar_add.setObjectName("PrimaryButton")
    calendar_edit = QPushButton("編輯選取")
    calendar_delete = QPushButton("刪除選取")
    calendar_edit.setEnabled(False)
    calendar_delete.setEnabled(False)
    for widget in (calendar_previous, calendar_today, calendar_next):
        calendar_toolbar.addWidget(widget)
    calendar_toolbar.addWidget(calendar_month)
    calendar_toolbar.addStretch()
    calendar_toolbar.addWidget(calendar_add)
    calendar_toolbar.addWidget(calendar_edit)
    calendar_toolbar.addWidget(calendar_delete)
    calendar_layout.addLayout(calendar_toolbar)
    calendar_view = MonthlyCalendarView()
    calendar_layout.addWidget(calendar_view)
    tabs.addTab(calendar_tab, tr("角色月曆"))

    diary_tab, diary_layout, diary_list = _list_tab()
    diary_delete = QPushButton("刪除選取")
    diary_layout.addWidget(diary_delete)
    tabs.addTab(diary_tab, tr("日記"))

    def selected_id(listing: QListWidget) -> str:
        item = listing.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    def save() -> None:
        panel.store.save(panel.settings)
        refresh()

    def delete(key: str, identifier: str) -> None:
        if not identifier:
            return
        with panel._agent_data_lock:
            panel.settings[key] = [
                item for item in panel.settings[key] if item.get("id") != identifier
            ]
            save()

    def open_weekly(identifier: str = "", weekday: int = 0, start_minute: int = 9 * 60) -> None:
        record = next(
            (
                item
                for item in panel.settings["character_weekly_routines"]
                if item.get("id") == identifier
            ),
            None,
        )
        dialog = _RoutineDialog(panel, record, weekday=weekday, start_minute=start_minute)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        with panel._agent_data_lock:
            if record is None:
                panel.settings["character_weekly_routines"].append(
                    {
                        "id": uuid.uuid4().hex,
                        "character": str(character.currentData() or ""),
                        **values,
                    }
                )
            else:
                record.update(values)
                record.pop("start_hour", None)
                record.pop("end_hour", None)
            save()

    def open_calendar(identifier: str = "", selected_date: date | None = None) -> None:
        record = next(
            (item for item in panel.settings["character_calendar"] if item.get("id") == identifier),
            None,
        )
        try:
            dialog = _CalendarDialog(panel, record, selected_date=selected_date)
        except ValueError:
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        with panel._agent_data_lock:
            if record is None:
                panel.settings["character_calendar"].append(
                    {
                        "id": uuid.uuid4().hex,
                        "character": str(character.currentData() or ""),
                        "status": "scheduled",
                        "source": "user",
                        **values,
                    }
                )
            else:
                record.update(values)
            save()
        start = datetime.fromisoformat(str(values["start_at"]))
        calendar_view.set_month(start.year, start.month)

    def refresh() -> None:
        current = str(character.currentData() or "")
        diary_list.clear()
        routines = [
            item
            for item in panel.settings.get("character_weekly_routines", [])
            if item.get("character") == current
        ]
        normalized = []
        for item in routines:
            start, end = _routine_minutes(item)
            normalized.append({**item, "start_minute": start, "end_minute": end})
        weekly_view.set_routines(normalized)
        calendar_view.set_events(
            [
                item
                for item in panel.settings.get("character_calendar", [])
                if item.get("character") == current
            ]
        )
        for item in panel.settings.get("character_diaries", []):
            if item.get("character") == current:
                _append(
                    diary_list,
                    item,
                    f"{item.get('date', '')} · {item.get('title', '')}\n{item.get('content', '')}",
                )

    weekly_add.clicked.connect(lambda: open_weekly())
    weekly_edit.clicked.connect(lambda: open_weekly(weekly_view.selected_id))
    weekly_delete.clicked.connect(
        lambda: delete("character_weekly_routines", weekly_view.selected_id)
    )
    weekly_view.edit_requested.connect(open_weekly)
    weekly_view.create_requested.connect(lambda day, minute: open_weekly("", day, minute))

    def weekly_selection_changed(identifier: str) -> None:
        weekly_edit.setEnabled(bool(identifier))
        weekly_delete.setEnabled(bool(identifier))

    weekly_view.selection_changed.connect(weekly_selection_changed)

    def calendar_selection_changed(identifier: str) -> None:
        calendar_edit.setEnabled(bool(identifier))
        calendar_delete.setEnabled(bool(identifier))

    def calendar_month_changed(_year: int, _month: int) -> None:
        calendar_month.setText(calendar_view.month_title)

    calendar_previous.clicked.connect(calendar_view.previous_month)
    calendar_today.clicked.connect(calendar_view.show_today)
    calendar_next.clicked.connect(calendar_view.next_month)
    calendar_add.clicked.connect(lambda: open_calendar())
    calendar_edit.clicked.connect(lambda: open_calendar(calendar_view.selected_id))
    calendar_delete.clicked.connect(lambda: delete("character_calendar", calendar_view.selected_id))
    calendar_view.edit_requested.connect(open_calendar)
    calendar_view.create_requested.connect(lambda selected: open_calendar("", cast(date, selected)))
    calendar_view.selection_changed.connect(calendar_selection_changed)
    calendar_view.month_changed.connect(calendar_month_changed)
    calendar_month_changed(calendar_view.year, calendar_view.month)
    diary_delete.clicked.connect(lambda: delete("character_diaries", selected_id(diary_list)))
    character.currentIndexChanged.connect(lambda _index: refresh())
    panel.page_refreshers["agent_planner"] = refresh
    refresh()
    QTimer.singleShot(0, lambda: weekly_scroll.verticalScrollBar().setValue(8 * 52))
    page.layout().addStretch()


def _list_tab() -> tuple[QWidget, QVBoxLayout, QListWidget]:
    tab = QWidget()
    layout = QVBoxLayout(tab)
    listing = _WrappingListWidget()
    listing.setMinimumHeight(360)
    layout.addWidget(listing)
    return tab, layout, listing


def _append(listing: QListWidget, record: dict[str, Any], text: str) -> None:
    listing.addItem(text)
    listing.item(listing.count() - 1).setData(Qt.ItemDataRole.UserRole, record.get("id"))
