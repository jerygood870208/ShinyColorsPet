"""Desktop control panel: navigation, pets, assets, settings, and system tray."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLockFile, QPointF, QRectF, QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from shiny_pet.app_paths import application_data_root, migrate_duplicated_data_root
from shiny_pet.i18n import SUPPORTED_LANGUAGES, set_locale, tr, tr_dynamic, trf
from shiny_pet.models.managed_models import (
    ManagedModelInput,
    managed_manifest_root,
    profile_character_ui_assets,
    profile_unit_ui_assets,
    update_from_downloaded_folder,
    update_managed_model,
)
from shiny_pet.models.runtime_catalog import (
    ModelSelection,
    RuntimeCatalog,
    application_root,
    discover_runtime_catalog,
)
from shiny_pet.process.manager import ProcessManager
from shiny_pet.settings.store import SettingsStore

from .pages import install_core_pages


def _navigation_icon(kind: str, color: str, size: int = 22) -> QIcon:
    """Draw a small, consistent line icon without relying on platform fonts."""
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.9)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "home":
        feather = QPainterPath(QPointF(5, 19))
        feather.cubicTo(5, 11, 8, 5, 18, 3)
        feather.cubicTo(19, 11, 14, 17, 5, 19)
        painter.drawPath(feather)
        painter.drawLine(QPointF(5, 19), QPointF(15, 7))
        painter.drawLine(QPointF(8, 15), QPointF(13, 14))
        painter.drawLine(QPointF(10, 11), QPointF(15, 10))
    elif kind == "add":
        painter.drawEllipse(QRectF(3, 3, 16, 16))
        painter.drawLine(QPointF(11, 7), QPointF(11, 15))
        painter.drawLine(QPointF(7, 11), QPointF(15, 11))
    elif kind == "outfit":
        painter.drawLine(QPointF(8, 5), QPointF(6, 8))
        painter.drawLine(QPointF(14, 5), QPointF(16, 8))
        painter.drawLine(QPointF(6, 8), QPointF(4, 18))
        painter.drawLine(QPointF(16, 8), QPointF(18, 18))
        painter.drawLine(QPointF(4, 18), QPointF(18, 18))
        painter.drawArc(QRectF(8, 3, 6, 5), 0, 180 * 16)
    elif kind == "assets":
        box = QPainterPath(QPointF(4, 8))
        box.lineTo(11, 4)
        box.lineTo(18, 8)
        box.lineTo(11, 12)
        box.closeSubpath()
        painter.drawPath(box)
        painter.drawLine(QPointF(4, 8), QPointF(4, 16))
        painter.drawLine(QPointF(4, 16), QPointF(11, 20))
        painter.drawLine(QPointF(11, 20), QPointF(18, 16))
        painter.drawLine(QPointF(18, 16), QPointF(18, 8))
        painter.drawLine(QPointF(11, 12), QPointF(11, 20))
    elif kind == "actions":
        painter.drawEllipse(QRectF(3, 3, 16, 16))
        painter.drawEllipse(QRectF(7, 8, 1, 1))
        painter.drawEllipse(QRectF(14, 8, 1, 1))
        smile = QPainterPath(QPointF(7, 12))
        smile.cubicTo(8, 16, 14, 16, 15, 12)
        painter.drawPath(smile)
    elif kind == "activity":
        painter.drawLine(QPointF(4, 6), QPointF(18, 6))
        painter.drawLine(QPointF(4, 11), QPointF(18, 11))
        painter.drawLine(QPointF(4, 16), QPointF(13, 16))
        painter.drawEllipse(QPointF(17, 16), 1, 1)
    elif kind == "display":
        painter.drawRoundedRect(QRectF(3, 4, 16, 12), 2, 2)
        painter.drawLine(QPointF(8, 19), QPointF(14, 19))
        painter.drawLine(QPointF(11, 16), QPointF(11, 19))
    elif kind == "floating":
        painter.drawRoundedRect(QRectF(3, 3, 16, 15), 2, 2)
        painter.drawLine(QPointF(3, 7), QPointF(19, 7))
        painter.drawEllipse(QPointF(6, 5), 0.8, 0.8)
        painter.drawEllipse(QPointF(9, 5), 0.8, 0.8)
    elif kind == "memory":
        heart = QPainterPath(QPointF(11, 18))
        heart.cubicTo(9, 16, 4, 13, 4, 8)
        heart.cubicTo(4, 4, 9, 3, 11, 7)
        heart.cubicTo(13, 3, 18, 4, 18, 8)
        heart.cubicTo(18, 13, 13, 16, 11, 18)
        painter.drawPath(heart)
    elif kind == "relationship":
        painter.drawEllipse(QRectF(4, 4, 5, 5))
        painter.drawEllipse(QRectF(13, 4, 5, 5))
        painter.drawArc(QRectF(2, 10, 9, 9), 0, 180 * 16)
        painter.drawArc(QRectF(11, 10, 9, 9), 0, 180 * 16)
        painter.drawLine(QPointF(9, 8), QPointF(13, 8))
    elif kind == "album":
        painter.drawRoundedRect(QRectF(3, 5, 16, 13), 2, 2)
        painter.drawEllipse(QRectF(6, 8, 3, 3))
        mountain = QPainterPath(QPointF(5, 16))
        mountain.lineTo(10, 12)
        mountain.lineTo(13, 15)
        mountain.lineTo(15, 13)
        mountain.lineTo(18, 16)
        painter.drawPath(mountain)
    elif kind == "history":
        painter.drawArc(QRectF(3, 3, 16, 16), 35 * 16, 285 * 16)
        painter.drawLine(QPointF(11, 7), QPointF(11, 11))
        painter.drawLine(QPointF(11, 11), QPointF(15, 13))
    elif kind == "statistics":
        painter.drawLine(QPointF(4, 19), QPointF(19, 19))
        painter.drawLine(QPointF(5, 19), QPointF(5, 4))
        painter.drawRoundedRect(QRectF(8, 13, 2, 6), 0.7, 0.7)
        painter.drawRoundedRect(QRectF(12, 9, 2, 10), 0.7, 0.7)
        painter.drawRoundedRect(QRectF(16, 6, 2, 13), 0.7, 0.7)
    elif kind == "persona":
        painter.drawEllipse(QRectF(8, 3, 6, 6))
        shoulders = QPainterPath(QPointF(4, 19))
        shoulders.cubicTo(4, 13, 8, 11, 11, 11)
        shoulders.cubicTo(14, 11, 18, 13, 18, 19)
        painter.drawPath(shoulders)
    elif kind == "llm":
        painter.drawRoundedRect(QRectF(3, 4, 16, 12), 3, 3)
        painter.drawLine(QPointF(7, 16), QPointF(5, 19))
        painter.drawEllipse(QPointF(8, 10), 0.8, 0.8)
        painter.drawEllipse(QPointF(11, 10), 0.8, 0.8)
        painter.drawEllipse(QPointF(14, 10), 0.8, 0.8)
    elif kind == "chat":
        painter.drawRoundedRect(QRectF(3, 4, 16, 12), 3, 3)
        painter.drawLine(QPointF(7, 16), QPointF(5, 19))
        painter.drawLine(QPointF(8, 9), QPointF(14, 9))
    elif kind == "tts":
        painter.drawRect(QRectF(4, 4, 6, 13))
        painter.drawLine(QPointF(6, 7), QPointF(8, 7))
        painter.drawLine(QPointF(6, 10), QPointF(8, 10))
        painter.drawLine(QPointF(13, 8), QPointF(13, 17))
        painter.drawLine(QPointF(13, 8), QPointF(18, 6))
        painter.drawLine(QPointF(18, 6), QPointF(18, 14))
        painter.drawEllipse(QPointF(11, 17), 2, 2)
        painter.drawEllipse(QPointF(16, 14), 2, 2)
    elif kind == "voice":
        painter.drawRoundedRect(QRectF(8, 2.5, 6, 12), 3, 3)
        cradle = QPainterPath(QPointF(5, 10))
        cradle.lineTo(5, 11.5)
        cradle.cubicTo(5, 16.5, 8, 19, 11, 19)
        cradle.cubicTo(14, 19, 17, 16.5, 17, 11.5)
        cradle.lineTo(17, 10)
        painter.drawPath(cradle)
        painter.drawLine(QPointF(11, 19), QPointF(11, 21))
        painter.drawLine(QPointF(8, 21), QPointF(14, 21))
    elif kind == "data":
        painter.drawRoundedRect(QRectF(4, 3, 14, 16), 2, 2)
        painter.drawLine(QPointF(7, 8), QPointF(15, 8))
        painter.drawLine(QPointF(7, 12), QPointF(15, 12))
        painter.drawLine(QPointF(7, 16), QPointF(12, 16))
    elif kind == "about":
        painter.drawEllipse(QRectF(3, 3, 16, 16))
        painter.drawLine(QPointF(11, 10), QPointF(11, 15))
        painter.drawPoint(QPointF(11, 7))
    elif kind == "add":
        painter.drawEllipse(QRectF(3, 3, 16, 16))
        painter.drawLine(QPointF(11, 7), QPointF(11, 15))
        painter.drawLine(QPointF(7, 11), QPointF(15, 11))
    elif kind == "reminders":
        painter.drawRoundedRect(QRectF(5, 5, 12, 13), 2, 2)
        painter.drawLine(QPointF(8, 3), QPointF(8, 7))
        painter.drawLine(QPointF(14, 3), QPointF(14, 7))
        painter.drawLine(QPointF(5, 9), QPointF(17, 9))
    elif kind == "screen_tools":
        painter.drawRoundedRect(QRectF(3, 4, 16, 12), 2, 2)
        painter.drawLine(QPointF(8, 19), QPointF(14, 19))
        painter.drawLine(QPointF(11, 16), QPointF(11, 19))
    elif kind == "p_letter":
        p_pen = QPen(QColor(color), 2.8)
        p_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(p_pen)
        letter_p = QPainterPath(QPointF(6, 19))
        letter_p.lineTo(6, 3)
        letter_p.lineTo(12, 3)
        letter_p.cubicTo(18, 3, 18, 11, 12, 11)
        letter_p.lineTo(6, 11)
        painter.drawPath(letter_p)

    painter.end()
    return QIcon(canvas)


def _navigation_icon_set(kind: str) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_navigation_icon(kind, "#59707d").pixmap(22, 22), QIcon.Mode.Normal)
    selected = _navigation_icon(kind, "#147fa8").pixmap(22, 22)
    icon.addPixmap(selected, QIcon.Mode.Selected)
    icon.addPixmap(selected, QIcon.Mode.Active, QIcon.State.On)
    icon.addPixmap(selected, QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(_navigation_icon(kind, "#9bb0ba").pixmap(22, 22), QIcon.Mode.Disabled)
    return icon


def runtime_root_for_session(
    configured: str, *, cli_root: Path | None = None, frozen: bool | None = None
) -> Path | None:
    """Choose an explicit runtime without overriding the bundled frozen runtime by accident."""
    if cli_root is not None:
        return cli_root.resolve()
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen or not configured:
        return None
    candidate = Path(configured).resolve()
    runtime = candidate / "spine-ts" / "build" / "spine-webgl.js"
    return candidate if runtime.is_file() else None


def persistent_pet_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Persist catalog identity instead of a machine-specific resolved manifest path."""
    result = dict(spec)
    fields = ("character_id", "outfit_id", "presentation", "costume_mode")
    if all(isinstance(result.get(key), str) and result[key] for key in fields):
        result.pop("path", None)
    return result


def preferred_catalog_selection(
    catalog: RuntimeCatalog,
    defaults: object,
    character_id: str,
    presentation: str,
) -> ModelSelection | None:
    """Resolve a user-selected default, falling back when its asset is unavailable."""
    if isinstance(defaults, dict):
        presentations = defaults.get(character_id)
        if isinstance(presentations, dict):
            configured = presentations.get(presentation)
            if isinstance(configured, dict):
                outfit_id = configured.get("outfit_id")
                costume_mode = configured.get("costume_mode")
                if isinstance(outfit_id, str) and isinstance(costume_mode, str):
                    selection = catalog.selection(
                        character_id, outfit_id, presentation, costume_mode
                    )
                    if selection is not None:
                        return selection
    return catalog.default_selection(character_id, presentation)


class DesktopControlPanel(QWidget):
    """Own the application shell and widget references used by controller methods."""

    action_character_label: QLabel
    action_grid: QGridLayout
    action_grid_host: QWidget
    action_hint: QLabel
    add_flow: QStackedWidget
    asset_summary: QLabel
    character_grid: QGridLayout
    character_grid_host: QWidget
    character_selector: QComboBox
    character_view: QWidget
    costume_selector: QComboBox
    debug_hit_areas: QCheckBox
    default_outfit_status: QLabel
    downloaded_model_root: QLineEdit
    fps: QSpinBox
    gaze_enabled: QCheckBox
    hit_test_mode: QComboBox
    idle_enabled: QCheckBox
    log: QTextEdit
    managed_asset_directory: QLineEdit
    managed_character: QComboBox
    managed_costume_mode: QComboBox
    managed_outfit_id: QLineEdit
    managed_outfit_name: QLineEdit
    managed_presentation: QComboBox
    model_update_progress: QProgressBar
    outfit_character_label: QLabel
    outfit_selector: QComboBox
    pets: QListWidget
    presentation_selector: QComboBox
    quality: QComboBox
    random_enabled: QCheckBox
    random_interval: QSpinBox
    rescan_models_button: QPushButton
    rescan_progress: QProgressBar
    reset_default_outfit_button: QPushButton
    running_count: QLabel
    scale: QDoubleSpinBox
    selected_character_label: QLabel
    set_default_outfit_button: QPushButton
    unit_grid: QGridLayout
    unit_grid_host: QWidget
    unit_selector: QComboBox
    unit_view: QWidget
    update_models_button: QPushButton
    vsync: QCheckBox

    def __init__(self, store: SettingsStore, settings: dict[str, Any],
                 runtime_root: Path | None) -> None:
        super().__init__()
        self.store, self.settings = store, settings
        set_locale(str(settings.get("ui_language", "zh-TW")))
        self.quitting = False
        self.manager = ProcessManager(runtime_root)
        extra_roots = [Path(value) for value in settings.get("asset_pack_roots", [])]
        self.manifest_root = managed_manifest_root(self.store.path.parent)
        self.runtime_catalog: RuntimeCatalog = discover_runtime_catalog(
            extra_roots, managed_manifest_root=self.manifest_root
        )
        self.ids: list[str] = []
        self.last_saved = ""
        self.nav_buttons: dict[str, QPushButton] = {}
        self.pages: dict[str, QWidget] = {}
        self.page_refreshers: dict[str, Callable[[], None]] = {}
        self.setObjectName("AppRoot")
        self.setWindowTitle(tr("ShinyColorsPet — 桌寵管理"))
        self.resize(1220, 820)
        self.setMinimumSize(980, 520)
        icon_path = application_root() / "assets" / "icon.png"
        if not icon_path.is_file():
            icon_path = Path(__file__).resolve().parents[2] / "assets" / "icon.png"
        self.app_icon = QIcon(str(icon_path))
        self.setWindowIcon(self.app_icon)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setWindowIcon(self.app_icon)

        shell = QHBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.sidebar = QFrame(self)
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(224)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(18, 24, 18, 20)
        sidebar_layout.setSpacing(8)
        brand = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setPixmap(self.app_icon.pixmap(40, 40))
        brand.addWidget(brand_icon)
        brand_text = QVBoxLayout()
        title = QLabel("ShinyColorsPet")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("283 PRODUCTION")
        subtitle.setObjectName("BrandSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand.addLayout(brand_text)
        sidebar_layout.addLayout(brand)
        sidebar_layout.addSpacing(14)
        nav_scroll = QScrollArea(self.sidebar)
        self.nav_scroll = nav_scroll
        nav_scroll.setObjectName("NavigationScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_host = QWidget(nav_scroll)
        nav_host.setObjectName("NavigationHost")
        self.nav_layout = QVBoxLayout(nav_host)
        self.nav_layout.setContentsMargins(0, 4, 0, 4)
        self.nav_layout.setSpacing(7)
        nav_scroll.setWidget(nav_host)
        sidebar_layout.addWidget(nav_scroll, 1)
        for key, icon, label in (
            ("home", "home", "桌面人物"),
            ("add", "add", "新增人物"),
            ("outfit", "outfit", "服裝管理"),
            ("actions", "actions", "動作與表情"),
        ):
            self._add_nav_item(key, icon, label)
        self.nav_layout.addSpacing(12)
        section = QLabel(tr("導航"))
        section.setObjectName("NavSection")
        self.nav_layout.addWidget(section)
        for key, icon, label in (
            ("display", "display", "顯示設定"),
            ("assets", "assets", "資產管理"),
            ("activity", "activity", "活動記錄"),
            ("about", "about", "關於"),
        ):
            self._add_nav_item(key, icon, label)
        self.nav_layout.addStretch()
        self.sidebar_status = QLabel("●  本機模式")
        self.sidebar_status.setObjectName("SidebarStatus")
        sidebar_layout.addWidget(self.sidebar_status)
        shell.addWidget(self.sidebar)

        self.content_stack = QStackedWidget(self)
        self.content_stack.setObjectName("ContentStack")
        shell.addWidget(self.content_stack, 1)

        install_core_pages(self, settings)

        self._apply_visual_style()
        self.manager.changed.connect(self.refresh)
        self.manager.error.connect(self.log.append)
        self.manager.message_received.connect(self.worker_event)
        self.pets.currentRowChanged.connect(lambda _row: self.refresh_outfit_controls())
        self.unit_selector.currentIndexChanged.connect(
            lambda _index: self.refresh_character_selector()
        )
        self.outfit_selector.currentIndexChanged.connect(
            lambda _index: self.refresh_costume_selector()
        )
        self.tray = QSystemTrayIcon(
            self.app_icon if not self.app_icon.isNull() else self.style().standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon
            ), self
        )
        self.tray.setToolTip("ShinyColorsPet")
        self.menu = QMenu(self)  # Keep a real QWidget owner for macOS.
        self.menu.setStyleSheet("""
            QMenu { background: white; color: #234757; border: 1px solid #cfe1e9;
                border-radius: 12px; padding: 8px; }
            QMenu::item { min-width: 170px; padding: 10px 16px; border-radius: 8px; }
            QMenu::item:selected { background: #dff6ff; color: #147fa8; }
            QMenu::separator { height: 1px; background: #dcecf3; margin: 5px 8px; }
        """)
        self.menu.addAction("桌寵管理", self.show_panel)
        self.menu.addAction("顯示所有寵物", lambda: self.broadcast("show"))
        self.menu.addAction("隱藏所有寵物", lambda: self.broadcast("hide"))
        self.menu.addSeparator()
        self.menu.addAction("結束", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        else:
            self.log.append("此桌面沒有可用托盤；請保留管理視窗，或使用退出按鈕。")
        self.save_timer = QTimer(self)
        self.save_timer.setInterval(3000)
        self.save_timer.timeout.connect(lambda: self.guard(self.persist))
        self.save_timer.start()
        self.refresh_unit_selector()
        self._refresh_asset_summary()
        self.show_page("home")
        for location, error in self.runtime_catalog.errors.items():
            self.log.append(f"資產包略過：{location}: {error}")
        restore = list(settings["pets"])
        for spec in restore:
            self.guard(lambda s=spec: self.restore(s))

    def _save_language(self, language: str) -> None:
        if language not in dict(SUPPORTED_LANGUAGES):
            return
        self.settings["ui_language"] = language
        self.store.save(self.settings)

    def translate_widgets(self) -> None:
        """Translate catalogued widget text, including labels created by pages."""
        for widget in self.findChildren(QWidget):
            for getter_name, setter_name in (
                ("text", "setText"),
                ("title", "setTitle"),
                ("placeholderText", "setPlaceholderText"),
                ("toolTip", "setToolTip"),
                ("accessibleName", "setAccessibleName"),
                ("format", "setFormat"),
                ("plainText", "setPlainText"),
                ("windowTitle", "setWindowTitle"),
            ):
                getter = getattr(widget, getter_name, None)
                setter = getattr(widget, setter_name, None)
                if callable(getter) and callable(setter):
                    value = str(getter())
                    translated = tr(value)
                    if translated != value:
                        setter(translated)
            if isinstance(widget, QComboBox):
                for index in range(widget.count()):
                    widget.setItemText(index, tr(widget.itemText(index)))
        for action in self.findChildren(QAction):
            action.setText(tr(action.text()))
        self._fit_sidebar_to_navigation()

    def _fit_sidebar_to_navigation(self) -> None:
        """Keep the sidebar compact while allowing longer translations to fit."""
        for button in self.nav_buttons.values():
            button.ensurePolished()
        button_width = max(
            (button.sizeHint().width() for button in self.nav_buttons.values()),
            default=0,
        )
        margins = self.sidebar.layout().contentsMargins() if self.sidebar.layout() else None
        horizontal_margins = margins.left() + margins.right() if margins is not None else 36
        scrollbar_width = self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        required_width = button_width + horizontal_margins + scrollbar_width + 8
        self.sidebar.setFixedWidth(max(224, min(480, required_width)))

    def _create_nav_button(self, key: str, icon: str, label: str) -> QPushButton:
        button = QPushButton(tr(label))
        button.setObjectName("NavButton")
        button.setIcon(_navigation_icon_set(icon))
        button.setIconSize(QSize(22, 22))
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, value=key: self.show_page(value))
        return button

    def _add_nav_item(self, key: str, icon: str, label: str) -> None:
        button = self._create_nav_button(key, icon, label)
        self.nav_layout.addWidget(button)
        self.nav_buttons[key] = button

    def add_navigation_page(
        self, key: str, icon: str, label: str, title: str, subtitle: str
    ) -> QWidget:
        button = self._create_nav_button(key, icon, label)
        display_button = self.nav_buttons.get("display")
        index = self.nav_layout.indexOf(display_button) if display_button is not None else -1
        self.nav_layout.insertWidget(max(0, index), button)
        self.nav_buttons[key] = button
        return self._new_page(tr(title), tr(subtitle))

    def _new_page(self, title: str, subtitle: str) -> QWidget:
        scroll = QScrollArea(self.content_stack)
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget(scroll)
        page.setObjectName("Page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(34, 28, 34, 30)
        layout.setSpacing(18)
        # Preserve useful control sizes. A short window scrolls instead of
        # squeezing the page until labels and controls collide.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        header = QLabel(tr(title))
        header.setObjectName("PageTitle")
        description = QLabel(tr(subtitle))
        description.setObjectName("PageSubtitle")
        layout.addWidget(header)
        layout.addWidget(description)
        scroll.setWidget(page)
        self.content_stack.addWidget(scroll)
        key = next((name for name in self.nav_buttons if name not in self.pages), title)
        self.pages[key] = scroll
        return page

    @staticmethod
    def _normalize_page_spacing(page: QWidget) -> None:
        """Give every nested page layout a readable minimum gutter."""
        layouts = page.findChildren(QLayout)
        root_layout = page.layout()
        if isinstance(root_layout, QLayout):
            layouts.insert(0, root_layout)
        for layout in layouts:
            if layout.spacing() < 10:
                layout.setSpacing(10)

    @staticmethod
    def _column(widget: QWidget) -> QVBoxLayout:
        layout = widget.layout()
        if not isinstance(layout, QVBoxLayout):
            raise TypeError("page requires a vertical layout")
        return layout

    @staticmethod
    def _flow_view(title: str, subtitle: str) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(2, 2, 12, 2)
        layout.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("FlowTitle")
        hint = QLabel(subtitle)
        hint.setObjectName("Muted")
        layout.addWidget(heading)
        layout.addWidget(hint)
        return host

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        page_content = page.widget() if isinstance(page, QScrollArea) else None
        if page_content is not None:
            self._normalize_page_spacing(page_content)
        self.content_stack.setCurrentWidget(page)
        refresher = self.page_refreshers.get(key)
        if refresher is not None:
            self.guard(refresher)
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)
        selected_button = self.nav_buttons.get(key)
        if selected_button is not None:
            self.nav_scroll.ensureWidgetVisible(selected_button, 0, 18)
        if key == "outfit":
            self.refresh_outfit_controls()
        elif key == "actions":
            self.refresh_action_controls()

    def _apply_visual_style(self) -> None:
        self.setStyleSheet("""
            * { font-family: "Segoe UI", "Microsoft JhengHei UI"; font-size: 14px; }
            QWidget#AppRoot, QWidget#Page, QStackedWidget#ContentStack,
            QStackedWidget#InnerStack, QScrollArea, QScrollArea > QWidget > QWidget {
                background: #f7fbfd; color: #183446;
            }
            QFrame#Sidebar { background: #ffffff; border-right: 1px solid #dcecf3; }
            QScrollArea#NavigationScroll, QWidget#NavigationHost {
                background: transparent; border: 0; }
            QLabel#BrandTitle { font-size: 18px; font-weight: 800; color: #123246; }
            QLabel#BrandSubtitle { font-size: 10px; font-weight: 700; color: #57bddd; letter-spacing: 1px; }
            QLabel#NavSection { color: #89a2af; font-size: 11px; font-weight: 700; margin: 6px 8px; }
            QPushButton#NavButton { text-align: left; min-height: 43px; padding: 0 14px;
                border: 0; border-radius: 12px; color: #59707d; background: transparent; font-weight: 600; }
            QPushButton#NavButton:hover { background: #edf9fd; color: #269ec8; }
            QPushButton#NavButton:checked { background: #dff6ff; color: #147fa8; border-left: 4px solid #8adfff; }
            QLabel#SidebarStatus { color: #3ba874; background: #edfbf4; border-radius: 10px; padding: 9px 12px; }
            QLabel#PageTitle { font-size: 28px; font-weight: 800; color: #15394d; }
            QLabel#PageSubtitle { color: #748d99; font-size: 14px; margin-bottom: 4px; }
            QLabel#HeroTitle, QLabel#FlowTitle { font-size: 20px; font-weight: 750; color: #173e52; }
            QLabel#SectionTitle { font-size: 16px; font-weight: 700; color: #214659; }
            QLabel#Muted { color: #78909c; }
            QLabel#SaveStatus { color: #6f8793; padding: 4px 2px; }
            QLabel#SaveStatus[state="dirty"] { color: #a36b16; }
            QLabel#SaveStatus[state="saving"] { color: #247b9c; }
            QLabel#SaveStatus[state="saved"] { color: #25845b; font-weight: 650; }
            QLabel#SaveStatus[state="error"] { color: #cf4d5d; font-weight: 650; }
            QLabel#Pill { background: #dff6ff; color: #147fa8; border-radius: 10px; padding: 4px 10px; }
            QFrame#HeroCard { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ffffff, stop:1 #dff6ff);
                border: 1px solid #ccecf7; border-radius: 18px; }
            QFrame#PanelCard, QFrame#AboutCard, QFrame#SelectionBar, QGroupBox {
                background: #ffffff; border: 1px solid #dcecf3; border-radius: 16px; }
            QFrame#SelectionBar { padding: 8px; }
            QGroupBox { margin-top: 16px; padding: 22px 18px 18px 18px; font-weight: 700; }
            QGroupBox::title { subcontrol-origin: margin; left: 18px; padding: 0 6px; color: #396173; }
            QListWidget#PetList, QTextEdit#ActivityLog { background: #ffffff; border: 1px solid #dcecf3;
                border-radius: 16px; padding: 10px; outline: none; }
            QListWidget#PetList::item { min-height: 54px; border-radius: 10px; padding: 4px 10px; }
            QListWidget#PetList::item:selected { background: #dff6ff; color: #147fa8; }
            QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QLineEdit {
                min-height: 38px; border: 1px solid #cfe1e9; border-radius: 10px; background: #ffffff;
                color: #234757; padding: 0 12px; }
            QPushButton:hover, QComboBox:hover { border-color: #8adfff; background: #f5fcff; }
            QPushButton#PrimaryButton { background: #8adfff; border-color: #69cbea; color: #11384a; font-weight: 750; padding: 0 18px; }
            QPushButton#PrimaryButton:hover { background: #70d5f7; }
            QPushButton#SecondaryButton { background: #ffffff; color: #247b9c; font-weight: 650; }
            QPushButton#GhostButton { background: transparent; border: 0; color: #278cae; font-weight: 650; }
            QPushButton#DangerButton { background: #fff4f5; border-color: #ffd5da; color: #cf4d5d; font-weight: 650; }
            QProgressBar { min-height: 24px; border: 1px solid #cfe1e9; border-radius: 8px;
                background: #edf5f8; color: #234757; text-align: center; font-weight: 650; }
            QProgressBar::chunk { background: #8adfff; border-radius: 7px; }
            QToolButton#CatalogCard { background: #ffffff; border: 1px solid #dcecf3; border-radius: 16px;
                color: #24495a; font-weight: 700; padding: 14px; }
            QToolButton#CatalogCard:hover { border: 2px solid #8adfff; background: #f4fcff; }
            QToolButton#CatalogCard:checked { border: 2px solid #54c8ed; background: #e7f8ff; }
            QLabel#AboutTitle { font-size: 30px; font-weight: 800; color: #173e52; }
            QCheckBox { spacing: 10px; color: #345665; }
            QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
            QScrollBar::handle:vertical { background: #b9dbe8; border-radius: 4px; min-height: 32px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

    def guard(self, callback: Any) -> bool:
        try:
            return callback() is not False
        except (OSError, ValueError, RuntimeError) as exc:
            self.log.append(str(exc))
            return False

    def show_panel(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_panel()

    def worker_event(self, pet_id: str, event: dict[str, Any]) -> None:
        if event["kind"] in ("ready", "exit", "command_error"):
            self.log.append(f"{pet_id}: {json.dumps(event, ensure_ascii=False)}")
        if event["kind"] == "ui_action":
            if pet_id in self.ids:
                self.pets.setCurrentRow(self.ids.index(pet_id))
            action = event.get("action")
            if action == "chat":
                self.open_chat_for_pet(pet_id)
            elif action in {"outfit", "actions"}:
                self.show_panel()
                self.show_page(str(action))

    def open_chat_for_pet(self, pet_id: str) -> None:
        """The composed application overrides this hook with its independent chat window."""
        del pet_id
        self.log.append(tr("此版本尚未啟用聊天室。"))

    def selected(self) -> str | None:
        index = self.pets.currentRow()
        return self.ids[index] if 0 <= index < len(self.ids) else None

    def refresh(self) -> None:
        if self.quitting or self.manager.closing:
            return
        selected = self.selected()
        self.ids = list(self.manager.workers)
        self.pets.clear()
        for pet_id, worker in self.manager.workers.items():
            character_id = str(worker.spec.get("character_id", ""))
            character = self.runtime_catalog.characters.get(character_id)
            label = self.runtime_catalog.label(character.name_key) if character else (
                Path(worker.spec["path"]).stem
            )
            self.pets.addItem(f"{pet_id} · {worker.spec['mode']} · {label} · {worker.state}")
        if selected in self.ids:
            self.pets.setCurrentRow(self.ids.index(selected))
        elif self.ids:
            self.pets.setCurrentRow(len(self.ids) - 1)
        self.running_count.setText(trf("{count} 位", count=len(self.ids)))
        self.refresh_outfit_controls()
        self.refresh_action_controls()

    def refresh_unit_selector(self) -> None:
        selected = self.unit_selector.currentData()
        self.unit_selector.clear()
        for unit in self.runtime_catalog.ordered_units():
            icon_path = self.runtime_catalog.asset_path(unit.ui_assets.get("icon"))
            self.unit_selector.addItem(
                QIcon(str(icon_path)) if icon_path else QIcon(),
                self.runtime_catalog.label(unit.name_key),
                unit.unit_id,
            )
        if selected is not None:
            index = self.unit_selector.findData(selected)
            if index >= 0:
                self.unit_selector.setCurrentIndex(index)
        self._rebuild_unit_cards()
        self.refresh_character_selector()

    def refresh_character_selector(self) -> None:
        selected = self.character_selector.currentData()
        self.character_selector.clear()
        unit_id = self.unit_selector.currentData()
        if isinstance(unit_id, str):
            for character in self.runtime_catalog.characters_for_unit(unit_id):
                portrait = self.runtime_catalog.asset_path(character.ui_assets.get("portrait"))
                self.character_selector.addItem(
                    QIcon(str(portrait)) if portrait else QIcon(),
                    self.runtime_catalog.label(character.name_key),
                    character.character_id,
                )
        if selected is not None:
            index = self.character_selector.findData(selected)
            if index >= 0:
                self.character_selector.setCurrentIndex(index)
        self._rebuild_character_cards()

    @staticmethod
    def _clear_grid(grid: QGridLayout) -> None:
        while grid.count():
            item = grid.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @staticmethod
    def _catalog_card(text: str, icon: QIcon, size: QSize) -> QToolButton:
        card = QToolButton()
        card.setObjectName("CatalogCard")
        card.setText(text)
        card.setIcon(icon)
        card.setIconSize(size)
        card.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setCheckable(True)
        return card

    def _rebuild_unit_cards(self) -> None:
        self._clear_grid(self.unit_grid)
        for index, unit in enumerate(self.runtime_catalog.ordered_units()):
            icon_path = self.runtime_catalog.asset_path(unit.ui_assets.get("icon"))
            card = self._catalog_card(
                f"{self.runtime_catalog.label(unit.name_key)}\n"
                + trf("{count} 位人物", count=len(unit.member_character_ids)),
                QIcon(str(icon_path)) if icon_path else QIcon(),
                QSize(150, 70),
            )
            card.setFixedSize(230, 155)
            card.clicked.connect(
                lambda _checked=False, unit_id=unit.unit_id: self._select_unit_card(unit_id)
            )
            self.unit_grid.addWidget(card, index // 3, index % 3)
        self.unit_grid.setColumnStretch(3, 1)

    def _select_unit_card(self, unit_id: str) -> None:
        index = self.unit_selector.findData(unit_id)
        if index >= 0:
            self.unit_selector.setCurrentIndex(index)
        unit = self.runtime_catalog.units.get(unit_id)
        if unit is not None:
            heading = self.character_view.findChild(QLabel, "FlowTitle")
            if heading is not None:
                heading.setText(
                    f"{tr('選擇人物')} · {self.runtime_catalog.label(unit.name_key)}"
                )
        self.add_flow.setCurrentWidget(self.character_view)

    def _rebuild_character_cards(self) -> None:
        self._clear_grid(self.character_grid)
        unit_id = self.unit_selector.currentData()
        if not isinstance(unit_id, str):
            return
        for index, character in enumerate(self.runtime_catalog.characters_for_unit(unit_id)):
            portrait = self.runtime_catalog.asset_path(character.ui_assets.get("portrait"))
            card = self._catalog_card(
                f"{self.runtime_catalog.label(character.name_key)}\n"
                + trf("{count} 套服裝", count=len(character.outfits)),
                QIcon(str(portrait)) if portrait else QIcon(),
                QSize(170, 205),
            )
            card.setFixedSize(220, 300)
            card.clicked.connect(
                lambda _checked=False, character_id=character.character_id:
                    self._select_character_card(character_id)
            )
            self.character_grid.addWidget(card, index // 3, index % 3)
        self.character_grid.setColumnStretch(3, 1)

    def _select_character_card(self, character_id: str) -> None:
        index = self.character_selector.findData(character_id)
        if index >= 0:
            self.character_selector.setCurrentIndex(index)
        character = self.runtime_catalog.characters.get(character_id)
        self.selected_character_label.setText(
            self.runtime_catalog.label(character.name_key) if character else tr("請選擇人物")
        )

    @staticmethod
    def selection_spec(selection: ModelSelection, *, x: int, y: int) -> dict[str, Any]:
        return {
            "mode": "spine",
            "path": str(selection.manifest_path),
            "character_id": selection.character_id,
            "outfit_id": selection.outfit_id,
            "presentation": selection.presentation,
            "costume_mode": selection.costume_mode,
            "x": x,
            "y": y,
        }

    def add_catalog_character(self) -> None:
        character_id = self.character_selector.currentData()
        presentation = self.presentation_selector.currentData()
        if not isinstance(character_id, str) or not isinstance(presentation, str):
            raise ValueError("沒有可載入的人物；請先安裝相容的本機資產包。")
        selection = preferred_catalog_selection(
            self.runtime_catalog,
            self.settings.get("character_default_outfits"),
            character_id,
            presentation,
        )
        if selection is None:
            raise ValueError("這個人物沒有可用的本機模型資產。")
        offset = 80 * len(self.manager.workers)
        self.launch(self.selection_spec(selection, x=80 + offset, y=80))

    def refresh_outfit_controls(self) -> None:
        self.outfit_selector.blockSignals(True)
        previous = self.outfit_selector.currentData()
        self.outfit_selector.clear()
        pet_id = self.selected()
        worker = self.manager.workers.get(pet_id) if pet_id else None
        self.outfit_character_label.setText(tr("尚未選取桌面人物"))
        self.default_outfit_status.setText(tr("目前使用資產內建預設"))
        self.set_default_outfit_button.setEnabled(False)
        self.reset_default_outfit_button.setEnabled(False)
        if worker is not None:
            character_id = worker.spec.get("character_id")
            presentation = worker.spec.get("presentation")
            if isinstance(character_id, str) and isinstance(presentation, str):
                character = self.runtime_catalog.characters.get(character_id)
                if character is not None:
                    self.outfit_character_label.setText(
                        self.runtime_catalog.label(character.name_key)
                    )
                for outfit in self.runtime_catalog.available_outfits(character_id, presentation):
                    self.outfit_selector.addItem(
                        self.runtime_catalog.label(outfit.name_key), outfit.outfit_id
                    )
                target = worker.spec.get("outfit_id", previous)
                index = self.outfit_selector.findData(target)
                if index >= 0:
                    self.outfit_selector.setCurrentIndex(index)
                self._refresh_default_outfit_status(character_id, presentation)
        self.outfit_selector.blockSignals(False)
        self.refresh_costume_selector()

    def _refresh_default_outfit_status(
        self, character_id: str, presentation: str
    ) -> None:
        self.set_default_outfit_button.setEnabled(True)
        defaults = self.settings.get("character_default_outfits")
        presentations = defaults.get(character_id) if isinstance(defaults, dict) else None
        configured = presentations.get(presentation) if isinstance(presentations, dict) else None
        if not isinstance(configured, dict):
            return
        self.reset_default_outfit_button.setEnabled(True)
        outfit_id = configured.get("outfit_id")
        costume_mode = configured.get("costume_mode")
        if not isinstance(outfit_id, str) or not isinstance(costume_mode, str):
            return
        selection = self.runtime_catalog.selection(
            character_id, outfit_id, presentation, costume_mode
        )
        if selection is None:
            self.default_outfit_status.setText(tr(
                "儲存的預設衣服目前不可用，載入時將使用資產內建預設。"
            ))
            return
        outfit = next((
            item for item in self.runtime_catalog.available_outfits(character_id, presentation)
            if item.outfit_id == outfit_id
        ), None)
        outfit_name = self.runtime_catalog.label(outfit.name_key) if outfit else outfit_id
        mode_name = tr("普通服") if costume_mode == "normal" else (
            tr("演出服") if costume_mode == "performance" else costume_mode
        )
        self.default_outfit_status.setText(
            tr("目前預設：{outfit}（{mode}）").format(
                outfit=outfit_name, mode=mode_name
            )
        )

    def refresh_costume_selector(self) -> None:
        self.costume_selector.clear()
        pet_id = self.selected()
        worker = self.manager.workers.get(pet_id) if pet_id else None
        outfit_id = self.outfit_selector.currentData()
        if worker is None or not isinstance(outfit_id, str):
            return
        character_id = worker.spec.get("character_id")
        presentation = worker.spec.get("presentation")
        if not isinstance(character_id, str) or not isinstance(presentation, str):
            return
        labels = {"normal": tr("普通服"), "performance": tr("演出服")}
        selections = self.runtime_catalog.available_selections(
            character_id, outfit_id, presentation
        )
        order = {"normal": 0, "performance": 1}
        for selection in sorted(selections, key=lambda item: order.get(item.costume_mode, 99)):
            self.costume_selector.addItem(
                labels.get(selection.costume_mode, selection.costume_mode),
                selection.costume_mode,
            )
        index = self.costume_selector.findData(worker.spec.get("costume_mode"))
        if index >= 0:
            self.costume_selector.setCurrentIndex(index)

    def refresh_action_controls(self) -> None:
        self._clear_grid(self.action_grid)
        pet_id = self.selected()
        worker = self.manager.workers.get(pet_id) if pet_id else None
        self.action_character_label.setText("尚未選取桌面人物")
        if worker is None:
            return
        character_id = str(worker.spec.get("character_id", ""))
        character = self.runtime_catalog.characters.get(character_id)
        if character is not None:
            self.action_character_label.setText(self.runtime_catalog.label(character.name_key))
        entries = [
            *(("gesture", key, "動作") for key in sorted(worker.semantic_actions)),
            *(("expression", key, "表情") for key in sorted(worker.semantic_expressions)),
        ]
        for index, (kind, key, category) in enumerate(entries):
            button = QPushButton(f"{category} · {key}")
            button.setObjectName("SecondaryButton")
            button.clicked.connect(
                lambda _checked=False, action_kind=kind, action_key=key, target=pet_id:
                    self.manager.semantic(target, action_kind, action_key)
            )
            self.action_grid.addWidget(button, index // 3, index % 3)
        if not entries:
            empty = QLabel("模型尚未 ready，或 manifest 沒有提供可預覽的語意動作。")
            empty.setObjectName("Muted")
            self.action_grid.addWidget(empty, 0, 0)

    def change_selected_outfit(self) -> None:
        pet_id = self.selected()
        worker = self.manager.workers.get(pet_id) if pet_id else None
        if pet_id is None or worker is None:
            raise ValueError("請先在上方清單選擇人物。")
        character_id = worker.spec.get("character_id")
        presentation = worker.spec.get("presentation")
        outfit_id = self.outfit_selector.currentData()
        costume_mode = self.costume_selector.currentData()
        if (
            not isinstance(character_id, str)
            or not isinstance(presentation, str)
            or not isinstance(outfit_id, str)
            or not isinstance(costume_mode, str)
        ):
            raise ValueError("手動匯入的模型目前沒有 catalog 換衣資料。")
        selection = self.runtime_catalog.selection(
            character_id, outfit_id, presentation, costume_mode
        )
        if selection is None:
            raise ValueError("所選衣服資產目前不可用。")
        spec = self.selection_spec(
            selection, x=int(worker.spec.get("x", 80)), y=int(worker.spec.get("y", 80))
        )
        process = worker.process
        process.finished.connect(
            lambda _code, _status, next_spec=spec: QTimer.singleShot(
                0, lambda: self.guard(
                    lambda: self.complete_outfit_change(pet_id, next_spec)
                )
            )
        )
        self.manager.stop(pet_id)

    def set_selected_outfit_as_default(self) -> None:
        pet_id = self.selected()
        worker = self.manager.workers.get(pet_id) if pet_id else None
        if worker is None:
            raise ValueError("請先在上方清單選擇人物。")
        character_id = worker.spec.get("character_id")
        presentation = worker.spec.get("presentation")
        outfit_id = self.outfit_selector.currentData()
        costume_mode = self.costume_selector.currentData()
        if not all(isinstance(value, str) and value for value in (
            character_id, presentation, outfit_id, costume_mode
        )):
            raise ValueError("手動匯入的模型目前沒有 catalog 換衣資料。")
        assert isinstance(character_id, str)
        assert isinstance(presentation, str)
        assert isinstance(outfit_id, str)
        assert isinstance(costume_mode, str)
        if self.runtime_catalog.selection(
            character_id, outfit_id, presentation, costume_mode
        ) is None:
            raise ValueError("所選衣服資產目前不可用。")
        previous = self.settings.get("character_default_outfits")
        defaults = deepcopy(previous) if isinstance(previous, dict) else {}
        presentations = defaults.setdefault(character_id, {})
        presentations[presentation] = {
            "outfit_id": outfit_id,
            "costume_mode": costume_mode,
        }
        self.settings["character_default_outfits"] = defaults
        try:
            self.persist()
        except (OSError, ValueError):
            self.settings["character_default_outfits"] = previous
            raise
        self._refresh_default_outfit_status(character_id, presentation)
        self.log.append("已儲存此角色的預設衣服。")

    def reset_selected_default_outfit(self) -> None:
        pet_id = self.selected()
        worker = self.manager.workers.get(pet_id) if pet_id else None
        if worker is None:
            raise ValueError("請先在上方清單選擇人物。")
        character_id = worker.spec.get("character_id")
        presentation = worker.spec.get("presentation")
        if not isinstance(character_id, str) or not isinstance(presentation, str):
            raise ValueError("手動匯入的模型目前沒有 catalog 換衣資料。")
        previous = self.settings.get("character_default_outfits")
        defaults = deepcopy(previous) if isinstance(previous, dict) else {}
        presentations = defaults.get(character_id)
        if isinstance(presentations, dict):
            presentations.pop(presentation, None)
            if not presentations:
                defaults.pop(character_id, None)
        self.settings["character_default_outfits"] = defaults
        try:
            self.persist()
        except (OSError, ValueError):
            self.settings["character_default_outfits"] = previous
            raise
        self.refresh_outfit_controls()
        self.log.append("已恢復此角色的資產內建預設衣服。")

    def complete_outfit_change(self, pet_id: str, spec: dict[str, Any]) -> None:
        previous = self.manager.workers.pop(pet_id, None)
        if previous is not None:
            previous.process.deleteLater()
        self.launch(spec)

    def rescan_asset_packs(self) -> None:
        self.rescan_models_button.setEnabled(False)
        self.rescan_progress.setRange(0, 0)
        self.rescan_progress.setFormat("正在掃描模型與 manifest…")
        QApplication.processEvents()
        try:
            extra_roots = [Path(value) for value in self.settings.get("asset_pack_roots", [])]
            self.runtime_catalog = discover_runtime_catalog(
                extra_roots, managed_manifest_root=self.manifest_root
            )
            self.refresh_unit_selector()
            self.refresh()
            self._refresh_asset_summary()
            for location, error in self.runtime_catalog.errors.items():
                self.log.append(f"資產包略過：{location}: {error}")
            self.log.append(f"已找到 {len(self.runtime_catalog.packs)} 個資產包、"
                            f"{len(self.runtime_catalog.characters)} 位人物。")
        except Exception:
            self.rescan_progress.setRange(0, 1)
            self.rescan_progress.setValue(0)
            self.rescan_progress.setFormat("掃描失敗，請查看活動記錄")
            raise
        else:
            self.rescan_progress.setRange(0, 1)
            self.rescan_progress.setValue(1)
            self.rescan_progress.setFormat("模型掃描完成")
        finally:
            self.rescan_models_button.setEnabled(True)

    def choose_downloaded_model_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "選擇包含 dresses.json 的資料夾")
        if selected:
            self.downloaded_model_root.setText(selected)

    def choose_single_asset_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "選擇包含 data.json 與 data.atlas 的 Spine 資產資料夾"
        )
        if selected:
            self.managed_asset_directory.setText(selected)

    def _idol_profiles(self) -> dict[str, dict[str, Any]]:
        path = self.runtime_catalog.asset_path(
            "asset://shinycolors-ui-v1/metadata/idol_profiles.json"
        )
        if path is None:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            str(item["idolId"]).zfill(2): item
            for item in payload.get("profiles", [])
            if isinstance(item, dict) and "idolId" in item
        }

    def update_downloaded_models(self) -> None:
        source = self.downloaded_model_root.text().strip()
        if not source:
            raise ValueError("請先選擇包含 dresses.json 的解壓縮資料夾")
        self.update_models_button.setEnabled(False)
        self.model_update_progress.setRange(0, 0)
        self.model_update_progress.setFormat(tr("正在分析下載資料夾…"))
        QApplication.processEvents()

        def progress(done: int, total: int, label: str) -> None:
            self.model_update_progress.setRange(0, max(1, total))
            self.model_update_progress.setValue(done)
            self.model_update_progress.setFormat(f"{label}　%v / %m")
            QApplication.processEvents()

        try:
            outputs = update_from_downloaded_folder(
                Path(source), self.manifest_root, self._idol_profiles(), progress
            )
            self.rescan_asset_packs()
            self.log.append(tr_dynamic(
                f"人物模型更新完成：資產已複製到 {self.manifest_root.parent / 'models'}；"
                f"已建立／更新 {len(outputs)} 份 manifest。"
            ))
        except Exception:
            self.model_update_progress.setRange(0, 1)
            self.model_update_progress.setValue(0)
            self.model_update_progress.setFormat(tr("更新失敗，請查看活動記錄"))
            raise
        else:
            self.model_update_progress.setRange(0, max(1, len(outputs)))
            self.model_update_progress.setValue(len(outputs))
            self.model_update_progress.setFormat(
                tr_dynamic(f"更新完成，共 {len(outputs)} 組模型")
            )
            QMessageBox.information(
                self, tr("人物模型已更新"),
                tr_dynamic(f"已建立／更新 {len(outputs)} 組模型。\n\n{self.manifest_root}")
            )
        finally:
            self.update_models_button.setEnabled(True)

    def update_single_managed_model(self) -> None:
        idol_id = str(self.managed_character.currentData() or "")
        profile = self._idol_profiles().get(idol_id)
        if profile is None:
            raise ValueError("請選擇人物")
        unit_number = int(profile["unitId"])
        output = update_managed_model(ManagedModelInput(
            character_id=f"idol-{int(profile['idolId']):02d}",
            display_name=str(profile["idolName"]),
            unit_id=f"unit-{unit_number:02d}",
            unit_name=str(profile["unit"]["unitName"]),
            outfit_id=self.managed_outfit_id.text(),
            outfit_name=self.managed_outfit_name.text(),
            presentation=str(self.managed_presentation.currentData()),
            costume_mode=str(self.managed_costume_mode.currentData()),
            asset_directory=Path(self.managed_asset_directory.text()),
            ui_assets=profile_character_ui_assets(profile),
            unit_ui_assets=profile_unit_ui_assets(profile),
        ), self.manifest_root)
        self.rescan_asset_packs()
        self.log.append(tr_dynamic(f"已新增／更新模型：{output}"))
        QMessageBox.information(self, tr("模型已更新"), str(output))

    def _refresh_asset_summary(self) -> None:
        variants = sum(
            len(outfit.variants)
            for character in self.runtime_catalog.characters.values()
            for outfit in character.outfits
        )
        self.asset_summary.setText(trf(
            "{packs} 個資產包  ·  {characters} 位人物  ·  {models} 個模型",
            packs=len(self.runtime_catalog.packs),
            characters=len(self.runtime_catalog.characters),
            models=variants,
        ))

    def restore(self, saved: dict[str, Any]) -> None:
        spec = dict(saved)
        if not isinstance(spec.get("path"), str):
            character_id = spec.get("character_id")
            outfit_id = spec.get("outfit_id")
            presentation = spec.get("presentation")
            costume_mode = spec.get("costume_mode")
            if (
                not isinstance(character_id, str)
                or not isinstance(outfit_id, str)
                or not isinstance(presentation, str)
                or not isinstance(costume_mode, str)
            ):
                raise ValueError("已略過不完整的已儲存人物設定。")
            selection = self.runtime_catalog.selection(
                character_id, outfit_id, presentation, costume_mode
            )
            if selection is None:
                raise ValueError("已儲存人物的本機資產包目前不存在。")
            spec["path"] = str(selection.manifest_path)
        self.launch(spec)

    def command(self, kind: str) -> None:
        pet_id = self.selected()
        if pet_id:
            self.manager.send(pet_id, kind)

    def broadcast(self, kind: str) -> None:
        for pet_id in self.manager.workers:
            self.manager.send(pet_id, kind)

    def stop_selected(self) -> None:
        pet_id = self.selected()
        if pet_id:
            self.manager.stop(pet_id)

    def restart_selected(self) -> None:
        pet_id = self.selected()
        if pet_id:
            worker = self.manager.workers[pet_id]
            if worker.state not in ("stopped", "failed"):
                self.log.append("請先關閉這隻寵物，待 stopped 後重新啟動。")
                return
            self.guard(lambda: self.launch(dict(worker.spec)))

    def launch(self, spec: dict[str, Any]) -> None:
        self.manager.start(spec, self.settings)

    def launch_chibi(self) -> None:
        image, _ = QFileDialog.getOpenFileName(self, "選擇 Q版模式 sprite sheet", "",
                                               "Sprite (*.webp *.png)")
        if not image:
            return
        frames, _ = QFileDialog.getOpenFileName(self, "選擇 frames.json", str(Path(image).parent),
                                                "Frames (*.json)")
        if frames:
            self.launch({"mode": "chibi", "path": str(Path(image).resolve()),
                         "frames": str(Path(frames).resolve()), "x": 80, "y": 80})

    def apply_settings(self) -> None:
        previous = dict(self.settings)
        self.settings.update(model_scale=self.scale.value(), renderer_fps=self.fps.value(),
                             renderer_quality=str(self.quality.currentData()),
                             renderer_vsync=self.vsync.isChecked(),
                             interaction_hit_test_mode=str(self.hit_test_mode.currentData()),
                             interaction_debug_hit_areas=self.debug_hit_areas.isChecked(),
                             interaction_gaze_enabled=self.gaze_enabled.isChecked(),
                             interaction_idle_enabled=self.idle_enabled.isChecked(),
                             interaction_random_enabled=self.random_enabled.isChecked(),
                             interaction_random_interval_seconds=self.random_interval.value())
        try:
            self.persist()
        except (OSError, ValueError):
            self.settings = previous
            raise
        options = {key: self.settings[key] for key in (
            "model_scale", "renderer_fps", "renderer_quality", "renderer_vsync",
            "interaction_hit_test_mode", "interaction_debug_hit_areas",
            "interaction_gaze_enabled", "interaction_idle_enabled",
            "interaction_random_enabled", "interaction_random_interval_seconds",
        )}
        for pet_id in self.manager.workers:
            self.manager.send(pet_id, "settings", settings=options)
        self.log.append("設定已儲存並送出；工作程序的套用錯誤會列於此處。")

    def persist(self) -> None:
        if self.quitting:
            return
        pets = []
        for worker in self.manager.workers.values():
            if worker.state not in ("starting", "ready"):
                continue
            pets.append(persistent_pet_spec(worker.spec))
        self.settings["pets"] = pets
        serialized = json.dumps(self.settings, sort_keys=True)
        if serialized != self.last_saved:
            self.store.save(self.settings)
            self.last_saved = serialized

    def quit(self) -> None:
        if self.quitting:
            return
        self.guard(self.persist)
        self.quitting = True
        self.save_timer.stop()
        self.manager.shutdown()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.tray.isVisible() and not self.quitting:
            self.hide()
            event.ignore()
        else:
            self.quit()
            event.accept()


def main(panel_class: type[DesktopControlPanel] = DesktopControlPanel) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="*", type=Path)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--settings-file", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("ShinyColorsPet")
    app.setApplicationName("ShinyColorsPet")
    app.setQuitOnLastWindowClosed(False)
    if args.settings_file is not None:
        path = args.settings_file
    else:
        data_root = application_data_root(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.GenericDataLocation
        ))
        migrate_duplicated_data_root(data_root)
        path = data_root / "settings.json"
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path) + ".lock")
    if not lock.tryLock(0):
        QMessageBox.critical(None, "ShinyColorsPet", "此設定檔已有管理程序使用，請切回既有視窗。")
        return 2
    try:
        store = SettingsStore(path)
        settings = store.load()
        if args.runtime_root:
            settings["runtime_root"] = str(args.runtime_root.resolve())
        runtime_root = runtime_root_for_session(
            str(settings.get("runtime_root", "")), cli_root=args.runtime_root
        )
        if args.manifest:
            settings["pets"] = [{"mode": "spine", "path": str(p.resolve()),
                                  "x": 80 + i * 100, "y": 80}
                                 for i, p in enumerate(args.manifest)]
        panel = panel_class(store, settings, runtime_root)
        app.aboutToQuit.connect(panel.quit)
        panel.show()
        return app.exec()
    except (OSError, ValueError, RuntimeError) as exc:
        QMessageBox.critical(None, "ShinyColorsPet", str(exc))
        return 2
    finally:
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
