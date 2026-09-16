"""View and edit per-character lore and inter-character relationships."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from shiny_pet.i18n import tr, trf

from ._shared import _card, _character_combo, _heading


def _primary(label: str) -> QPushButton:
    button = QPushButton(tr(label))
    button.setObjectName("PrimaryButton")
    return button


def _install_character_knowledge(panel: Any) -> None:
    page = panel.add_navigation_page(
        "character_knowledge", "book", "角色知識", "角色知識",
        "查看並逐筆管理角色背景設定與人物關係，也可由 JSON 批次匯入",
    )
    _, layout = _card(page)
    character = _character_combo(panel)
    layout.addWidget(QLabel(tr("角色")))
    layout.addWidget(character)
    tabs = QTabWidget()
    layout.addWidget(tabs)

    lore_tab = QWidget()
    lore_layout = QVBoxLayout(lore_tab)
    _heading(lore_layout, "背景知識", "聊天時會依最新訊息自動選取最相關的最多五筆。")
    lore_count = QLabel()
    lore_count.setObjectName("Muted")
    lore_list = QListWidget()
    lore_list.setMinimumHeight(210)
    lore_title = QLineEdit()
    lore_title.setPlaceholderText(tr("例如：喜歡的地方"))
    lore_content = QTextEdit()
    lore_content.setMaximumHeight(120)
    lore_content.setPlaceholderText(tr("輸入角色背景事實；請勿放入要求模型執行的指令"))
    lore_tags = QLineEdit()
    lore_tags.setPlaceholderText(tr("以逗號分隔，例如：喜好, 日常"))
    lore_importance = QSpinBox()
    lore_importance.setRange(1, 10)
    lore_importance.setValue(5)
    lore_form = QFormLayout()
    lore_form.addRow(tr("標題"), lore_title)
    lore_form.addRow(tr("內容"), lore_content)
    lore_form.addRow(tr("標籤"), lore_tags)
    lore_form.addRow(tr("重要度"), lore_importance)
    lore_layout.addWidget(lore_count)
    lore_layout.addWidget(lore_list)
    lore_layout.addLayout(lore_form)
    lore_buttons = QHBoxLayout()
    lore_new = QPushButton(tr("新增／清空"))
    lore_save = _primary("儲存知識")
    lore_delete = QPushButton(tr("刪除選取"))
    lore_import = QPushButton(tr("匯入 lore JSON"))
    for button in (lore_new, lore_save, lore_delete, lore_import):
        lore_buttons.addWidget(button)
    lore_layout.addLayout(lore_buttons)
    tabs.addTab(lore_tab, tr("背景知識"))

    relation_tab = QWidget()
    relation_layout = QVBoxLayout(relation_tab)
    _heading(relation_layout, "人物關係", "提到對方姓名時，人物關係會優先提供給模型。")
    relation_count = QLabel()
    relation_count.setObjectName("Muted")
    relation_list = QListWidget()
    relation_list.setMinimumHeight(210)
    relation_other = QLineEdit()
    relation_other.setPlaceholderText(tr("對方姓名"))
    relation_label = QLineEdit()
    relation_label.setPlaceholderText(tr("例如：團體夥伴、摯友"))
    relation_description = QTextEdit()
    relation_description.setMaximumHeight(120)
    relation_description.setPlaceholderText(tr("描述角色與對方的關係"))
    relation_importance = QSpinBox()
    relation_importance.setRange(1, 10)
    relation_importance.setValue(5)
    relation_form = QFormLayout()
    relation_form.addRow(tr("對方"), relation_other)
    relation_form.addRow(tr("關係標籤"), relation_label)
    relation_form.addRow(tr("關係描述"), relation_description)
    relation_form.addRow(tr("重要度"), relation_importance)
    relation_layout.addWidget(relation_count)
    relation_layout.addWidget(relation_list)
    relation_layout.addLayout(relation_form)
    relation_buttons = QHBoxLayout()
    relation_new = QPushButton(tr("新增／清空"))
    relation_save = _primary("儲存關係")
    relation_delete = QPushButton(tr("刪除選取"))
    relation_import = QPushButton(tr("匯入 relations JSON"))
    for button in (relation_new, relation_save, relation_delete, relation_import):
        relation_buttons.addWidget(button)
    relation_layout.addLayout(relation_buttons)
    tabs.addTab(relation_tab, tr("人物關係"))

    lore_records: dict[int, Any] = {}
    relation_records: dict[int, Any] = {}

    def character_id() -> str:
        return str(character.currentData() or "")

    def clear_lore() -> None:
        lore_list.clearSelection()
        lore_title.clear()
        lore_content.clear()
        lore_tags.clear()
        lore_importance.setValue(5)

    def clear_relation() -> None:
        relation_list.clearSelection()
        relation_other.clear()
        relation_label.clear()
        relation_description.clear()
        relation_importance.setValue(5)

    def refresh() -> None:
        nonlocal lore_records, relation_records
        lore_list.clear()
        relation_list.clear()
        lore_records = {item.id: item for item in panel.chat_database.lore_records(character_id())}
        relation_records = {
            item.id: item
            for item in panel.chat_database.character_relation_records(character_id())
        }
        for item in lore_records.values():
            tags = f" · {', '.join(item.tags)}" if item.tags else ""
            lore_list.addItem(f"★{item.importance} · {item.title}{tags}")
            lore_list.item(lore_list.count() - 1).setData(Qt.ItemDataRole.UserRole, item.id)
        for item in relation_records.values():
            relation_list.addItem(
                f"★{item.importance} · {item.other_character}／{item.relation_label}"
            )
            relation_list.item(relation_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, item.id
            )
        lore_count.setText(trf("共 {count} 筆背景知識", count=len(lore_records)))
        relation_count.setText(trf("共 {count} 筆人物關係", count=len(relation_records)))
        clear_lore()
        clear_relation()

    def selected_id(widget: QListWidget) -> int:
        item = widget.currentItem()
        return int(item.data(Qt.ItemDataRole.UserRole) or 0) if item is not None else 0

    def load_lore() -> None:
        record = lore_records.get(selected_id(lore_list))
        if record is None:
            return
        lore_title.setText(record.title)
        lore_content.setPlainText(record.content)
        lore_tags.setText(", ".join(record.tags))
        lore_importance.setValue(record.importance)

    def load_relation() -> None:
        record = relation_records.get(selected_id(relation_list))
        if record is None:
            return
        relation_other.setText(record.other_character)
        relation_label.setText(record.relation_label)
        relation_description.setPlainText(record.description)
        relation_importance.setValue(record.importance)

    def save_lore() -> None:
        tags = [item.strip() for item in lore_tags.text().replace("，", ",").split(",")
                if item.strip()]
        panel.chat_database.save_lore_record(
            character_id(), lore_title.text(), lore_content.toPlainText(), tags,
            lore_importance.value(), selected_id(lore_list),
        )
        panel.log.append(f"{character.currentText()}：角色知識已儲存。")
        refresh()

    def save_relation() -> None:
        panel.chat_database.save_character_relation_record(
            character_id(), relation_other.text(), relation_label.text(),
            relation_description.toPlainText(), relation_importance.value(),
            selected_id(relation_list),
        )
        panel.log.append(f"{character.currentText()}：人物關係已儲存。")
        refresh()

    def delete_lore() -> None:
        identifier = selected_id(lore_list)
        if identifier and QMessageBox.question(
            panel, tr("刪除角色知識"), tr("確定刪除選取的背景知識？")
        ) == QMessageBox.StandardButton.Yes:
            panel.chat_database.delete_lore_record(character_id(), identifier)
            refresh()

    def delete_relation() -> None:
        identifier = selected_id(relation_list)
        if identifier and QMessageBox.question(
            panel, tr("刪除人物關係"), tr("確定刪除選取的人物關係？")
        ) == QMessageBox.StandardButton.Yes:
            panel.chat_database.delete_character_relation_record(character_id(), identifier)
            refresh()

    def import_records(kind: str) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            panel, tr("選擇 JSON 檔"), "", "JSON (*.json)"
        )
        if not path:
            return
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError("匯入檔必須是 JSON 物件陣列。")
        counts = panel.chat_database.import_lore(
            character_id(), payload if kind == "lore" else [],
            payload if kind == "relations" else [],
        )
        panel.log.append(f"知識匯入完成：背景 {counts[0]} 筆、關係 {counts[1]} 筆。")
        refresh()

    character.currentIndexChanged.connect(lambda _index: refresh())
    lore_list.itemSelectionChanged.connect(load_lore)
    relation_list.itemSelectionChanged.connect(load_relation)
    lore_new.clicked.connect(clear_lore)
    relation_new.clicked.connect(clear_relation)
    lore_save.clicked.connect(lambda: panel.guard(save_lore))
    relation_save.clicked.connect(lambda: panel.guard(save_relation))
    lore_delete.clicked.connect(delete_lore)
    relation_delete.clicked.connect(delete_relation)
    lore_import.clicked.connect(lambda: panel.guard(lambda: import_records("lore")))
    relation_import.clicked.connect(lambda: panel.guard(lambda: import_records("relations")))
    panel.page_refreshers["character_knowledge"] = refresh
    refresh()
    page.layout().addStretch()
