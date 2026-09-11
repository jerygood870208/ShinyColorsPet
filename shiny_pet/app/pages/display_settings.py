"""Build the display settings navigation page."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QSpinBox,
)

from ._shared import _save_button


def build_display_settings_page(panel: Any, settings: dict[str, Any]) -> None:
    display_page = panel._new_page("顯示設定", "調整所有桌面人物的渲染品質")
    display_card = QFrame()
    display_card.setObjectName("PanelCard")
    form = QFormLayout(display_card)
    form.setContentsMargins(28, 28, 28, 28)
    panel.scale = QDoubleSpinBox()
    panel.scale.setRange(0.1, 4)
    panel.scale.setSingleStep(0.1)
    panel.scale.setValue(settings["model_scale"])
    form.addRow("角色縮放", panel.scale)
    panel.fps = QSpinBox()
    panel.fps.setRange(1, 120)
    panel.fps.setValue(settings["renderer_fps"])
    form.addRow("Spine FPS", panel.fps)
    panel.quality = QComboBox()
    panel.quality.addItem("省電", "low")
    panel.quality.addItem("平衡", "balanced")
    panel.quality.addItem("高品質", "high")
    quality_index = panel.quality.findData(settings["renderer_quality"])
    panel.quality.setCurrentIndex(max(0, quality_index))
    form.addRow("模型品質", panel.quality)
    panel.vsync = QCheckBox("啟用垂直同步")
    panel.vsync.setChecked(settings["renderer_vsync"])
    form.addRow("", panel.vsync)
    panel.hit_test_mode = QComboBox()
    panel.hit_test_mode.addItem("自動（優先透明像素）", "auto")
    panel.hit_test_mode.addItem("Spine 命中區域", "attachment")
    panel.hit_test_mode.addItem("整體模型範圍", "model-bounds")
    panel.hit_test_mode.setCurrentIndex(
        max(0, panel.hit_test_mode.findData(settings["interaction_hit_test_mode"]))
    )
    form.addRow("滑鼠命中方式", panel.hit_test_mode)
    panel.debug_hit_areas = QCheckBox("顯示命中區域（除錯）")
    panel.debug_hit_areas.setChecked(settings["interaction_debug_hit_areas"])
    form.addRow("", panel.debug_hit_areas)
    panel.gaze_enabled = QCheckBox("支援時讓角色視線跟隨游標")
    panel.gaze_enabled.setChecked(settings["interaction_gaze_enabled"])
    form.addRow("", panel.gaze_enabled)
    panel.idle_enabled = QCheckBox("啟用待機動作")
    panel.idle_enabled.setChecked(settings["interaction_idle_enabled"])
    form.addRow("", panel.idle_enabled)
    panel.random_enabled = QCheckBox("啟用隨機動作")
    panel.random_enabled.setChecked(settings["interaction_random_enabled"])
    form.addRow("", panel.random_enabled)
    panel.random_interval = QSpinBox()
    panel.random_interval.setRange(5, 600)
    panel.random_interval.setSuffix(" 秒")
    panel.random_interval.setValue(settings["interaction_random_interval_seconds"])
    panel.random_interval.setEnabled(panel.random_enabled.isChecked())
    panel.random_enabled.toggled.connect(panel.random_interval.setEnabled)
    form.addRow("隨機動作間隔", panel.random_interval)
    _save_button(
        form,
        "儲存並套用至所有人物",
        panel.apply_settings,
        success_text="已儲存，並已套用至所有人物",
    )
    panel._column(display_page).addWidget(display_card)
    panel._column(display_page).addStretch()
