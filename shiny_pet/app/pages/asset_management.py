"""Build the asset management navigation page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)


def build_asset_management_page(panel: Any, settings: dict[str, Any]) -> None:
    assets_page = panel._new_page("模型與資產", "從已解壓縮的下載資料建立並集中管理模型設定")
    scan_card = QFrame()
    scan_card.setObjectName("HeroCard")
    scan_layout = QHBoxLayout(scan_card)
    panel.asset_summary = QLabel()
    panel.asset_summary.setObjectName("HeroTitle")
    scan_layout.addWidget(panel.asset_summary, 1)
    panel.rescan_models_button = QPushButton("重新掃描模型")
    panel.rescan_models_button.setObjectName("PrimaryButton")
    panel.rescan_models_button.clicked.connect(lambda: panel.guard(panel.rescan_asset_packs))
    scan_layout.addWidget(panel.rescan_models_button)
    panel._column(assets_page).addWidget(scan_card)
    panel.rescan_progress = QProgressBar()
    panel.rescan_progress.setRange(0, 1)
    panel.rescan_progress.setValue(0)
    panel.rescan_progress.setFormat("尚未重新掃描")
    panel._column(assets_page).addWidget(panel.rescan_progress)
    model_management_columns = QHBoxLayout()
    model_management_columns.setSpacing(18)
    panel._column(assets_page).addLayout(model_management_columns)
    bulk = QGroupBox("從下載資料夾更新人物模型")
    bulk_layout = QVBoxLayout(bulk)
    bulk_hint = QLabel(
        "選擇已解壓縮、內含 dresses.json 的資料夾。程式會尋找所有完整的 "
        "Spine 3.6 模型，將資產複製到 AppData，並把 manifest 集中保存到：\n"
        + str(panel.manifest_root)
    )
    bulk_hint.setWordWrap(True)
    bulk_hint.setObjectName("Muted")
    bulk_layout.addWidget(bulk_hint)
    bulk_row = QHBoxLayout()
    panel.downloaded_model_root = QLineEdit()
    panel.downloaded_model_root.setPlaceholderText("尚未選擇下載後解壓縮的資料夾")
    choose_download = QPushButton("選擇資料夾…")
    choose_download.clicked.connect(panel.choose_downloaded_model_root)
    bulk_row.addWidget(panel.downloaded_model_root, 1)
    bulk_row.addWidget(choose_download)
    bulk_layout.addLayout(bulk_row)
    panel.model_update_progress = QProgressBar()
    panel.model_update_progress.setRange(0, 1)
    panel.model_update_progress.setValue(0)
    panel.model_update_progress.setFormat("尚未更新")
    bulk_layout.addWidget(panel.model_update_progress)
    panel.update_models_button = QPushButton("更新人物模型")
    panel.update_models_button.setObjectName("PrimaryButton")
    panel.update_models_button.clicked.connect(lambda: panel.guard(panel.update_downloaded_models))
    bulk_layout.addWidget(panel.update_models_button)
    model_management_columns.addWidget(bulk, 1)

    single = QGroupBox("新增或更新一組 Spine 資產")
    single_layout = QVBoxLayout(single)
    single_layout.setContentsMargins(22, 22, 22, 22)
    single_layout.setSpacing(16)
    single_hint = QLabel(
        "人物與所屬團體使用內建的偶像資料；只需填寫服裝資訊並選擇一組 Spine 資產。"
    )
    single_hint.setWordWrap(True)
    single_hint.setObjectName("Muted")
    single_layout.addWidget(single_hint)
    single_form = QFormLayout()
    single_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    single_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    single_form.setHorizontalSpacing(18)
    single_form.setVerticalSpacing(12)
    panel.managed_character = QComboBox()
    for idol_id, profile in sorted(panel._idol_profiles().items(), key=lambda item: int(item[0])):
        unit_name = str(profile.get("unit", {}).get("unitName") or "未分類")
        panel.managed_character.addItem(
            f"{profile.get('idolName', idol_id)}　／　{unit_name}", idol_id
        )
    panel.managed_outfit_id = QLineEdit()
    panel.managed_outfit_id.setPlaceholderText("例如：card-1040030010")
    panel.managed_outfit_name = QLineEdit()
    panel.managed_outfit_name.setPlaceholderText("顯示在服裝選單中的名稱")
    panel.managed_presentation = QComboBox()
    panel.managed_presentation.addItem("一般", "standard")
    panel.managed_presentation.addItem("Q版", "chibi")
    panel.managed_costume_mode = QComboBox()
    panel.managed_costume_mode.addItem("通常服", "normal")
    panel.managed_costume_mode.addItem("演出服", "performance")
    panel.managed_asset_directory = QLineEdit()
    asset_row = QHBoxLayout()
    asset_row.addWidget(panel.managed_asset_directory, 1)
    choose_asset = QPushButton("選擇 Spine 資產資料夾…")
    choose_asset.clicked.connect(panel.choose_single_asset_directory)
    asset_row.addWidget(choose_asset)
    single_form.addRow("人物", panel.managed_character)
    single_form.addRow("服裝 ID", panel.managed_outfit_id)
    single_form.addRow("服裝名稱", panel.managed_outfit_name)
    single_form.addRow("顯示類型", panel.managed_presentation)
    single_form.addRow("服裝類型", panel.managed_costume_mode)
    single_form.addRow("資產資料夾", asset_row)
    single_layout.addLayout(single_form)
    update_one = QPushButton("新增／更新這組模型")
    update_one.setObjectName("PrimaryButton")
    update_one.clicked.connect(lambda: panel.guard(panel.update_single_managed_model))
    single_layout.addWidget(update_one)
    model_management_columns.addWidget(single, 1)
    panel._column(assets_page).addStretch()
