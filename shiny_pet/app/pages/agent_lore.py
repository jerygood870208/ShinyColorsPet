"""Per-character proactive interaction preferences."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QTimeEdit,
)

from shiny_pet.i18n import tr

from ._shared import _card, _character_combo, _heading, _save_button


def _install_agent_lore(panel: Any) -> None:
    page = panel.add_navigation_page(
        "agent_lore", "proactive", "主動互動", "主動互動",
        "設定每位角色的主動搭話頻率與靜默時段",
    )
    _, layout = _card(page)
    _heading(layout, "主動互動", "新角色預設關閉。排程訊息不會播放語音或增加好感度。")
    character = _character_combo(panel)
    enabled = QCheckBox(tr("允許此角色主動搭話"))
    from PySide6.QtWidgets import QComboBox
    tier = QComboBox()
    tier.addItem(tr("安靜（72 小時／每日 1 則）"), "quiet")
    tier.addItem(tr("一般（24 小時／每日 3 則）"), "normal")
    tier.addItem(tr("黏人（8 小時／每日 6 則）"), "clingy")
    quiet_start = QTimeEdit(QTime(23, 0))
    quiet_start.setDisplayFormat("HH:mm")
    quiet_end = QTimeEdit(QTime(8, 0))
    quiet_end.setDisplayFormat("HH:mm")
    timezone_hint = QLabel(tr("時區：跟隨電腦目前設定"))
    timezone_hint.setObjectName("Muted")
    form = QFormLayout()
    form.addRow(tr("角色"), character)
    form.addRow("", enabled)
    form.addRow(tr("主動程度"), tier)
    form.addRow(tr("靜默開始"), quiet_start)
    form.addRow(tr("靜默結束"), quiet_end)
    form.addRow("", timezone_hint)
    layout.addLayout(form)

    def refresh() -> None:
        key = str(character.currentData() or "")
        if not key:
            enabled.setEnabled(False)
            tier.setEnabled(False)
            return
        enabled.setEnabled(True)
        tier.setEnabled(True)
        state = panel.chat_database.ensure_schedule_state(key)
        enabled.setChecked(state.proactive_enabled)
        tier.setCurrentIndex(max(0, tier.findData(state.proactive_tier)))
        quiet_start.setTime(QTime.fromString(state.quiet_hours_start, "HH:mm"))
        quiet_end.setTime(QTime.fromString(state.quiet_hours_end, "HH:mm"))

    def save() -> None:
        panel.chat_database.update_schedule_preferences(
            str(character.currentData() or ""), enabled=enabled.isChecked(),
            tier=str(tier.currentData() or "normal"),
            quiet_start=quiet_start.time().toString("HH:mm"),
            quiet_end=quiet_end.time().toString("HH:mm"),
        )

    _save_button(layout, "儲存主動互動設定", save)
    character.currentIndexChanged.connect(lambda _index: refresh())
    panel.page_refreshers["agent_lore"] = refresh
    refresh()
    page.layout().addStretch()
