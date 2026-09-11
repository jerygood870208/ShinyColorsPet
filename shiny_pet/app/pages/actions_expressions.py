"""Build the actions expressions navigation page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


def build_actions_expressions_page(panel: Any, settings: dict[str, Any]) -> None:
    actions_page = panel._new_page("動作與表情", "預覽目前模型 manifest 提供的安全語意動作")
    action_card = QFrame()
    action_card.setObjectName("PanelCard")
    action_layout = QVBoxLayout(action_card)
    action_layout.setContentsMargins(28, 28, 28, 28)
    action_layout.setSpacing(16)
    panel.action_character_label = QLabel("尚未選取桌面人物")
    panel.action_character_label.setObjectName("HeroTitle")
    action_layout.addWidget(panel.action_character_label)
    panel.action_hint = QLabel("人物 ready 後，可在此直接確認每個動作與表情。")
    panel.action_hint.setObjectName("Muted")
    action_layout.addWidget(panel.action_hint)
    panel.action_grid_host = QWidget()
    panel.action_grid = QGridLayout(panel.action_grid_host)
    panel.action_grid.setSpacing(10)
    action_layout.addWidget(panel.action_grid_host)
    action_layout.addStretch()
    panel._column(actions_page).addWidget(action_card, 1)
