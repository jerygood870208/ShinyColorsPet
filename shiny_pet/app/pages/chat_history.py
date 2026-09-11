"""Build the chat history settings page."""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
)

from shiny_pet.local_time import format_stored_local

from ._shared import _card, _character_combo


def _install_chat_history(panel: Any) -> None:
    page = panel.add_navigation_page(
        "chat_history", "history", "聊天記錄", "聊天記錄", "按偶像查看各自保存的私人對話"
    )
    _, layout = _card(page)
    character = _character_combo(panel)
    search = QLineEdit()
    search.setPlaceholderText("搜尋聊天內容")
    history = QListWidget()
    history.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
    history.setMinimumHeight(400)
    layout.addWidget(character)
    layout.addWidget(search)
    layout.addWidget(history, 1)
    actions = QHBoxLayout()
    export_button = QPushButton("匯出目前結果…")
    delete_button = QPushButton("刪除選取訊息")
    actions.addWidget(export_button)
    actions.addWidget(delete_button)
    layout.addLayout(actions)

    def refresh() -> None:
        history.clear()
        records = panel.chat_database.search_messages(
            str(character.currentData() or ""), search.text(), 1000
        )
        for item in records:
            speaker = "你" if item.role == "user" else character.currentText()
            history.addItem(f"{speaker}　{format_stored_local(item.created_at)}\n{item.content}")
            history.item(history.count() - 1).setData(Qt.ItemDataRole.UserRole, item.id)

    def delete_selected() -> None:
        identifiers = [int(item.data(Qt.ItemDataRole.UserRole)) for item in history.selectedItems()]
        if (
            identifiers
            and QMessageBox.question(
                panel, "刪除聊天記錄", f"確定刪除選取的 {len(identifiers)} 則訊息？"
            )
            == QMessageBox.StandardButton.Yes
        ):
            panel.chat_database.delete_messages(identifiers)
            refresh()

    def export_results() -> None:
        path, _ = QFileDialog.getSaveFileName(
            panel, "匯出聊天記錄", "chat-history.md", "Markdown (*.md);;JSON (*.json);;Text (*.txt)"
        )
        if not path:
            return
        records = panel.chat_database.search_messages(
            str(character.currentData() or ""), search.text(), 2000
        )
        target = Path(path)
        if target.suffix.lower() == ".json":
            target.write_text(
                json.dumps(
                    [
                        item.__dict__
                        if hasattr(item, "__dict__")
                        else {
                            "id": item.id,
                            "character": item.character,
                            "role": item.role,
                            "content": item.content,
                            "created_at": item.created_at,
                        }
                        for item in reversed(records)
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            lines = [
                f"## {item.created_at} · {item.role}\n\n{item.content}\n"
                for item in reversed(records)
            ]
            target.write_text("\n".join(lines), encoding="utf-8")

    character.currentIndexChanged.connect(lambda _index: refresh())
    search.textChanged.connect(lambda _text: refresh())
    delete_button.clicked.connect(delete_selected)
    export_button.clicked.connect(export_results)
    refresh()
