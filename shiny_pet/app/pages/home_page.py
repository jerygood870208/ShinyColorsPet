"""Build the home page navigation page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)


def build_home_page(panel: Any, settings: dict[str, Any]) -> None:
    home = panel._new_page("桌面人物", "管理目前正在桌面上活動的角色")
    hero = QFrame()
    hero.setObjectName("HeroCard")
    hero_layout = QHBoxLayout(hero)
    hero_layout.setContentsMargins(28, 24, 28, 24)
    hero_text = QVBoxLayout()
    hero_title = QLabel("讓 283 PRO 的日常陪在桌面上")
    hero_title.setObjectName("HeroTitle")
    hero_body = QLabel("每位人物使用獨立程序運行，可依需要同時載入多位桌面人物。")
    hero_body.setObjectName("Muted")
    hero_text.addWidget(hero_title)
    hero_text.addWidget(hero_body)
    hero_layout.addLayout(hero_text, 1)
    add_from_home = QPushButton("＋ 新增人物")
    add_from_home.setObjectName("PrimaryButton")
    add_from_home.clicked.connect(lambda: panel.show_page("add"))
    hero_layout.addWidget(add_from_home)
    panel._column(home).addWidget(hero)
    running_header = QHBoxLayout()
    running_title = QLabel("目前人物")
    running_title.setObjectName("SectionTitle")
    panel.running_count = QLabel("0 位")
    panel.running_count.setObjectName("Pill")
    running_header.addWidget(running_title)
    running_header.addWidget(panel.running_count)
    running_header.addStretch()
    panel._column(home).addLayout(running_header)
    panel.pets = QListWidget()
    panel.pets.setObjectName("PetList")
    panel.pets.setMinimumHeight(260)
    panel._column(home).addWidget(panel.pets, 1)
    buttons = QHBoxLayout()
    for label, name, callback in (
        ("顯示", "SecondaryButton", lambda: panel.command("show")),
        ("隱藏", "SecondaryButton", lambda: panel.command("hide")),
        ("重新啟動", "SecondaryButton", panel.restart_selected),
        ("關閉人物", "DangerButton", panel.stop_selected),
    ):
        button = QPushButton(label)
        button.setObjectName(name)
        button.clicked.connect(callback)
        buttons.addWidget(button)
    buttons.addStretch()
    panel._column(home).addLayout(buttons)
