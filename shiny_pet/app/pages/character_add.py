"""Build the character add navigation page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QWidget,
)


def build_character_add_page(panel: Any, settings: dict[str, Any]) -> None:
    add_page = panel._new_page("新增人物", "選擇團體，再選擇人物與顯示類型")
    panel.add_flow = QStackedWidget()
    panel.add_flow.setObjectName("InnerStack")
    panel.unit_view = panel._flow_view("選擇團體", "先選擇人物所屬的團體")
    panel.unit_grid_host = QWidget()
    panel.unit_grid = QGridLayout(panel.unit_grid_host)
    panel.unit_grid.setSpacing(16)
    panel.unit_grid.setContentsMargins(0, 8, 0, 8)
    panel._column(panel.unit_view).addWidget(panel.unit_grid_host)
    panel._column(panel.unit_view).addStretch()
    panel.add_flow.addWidget(panel.unit_view)
    panel.character_view = panel._flow_view("選擇人物", "選擇後即可載入預設穿著")
    back = QPushButton("← 返回團體")
    back.setObjectName("GhostButton")
    back.clicked.connect(lambda: panel.add_flow.setCurrentWidget(panel.unit_view))
    panel._column(panel.character_view).insertWidget(0, back, 0, Qt.AlignmentFlag.AlignLeft)
    panel.character_grid_host = QWidget()
    panel.character_grid = QGridLayout(panel.character_grid_host)
    panel.character_grid.setSpacing(16)
    panel._column(panel.character_view).addWidget(panel.character_grid_host)
    selection_bar = QFrame()
    selection_bar.setObjectName("SelectionBar")
    selection_layout = QHBoxLayout(selection_bar)
    panel.selected_character_label = QLabel("請選擇人物")
    panel.selected_character_label.setObjectName("SectionTitle")
    selection_layout.addWidget(panel.selected_character_label, 1)
    panel.unit_selector = QComboBox()
    panel.character_selector = QComboBox()
    panel.unit_selector.hide()
    panel.character_selector.hide()
    panel.unit_selector.setIconSize(QSize(48, 48))
    panel.character_selector.setIconSize(QSize(64, 64))
    panel.presentation_selector = QComboBox()
    panel.presentation_selector.addItem("一般", "standard")
    panel.presentation_selector.addItem("Q版", "chibi")
    selection_layout.addWidget(QLabel("顯示類型"))
    selection_layout.addWidget(panel.presentation_selector)
    add_character = QPushButton("載入預設穿著")
    add_character.setObjectName("PrimaryButton")
    add_character.clicked.connect(lambda: panel.guard(panel.add_catalog_character))
    selection_layout.addWidget(add_character)
    panel._column(panel.character_view).addWidget(selection_bar)
    panel.add_flow.addWidget(panel.character_view)
    panel._column(add_page).addWidget(panel.add_flow, 1)
