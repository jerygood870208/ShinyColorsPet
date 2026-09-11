"""Build the outfit management navigation page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
)


def build_outfit_management_page(panel: Any, settings: dict[str, Any]) -> None:
    outfit_page = panel._new_page("服裝管理", "為目前選取的桌面人物更換服裝")
    outfit_card = QFrame()
    outfit_card.setObjectName("PanelCard")
    outfit_form = QFormLayout(outfit_card)
    outfit_form.setContentsMargins(28, 28, 28, 28)
    panel.outfit_character_label = QLabel("尚未選取桌面人物")
    panel.outfit_character_label.setObjectName("HeroTitle")
    outfit_form.addRow(panel.outfit_character_label)
    panel.outfit_selector = QComboBox()
    panel.costume_selector = QComboBox()
    outfit_form.addRow("衣服名稱", panel.outfit_selector)
    outfit_form.addRow("普通／演出服", panel.costume_selector)
    panel.default_outfit_status = QLabel("目前使用資產內建預設")
    panel.default_outfit_status.setObjectName("Muted")
    panel.default_outfit_status.setWordWrap(True)
    outfit_form.addRow("載入預設", panel.default_outfit_status)
    change_outfit = QPushButton("套用到選取人物")
    change_outfit.setObjectName("PrimaryButton")
    change_outfit.clicked.connect(lambda: panel.guard(panel.change_selected_outfit))
    outfit_form.addRow(change_outfit)
    default_buttons = QHBoxLayout()
    panel.set_default_outfit_button = QPushButton("設為此角色的預設衣服")
    panel.set_default_outfit_button.setObjectName("SecondaryButton")
    panel.set_default_outfit_button.clicked.connect(
        lambda: panel.guard(panel.set_selected_outfit_as_default)
    )
    panel.reset_default_outfit_button = QPushButton("恢復資產內建預設")
    panel.reset_default_outfit_button.setObjectName("GhostButton")
    panel.reset_default_outfit_button.clicked.connect(
        lambda: panel.guard(panel.reset_selected_default_outfit)
    )
    default_buttons.addWidget(panel.set_default_outfit_button)
    default_buttons.addWidget(panel.reset_default_outfit_button)
    default_buttons.addStretch()
    outfit_form.addRow(default_buttons)
    panel._column(outfit_page).addWidget(outfit_card)
    panel._column(outfit_page).addStretch()
