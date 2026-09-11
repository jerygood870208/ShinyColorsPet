"""Build the screen tools settings page."""

# ruff: noqa: E501

from __future__ import annotations

import json
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QSpinBox,
    QTextEdit,
)

from ._shared import _card, _heading, _save_button


def _install_screen_tools(panel: Any) -> None:
    page = panel.add_navigation_page(
        "screen_tools",
        "display",
        "螢幕認知與工具控制",
        "螢幕認知與工具控制",
        "所有畫面內容與外部工具都必須由使用者明確啟用",
    )
    _, layout = _card(page)
    enabled = QCheckBox("允許在送出聊天時擷取一次螢幕並加入去敏感化情境")
    enabled.setChecked(bool(panel.settings["screen_awareness_enabled"]))
    include_title = QCheckBox("摘要中加入前景視窗標題（可能包含敏感資訊）")
    include_title.setChecked(
        bool(panel.settings.get("screen_awareness_include_window_title", False))
    )
    max_width = QSpinBox()
    max_width.setRange(640, 1920)
    max_width.setValue(int(panel.settings.get("screen_awareness_max_screenshot_width", 1280)))
    servers = QTextEdit(
        json.dumps(panel.settings.get("mcp_servers", []), ensure_ascii=False, indent=2)
    )
    servers.setMaximumHeight(300)
    servers.setPlaceholderText(
        '[{"name":"local","url":"http://127.0.0.1:...",'
        '"token_env":"MCP_TOKEN","allowed_tools":["tool_name"]}]'
    )
    layout.addWidget(enabled)
    layout.addWidget(include_title)
    screenshot_form = QFormLayout()
    screenshot_form.addRow("送給視覺模型的最長邊", max_width)
    layout.addLayout(screenshot_form)
    _heading(
        layout,
        "MCP 伺服器",
        "HTTP 僅限本機；遠端必須使用 HTTPS。只有 allowed_tools 明列的工具會提供給模型，每次回覆最多執行一次。",
    )
    layout.addWidget(servers)

    def save() -> None:
        value = json.loads(servers.toPlainText() or "[]")
        if not isinstance(value, list):
            raise ValueError("MCP 設定必須是 JSON 陣列")
        panel.settings["screen_awareness_enabled"] = enabled.isChecked()
        panel.settings["screen_awareness_include_window_title"] = include_title.isChecked()
        panel.settings["screen_awareness_max_screenshot_width"] = max_width.value()
        panel.settings["mcp_servers"] = value
        panel.persist()

    _save_button(layout, "儲存螢幕與工具設定", save)
    page.layout().addStretch()
