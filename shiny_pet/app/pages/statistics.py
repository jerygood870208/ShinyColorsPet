"""Build the statistics settings page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
)

from shiny_pet.i18n import tr, trf

from ._shared import _card, _character_combo


def _install_statistics(panel: Any) -> None:
    page = panel.add_navigation_page(
        "statistics", "statistics", "數據統計", "數據統計", "查看各偶像的對話、記憶與關係概況"
    )
    _, layout = _card(page)
    character = _character_combo(panel)
    period = QComboBox()
    period.addItem("今天", 1)
    period.addItem("最近 7 天", 7)
    period.addItem("最近 30 天", 30)
    period.addItem("全部時間", 0)
    summary = QLabel()
    summary.setObjectName("HeroTitle")
    summary.setWordWrap(True)
    layout.addWidget(character)
    layout.addWidget(period)
    layout.addWidget(summary)

    def refresh() -> None:
        key = str(character.currentData() or "")
        relation = panel.chat_database.relationship(key, panel.relationship_user_key())
        stats = panel.chat_database.statistics(
            key, relation.user_key, int(period.currentData() or 0)
        )
        total = int(stats["messages"])
        ratio = round(int(stats["user_messages"]) * 100 / total) if total else 0
        summary.setText(trf(
            "好感度　{affection} / 100\n目前心情　{mood}\n"
            "訊息總數　{messages} 則\n活躍天數　{days} 天\n"
            "使用者訊息比例　{ratio}%\n長期記憶　{memories} 則\n"
            "最近互動　{latest}",
            affection=relation.affection,
            mood=relation.mood,
            messages=total,
            days=stats["active_days"],
            ratio=ratio,
            memories=stats["memories"],
            latest=stats["latest"] or tr("尚無"),
        ))

    character.currentIndexChanged.connect(lambda _index: refresh())
    period.currentIndexChanged.connect(lambda _index: refresh())
    refresh()
    page.layout().addStretch()
