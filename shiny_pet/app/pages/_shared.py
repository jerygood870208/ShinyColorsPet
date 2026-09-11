"""Shared widgets for settings pages."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from shiny_pet.i18n import tr


def _card(page: QWidget) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame(page)
    card.setObjectName("PanelCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(26, 24, 26, 24)
    layout.setSpacing(13)
    page.layout().addWidget(card)  # type: ignore[union-attr]
    return card, layout


def _heading(layout: QVBoxLayout, title: str, detail: str = "") -> None:
    label = QLabel(tr(title))
    label.setObjectName("SectionTitle")
    layout.addWidget(label)
    if detail:
        hint = QLabel(tr(detail))
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        layout.addWidget(hint)


def _save_button(
    layout: QLayout,
    label: str,
    callback: Any,
    *,
    success_text: str = "已儲存，目前設定已生效",
) -> QPushButton:
    """Add a save action with persistent, in-context state feedback."""
    row = QWidget()
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(12)
    button = QPushButton(tr(label))
    button.setObjectName("PrimaryButton")
    status = QLabel(tr("目前顯示已儲存的設定"))
    status.setObjectName("SaveStatus")
    status.setWordWrap(True)

    def set_status(text: str, state: str) -> None:
        status.setText(tr(text))
        status.setProperty("state", state)
        status.style().unpolish(status)
        status.style().polish(status)

    def mark_dirty(*_args: Any) -> None:
        set_status("有尚未儲存的變更", "dirty")

    def run() -> None:
        set_status("正在儲存…", "saving")
        button.setEnabled(False)
        panel = button.window()
        guard = getattr(panel, "guard", None)
        succeeded = bool(guard(callback)) if callable(guard) else callback() is not False
        button.setEnabled(True)
        set_status(
            success_text if succeeded else "儲存失敗，請查看活動記錄",
            "saved" if succeeded else "error",
        )

    row_layout.addWidget(button)
    row_layout.addWidget(status, 1)
    button.clicked.connect(run)
    layout.addWidget(row)

    owner = layout.parentWidget()
    if owner is not None:
        for widget in owner.findChildren(QWidget):
            if widget is button:
                continue
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(mark_dirty)
            elif isinstance(widget, QTextEdit):
                widget.textChanged.connect(mark_dirty)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(mark_dirty)
                if widget.isEditable():
                    widget.currentTextChanged.connect(mark_dirty)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.valueChanged.connect(mark_dirty)
            elif isinstance(widget, QAbstractButton) and widget.isCheckable():
                widget.toggled.connect(mark_dirty)
    return button


def _character_combo(panel: Any) -> QComboBox:
    combo = QComboBox()
    for character in panel.runtime_catalog.characters.values():
        combo.addItem(panel.runtime_catalog.label(character.name_key), character.character_id)
    return combo
