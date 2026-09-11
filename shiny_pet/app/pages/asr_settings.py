"""Build the asr settings settings page."""

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
)

from shiny_pet.i18n import tr, tr_dynamic, trf
from shiny_pet.voice import LOCAL_ASR_MODEL, input_devices

from ._shared import _card, _save_button


def _install_asr(panel: Any) -> None:
    page = panel.add_navigation_page(
        "asr",
        "voice",
        "語音辨識",
        "語音辨識（ASR）",
        "使用內建 whisper-large-v3，或連接 OpenAI 相容的語音辨識服務",
    )
    _, layout = _card(page)
    enabled = QCheckBox("啟用語音辨識")
    enabled.setChecked(bool(panel.settings["asr_enabled"]))
    provider = QComboBox()
    provider.addItem("內建 Whisper（whisper-large-v3）", "local_whisper")
    provider.addItem("外部 OpenAI 相容服務", "openai_compatible")
    provider.setCurrentIndex(max(0, provider.findData(panel.settings["asr_provider"])))
    compute_device = QComboBox()
    compute_device.addItem("自動（相容 GPU 時優先使用）", "auto")
    compute_device.addItem("CPU 相容模式（int8）", "cpu")
    compute_device.setCurrentIndex(
        max(0, compute_device.findData(panel.settings.get("asr_compute_device", "auto")))
    )
    url = QLineEdit(str(panel.settings["asr_api_url"]))
    model = QLineEdit(str(panel.settings["asr_model"]))
    key = QLineEdit(str(panel.settings["asr_api_key"]))
    key.setEchoMode(QLineEdit.EchoMode.Password)
    language = QLineEdit(str(panel.settings.get("asr_language", "")))
    language.setPlaceholderText("留空自動偵測，例如 ja 或 zh")
    device = QComboBox()
    configured_device = int(panel.settings.get("asr_input_device", -1))
    device_status = QLabel()
    device_status.setObjectName("Muted")
    install_status = QLabel()
    install_status.setObjectName("Muted")
    install_status.setWordWrap(True)
    install_button = QPushButton("一鍵安裝內建 whisper-large-v3")
    install_button.setObjectName("PrimaryButton")

    def refresh_devices(preferred: int | None = None) -> None:
        target = configured_device if preferred is None else preferred
        available = input_devices()
        device.clear()
        device.addItem("系統預設麥克風", -1)
        for index, label in available:
            device.addItem(label, index)
        selected_device = device.findData(target)
        if selected_device < 0 and target >= 0:
            device.addItem(trf("裝置 {device}（目前無法使用）", device=target), target)
            selected_device = device.count() - 1
        device.setCurrentIndex(max(0, selected_device))
        device_status.setText(
            trf("偵測到 {count} 個可錄音裝置。", count=len(available))
            if available
            else tr("未偵測到可列出的麥克風；可先使用系統預設裝置。")
        )

    refresh_devices()
    form = QFormLayout()
    form.addRow("", enabled)
    form.addRow("辨識方式", provider)
    form.addRow("運算裝置", compute_device)
    form.addRow("API URL", url)
    form.addRow("模型", model)
    form.addRow("API Key", key)
    form.addRow("語言", language)
    form.addRow("麥克風", device)
    layout.addLayout(form)
    refresh_device = QPushButton("重新偵測麥克風")
    refresh_device.clicked.connect(lambda: refresh_devices(int(device.currentData())))
    device_buttons = QHBoxLayout()
    device_buttons.addWidget(refresh_device)
    test_device = QPushButton("測試選取的麥克風（2 秒）")
    device_buttons.addWidget(test_device)
    layout.addLayout(device_buttons)
    layout.addWidget(device_status)
    layout.addWidget(install_button)
    layout.addWidget(install_status)

    def update_provider() -> None:
        local = provider.currentData() == "local_whisper"
        for widget in (url, model, key):
            widget.setEnabled(not local)
        compute_device.setEnabled(local)
        install_button.setVisible(local)
        if local:
            url.setText(panel.local_asr_server.api_url)
            model.setText(LOCAL_ASR_MODEL)
            install_status.setText(tr(
                "內建 Whisper 已安裝；模型會在背景載入。"
                if panel.local_asr_server.installed
                else "尚未安裝。需要網路與 Python 3.10 以上版本；模型約需 3 GB 空間。"
            ))

    def install() -> None:
        install_button.setEnabled(False)
        install_status.setText(tr("正在開始安裝…"))
        panel.install_local_asr()

    def installed(api_url: str) -> None:
        install_button.setEnabled(True)
        enabled.setChecked(True)
        url.setText(api_url)
        model.setText(LOCAL_ASR_MODEL)
        install_status.setText(tr("安裝完成。whisper-large-v3 正在背景下載或載入，首次辨識會較久。"))
        panel.settings.update(
            asr_enabled=True,
            asr_provider="local_whisper",
            asr_api_url=api_url,
            asr_model=LOCAL_ASR_MODEL,
        )
        panel.persist()

    def install_error(message: str) -> None:
        install_button.setEnabled(True)
        install_status.setText(tr_dynamic("安裝失敗：" + message))

    def test_microphone() -> None:
        test_device.setEnabled(False)
        device_status.setText(tr("正在測試麥克風，請說話…"))
        panel.test_microphone(int(device.currentData()))

    def microphone_tested(result: Any) -> None:
        test_device.setEnabled(True)
        percent = int(result.level_percent)
        if result.peak < 0.003:
            device_status.setText(tr("麥克風可開啟，但幾乎沒有收到聲音；請檢查音量或隱私權限。"))
        else:
            device_status.setText(tr_dynamic(
                f"麥克風測試成功：輸入音量約 {percent}%（峰值 {result.peak:.2f}）。"
            ))

    def microphone_test_error(message: str) -> None:
        test_device.setEnabled(True)
        device_status.setText(tr_dynamic("麥克風測試失敗：" + message))

    provider.currentIndexChanged.connect(update_provider)
    install_button.clicked.connect(install)
    panel.signals.asr_install_progress.connect(lambda text: install_status.setText(tr_dynamic(text)))
    panel.signals.asr_installed.connect(installed)
    panel.signals.asr_install_error.connect(install_error)
    test_device.clicked.connect(test_microphone)
    panel.signals.microphone_tested.connect(microphone_tested)
    panel.signals.microphone_test_error.connect(microphone_test_error)
    panel.signals.asr_cpu_fallback.connect(
        lambda: compute_device.setCurrentIndex(max(0, compute_device.findData("cpu")))
    )
    update_provider()

    def save() -> None:
        selected_provider = str(provider.currentData())
        panel.settings.update(
            asr_enabled=enabled.isChecked(),
            asr_provider=selected_provider,
            asr_compute_device=str(compute_device.currentData()),
            asr_api_url=(
                panel.local_asr_server.api_url
                if selected_provider == "local_whisper"
                else url.text().strip()
            ),
            asr_model=model.text().strip(),
            asr_api_key=key.text().strip(),
            asr_language=language.text().strip(),
            asr_input_device=int(device.currentData()),
        )
        panel.persist()

    _save_button(layout, "儲存語音辨識設定", save)
    page.layout().addStretch()
