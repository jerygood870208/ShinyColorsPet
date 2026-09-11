"""Build the llm settings settings page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
)

from shiny_pet.oauth_proxy import PROXY_URL

from ._shared import _card, _save_button


def _install_llm(panel: Any) -> None:
    page = panel.add_navigation_page("llm", "llm", "LLM 設定", "LLM 設定", "設定聊天模型與相容 API")
    _, layout = _card(page)
    provider = QComboBox()
    provider.addItem("OpenAI 相容", "openai_compatible")
    provider.addItem("外部 openai-oauth proxy（實驗性）", "openai_oauth_proxy")
    provider.setCurrentIndex(max(0, provider.findData(panel.settings["llm_provider"])))
    url = QLineEdit(str(panel.settings["llm_api_url"]))
    model = QComboBox()
    model.setEditable(True)
    configured_model = str(panel.settings["llm_model"]).strip()
    if configured_model:
        model.addItem(configured_model)
        model.setCurrentText(configured_model)
    model.setPlaceholderText("選擇服務提供的模型，或手動輸入模型 ID")
    key = QLineEdit(str(panel.settings["llm_api_key"]))
    key.setEchoMode(QLineEdit.EchoMode.Password)
    temperature = QSpinBox()
    temperature.setRange(0, 200)
    temperature.setValue(round(float(panel.settings["llm_temperature"]) * 100))
    history_limit = QSpinBox()
    history_limit.setRange(1, 1_000_000)
    history_limit.setValue(int(panel.settings["chat_history_limit"]))
    max_tokens = QSpinBox()
    max_tokens.setRange(16, 1_000_000)
    max_tokens.setValue(int(panel.settings["llm_max_tokens"]))
    timeout = QSpinBox()
    timeout.setRange(5, 600)
    timeout.setSuffix(" 秒")
    timeout.setValue(round(float(panel.settings["llm_timeout_seconds"])))
    form = QFormLayout()
    form.addRow("供應端", provider)
    form.addRow("API URL", url)
    form.addRow("模型", model)
    form.addRow("API Key", key)
    form.addRow("Temperature ×100", temperature)
    form.addRow("送出歷史訊息數", history_limit)
    form.addRow("最大輸出 Token", max_tokens)
    form.addRow("請求逾時", timeout)
    layout.addLayout(form)
    oauth_note = QLabel(
        "openai-oauth 是非官方第三方專案，並非 OpenAI 背書的 ShinyColorsPet 功能。"
        "同意後程式會在您的本機資料目錄下載固定版本的 Node.js 與 openai-oauth、開啟瀏覽器登入，"
        "並只連到 127.0.0.1:10531。憑證由第三方工具保存在 ~/.codex；ShinyColorsPet 不讀取、"
        "傳送或集中保存 token。您必須只使用本人帳號，不得分享憑證或規避任何限制。"
    )
    oauth_note.setWordWrap(True)
    oauth_note.setObjectName("Muted")
    layout.addWidget(oauth_note)
    oauth_consent = QCheckBox("我確認僅使用本人帳號，並接受上述非官方整合免責聲明")
    oauth_consent.setChecked(bool(panel.settings["openai_oauth_personal_use_accepted"]))
    layout.addWidget(oauth_consent)
    oauth_status = QLabel("尚未啟動 openai-oauth 本機服務。")
    oauth_status.setWordWrap(True)
    oauth_status.setObjectName("Muted")
    layout.addWidget(oauth_status)

    def oauth_update(message: str, discovered_models: object) -> None:
        oauth_status.setText(message)
        available = (
            tuple(
                str(item).strip()
                for item in discovered_models
                if isinstance(item, str) and item.strip()
            )
            if isinstance(discovered_models, (list, tuple))
            else ()
        )
        if available:
            url.setText(PROXY_URL)
            current = model.currentText().strip()
            model.blockSignals(True)
            model.clear()
            model.addItems(list(available))
            model.setCurrentText(current if current in available else available[0])
            model.blockSignals(False)
            panel.settings.update(
                llm_provider="openai_oauth_proxy",
                llm_api_url=url.text().strip(),
                llm_model=model.currentText().strip(),
            )
            panel.guard(panel.persist)

    panel.signals.oauth_status.connect(oauth_update)

    def start_oauth() -> None:
        if not oauth_consent.isChecked():
            raise ValueError("請先閱讀並勾選 openai-oauth 本人使用及免責聲明")
        provider.setCurrentIndex(provider.findData("openai_oauth_proxy"))
        url.setText(PROXY_URL)
        panel.settings.update(
            llm_provider="openai_oauth_proxy",
            llm_api_url=url.text().strip(),
            llm_model=model.currentText().strip(),
            openai_oauth_personal_use_accepted=True,
        )
        panel.persist()
        oauth_status.setText("準備受控的本機 runtime…")
        panel.start_openai_oauth()

    oauth_buttons = QHBoxLayout()
    oauth_start = QPushButton("同意並自動安裝／登入")
    oauth_stop = QPushButton("停止本機服務")
    oauth_refresh = QPushButton("重新整理模型")
    oauth_start.clicked.connect(lambda: panel.guard(start_oauth))
    oauth_stop.clicked.connect(panel.stop_openai_oauth)
    oauth_refresh.clicked.connect(panel.refresh_openai_oauth_models)
    oauth_buttons.addWidget(oauth_start)
    oauth_buttons.addWidget(oauth_refresh)
    oauth_buttons.addWidget(oauth_stop)
    layout.addLayout(oauth_buttons)

    def apply_provider(index: int) -> None:
        if provider.itemData(index) == "openai_oauth_proxy":
            if not url.text().strip():
                url.setText(PROXY_URL)
            panel.refresh_openai_oauth_models()

    provider.currentIndexChanged.connect(apply_provider)

    def save() -> None:
        if provider.currentData() == "openai_oauth_proxy" and not oauth_consent.isChecked():
            raise ValueError("使用 openai-oauth 前必須重新確認本人使用及免責聲明")
        panel.settings.update(
            llm_provider=provider.currentData(),
            llm_api_url=url.text().strip(),
            llm_model=model.currentText().strip(),
            llm_api_key=key.text().strip(),
            llm_temperature=temperature.value() / 100,
            chat_history_limit=history_limit.value(),
            llm_max_tokens=max_tokens.value(),
            llm_timeout_seconds=timeout.value(),
            openai_oauth_personal_use_accepted=(
                oauth_consent.isChecked()
                if provider.currentData() == "openai_oauth_proxy"
                else False
            ),
        )
        panel.persist()
        if provider.currentData() == "openai_oauth_proxy":
            panel.start_openai_oauth()

    _save_button(layout, "儲存 LLM 設定", save)
    if provider.currentData() == "openai_oauth_proxy":
        panel.refresh_openai_oauth_models()
    page.layout().addStretch()
