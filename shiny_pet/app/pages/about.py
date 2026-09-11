"""Build the about navigation page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from shiny_pet.i18n import SUPPORTED_LANGUAGES, tr

from ._shared import _save_button


def build_about_page(panel: Any, settings: dict[str, Any]) -> None:
    about_page = panel._new_page("關於", "ShinyColorsPet desktop companion")
    about_card = QFrame()
    about_card.setObjectName("AboutCard")
    about_layout = QVBoxLayout(about_card)
    about_logo = QLabel()
    about_logo.setPixmap(panel.app_icon.pixmap(128, 128))
    about_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    about_title = QLabel("ShinyColorsPet")
    about_title.setObjectName("AboutTitle")
    about_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    about_body = QLabel("以青空般的陪伴，讓偶像在你的桌面展開日常。\nSpine 3.6 desktop companion")
    about_body.setObjectName("Muted")
    about_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
    language_row = QHBoxLayout()
    language_label = QLabel(tr("語言"))
    language = QComboBox()
    for code, label in SUPPORTED_LANGUAGES:
        language.addItem(label, code)
    language.setCurrentIndex(max(0, language.findData(str(settings.get("ui_language", "zh-TW")))))
    language_row.addWidget(language_label)
    language_row.addWidget(language, 1)
    language_hint = QLabel(tr("重新啟動後生效"))
    language_hint.setObjectName("Muted")
    about_layout.addStretch()
    about_layout.addWidget(about_logo)
    about_layout.addWidget(about_title)
    about_layout.addWidget(about_body)
    about_layout.addLayout(language_row)
    about_layout.addWidget(language_hint, 0, Qt.AlignmentFlag.AlignCenter)
    _save_button(
        about_layout,
        tr("儲存設定"),
        lambda: panel._save_language(str(language.currentData())),
        success_text="已儲存，重新啟動後生效",
    )
    quit_button = QPushButton("結束所有寵物並退出")
    quit_button.setObjectName("DangerButton")
    quit_button.clicked.connect(panel.quit)
    about_layout.addWidget(quit_button, 0, Qt.AlignmentFlag.AlignCenter)
    about_layout.addStretch()
    panel._column(about_page).addWidget(about_card, 1)
