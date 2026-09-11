"""Build the chat integration settings page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
)

from ._shared import _card, _save_button


def _install_chat_integration(panel: Any) -> None:
    page = panel.add_navigation_page(
        "chat_integration", "chat", "聊天接入", "聊天接入", "設定外部聊天訊息接入的本機端點"
    )
    _, layout = _card(page)
    enabled = QCheckBox("啟用外部聊天接入")
    enabled.setChecked(bool(panel.settings.get("chat_integration_enabled", False)))
    host = QLineEdit(str(panel.settings.get("chat_integration_host", "127.0.0.1")))
    port = QSpinBox()
    port.setRange(1024, 65535)
    port.setValue(int(panel.settings.get("chat_integration_port", 17384)))
    token = QLineEdit(str(panel.settings.get("chat_integration_token", "")))
    token.setEchoMode(QLineEdit.EchoMode.Password)
    form = QFormLayout()
    form.addRow("", enabled)
    form.addRow("監聽位址", host)
    form.addRow("連接埠", port)
    form.addRow("Token", token)
    layout.addLayout(form)
    status = QLabel(
        "僅接受本機回環位址。POST /v1/chat/messages，使用 Authorization: Bearer <Token>。"
    )
    status.setObjectName("Muted")
    layout.addWidget(status)

    def save() -> None:
        if host.text().strip() not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("聊天接入目前只允許本機回環位址")
        panel.settings.update(
            chat_integration_enabled=enabled.isChecked(),
            chat_integration_host=host.text().strip(),
            chat_integration_port=port.value(),
            chat_integration_token=token.text().strip(),
        )
        panel.persist()
        panel.configure_chat_integration()
        generated = str(panel.settings.get("chat_integration_token", ""))
        if generated and not token.text().strip():
            token.setText(generated)
        running = panel.chat_integration_server
        display_host = (
            f"[{running.host}]"
            if running is not None and ":" in running.host
            else (running.host if running is not None else "")
        )
        status.setText(
            f"服務已啟動：http://{display_host}:{running.port}/v1/chat/messages"
            if running is not None
            else "服務目前未啟動；詳細原因請查看活動記錄。"
        )

    _save_button(layout, "儲存聊天接入設定", save)
    page.layout().addStretch()
