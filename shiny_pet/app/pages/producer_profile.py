"""Build the single local producer profile settings page."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFormLayout, QLineEdit, QSpinBox, QTextEdit

from shiny_pet.agent import normalize_month_day

from ._shared import _card, _heading, _save_button


def _install_producer_profile(panel: Any) -> None:
    page = panel.add_navigation_page(
        "producer",
        "p_letter",
        "製作人資料",
        "製作人資料",
        "設定製作人的本機資料",
    )
    _, layout = _card(page)
    _heading(
        layout,
        "製作人資料",
        "名稱只儲存在本機，不會傳送給聊天模型。生日、年齡和其他細節會依目前介面語言提供給聊天模型。",
    )
    name = QLineEdit(str(panel.settings.get("producer_name", "")))
    birthday = QLineEdit(str(panel.settings.get("producer_birthday", "")))
    birthday.setPlaceholderText("MM-DD（例如：03-19）")
    age = QSpinBox()
    age.setRange(0, 150)
    age.setSpecialValueText("未填寫")
    age.setValue(int(panel.settings.get("producer_age", 0)))
    details = QTextEdit(str(panel.settings.get("producer_details", "")))
    details.setPlaceholderText("可自由填寫偶像對製作人的印象")
    details.setMaximumHeight(150)
    form = QFormLayout()
    form.addRow("名稱", name)
    form.addRow("生日", birthday)
    form.addRow("年齡", age)
    form.addRow("其他細節", details)
    layout.addLayout(form)

    def save() -> None:
        panel.settings["producer_name"] = name.text().strip()
        normalized = normalize_month_day(birthday.text())
        if birthday.text().strip() and not normalized.replace("-", "").isdigit():
            raise ValueError("生日請使用 MM-DD，例如 03-19。")
        panel.settings["producer_birthday"] = normalized
        birthday.setText(normalized)
        panel.settings["producer_age"] = age.value()
        panel.settings["producer_details"] = details.toPlainText().strip()
        panel.persist()

    _save_button(
        layout,
        "儲存製作人資料",
        save,
        success_text="已儲存製作人資料",
    )
    page.layout().addStretch()
