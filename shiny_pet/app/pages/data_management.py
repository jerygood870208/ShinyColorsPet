"""Build the data management settings page."""

# ruff: noqa: E501

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
)

from shiny_pet.i18n import tr, tr_dynamic, trf

from ._shared import _card, _heading, _save_button


def _install_data_management(panel: Any) -> None:
    page = panel.add_navigation_page(
        "data_management", "data", "資料管理", "資料管理", "備份設定、聊天記錄、關係與記憶資料"
    )
    _, layout = _card(page)
    _heading(layout, "本機資料位置")
    locations = QTextBrowser()
    locations.setMaximumHeight(130)
    locations.setPlainText(
        f"設定：{panel.store.path}\n"
        f"聊天與記憶：{panel.chat_database.path}\n"
        f"語音快取：{panel.store.path.parent / 'voice-cache'}"
    )
    panel.data_locations = locations
    layout.addWidget(locations)
    backup_status = QLabel("尚未建立備份")
    backup_status.setObjectName("Muted")
    layout.addWidget(backup_status)
    shortcuts = QHBoxLayout()
    assets = QPushButton("模型與資產管理")
    activity = QPushButton("開啟活動記錄")
    assets.clicked.connect(lambda: panel.show_page("assets"))
    activity.clicked.connect(lambda: panel.show_page("activity"))
    shortcuts.addWidget(assets)
    shortcuts.addWidget(activity)
    layout.addLayout(shortcuts)

    _heading(
        layout,
        "生成語音快取",
        "選擇是否自動清理儲存在 AppData 的生成語音。容量模式會優先移除最舊檔案。",
    )
    voice_cache_mode = QComboBox()
    voice_cache_mode.addItem("不自動清理", "never")
    voice_cache_mode.addItem("超過容量時自動清理", "size_limit")
    voice_cache_mode.addItem("退出程式時全部清理", "on_exit")
    configured_mode = str(panel.settings.get("voice_cache_cleanup_mode", "on_exit"))
    selected_mode = voice_cache_mode.findData(configured_mode)
    voice_cache_mode.setCurrentIndex(max(0, selected_mode))
    voice_cache_limit = QDoubleSpinBox()
    voice_cache_limit.setRange(0.1, 1000.0)
    voice_cache_limit.setDecimals(1)
    voice_cache_limit.setSingleStep(0.5)
    voice_cache_limit.setSuffix(" GB")
    voice_cache_limit.setValue(float(panel.settings.get("voice_cache_max_gb", 2.0)))
    voice_cache_form = QFormLayout()
    voice_cache_form.addRow("自動清理方式", voice_cache_mode)
    voice_cache_form.addRow("容量上限", voice_cache_limit)
    layout.addLayout(voice_cache_form)

    def update_voice_cache_controls() -> None:
        voice_cache_limit.setEnabled(voice_cache_mode.currentData() == "size_limit")

    def save_voice_cache_policy() -> bool:
        panel.settings["voice_cache_cleanup_mode"] = str(voice_cache_mode.currentData())
        panel.settings["voice_cache_max_gb"] = voice_cache_limit.value()
        apply_policy = getattr(panel, "apply_voice_cache_policy", None)
        if callable(apply_policy):
            apply_policy()
        panel.persist()
        return True

    voice_cache_mode.currentIndexChanged.connect(
        lambda _index: update_voice_cache_controls()
    )
    update_voice_cache_controls()
    _save_button(
        layout,
        "儲存語音快取設定",
        save_voice_cache_policy,
        success_text="語音快取設定已儲存",
    )

    def backup() -> bool:
        destination = QFileDialog.getExistingDirectory(panel, tr("選擇備份資料夾"))
        if not destination:
            return False
        target = Path(destination) / (
            "ShinyColorsPet-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        )
        target.mkdir(parents=True)
        panel.persist()
        shutil.copy2(panel.store.path, target / "settings.json")
        if panel.chat_database.path.is_file():
            shutil.copy2(panel.chat_database.path, target / "chat.sqlite3")
        (target / "backup.json").write_text(
            json.dumps(
                {
                    "format": 1,
                    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "files": ["settings.json", "chat.sqlite3"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        backup_status.setText(trf("備份完成：{path}", path=target))
        return True

    _save_button(
        layout,
        "建立資料備份…",
        lambda: panel.guard(backup),
        success_text="資料備份已建立",
    )
    restore_row = QHBoxLayout()
    restore_settings = QCheckBox("一般設定與提醒")
    restore_chat = QCheckBox("聊天、關係與記憶")
    restore_settings.setChecked(True)
    restore_chat.setChecked(True)
    restore_row.addWidget(restore_settings)
    restore_row.addWidget(restore_chat)
    layout.addLayout(restore_row)

    def restore() -> bool:
        source_value = QFileDialog.getExistingDirectory(
            panel, tr("選擇 ShinyColorsPet 備份資料夾")
        )
        if not source_value:
            return False
        source = Path(source_value)
        if not (source / "backup.json").is_file():
            raise ValueError("選取的資料夾不是有效的 ShinyColorsPet 備份")
        safety = panel.store.path.parent / (
            "pre-restore-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        )
        safety.mkdir(parents=True)
        panel.persist()
        shutil.copy2(panel.store.path, safety / "settings.json")
        if panel.chat_database.path.is_file():
            shutil.copy2(panel.chat_database.path, safety / "chat.sqlite3")
        if restore_settings.isChecked() and (source / "settings.json").is_file():
            shutil.copy2(source / "settings.json", panel.store.path)
            panel.settings.clear()
            panel.settings.update(panel.store.load())
        if restore_chat.isChecked() and (source / "chat.sqlite3").is_file():
            shutil.copy2(source / "chat.sqlite3", panel.chat_database.path)
        backup_status.setText(tr_dynamic(
            f"還原完成；重新啟動後完全套用。還原前備份：{safety}"
        ))
        return True

    _save_button(
        layout,
        "從備份還原…",
        lambda: panel.guard(restore),
        success_text="資料已還原，重新啟動後完全套用",
    )
    reset_kind = QComboBox()
    reset_kind.addItem("只清除聊天記錄", "messages")
    reset_kind.addItem("只清除關係與長期記憶", "memory")
    reset_kind.addItem("清除聊天、關係與記憶", "all")
    layout.addWidget(reset_kind)

    def reset_selected() -> bool:
        label = reset_kind.currentText()
        if (
            QMessageBox.warning(
                panel,
                tr("重設指定資料"),
                tr_dynamic(f"確定要{label}？此操作無法復原。"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return False
        deleted = panel.chat_database.clear(str(reset_kind.currentData()))
        backup_status.setText(tr_dynamic(f"已重設指定資料，共移除 {deleted} 筆記錄。"))
        return True

    _save_button(
        layout,
        "重設指定資料…",
        reset_selected,
        success_text="指定資料已重設",
    )
    page.layout().addStretch()
