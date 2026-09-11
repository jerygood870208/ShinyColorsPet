"""Build the window settings settings page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QSpinBox,
)

from ._shared import _card, _save_button


def _install_floating(panel: Any) -> None:
    page = panel.add_navigation_page(
        "floating", "floating", "懸浮窗設定", "懸浮窗設定", "調整獨立聊天室的預設尺寸與置頂行為"
    )
    _, layout = _card(page)
    width = QSpinBox()
    width.setRange(360, 1000)
    width.setValue(int(panel.settings.get("chat_window_width", 430)))
    height = QSpinBox()
    height.setRange(540, 1200)
    height.setValue(int(panel.settings.get("chat_window_height", 720)))
    top = QCheckBox("聊天室保持最上層")
    top.setChecked(bool(panel.settings.get("chat_window_topmost", False)))
    form = QFormLayout()
    form.addRow("寬度", width)
    form.addRow("高度", height)
    form.addRow("", top)
    layout.addLayout(form)

    def save() -> None:
        panel.settings.update(
            chat_window_width=width.value(),
            chat_window_height=height.value(),
            chat_window_topmost=top.isChecked(),
        )
        panel.persist()
        panel.apply_chat_window_preferences()

    _save_button(layout, "套用聊天室視窗設定", save)
    page.layout().addStretch()
