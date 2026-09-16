"""Independent, character-scoped chat window."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from shiny_pet.i18n import tr, trf
from shiny_pet.local_time import computer_local_now, stored_as_computer_local

from .database import Message


def _round_pixmap(source: QPixmap, size: int) -> QPixmap:
    """Return a circular avatar with its border drawn inside the image bounds."""
    scaled = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(0, 0, size, size)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, scaled)
    painter.setClipping(False)
    border = QPen(QColor("white"), 2.0)
    border.setCosmetic(True)
    painter.setPen(border)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    painter.end()
    return result


def _chat_icon(kind: str, color: str, size: int = 24) -> QIcon:
    """Draw crisp UI icons without relying on emoji or icon fonts."""
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    if kind == "microphone":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(8, 2.5, 8, 13), 4, 4)
        cradle = QPainterPath(QPointF(5, 10))
        cradle.lineTo(5, 11.5)
        cradle.cubicTo(5, 16.5, 8, 19, 12, 19)
        cradle.cubicTo(16, 19, 19, 16.5, 19, 11.5)
        cradle.lineTo(19, 10)
        painter.drawPath(cradle)
        painter.drawLine(QPointF(12, 19), QPointF(12, 22))
        painter.drawLine(QPointF(8.5, 22), QPointF(15.5, 22))
    elif kind == "send":
        plane = QPainterPath(QPointF(2.5, 11))
        plane.lineTo(21.5, 2.5)
        plane.lineTo(15.5, 21.5)
        plane.lineTo(11, 14)
        plane.closeSubpath()
        painter.setBrush(QColor(color))
        painter.drawPath(plane)
        painter.drawLine(QPointF(11, 14), QPointF(20.5, 3.5))
    elif kind == "stop":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(5, 5, 14, 14), 2.5, 2.5)

    painter.end()
    return QIcon(canvas)


class ConversationView(QScrollArea):
    """A widget-backed transcript whose row alignment cannot leak between messages."""

    replay_requested = Signal(str)
    retry_requested = Signal(str)
    older_history_requested = Signal()

    def __init__(self, display_name: str, avatar: QPixmap | None = None,
                 background: Path | None = None) -> None:
        super().__init__()
        self.display_name = display_name
        self.avatar = avatar
        self.setObjectName("Conversation")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setObjectName("ConversationViewport")
        if background is not None and background.is_file():
            image = str(background).replace("\\", "/").replace("'", "\\'")
            self.viewport().setStyleSheet(
                "QWidget#ConversationViewport { background: transparent; "
                f"border-image: url('{image}') 0 0 0 0 stretch stretch; }}"
            )

        self.content = QWidget()
        self.content.setObjectName("ConversationContent")
        if background is not None and background.is_file():
            self.content.setStyleSheet("QWidget#ConversationContent { background: transparent; }")
        self.messages = QVBoxLayout(self.content)
        self.messages.setContentsMargins(18, 20, 18, 20)
        self.messages.setSpacing(16)
        # Keep short conversations next to the composer; once the transcript is
        # taller than the viewport, normal scrolling still exposes older rows.
        self.messages.setAlignment(Qt.AlignmentFlag.AlignBottom)
        self.setWidget(self.content)
        self._bubbles: list[QLabel] = []
        self._last_message_date: date | None = None
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._finish_scroll_to_bottom)
        self._can_load_older = False
        self._top_request_ready = False

    def clear(self) -> None:
        self._scroll_timer.stop()
        self._top_request_ready = False
        while self.messages.count():
            item = self.messages.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._bubbles.clear()
        self._last_message_date = None

    def append_message(
        self,
        role: str,
        text: str,
        replay_key: str = "",
        retry_text: str = "",
        created_at: str = "",
        *,
        auto_scroll: bool = True,
    ) -> None:
        if auto_scroll:
            # Layout changes can temporarily leave the old scroll value near the
            # top. Disarm pagination before adding the row so that automatic
            # bottom scrolling can never look like a user history request.
            self._top_request_ready = False
        moment = stored_as_computer_local(created_at) if created_at else None
        if moment is None:
            moment = computer_local_now().astimezone()
        if moment.date() != self._last_message_date:
            separator = QLabel(_chat_date_label(moment), self.content)
            separator.setObjectName("ChatDateSeparator")
            separator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.messages.addWidget(separator)
            self._last_message_date = moment.date()

        row = QWidget(self.content)
        row.setObjectName("ChatMessageRow")
        row.setProperty("messageRole", role)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        bubble = QLabel(text)
        bubble.setObjectName("ChatBubble")
        bubble.setProperty("messageRole", role)
        bubble.setTextFormat(Qt.TextFormat.PlainText)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setWordWrap(True)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        message_font = bubble.font()
        message_font.setFamilies([
            "Segoe UI Symbol",
            "Yu Gothic UI",
            "Microsoft JhengHei UI",
            "Noto Sans Symbols 2",
            "sans-serif",
        ])
        bubble.setFont(message_font)
        self._bubbles.append(bubble)
        timestamp = QLabel(moment.strftime("%H:%M"))
        timestamp.setObjectName("ChatTimestamp")

        if role == "user":
            layout.addStretch(1)
            stack = QVBoxLayout()
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(3)
            stack.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
            stack.addWidget(timestamp, 0, Qt.AlignmentFlag.AlignRight)
            layout.addLayout(stack)
        elif role == "assistant":
            avatar = QLabel()
            avatar.setObjectName("MessageAvatar")
            avatar.setFixedSize(42, 42)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if self.avatar is not None and not self.avatar.isNull():
                avatar.setProperty("hasAvatarImage", "true")
                avatar.setPixmap(_round_pixmap(self.avatar, 42))
            else:
                avatar.setProperty("hasAvatarImage", "false")
                avatar.setText(self.display_name[:1])

            stack = QVBoxLayout()
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(5)
            name = QLabel(self.display_name)
            name.setObjectName("MessageAuthor")
            stack.addWidget(name, 0, Qt.AlignmentFlag.AlignLeft)
            stack.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
            stack.addWidget(timestamp, 0, Qt.AlignmentFlag.AlignLeft)
            if replay_key:
                replay = QPushButton(f"▶ {tr('重播語音')}")
                replay.setObjectName("ReplayVoiceButton")
                replay.clicked.connect(
                    lambda _checked=False, key=replay_key: self.replay_requested.emit(key)
                )
                stack.addWidget(replay, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignTop)
            layout.addLayout(stack)
            layout.addStretch(1)
        else:
            layout.addStretch(1)
            stack = QVBoxLayout()
            stack.addWidget(bubble, 0, Qt.AlignmentFlag.AlignCenter)
            stack.addWidget(timestamp, 0, Qt.AlignmentFlag.AlignCenter)
            if retry_text:
                retry = QPushButton(f"↻ {tr('重新傳送')}")
                retry.setObjectName("RetryMessageButton")
                retry.clicked.connect(
                    lambda _checked=False, value=retry_text: self.retry_requested.emit(value)
                )
                stack.addWidget(retry, 0, Qt.AlignmentFlag.AlignCenter)
            layout.addLayout(stack)
            layout.addStretch(1)

        self.messages.addWidget(row)
        self._update_bubble_widths()
        self.messages.activate()
        self.content.adjustSize()

        if auto_scroll:
            self.ensureWidgetVisible(row, 0, 0)
            self.scroll_to_bottom_later()

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _finish_scroll_to_bottom(self) -> None:
        self._scroll_to_bottom()
        self._top_request_ready = True

    def scroll_to_bottom_later(self) -> None:
        self._top_request_ready = False
        self._scroll_to_bottom()
        self._scroll_timer.start(40)

    def set_can_load_older(self, enabled: bool) -> None:
        self._can_load_older = bool(enabled)

    def restore_after_prepend(self, previous_maximum: int, previous_value: int) -> None:
        self._top_request_ready = False

        def restore() -> None:
            bar = self.verticalScrollBar()
            added_height = max(0, bar.maximum() - previous_maximum)
            bar.setValue(previous_value + added_height)
            self._top_request_ready = True

        QTimer.singleShot(40, restore)

    def _request_older_near_top(self, value: int) -> None:
        bar = self.verticalScrollBar()
        upper_third = bar.minimum() + (bar.maximum() - bar.minimum()) // 3
        if (
            self._can_load_older
            and self._top_request_ready
            and bar.maximum() > bar.minimum()
            and value <= upper_third
        ):
            self._top_request_ready = False
            self.older_history_requested.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        super().wheelEvent(event)
        # Pagination responds only to deliberate user scrolling. Scroll values
        # also change during relayout and automatic bottom positioning.
        self._request_older_near_top(self.verticalScrollBar().value())

    def _update_bubble_widths(self) -> None:
        maximum = max(190, int(self.viewport().width() * 0.72))
        for bubble in self._bubbles:
            bubble.setMaximumWidth(maximum)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_bubble_widths()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # History is populated while its parent window is still hidden, when the
        # scroll range is usually zero. Retry after the first visible layout pass.
        self.scroll_to_bottom_later()


class IdolChatWindow(QWidget):
    """A top-level conversation window whose identity never changes with outfits."""

    send_requested = Signal(str, str)
    record_requested = Signal(str)
    tts_changed = Signal(bool)
    debug_changed = Signal(bool)
    replay_requested = Signal(str, str)
    retry_message_requested = Signal(str, str)
    older_history_requested = Signal(str, int)

    def __init__(
        self,
        character_id: str,
        display_name: str,
        *,
        avatar: Path | None = None,
        background: Path | None = None,
        app_icon: QIcon | None = None,
        tts_enabled: bool = False,
        debug_enabled: bool = False,
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.character_id = character_id
        self.display_name = display_name
        self._history_messages: list[Message] = []
        self._replay_available: Callable[[str], bool] | None = None
        self._has_older_history = False
        self.setObjectName("IdolChatWindow")
        self.setWindowTitle(f"{display_name} — {tr('聊天室')}")
        self.resize(430, 720)
        self.setMinimumSize(360, 540)
        if app_icon is not None:
            self.setWindowIcon(app_icon)

        avatar_pixmap = QPixmap(str(avatar)) if avatar is not None and avatar.is_file() else None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QWidget(self)
        header.setObjectName("ChatHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(14, 11, 18, 11)
        header_row.setSpacing(11)

        close = QPushButton("‹")
        close.setObjectName("ChatBackButton")
        close.setAccessibleName(tr("關閉聊天室"))
        close.setFixedSize(36, 44)
        close.clicked.connect(self.close)
        portrait = QLabel()
        portrait.setObjectName("ChatAvatar")
        portrait.setFixedSize(46, 46)
        portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if avatar_pixmap is not None and not avatar_pixmap.isNull():
            portrait.setProperty("hasAvatarImage", "true")
            portrait.setPixmap(_round_pixmap(avatar_pixmap, 46))
        else:
            portrait.setProperty("hasAvatarImage", "false")
            portrait.setText(display_name[:1])
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel(display_name)
        title.setObjectName("ChatPersonName")
        self.status = QLabel(f"●  {tr('線上')}")
        self.status.setObjectName("ChatStatus")
        title_box.addWidget(title)
        title_box.addWidget(self.status)
        header_row.addWidget(close)
        header_row.addWidget(portrait)
        header_row.addLayout(title_box)
        header_row.addStretch()
        settings_button = QToolButton()
        settings_button.setObjectName("ChatSettingsButton")
        settings_button.setText("☰")
        settings_button.setAccessibleName(tr("聊天室設定"))
        settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        settings_menu = QMenu(settings_button)
        self.tts_toggle: QAction = settings_menu.addAction(tr("開啟語音回覆"))
        self.tts_toggle.setCheckable(True)
        self.tts_toggle.setChecked(tts_enabled)
        self.tts_toggle.toggled.connect(self.tts_changed)
        self.debug_toggle: QAction = settings_menu.addAction(tr("開啟除錯模式"))
        self.debug_toggle.setCheckable(True)
        self.debug_toggle.setChecked(debug_enabled)
        self.debug_toggle.toggled.connect(self.debug_changed)
        self.debug_view_action = settings_menu.addAction(tr("查看 LLM 原始內容…"))
        self.debug_view_action.setEnabled(debug_enabled)
        settings_button.setMenu(settings_menu)
        header_row.addWidget(settings_button)
        root.addWidget(header)

        self.history = ConversationView(display_name, avatar_pixmap, background)
        if background is not None and background.is_file():
            background_pixmap = QPixmap(str(background))
            logical_height = 512
            if not background_pixmap.isNull() and background_pixmap.height() > 0:
                logical_width = max(1, round(
                    logical_height * background_pixmap.width() / background_pixmap.height()
                ))
                self.history.setFixedSize(logical_width, logical_height)
        self.history.replay_requested.connect(
            lambda key: self.replay_requested.emit(self.character_id, key)
        )
        self.history.retry_requested.connect(
            lambda text: self.retry_message_requested.emit(self.character_id, text)
        )
        self.history.older_history_requested.connect(self._request_older_history)
        root.addWidget(self.history, 1)

        controls = QWidget(self)
        controls.setObjectName("ChatControls")
        controls_box = QVBoxLayout(controls)
        controls_box.setContentsMargins(14, 8, 14, 13)
        controls_box.setSpacing(8)
        self.debug_output = QTextEdit()
        self.debug_output.setWindowFlag(Qt.WindowType.Tool, True)
        self.debug_output.setObjectName("ChatDebugOutput")
        self.debug_output.setWindowTitle(f"{display_name} — {tr('LLM 除錯')}")
        self.debug_output.setReadOnly(True)
        self.debug_output.resize(760, 560)
        self.debug_output.setStyleSheet(
            "QTextEdit { background: #20252b; color: #d8f3f8; border: 1px solid #38434d; "
            "font-family: Consolas; font-size: 11px; padding: 7px; }"
        )
        self.debug_toggle.toggled.connect(self.debug_output.setVisible)
        self.debug_toggle.toggled.connect(self.debug_view_action.setEnabled)
        self.debug_view_action.triggered.connect(self.debug_output.show)
        if debug_enabled:
            self.debug_output.show()
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._microphone_icon = _chat_icon("microphone", "#458391")
        self._stop_icon = _chat_icon("stop", "#c95f66")
        self.record = QPushButton()
        self.record.setObjectName("ChatVoiceButton")
        self.record.setIcon(self._microphone_icon)
        self.record.setIconSize(QSize(22, 22))
        self.record.setFixedWidth(42)
        self.record.setAccessibleName(tr("語音輸入"))
        self.record.setToolTip(tr("語音輸入"))
        self.record.clicked.connect(lambda: self.record_requested.emit(self.character_id))
        self.input = QLineEdit()
        self.input.setObjectName("ChatMessageInput")
        self.input.setPlaceholderText(tr("輸入訊息…"))
        self.input.returnPressed.connect(self.submit)
        self.send_button = QPushButton()
        self.send_button.setObjectName("ChatSendButton")
        self.send_button.setIcon(_chat_icon("send", "#ffffff"))
        self.send_button.setIconSize(QSize(22, 22))
        self.send_button.setFixedWidth(44)
        self.send_button.setAccessibleName(tr("傳送訊息"))
        self.send_button.setToolTip(tr("傳送訊息"))
        self.send_button.clicked.connect(self.submit)
        input_row.addWidget(self.record)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_button)
        controls_box.addLayout(input_row)
        root.addWidget(controls)

        self.setStyleSheet("""
            QWidget#IdolChatWindow { background: #fff9dc; color: #3c4650; }
            QWidget#ChatHeader { background: #73d5e7; border-bottom: 1px solid #65c6da; }
            QPushButton#ChatBackButton { border: 0; background: transparent; color: white;
                font-size: 38px; font-weight: 500; padding: 0; }
            QPushButton#ChatBackButton:hover { color: #e9fbff; }
            QToolButton#ChatSettingsButton { border: 0; background: transparent; color: white;
                font-size: 23px; font-weight: 700; padding: 6px 9px; }
            QLabel#ChatAvatar, QLabel#MessageAvatar { background: transparent; border: 0;
                color: #279fc8; font-size: 18px; font-weight: 800; }
            QLabel#ChatAvatar[hasAvatarImage="false"],
            QLabel#MessageAvatar[hasAvatarImage="false"] { background: white;
                border: 2px solid rgba(255,255,255,0.9); border-radius: 23px; }
            QLabel#MessageAvatar[hasAvatarImage="false"] { border-radius: 21px; }
            QLabel#ChatPersonName { color: white; font-size: 17px; font-weight: 800; }
            QLabel#ChatStatus { color: #eaffff; font-size: 11px; }
            QScrollArea#Conversation { background: #fff9dc; border: 0; }
            QWidget#ConversationViewport { background-color: #fff9dc; }
            QWidget#ConversationContent { background-color: #fff9dc; }
            QLabel#MessageAuthor { color: #59616a; font-size: 12px; font-weight: 700; }
            QLabel#ChatTimestamp { color: #9a9585; font-size: 10px; padding: 0 3px; }
            QLabel#ChatDateSeparator { color: #8b856f; font-size: 11px; font-weight: 700;
                background: rgba(255,255,255,0.72); border-radius: 10px; padding: 4px 11px; }
            QLabel#ChatBubble { padding: 10px 13px; border-radius: 16px;
                font-size: 14px; }
            QLabel#ChatBubble[messageRole="user"] { background: #73d5e7; color: #253f49;
                border-bottom-right-radius: 5px; }
            QLabel#ChatBubble[messageRole="assistant"] { background: white; color: #3c4650;
                border: 1px solid #e3ddc4; border-bottom-left-radius: 5px; }
            QLabel#ChatBubble[messageRole="system"] { background: rgba(113,105,83,0.12);
                color: #827b69; padding: 6px 11px; font-size: 12px; }
            QWidget#ChatControls { background: rgba(255,255,255,0.97);
                border-top: 1px solid #e9e2c9; }
            QLineEdit#ChatMessageInput { min-height: 40px; background: #f8f8f8;
                border: 1px solid #dedede; border-radius: 20px; padding: 0 14px;
                selection-background-color: #73d5e7; }
            QLineEdit#ChatMessageInput:focus { border: 1px solid #73d5e7; }
            QPushButton#ChatSendButton { min-height: 40px; padding: 0;
                border: 0; border-radius: 20px; background: #73d5e7; color: white;
                font-weight: 800; }
            QPushButton#ChatSendButton:hover { background: #5cc9dd; }
            QPushButton#ChatVoiceButton { min-height: 38px; border: 1px solid #c9e5ea;
                border-radius: 19px; background: white; padding: 0; color: #458391; }
            QPushButton#ChatVoiceButton:hover { background: #effbfc; }
            QPushButton#ReplayVoiceButton { border: 0; background: transparent;
                color: #458391; font-size: 12px; padding: 2px 4px; }
            QPushButton#RetryMessageButton { border: 1px solid #d2b7a9;
                border-radius: 12px; background: white; color: #9a5f48; padding: 4px 10px; }
            QCheckBox { color: #77766f; spacing: 8px; font-size: 12px; }
            QTextEdit#ChatDebugOutput { background: #20252b; color: #d8f3f8;
                border: 1px solid #38434d; border-radius: 8px; font-family: Consolas;
                font-size: 11px; padding: 7px; }
        """)
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.send_requested.emit(self.character_id, text)

    def load_history(
        self,
        messages: list[Message],
        replay_available: Callable[[str], bool] | None = None,
        *,
        has_older: bool = False,
    ) -> None:
        self._history_messages = list(messages)
        self._replay_available = replay_available
        self._has_older_history = has_older
        self._render_history()
        self.history.set_can_load_older(has_older)
        self.history.scroll_to_bottom_later()

    def load_older_history(self, messages: list[Message], *, has_older: bool) -> None:
        bar = self.history.verticalScrollBar()
        previous_maximum = bar.maximum()
        previous_value = bar.value()
        self._history_messages = list(messages)
        self._has_older_history = has_older
        self._render_history()
        self.history.set_can_load_older(has_older)
        self.history.restore_after_prepend(previous_maximum, previous_value)

    def _render_history(self) -> None:
        self.history.clear()
        for message in self._history_messages:
            replay_key = message.voice_cache_key
            if (
                replay_key
                and self._replay_available is not None
                and not self._replay_available(replay_key)
            ):
                replay_key = ""
            self.history.append_message(
                message.role,
                message.content,
                replay_key,
                created_at=message.scheduled_for or message.created_at,
                auto_scroll=False,
            )

    def _request_older_history(self) -> None:
        if self._has_older_history:
            self.older_history_requested.emit(self.character_id, len(self._history_messages))

    def append_message(
        self, role: str, content: str, replay_key: str = "", created_at: str = ""
    ) -> None:
        self.history.append_message(role, content, replay_key, created_at=created_at)

    def append_retry_error(self, content: str, original_text: str) -> None:
        self.history.append_message("system", content, retry_text=original_text)

    def set_busy(self, busy: bool) -> None:
        self.status.setText(f"●  {tr('回覆中…') if busy else tr('線上')}")
        self.input.setEnabled(not busy)

    def set_voice_preparing(self) -> None:
        self.status.setText(f"●  {tr('正在準備語音…')}")
        self.input.setEnabled(False)

    def show_debug_exchange(self, text: str) -> None:
        self.debug_output.setPlainText(text)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.debug_output.hide()
        super().closeEvent(event)

    def set_recording(self, recording: bool) -> None:
        self.record.setIcon(self._stop_icon if recording else self._microphone_icon)
        label = tr("停止錄音") if recording else tr("語音輸入")
        self.record.setAccessibleName(label)
        self.record.setToolTip(label)


def _chat_date_label(moment: datetime) -> str:
    weekdays = (
        "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"
    )
    return trf(
        "{month}月{day}日 {weekday}",
        month=moment.month,
        day=moment.day,
        weekday=tr(weekdays[moment.weekday()]),
    )
