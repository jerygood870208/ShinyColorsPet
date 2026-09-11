"""Build the activity log navigation page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QTextEdit,
)


def build_activity_log_page(panel: Any, settings: dict[str, Any]) -> None:
    activity_page = panel._new_page("活動記錄", "模型載入、資產掃描與程序狀態")
    panel.log = QTextEdit()
    panel.log.setObjectName("ActivityLog")
    panel.log.setReadOnly(True)
    panel.log.document().setMaximumBlockCount(200)
    panel._column(activity_page).addWidget(panel.log, 1)
