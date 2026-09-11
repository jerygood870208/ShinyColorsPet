"""Build the persona settings settings page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
)

from shiny_pet.ai.persona import active_persona, clear_persona_override, soul_prompt
from shiny_pet.i18n import tr

from ._shared import _card, _character_combo, _save_button


def _install_persona(panel: Any) -> None:
    page = panel.add_navigation_page(
        "persona", "persona", "角色人格", "角色人格", "檢視或覆寫各偶像的角色扮演提示"
    )
    _, layout = _card(page)
    character = _character_combo(panel)
    prompt = QTextEdit()
    prompt.setMinimumHeight(390)
    source_status = QLabel()
    source_status.setObjectName("Muted")
    layout.addWidget(character)
    layout.addWidget(source_status)
    layout.addWidget(prompt, 1)
    restore_builtin = QPushButton(tr("恢復 souls 內建人格"))
    restore_builtin.setObjectName("SecondaryButton")
    layout.addWidget(restore_builtin)

    def refresh() -> None:
        key = str(character.currentData() or "")
        overridden = bool(active_persona(panel.settings, key))
        source_status.setText(tr(
            "目前使用本機自訂人格" if overridden else "目前使用 souls 內建人格"
        ))
        restore_builtin.setEnabled(overridden)
        prompt.setPlainText(soul_prompt(panel.settings, key))

    def save() -> None:
        key = str(character.currentData() or "")
        identifier = "ui-custom"
        presets = panel.settings.setdefault("character_persona_presets", {})
        presets[key] = [
            {"id": identifier, "title": "自訂人格", "prompt": prompt.toPlainText().strip()}
        ]
        panel.settings.setdefault("character_persona_active", {})[key] = identifier
        panel.persist()
        refresh()

    def restore() -> None:
        key = str(character.currentData() or "")
        if not active_persona(panel.settings, key):
            refresh()
            return
        if (
            QMessageBox.question(
                panel,
                tr("恢復 souls 內建人格"),
                tr("確定要刪除此角色的本機自訂人格，並恢復 souls 內建內容嗎？"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        clear_persona_override(panel.settings, key)
        panel.persist()
        refresh()
        panel.log.append(tr("已恢復此角色的 souls 內建人格。"))

    character.currentIndexChanged.connect(lambda _index: refresh())
    restore_builtin.clicked.connect(restore)
    _save_button(layout, "儲存並啟用人格", save)
    refresh()
