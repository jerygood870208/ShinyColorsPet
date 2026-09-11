"""Build the memory settings page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTextEdit,
)

from shiny_pet.chat import Relationship

from ._shared import _card, _character_combo, _heading, _save_button


def _install_memory(panel: Any) -> None:
    page = panel.add_navigation_page(
        "memory", "memory", "好感度／記憶", "好感度／記憶", "管理每位偶像獨立的關係狀態與長期記憶"
    )
    _, layout = _card(page)
    character = _character_combo(panel)
    affection = QSpinBox()
    affection.setRange(0, 100)
    mood = QLineEdit()
    summary = QTextEdit()
    summary.setMaximumHeight(90)
    memories = QListWidget()
    memories.setMinimumHeight(130)
    new_memory = QLineEdit()
    new_memory.setPlaceholderText("新增一段值得記住的事情")
    form = QFormLayout()
    form.addRow("偶像", character)
    form.addRow("好感度", affection)
    form.addRow("目前心情", mood)
    form.addRow("關係摘要", summary)
    layout.addLayout(form)
    _heading(layout, "長期記憶")
    layout.addWidget(memories)
    layout.addWidget(new_memory)
    buttons = QHBoxLayout()
    load = QPushButton("重新載入")
    buttons.addWidget(load)
    layout.addLayout(buttons)
    memory_buttons = QHBoxLayout()
    edit_memory = QPushButton("更新選取記憶")
    delete_memory = QPushButton("刪除選取記憶")
    refresh_summary = QPushButton("重新整理關係摘要")
    memory_buttons.addWidget(edit_memory)
    memory_buttons.addWidget(delete_memory)
    memory_buttons.addWidget(refresh_summary)
    layout.addLayout(memory_buttons)

    def refresh() -> None:
        key = str(character.currentData() or "")
        relation = panel.chat_database.relationship(key, panel.relationship_user_key())
        affection.setValue(relation.affection)
        mood.setText(relation.mood)
        summary.setPlainText(relation.summary)
        memories.clear()
        for record in panel.chat_database.memory_records(key, relation.user_key, limit=200):
            source = "AI" if "llm" in record.tags else "手動"
            memories.addItem(f"[{source}] {record.content}")
            memories.item(memories.count() - 1).setData(Qt.ItemDataRole.UserRole, record.id)

    def persist() -> None:
        key = str(character.currentData() or "")
        user_key = panel.relationship_user_key()
        panel.chat_database.update_relationship(
            Relationship(
                key,
                user_key,
                affection.value(),
                mood.text().strip() or "calm",
                summary.toPlainText().strip(),
            )
        )
        if new_memory.text().strip():
            if panel.chat_database.remember(key, user_key, new_memory.text(), ("manual",)):
                summary.setPlainText(
                    panel.chat_database.refresh_relationship_summary(key, user_key)
                )
            new_memory.clear()
        refresh()
        panel.log.append(f"{character.currentText()}：關係與記憶已儲存。")

    character.currentIndexChanged.connect(lambda _index: refresh())
    load.clicked.connect(refresh)
    _save_button(
        layout,
        "儲存關係與記憶",
        persist,
        success_text="已儲存目前偶像的關係與記憶",
    )

    def selected_memory_id() -> int:
        item = memories.currentItem()
        return int(item.data(Qt.ItemDataRole.UserRole) or 0) if item is not None else 0

    def load_memory() -> None:
        identifier = selected_memory_id()
        if not identifier:
            return
        record = next(
            (
                item
                for item in panel.chat_database.memory_records(
                    str(character.currentData() or ""), panel.relationship_user_key(), limit=500
                )
                if item.id == identifier
            ),
            None,
        )
        if record is not None:
            new_memory.setText(record.content)

    def update_memory() -> None:
        if panel.chat_database.update_memory(selected_memory_id(), new_memory.text()):
            new_memory.clear()
            summary.setPlainText(
                panel.chat_database.refresh_relationship_summary(
                    str(character.currentData() or ""), panel.relationship_user_key()
                )
            )
            refresh()

    def delete_selected_memory() -> None:
        if panel.chat_database.delete_memories([selected_memory_id()]):
            summary.setPlainText(
                panel.chat_database.refresh_relationship_summary(
                    str(character.currentData() or ""), panel.relationship_user_key()
                )
            )
            refresh()

    def rebuild_summary() -> None:
        summary.setPlainText(
            panel.chat_database.refresh_relationship_summary(
                str(character.currentData() or ""), panel.relationship_user_key()
            )
        )

    memories.itemSelectionChanged.connect(load_memory)
    edit_memory.clicked.connect(update_memory)
    delete_memory.clicked.connect(delete_selected_memory)
    refresh_summary.clicked.connect(rebuild_summary)
    panel.page_refreshers["memory"] = refresh
    refresh()
