"""Build the tts settings settings page."""

# ruff: noqa: E501

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from shiny_pet.i18n import tr, tr_dynamic, trf
from shiny_pet.voice import LOCAL_IRODORI_MODEL
from shiny_pet.voice.reference_audio import (
    MAX_REFERENCE_SECONDS,
    ReferenceAudioImporter,
    custom_reference_path,
    default_reference_path,
)

from ._shared import _card, _character_combo, _save_button


def _install_tts(panel: Any) -> None:
    page = panel.add_navigation_page(
        "tts", "tts", "TTS 設定", "TTS 設定", "設定日文朗讀與角色參考聲音"
    )
    _, layout = _card(page)
    enabled = QCheckBox("啟用角色語音朗讀")
    enabled.setChecked(bool(panel.settings["tts_enabled"]))
    provider = QComboBox()
    provider.addItem(tr("內建 Irodori-TTS v4.1"), "irodori_local")
    provider.addItem(tr("外部 OpenAI 相容"), "openai_compatible")
    provider.setCurrentIndex(max(0, provider.findData(panel.settings["tts_provider"])))
    url = QLineEdit(str(panel.settings["tts_api_url"]))
    root = QLineEdit(str(panel.settings["tts_reference_root"]))
    model = QLineEdit(str(panel.settings.get("tts_model", "tts-1")))
    voice = QLineEdit(str(panel.settings.get("tts_voice", "")))
    key = QLineEdit(str(panel.settings.get("tts_api_key", "")))
    key.setEchoMode(QLineEdit.EchoMode.Password)
    language = QLineEdit(str(panel.settings.get("tts_language", "Japanese")))
    form = QFormLayout()
    form.addRow("", enabled)
    form.addRow("供應端", provider)
    form.addRow("API URL", url)
    form.addRow("遠端模型", model)
    form.addRow("遠端 Voice", voice)
    form.addRow("API Key", key)
    form.addRow("語言", language)
    form.addRow("參考聲音目錄", root)
    layout.addLayout(form)
    install_status = QLabel()
    install_status.setObjectName("Muted")
    install_status.setWordWrap(True)
    install_button = QPushButton(tr("一鍵安裝內建 Irodori-TTS v4.1"))
    install_button.setObjectName("PrimaryButton")
    layout.addWidget(install_button)
    layout.addWidget(install_status)

    _, reference_layout = _card(page)
    reference_layout.addWidget(QLabel(tr("自訂角色參考音檔")))
    character = _character_combo(panel)
    character.setObjectName("TTSReferenceCharacter")
    reference_layout.addWidget(character)
    hint = QLabel(trf(
        "每個角色只能保留一個自訂參考音檔，長度上限 {seconds} 秒。"
        "匯入新檔會取代該角色的舊自訂檔；可一鍵恢復預設。"
        "支援 WAV、FLAC、OGG、M4A、MP3，請使用單人清晰說話的錄音。"
        "此功能適用於內建 Irodori-TTS。",
        seconds=MAX_REFERENCE_SECONDS,
    ))
    hint.setWordWrap(True)
    hint.setObjectName("Muted")
    reference_layout.addWidget(hint)
    reference_status = QLabel()
    reference_status.setObjectName("TTSReferenceStatus")
    reference_status.setWordWrap(True)
    reference_layout.addWidget(reference_status)
    import_button = QPushButton(tr("匯入參考音檔"))
    import_button.setObjectName("TTSReferenceImport")
    restore_button = QPushButton(tr("恢復預設參考音檔"))
    restore_button.setObjectName("TTSReferenceRestore")
    reference_layout.addWidget(import_button)
    reference_layout.addWidget(restore_button)
    importer = ReferenceAudioImporter(page)
    app = QCoreApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(importer.cancel)
    importing = False

    def refresh_reference() -> None:
        key = str(character.currentData() or "")
        try:
            custom = custom_reference_path(panel.local_irodori_server.reference_override_root, key)
        except ValueError:
            custom = None
        default = default_reference_path(
            Path(str(panel.settings.get("tts_reference_root", "audio_reference"))), key,
        )
        overridden = custom is not None and custom.is_file()
        if overridden:
            reference_status.setText(tr("目前使用自訂參考音檔"))
        elif default is not None:
            reference_status.setText(trf("目前使用預設參考音檔：{filename}", filename=default.name))
        else:
            reference_status.setText(tr("此角色目前沒有預設參考音檔。"))
        local = provider.currentData() == "irodori_local"
        character.setEnabled(not importing)
        import_button.setEnabled(local and custom is not None and not importing)
        restore_button.setEnabled(local and overridden and not importing)

    def import_reference() -> None:
        nonlocal importing
        filename, _filter = QFileDialog.getOpenFileName(
            page, tr("選擇參考音檔"), "", "Audio (*.wav *.flac *.ogg *.m4a *.mp3)",
        )
        if not filename:
            return
        destination = custom_reference_path(
            panel.local_irodori_server.reference_override_root, str(character.currentData()),
        )
        importing = True
        refresh_reference()
        reference_status.setText(tr("正在檢查並匯入音檔…"))
        importer.start(Path(filename), destination)

    def imported(_path: str, duration: float) -> None:
        nonlocal importing
        importing = False
        refresh_reference()
        reference_status.setText(trf(
            "已匯入自訂參考音檔（{seconds:.1f} 秒），下次朗讀時生效。",
            seconds=duration,
        ))

    def import_failed(message: str) -> None:
        nonlocal importing
        importing = False
        refresh_reference()
        reference_status.setText(tr("匯入失敗，原有參考音檔未變更：") + message)

    def restore_reference() -> None:
        try:
            custom_reference_path(
                panel.local_irodori_server.reference_override_root, str(character.currentData()),
            ).unlink(missing_ok=True)
        except OSError as exc:
            reference_status.setText(tr("恢復預設失敗：") + str(exc))
            return
        refresh_reference()

    character.currentIndexChanged.connect(refresh_reference)
    import_button.clicked.connect(import_reference)
    restore_button.clicked.connect(restore_reference)
    importer.imported.connect(imported)
    importer.failed.connect(import_failed)

    def update_provider() -> None:
        selected = str(provider.currentData())
        local_irodori = selected == "irodori_local"
        install_button.setVisible(local_irodori)
        for widget in (url, model, voice, key):
            widget.setEnabled(not local_irodori)
        if local_irodori:
            url.setText(panel.local_irodori_server.api_url)
            model.setText(LOCAL_IRODORI_MODEL)
            voice.setText("")
            install_status.setText(tr(
                "內建 Irodori-TTS 已安裝；使用時會自動啟動並載入模型。"
                if panel.local_irodori_server.installed
                else "尚未安裝。需要網路、Python 3.10 以上、Git、NVIDIA GPU，"
                     "並預留約 9 GB 空間。"
            ))
        else:
            install_status.setText("")
        refresh_reference()

    def install() -> None:
        install_button.setEnabled(False)
        install_status.setText(tr("正在開始安裝…"))
        panel.settings["tts_reference_root"] = root.text().strip() or "audio_reference"
        panel.install_local_irodori()

    def installed(api_url: str) -> None:
        install_button.setEnabled(True)
        enabled.setChecked(True)
        url.setText(api_url)
        model.setText(LOCAL_IRODORI_MODEL)
        voice.setText("")
        install_status.setText(tr("安裝完成；Irodori-TTS v4.1 已在本機啟動。"))
        panel.settings.update(
            tts_enabled=True,
            tts_provider="irodori_local",
            tts_api_url=api_url,
            tts_model=LOCAL_IRODORI_MODEL,
            tts_voice="",
        )
        panel.persist()

    def install_error(message: str) -> None:
        install_button.setEnabled(True)
        install_status.setText(tr("安裝失敗：") + tr_dynamic(message))

    provider.currentIndexChanged.connect(update_provider)
    install_button.clicked.connect(install)
    panel.signals.tts_install_progress.connect(
        lambda message: install_status.setText(tr_dynamic(message))
    )
    panel.signals.tts_installed.connect(installed)
    panel.signals.tts_install_error.connect(install_error)
    update_provider()

    def save() -> None:
        selected_provider = str(provider.currentData())
        panel.settings.update(
            tts_enabled=enabled.isChecked(),
            tts_provider=selected_provider,
            tts_api_url=(
                panel.local_irodori_server.api_url
                if selected_provider == "irodori_local"
                else url.text().strip()
            ),
            tts_model=(
                LOCAL_IRODORI_MODEL
                if selected_provider == "irodori_local"
                else model.text().strip() or "tts-1"
            ),
            tts_voice="" if selected_provider == "irodori_local" else voice.text().strip(),
            tts_api_key=key.text().strip(),
            tts_language=language.text().strip() or "Japanese",
            tts_reference_root=root.text().strip(),
        )
        panel._set_tts_enabled(enabled.isChecked())
        refresh_reference()

    _save_button(layout, "儲存 TTS 設定", save)
    page.layout().addStretch()
