"""Build the memory album settings page."""

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


def _install_memory_album(panel: Any) -> None:
    page = panel.add_navigation_page(
        "memory_album", "album", "記憶相簿", "記憶相簿", "回顧目前關係線中由偶像記住的重要片段"
    )
    _, layout = _card(page)
    character = _character_combo(panel)
    search = QLineEdit()
    search.setPlaceholderText("搜尋記憶")
    album = QListWidget()
    album.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
    album.setMinimumHeight(430)
    layout.addWidget(character)
    layout.addWidget(search)
    layout.addWidget(album, 1)
    actions = QHBoxLayout()
    export_button = QPushButton("匯出目前結果…")
    delete_button = QPushButton("刪除選取記憶")
    actions.addWidget(export_button)
    actions.addWidget(delete_button)
    layout.addLayout(actions)

    def refresh() -> None:
        album.clear()
        records = panel.chat_database.memory_records(
            str(character.currentData() or ""), panel.relationship_user_key(), search.text(), 500
        )
        for record in records:
            album.addItem(f"{format_stored_local(record.created_at)} · {record.content}")
            album.item(album.count() - 1).setData(Qt.ItemDataRole.UserRole, record.id)
        if not album.count():
            album.addItem("還沒有保存的長期記憶。")

    character.currentIndexChanged.connect(lambda _index: refresh())
    search.textChanged.connect(lambda _text: refresh())

    def delete_selected() -> None:
        identifiers = [
            int(item.data(Qt.ItemDataRole.UserRole))
            for item in album.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole)
        ]
        if (
            identifiers
            and QMessageBox.question(
                panel, "刪除長期記憶", f"確定刪除選取的 {len(identifiers)} 項記憶？"
            )
            == QMessageBox.StandardButton.Yes
        ):
            panel.chat_database.delete_memories(identifiers)
            panel.chat_database.refresh_relationship_summary(
                str(character.currentData() or ""), panel.relationship_user_key()
            )
            refresh()

    def export_results() -> None:
        path, _ = QFileDialog.getSaveFileName(
            panel, "匯出記憶", "memories.md", "Markdown (*.md);;JSON (*.json)"
        )
        if not path:
            return
        records = panel.chat_database.memory_records(
            str(character.currentData() or ""), panel.relationship_user_key(), search.text(), 2000
        )
        target = Path(path)
        if target.suffix.lower() == ".json":
            payload = [
                {
                    "id": item.id,
                    "content": item.content,
                    "tags": list(item.tags),
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                }
                for item in reversed(records)
            ]
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            target.write_text(
                "\n".join(f"- {item.created_at} — {item.content}" for item in reversed(records))
                + "\n",
                encoding="utf-8",
            )

    delete_button.clicked.connect(delete_selected)
    export_button.clicked.connect(export_results)
    panel.page_refreshers["memory_album"] = refresh
    refresh()
