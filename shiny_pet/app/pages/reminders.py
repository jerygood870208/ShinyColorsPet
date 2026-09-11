"""Build the reminders settings page."""

# ruff: noqa: E501

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
)

from shiny_pet.reminders import Reminder

from ._shared import _card, _character_combo, _heading, _save_button


def _install_reminders(panel: Any) -> None:
    page = panel.add_navigation_page(
        "reminders", "reminders", "鬧鐘／番茄鐘", "鬧鐘／番茄鐘", "由指定偶像提供定時提醒與專注陪伴"
    )
    _, layout = _card(page)
    _heading(layout, "新增提醒")
    character = _character_combo(panel)
    text = QLineEdit()
    text.setPlaceholderText("提醒內容")
    when = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
    when.setCalendarPopup(True)
    enabled = QCheckBox("啟用")
    enabled.setChecked(True)
    repeat_checks = [QCheckBox(label) for label in ("一", "二", "三", "四", "五", "六", "日")]
    repeat_row = QHBoxLayout()
    for checkbox in repeat_checks:
        repeat_row.addWidget(checkbox)
    form = QFormLayout()
    form.addRow("偶像", character)
    form.addRow("內容", text)
    form.addRow("時間", when)
    form.addRow("狀態", enabled)
    form.addRow("每週重複", repeat_row)
    layout.addLayout(form)
    reminder_list = QListWidget()

    def refresh() -> None:
        reminder_list.clear()
        for item in panel.reminder_queue.reminders:
            repeat = "、".join(str(day + 1) for day in item.repeat_days) or "單次"
            state = "啟用" if item.enabled else "停用"
            row = f"{item.at:%Y-%m-%d %H:%M} · {repeat} · {state} · {item.text}"
            reminder_list.addItem(row)
            reminder_list.item(reminder_list.count() - 1).setData(Qt.ItemDataRole.UserRole, item.id)

    def add_reminder() -> bool:
        value = text.text().strip()
        if not value:
            return False
        at = datetime.fromtimestamp(when.dateTime().toSecsSinceEpoch())
        days = tuple(index for index, box in enumerate(repeat_checks) if box.isChecked())
        item = Reminder(
            uuid.uuid4().hex,
            value,
            at,
            days,
            str(character.currentData() or ""),
            enabled.isChecked(),
        )
        panel.reminder_queue.reminders.append(item)
        panel.save_reminders()
        text.clear()
        refresh()
        return True

    _save_button(
        layout,
        "新增鬧鐘／提醒",
        add_reminder,
        success_text="提醒已新增並啟用",
    )
    layout.addWidget(reminder_list)
    reminder_buttons = QHBoxLayout()
    edit_reminder = QPushButton("更新選取提醒")
    delete_reminder = QPushButton("刪除選取提醒")
    test_reminder = QPushButton("立即測試")
    reminder_buttons.addWidget(edit_reminder)
    reminder_buttons.addWidget(delete_reminder)
    reminder_buttons.addWidget(test_reminder)
    layout.addLayout(reminder_buttons)

    def selected_index() -> int:
        selected = reminder_list.currentItem()
        if selected is None:
            return -1
        identifier = str(selected.data(Qt.ItemDataRole.UserRole) or "")
        return next(
            (
                index
                for index, item in enumerate(panel.reminder_queue.reminders)
                if item.id == identifier
            ),
            -1,
        )

    def load_selected() -> None:
        index = selected_index()
        if index < 0:
            return
        item = panel.reminder_queue.reminders[index]
        text.setText(item.text)
        when.setDateTime(QDateTime.fromSecsSinceEpoch(int(item.at.timestamp())))
        enabled.setChecked(item.enabled)
        character.setCurrentIndex(max(0, character.findData(item.character)))
        for day, box in enumerate(repeat_checks):
            box.setChecked(day in item.repeat_days)

    def update_selected() -> None:
        index = selected_index()
        if index < 0 or not text.text().strip():
            return
        current = panel.reminder_queue.reminders[index]
        panel.reminder_queue.reminders[index] = replace(
            current,
            text=text.text().strip(),
            at=datetime.fromtimestamp(when.dateTime().toSecsSinceEpoch()),
            repeat_days=tuple(day for day, box in enumerate(repeat_checks) if box.isChecked()),
            character=str(character.currentData() or ""),
            enabled=enabled.isChecked(),
        )
        panel.save_reminders()
        refresh()

    def delete_selected() -> None:
        index = selected_index()
        if index < 0:
            return
        del panel.reminder_queue.reminders[index]
        panel.save_reminders()
        refresh()

    def test_selected() -> None:
        index = selected_index()
        if index < 0:
            return
        panel.deliver_reminder(panel.reminder_queue.reminders[index])

    reminder_list.itemSelectionChanged.connect(load_selected)
    edit_reminder.clicked.connect(update_selected)
    delete_reminder.clicked.connect(delete_selected)
    test_reminder.clicked.connect(test_selected)
    _, pomo_layout = _card(page)
    _heading(pomo_layout, "番茄鐘", "建立一個專注結束提醒；完成時會由選取偶像通知。")
    minutes = QSpinBox()
    minutes.setRange(1, 180)
    minutes.setValue(25)
    purpose = QLineEdit()
    purpose.setPlaceholderText("這次要專注的事情")
    pomo_form = QFormLayout()
    pomo_form.addRow("專注分鐘", minutes)
    pomo_form.addRow("說明", purpose)
    pomo_layout.addLayout(pomo_form)

    def start_pomodoro() -> None:
        label = purpose.text().strip() or "專注時間"
        item = Reminder(
            uuid.uuid4().hex,
            f"{label}完成了，休息一下吧！",
            datetime.now() + timedelta(minutes=minutes.value()),
            (),
            str(character.currentData() or ""),
        )
        panel.reminder_queue.reminders.append(item)
        panel.save_reminders()
        refresh()

    _save_button(
        pomo_layout,
        "開始番茄鐘",
        start_pomodoro,
        success_text="番茄鐘已開始",
    )
    refresh()
