"""Application composition for desktop pets, chat, integrations, TTS, and ASR."""

# ruff: noqa: E501

from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from shiny_pet.ai import (
    ActionDirective,
    ChatClient,
    LLMConfig,
    OpenAICompatibleClient,
    discover_openai_model,
    discover_openai_models,
)
from shiny_pet.chat import ChatDatabase, ChatResult, ChatService, IdolChatWindow
from shiny_pet.chat_integration import LocalChatIntegrationServer
from shiny_pet.i18n import tr
from shiny_pet.integrations import ExternalMessage, MCPToolRouter
from shiny_pet.oauth_proxy import PROXY_URL, OpenAIOAuthProxyManager
from shiny_pet.reminders import Reminder, ReminderQueue
from shiny_pet.screen_context import VisionScreenContextProvider
from shiny_pet.voice import (
    LOCAL_ASR_MODEL,
    LOCAL_IRODORI_MODEL,
    ASRConfig,
    HttpTTSClient,
    LocalASRInstallCancelled,
    LocalIrodoriInstallCancelled,
    LocalIrodoriTTSServer,
    LocalWhisperASRServer,
    OpenAIASRClient,
    PlatformAudioPlayer,
    SoundDeviceRecorder,
    TTSConfig,
    VoiceCache,
    VoiceCoordinator,
    irodori_emotion_caption,
    irodori_voice_id,
    is_connection_reset_error,
    test_input_device,
)

from .desktop_panel import DesktopControlPanel
from .desktop_panel import main as run_desktop_panel
from .pages import install_settings_pages


class _Signals(QObject):
    reply = Signal(str, object)
    chat_error = Signal(str, str)
    error = Signal(str)
    mouth = Signal(str, float, float)
    transcript = Signal(str, str)
    recording_finished = Signal(str)
    tts_started = Signal(object)
    tts_finished = Signal(object, bool, str)
    tts_install_progress = Signal(str)
    tts_installed = Signal(str)
    tts_install_error = Signal(str)
    external_chat = Signal(str, str)
    oauth_status = Signal(str, object)
    restore_wait = Signal(str)
    asr_install_progress = Signal(str)
    asr_installed = Signal(str)
    asr_install_error = Signal(str)
    microphone_tested = Signal(object)
    microphone_test_error = Signal(str)
    asr_cpu_fallback = Signal()


@dataclass(slots=True)
class _PendingSpokenReply:
    character_id: str
    text: str
    created_at: str = ""
    revealed: threading.Event = field(default_factory=threading.Event)
    displayed: bool = False
    cache_key: str = ""


class CompanionControlPanel(DesktopControlPanel):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        db_path = self.store.path.with_name("chat.sqlite3")
        self.chat_database = ChatDatabase(db_path)
        self.chat_cancels: dict[str, threading.Event] = {}
        self.pending_chat_messages: dict[str, str] = {}
        self.pending_chat_created_at: dict[str, str] = {}
        self.processed_pending_chats: set[str] = set()
        self.voice_cancel = threading.Event()
        self.record_cancel = threading.Event()
        self.asr_cancel = threading.Event()
        self._recording = False
        self._recording_character = ""
        self.chat_windows: dict[str, IdolChatWindow] = {}
        self._character_pet: dict[str, str] = {}
        self.chat_integration_server: LocalChatIntegrationServer | None = None
        self.oauth_proxy = OpenAIOAuthProxyManager(
            self.store.path.parent / "openai-oauth-runtime"
        )
        self._oauth_starting = False
        self.local_irodori_server = LocalIrodoriTTSServer(
            self.store.path.parent / "irodori-runtime"
        )
        self.tts_install_cancel = threading.Event()
        self._tts_install_thread: threading.Thread | None = None
        self.local_asr_server = LocalWhisperASRServer(self.store.path.parent / "asr-runtime")
        self.asr_install_cancel = threading.Event()
        self._asr_install_thread: threading.Thread | None = None
        self._microphone_test_thread: threading.Thread | None = None
        self.voice_cache = VoiceCache(self.store.path.parent / "voice-cache", None)
        self.apply_voice_cache_policy()
        self.reminder_queue = ReminderQueue(self._load_reminders())
        self.signals = _Signals(self)
        self.signals.reply.connect(self._chat_reply)
        self.signals.chat_error.connect(self._chat_error)
        self.signals.error.connect(self.log.append)
        self.signals.mouth.connect(self._mouth)
        self.signals.transcript.connect(self._transcript)
        self.signals.recording_finished.connect(self._recording_finished)
        self.signals.tts_started.connect(self._tts_started)
        self.signals.tts_finished.connect(self._tts_finished)
        self.signals.asr_cpu_fallback.connect(self._persist_asr_cpu_fallback)
        self.signals.external_chat.connect(self._external_chat_request)
        self.signals.restore_wait.connect(self._restore_pet_wait)
        install_settings_pages(self)
        self.configure_chat_integration()
        self.reminder_timer = QTimer(self)
        self.reminder_timer.setInterval(30_000)
        self.reminder_timer.timeout.connect(self._check_reminders)
        self.reminder_timer.start()

    def apply_voice_cache_policy(self) -> None:
        """Apply the persisted voice-cache policy immediately."""
        mode = str(self.settings.get("voice_cache_cleanup_mode", "on_exit"))
        if mode == "size_limit":
            gibibytes = float(self.settings.get("voice_cache_max_gb", 2.0))
            self.voice_cache.configure(max(1, int(gibibytes * 1024**3)))
        else:
            self.voice_cache.configure(None)

    def _set_tts_enabled(self, enabled: bool) -> None:
        self.settings["tts_enabled"] = enabled
        for window in self.chat_windows.values():
            if window.tts_toggle.isChecked() != enabled:
                window.tts_toggle.setChecked(enabled)
        self.persist()
        if not enabled:
            self.voice_cancel.set()
            self.local_irodori_server.stop()

    def install_local_irodori(self) -> None:
        """Install the managed Irodori server without blocking the settings window."""
        if self._tts_install_thread is not None and self._tts_install_thread.is_alive():
            return
        self.tts_install_cancel = threading.Event()
        reference_root = Path(str(self.settings.get("tts_reference_root", "audio_reference")))

        def run() -> None:
            try:
                url = self.local_irodori_server.install(
                    reference_root,
                    self.tts_install_cancel,
                    self.signals.tts_install_progress.emit,
                )
                if not self.tts_install_cancel.is_set():
                    self.signals.tts_installed.emit(url)
            except LocalIrodoriInstallCancelled:
                return
            except Exception as exc:
                self.signals.tts_install_error.emit(str(exc))

        self._tts_install_thread = threading.Thread(
            target=run, name="shiny-irodori-install", daemon=True
        )
        self._tts_install_thread.start()

    def _set_chat_debug_enabled(self, enabled: bool) -> None:
        self.settings["chat_debug_enabled"] = enabled
        for window in self.chat_windows.values():
            if window.debug_toggle.isChecked() != enabled:
                window.debug_toggle.setChecked(enabled)
        self.guard(self.persist)

    def _load_reminders(self) -> list[Reminder]:
        result: list[Reminder] = []
        for item in self.settings.get("reminders", []):
            if not isinstance(item, dict):
                continue
            try:
                repeat = tuple(day for day in item.get("repeat_days", [])
                               if type(day) is int and 0 <= day <= 6)
                result.append(Reminder(str(item["id"]), str(item["text"]),
                    datetime.fromisoformat(str(item["at"])), repeat,
                    str(item.get("character", "")), bool(item.get("enabled", True)),
                    str(item.get("last_triggered", ""))))
            except (KeyError, TypeError, ValueError):
                self.log.append("已略過格式錯誤的提醒。")
        return result

    def save_reminders(self) -> None:
        self.settings["reminders"] = [
            {
                "id": item.id,
                "text": item.text,
                "at": item.at.isoformat(timespec="minutes"),
                "repeat_days": list(item.repeat_days),
                "character": item.character,
                "enabled": item.enabled,
                "last_triggered": item.last_triggered,
            }
            for item in self.reminder_queue.reminders
        ]
        self.guard(self.persist)

    def relationship_user_key(self) -> str:
        return "default"

    def _check_reminders(self) -> None:
        due = self.reminder_queue.due(datetime.now())
        for reminder in due:
            self.deliver_reminder(reminder)
        if due:
            self.save_reminders()

    def deliver_reminder(self, reminder: Reminder) -> None:
        window = self.chat_windows.get(reminder.character)
        if window is not None:
            window.append_message("system", f"提醒：{reminder.text}")
        if self.tray.isVisible():
            self.tray.showMessage("ShinyColorsPet 提醒", reminder.text)
        pet_id = self._resolve_pet_for_character(reminder.character)
        if pet_id:
            self.manager.semantic(pet_id, "gesture", "greeting")
            if bool(self.settings.get("tts_enabled", False)):
                self._speak(pet_id, reminder.character, reminder.text,
                            f"提醒：{reminder.text}")

    def _chat_identity(self, pet_id: str) -> tuple[str, str, Path | None, Path | None]:
        worker = self.manager.workers.get(pet_id)
        if worker is None:
            raise ValueError("找不到要開啟聊天室的桌面人物。")
        character_id = str(worker.spec.get("character_id", "")).strip()
        character = self.runtime_catalog.characters.get(character_id)
        if character is None:
            # Manually registered models remain usable and are isolated by pet id.
            return pet_id, Path(str(worker.spec.get("path", pet_id))).stem, None, None
        name = self.runtime_catalog.label(character.name_key)
        avatar = self.runtime_catalog.asset_path(character.ui_assets.get("chat_icon"))
        background = self.runtime_catalog.asset_path(character.ui_assets.get("chat_background"))
        return character_id, name, avatar, background

    def open_chat_for_pet(self, pet_id: str) -> None:
        try:
            character_id, name, avatar, background = self._chat_identity(pet_id)
        except ValueError as exc:
            self.log.append(str(exc))
            return
        self._character_pet[character_id] = pet_id
        window = self.chat_windows.get(character_id)
        if window is None:
            window = IdolChatWindow(
                character_id,
                name,
                avatar=avatar,
                background=background,
                app_icon=self.app_icon,
                tts_enabled=bool(self.settings.get("tts_enabled", False)),
                debug_enabled=bool(self.settings.get("chat_debug_enabled", False)),
            )
            window.load_history(self.chat_database.history(
                character_id, int(self.settings.get("chat_history_limit", 24))
            ))
            window.send_requested.connect(self.send_chat)
            window.record_requested.connect(self.toggle_recording)
            window.tts_changed.connect(self._set_tts_enabled)
            window.debug_changed.connect(self._set_chat_debug_enabled)
            window.replay_requested.connect(self._replay_voice)
            window.retry_message_requested.connect(self._retry_chat)
            self.chat_windows[character_id] = window
        self.apply_chat_window_preferences(window)
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def apply_chat_window_preferences(self, target: IdolChatWindow | None = None) -> None:
        windows = [target] if target is not None else list(self.chat_windows.values())
        width = max(360, int(self.settings.get("chat_window_width", 430)))
        height = max(540, int(self.settings.get("chat_window_height", 720)))
        topmost = bool(self.settings.get("chat_window_topmost", False))
        for window in windows:
            window.resize(width, height)
            window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, topmost)

    def _selected_worker(self) -> tuple[str, Any] | None:
        pet_id = self.selected()
        if not pet_id:
            self.log.append("請先選擇一隻已啟動的寵物。")
            return None
        worker = self.manager.workers[pet_id]
        if worker.state != "ready":
            self.log.append("選取的寵物尚未 ready。")
            return None
        return pet_id, worker

    def _resolve_pet_for_character(self, character_id: str) -> str:
        existing = self._character_pet.get(character_id, "")
        if existing in self.manager.workers:
            return existing
        for pet_id, worker in self.manager.workers.items():
            if str(worker.spec.get("character_id", "")).strip() == character_id:
                self._character_pet[character_id] = pet_id
                return pet_id
        return ""

    def configure_chat_integration(self) -> None:
        if self.chat_integration_server is not None:
            self.chat_integration_server.stop()
            self.chat_integration_server = None
        if not bool(self.settings.get("chat_integration_enabled", False)):
            self.log.append("本機聊天接入未啟用。")
            return
        token = str(self.settings.get("chat_integration_token", "")).strip()
        if not token:
            token = secrets.token_urlsafe(32)
            self.settings["chat_integration_token"] = token
            self.guard(self.persist)

        def receive(message: ExternalMessage) -> dict[str, Any]:
            self.signals.external_chat.emit(message.character, message.text.strip())
            return {"accepted": True, "character": message.character}

        try:
            server = LocalChatIntegrationServer(
                str(self.settings.get("chat_integration_host", "127.0.0.1")),
                int(self.settings.get("chat_integration_port", 17384)), token, receive,
            )
            server.start()
        except (OSError, RuntimeError, ValueError) as exc:
            self.log.append("聊天接入啟動失敗：" + str(exc))
            return
        self.chat_integration_server = server
        display_host = f"[{server.host}]" if ":" in server.host else server.host
        self.log.append(
            f"聊天接入已啟動：http://{display_host}:{server.port}/v1/chat/messages"
        )

    def _external_chat_request(self, character_id: str, text: str) -> None:
        pet_id = self._resolve_pet_for_character(character_id)
        if not pet_id:
            return
        self.open_chat_for_pet(pet_id)
        self.send_chat(character_id, text)

    def start_openai_oauth(self) -> None:
        if self._oauth_starting:
            self.signals.oauth_status.emit("openai-oauth 正在設定中，請稍候。", ())
            return
        if not bool(self.settings.get("openai_oauth_personal_use_accepted", False)):
            self.signals.oauth_status.emit("必須先確認僅使用本人帳號並接受免責聲明。", ())
            return
        self._oauth_starting = True

        def progress(message: str) -> None:
            self.signals.oauth_status.emit(message, ())

        def run() -> None:
            try:
                models = self.oauth_proxy.ensure_and_start(progress)
            except (OSError, RuntimeError, ValueError) as exc:
                self.signals.oauth_status.emit("openai-oauth 啟動失敗：" + str(exc), ())
            else:
                self.signals.oauth_status.emit(
                    f"openai-oauth 已在本機啟動；找到 {len(models)} 個聊天模型。", models
                )
            finally:
                self._oauth_starting = False

        threading.Thread(target=run, name="shiny-openai-oauth", daemon=True).start()

    def stop_openai_oauth(self) -> None:
        def run() -> None:
            self.oauth_proxy.stop()
            self.signals.oauth_status.emit("openai-oauth 本機服務已停止。", ())

        threading.Thread(target=run, name="shiny-openai-oauth-stop", daemon=True).start()

    def refresh_openai_oauth_models(self) -> None:
        def run() -> None:
            models = discover_openai_models(PROXY_URL)
            if models:
                self.signals.oauth_status.emit(
                    f"已從本機服務取得 {len(models)} 個聊天模型。", models
                )
            else:
                self.signals.oauth_status.emit(
                    "無法取得模型清單；請確認 openai-oauth 服務仍在執行。", ()
                )

        threading.Thread(target=run, name="shiny-openai-oauth-models", daemon=True).start()

    def _llm_client(self) -> ChatClient:
        url = str(self.settings.get("llm_api_url") or os.getenv("SHINY_PET_API_URL", ""))
        model = str(self.settings.get("llm_model") or os.getenv("SHINY_PET_MODEL", ""))
        key = str(self.settings.get("llm_api_key") or os.getenv("SHINY_PET_API_KEY", ""))
        provider = str(self.settings.get("llm_provider", "openai_compatible"))
        if provider == "openai_oauth_proxy":
            url = url or PROXY_URL
            model = model or discover_openai_model(url)
        if not url or not model:
            raise ValueError(
                "請設定 OpenAI 相容 API URL 與模型。"
            )
        config = LLMConfig(
            url, model, key, timeout_seconds=float(self.settings["llm_timeout_seconds"]),
            temperature=float(self.settings["llm_temperature"]),
            max_tokens=int(self.settings["llm_max_tokens"]),
        )
        return OpenAICompatibleClient(config)

    def send_chat(self, character_id: str, text: str, *, retry: bool = False) -> None:
        window = self.chat_windows.get(character_id)
        pet_id = self._resolve_pet_for_character(character_id)
        worker = self.manager.workers.get(pet_id)
        if window is None or worker is None or worker.state != "ready" or not text.strip():
            if window is not None:
                window.append_message("system", "此偶像目前不在桌面上，請先載入人物。")
            return
        value = text.strip()
        if not retry:
            message = self.chat_database.add_message(character_id, "user", value)
            self.pending_chat_created_at[character_id] = message.created_at
            window.append_message("user", value, created_at=message.created_at)
            self.processed_pending_chats.discard(character_id)
        self.pending_chat_messages[character_id] = value
        window.set_busy(True)
        try:
            client = self._llm_client()
        except ValueError as exc:
            self._chat_error(character_id, str(exc))
            return
        previous = self.chat_cancels.get(character_id)
        if previous is not None:
            previous.set()
        cancel = threading.Event()
        self.chat_cancels[character_id] = cancel
        screen = (VisionScreenContextProvider(client, self.settings, cancel)
                  if self.settings.get("screen_awareness_enabled", False) else None)
        servers = self.settings.get("mcp_servers", [])
        tools = MCPToolRouter(servers) if isinstance(servers, list) and servers else None
        service = ChatService(self.chat_database, client, self.settings, screen, tools)
        process_interaction = character_id not in self.processed_pending_chats
        self.processed_pending_chats.add(character_id)

        def run() -> None:
            try:
                result = service.send(character_id, value,
                    actions=set(worker.semantic_actions),
                    expressions=set(worker.semantic_expressions), cancel=cancel,
                    persist_user_message=False, process_user_interaction=process_interaction,
                    user_created_at=self.pending_chat_created_at.get(character_id, ""))
                self.signals.reply.emit(character_id, result)
            except (OSError, RuntimeError, ValueError) as exc:
                if not cancel.is_set():
                    self.signals.chat_error.emit(character_id, str(exc))

        threading.Thread(target=run, name="shiny-chat", daemon=True).start()

    def _chat_error(self, character_id: str, message: str) -> None:
        window = self.chat_windows.get(character_id)
        if window is not None:
            window.set_busy(False)
            original = self.pending_chat_messages.get(character_id, "")
            if original:
                window.append_retry_error(message, original)
            else:
                window.append_message("system", message)
        self.log.append(message)

    def _retry_chat(self, character_id: str, text: str) -> None:
        if self.pending_chat_messages.get(character_id) == text:
            self.send_chat(character_id, text, retry=True)

    def _chat_reply(self, character_id: str, result: ChatResult) -> None:
        window = self.chat_windows.get(character_id)
        if window is None:
            return
        pending_messages = getattr(self, "pending_chat_messages", None)
        if isinstance(pending_messages, dict):
            pending_messages.pop(character_id, None)
        self.pending_chat_created_at.pop(character_id, None)
        processed = getattr(self, "processed_pending_chats", None)
        if isinstance(processed, set):
            processed.discard(character_id)
        if result.debug_exchanges:
            sections: list[str] = []
            for index, (request, response) in enumerate(result.debug_exchanges, 1):
                sections.append(
                    f"===== REQUEST {index} =====\n"
                    + json.dumps(request, ensure_ascii=False, indent=2)
                    + f"\n\n===== RESPONSE {index} =====\n{response}"
                )
            window.show_debug_exchange("\n\n".join(sections))
        pet_id = self._character_pet.get(character_id, "")
        for directive in result.directives:
            command = "expression" if directive.kind == "expression" else "gesture"
            if pet_id:
                self.manager.semantic(pet_id, command, directive.key)
        if result.unknown:
            self.log.append("已忽略未知 AI 動作鍵：" + ", ".join(result.unknown))
        tts_environment = os.getenv("SHINY_PET_TTS_ENABLED", "").lower()
        tts_enabled = (
            window.tts_toggle.isChecked()
            or tts_environment in {"1", "true", "yes", "on"}
        )
        if tts_enabled:
            if result.speech_text:
                if self._speak(
                    pet_id,
                    character_id,
                    result.speech_text,
                    result.text,
                    result.directives,
                    result.created_at,
                ):
                    window.set_voice_preparing()
                    return
            else:
                self.log.append(tr(
                    "AI 回覆缺少有效日文；本次不朗讀，介面語言內容仍保留。"
                ))
        window.set_busy(False)
        window.append_message("assistant", result.text, created_at=result.created_at)

    def _speak(
        self,
        pet_id: str,
        character_id: str,
        text: str,
        visible_text: str,
        directives: tuple[ActionDirective, ...] = (),
        created_at: str = "",
    ) -> bool:
        provider = str(self.settings.get("tts_provider", "irodori_local"))
        use_local_irodori = provider == "irodori_local"
        if use_local_irodori:
            url = self.local_irodori_server.api_url
        else:
            url = str(self.settings.get("tts_api_url", ""))
        if not url:
            self.log.append("TTS 已啟用，但尚未設定 API URL。")
            return False
        self.voice_cancel.set()
        self.voice_cancel = threading.Event()
        pending = _PendingSpokenReply(character_id, visible_text, created_at)
        model = (
            LOCAL_IRODORI_MODEL
            if use_local_irodori
            else str(self.settings.get("tts_model", "tts-1"))
        )
        configured_voice = str(self.settings.get("tts_voice", ""))
        is_irodori = model.strip().casefold() == "irodori-tts"
        voice = irodori_voice_id(character_id, configured_voice) if is_irodori else configured_voice
        caption = irodori_emotion_caption(directives) if is_irodori else ""
        synth = HttpTTSClient(TTSConfig(
            api_url=url,
            voice=voice,
            api_key=str(self.settings.get("tts_api_key", "")),
            model=model,
            caption=caption,
        ))
        def mouth(openness: float, form: float) -> bool:
            self.signals.mouth.emit(pet_id, openness, form)
            return True

        coordinator = VoiceCoordinator(synth, PlatformAudioPlayer(), mouth)
        coordinator.cancel_event = self.voice_cancel

        def playback_start() -> None:
            self.signals.tts_started.emit(pending)
            # The UI acknowledges on its next event-loop turn, after scheduling a repaint.
            pending.revealed.wait(timeout=2.0)

        def cache_audio(audio: bytes, media_type: str) -> None:
            try:
                pending.cache_key = self.voice_cache.store(audio, media_type)
            except OSError as exc:
                self.signals.error.emit("無法暫存語音：" + str(exc))

        def run() -> None:
            try:
                if use_local_irodori:
                    self.local_irodori_server.ensure_running(
                        Path(str(self.settings.get("tts_reference_root", "audio_reference"))),
                        self.voice_cancel,
                    )
                coordinator.speak(text, self.voice_cancel, playback_start, cache_audio)
            except (OSError, RuntimeError, ValueError) as exc:
                if not self.voice_cancel.is_set():
                    self.signals.error.emit(str(exc))
                self.signals.tts_finished.emit(pending, False, str(exc))
            else:
                self.signals.tts_finished.emit(pending, True, "")

        threading.Thread(target=run, name="shiny-tts", daemon=True).start()
        return True

    def _tts_started(self, pending: _PendingSpokenReply) -> None:
        window = self.chat_windows.get(pending.character_id)
        if window is not None and not pending.displayed:
            window.append_message(
                "assistant", pending.text, pending.cache_key, pending.created_at
            )
            window.set_busy(False)
            pending.displayed = True
        # Let the append/layout event paint before releasing the audio worker.
        QTimer.singleShot(0, pending.revealed.set)

    def _tts_finished(
        self,
        pending: _PendingSpokenReply,
        _succeeded: bool,
        _message: str,
    ) -> None:
        if pending.displayed:
            restore = getattr(self, "_restore_pet_wait", None)
            if callable(restore):
                restore(pending.character_id)
            return
        window = self.chat_windows.get(pending.character_id)
        if window is not None:
            window.append_message(
                "assistant", pending.text, pending.cache_key, pending.created_at
            )
            window.set_busy(False)
            pending.displayed = True
        pending.revealed.set()
        restore = getattr(self, "_restore_pet_wait", None)
        if callable(restore):
            restore(pending.character_id)

    def _restore_pet_wait(self, character_id: str) -> None:
        pet_id = self._resolve_pet_for_character(character_id)
        if not pet_id:
            return
        worker = self.manager.workers.get(pet_id)
        if worker is None:
            return
        if "neutral" in worker.semantic_expressions:
            self.manager.semantic(pet_id, "expression", "neutral")
        if "idle" in worker.semantic_actions:
            self.manager.semantic(pet_id, "gesture", "idle")

    def _replay_voice(self, character_id: str, cache_key: str) -> None:
        cached = self.voice_cache.load(cache_key)
        pet_id = self._resolve_pet_for_character(character_id)
        if cached is None or not pet_id:
            window = self.chat_windows.get(character_id)
            if window is not None:
                window.append_message("system", "暫存語音已不存在，無法重播。")
            return
        audio, media_type = cached
        self.voice_cancel.set()
        self.voice_cancel = threading.Event()

        class CachedSynthesizer:
            def synthesize(self, _text: str, _cancel: threading.Event) -> tuple[bytes, str]:
                return audio, media_type

        def mouth(openness: float, form: float) -> bool:
            self.signals.mouth.emit(pet_id, openness, form)
            return True

        coordinator = VoiceCoordinator(CachedSynthesizer(), PlatformAudioPlayer(), mouth)

        def run() -> None:
            try:
                coordinator.speak("replay", self.voice_cancel)
            except (OSError, RuntimeError, ValueError) as exc:
                if not self.voice_cancel.is_set():
                    self.signals.error.emit(str(exc))
            finally:
                self.signals.restore_wait.emit(character_id)

        threading.Thread(target=run, name="shiny-tts-replay", daemon=True).start()

    def _mouth(self, pet_id: str, openness: float, form: float) -> None:
        worker = self.manager.workers.get(pet_id)
        if worker:
            self.manager.send(pet_id, "mouth", openness=openness, form=form)

    def toggle_recording(self, character_id: str) -> None:
        window = self.chat_windows.get(character_id)
        if window is None:
            return
        if self._recording:
            self.record_cancel.set()
            active = self.chat_windows.get(self._recording_character)
            if active is not None:
                active.set_recording(False)
            self._recording = False
            return
        if not self.settings.get("asr_enabled"):
            window.append_message("system", "ASR 尚未啟用。")
            return
        self.record_cancel = threading.Event()
        self.asr_cancel = threading.Event()
        self._recording = True
        self._recording_character = character_id
        window.set_recording(True)

        def run() -> None:
            try:
                audio, media = SoundDeviceRecorder(
                    int(self.settings.get("asr_input_device", -1))
                ).record(self.record_cancel)
                provider = str(self.settings.get("asr_provider", "local_whisper"))
                if provider == "local_whisper":
                    self.local_asr_server.ensure_running(
                        self.asr_cancel,
                        force_cpu=self.settings.get("asr_compute_device") == "cpu",
                    )
                    api_url = self.local_asr_server.api_url
                    model = LOCAL_ASR_MODEL
                else:
                    api_url = str(self.settings.get("asr_api_url", ""))
                    model = str(self.settings.get("asr_model", "whisper-1"))
                config = ASRConfig(api_url,
                    str(self.settings.get("asr_api_key", "")),
                    model, str(self.settings.get("asr_language", "")),
                    float(self.settings.get("asr_timeout_seconds", 600)))
                if self.asr_cancel.is_set():
                    return
                client = OpenAIASRClient(config)
                try:
                    text = client.transcribe(audio, media, self.asr_cancel)
                except RuntimeError as exc:
                    if provider != "local_whisper" or not is_connection_reset_error(exc):
                        raise
                    self.signals.error.emit(
                        "Whisper GPU 程序異常中止，正在自動切換 CPU/int8 並重試一次。"
                    )
                    self.local_asr_server.ensure_running(self.asr_cancel, force_cpu=True)
                    self.signals.asr_cpu_fallback.emit()
                    text = client.transcribe(audio, media, self.asr_cancel)
                self.signals.transcript.emit(character_id, text)
            except (OSError, RuntimeError, ValueError) as exc:
                self.signals.chat_error.emit(character_id, "語音辨識失敗：" + str(exc))
            finally:
                self._recording = False
                self.signals.recording_finished.emit(character_id)

        threading.Thread(target=run, name="shiny-asr", daemon=True).start()

    def _recording_finished(self, character_id: str) -> None:
        window = self.chat_windows.get(character_id)
        if window is not None:
            window.set_recording(False)

    def _transcript(self, character_id: str, text: str) -> None:
        window = self.chat_windows.get(character_id)
        if window is not None:
            window.input.setText(text)
            window.submit()

    def install_local_asr(self) -> None:
        """Install the managed recognizer without blocking the settings window."""
        if self._asr_install_thread is not None and self._asr_install_thread.is_alive():
            return
        self.asr_install_cancel = threading.Event()

        def run() -> None:
            try:
                url = self.local_asr_server.install(
                    self.asr_install_cancel, self.signals.asr_install_progress.emit
                )
                if not self.asr_install_cancel.is_set():
                    self.signals.asr_installed.emit(url)
            except LocalASRInstallCancelled:
                return
            except Exception as exc:
                self.signals.asr_install_error.emit(str(exc))

        self._asr_install_thread = threading.Thread(
            target=run, name="shiny-asr-install", daemon=True
        )
        self._asr_install_thread.start()

    def test_microphone(self, device: int) -> None:
        """Test a selected input device without blocking the settings window."""
        if self._microphone_test_thread is not None and self._microphone_test_thread.is_alive():
            return

        def run() -> None:
            try:
                self.signals.microphone_tested.emit(test_input_device(device))
            except (OSError, RuntimeError, ValueError) as exc:
                self.signals.microphone_test_error.emit(str(exc))

        self._microphone_test_thread = threading.Thread(
            target=run, name="shiny-microphone-test", daemon=True
        )
        self._microphone_test_thread.start()

    def _persist_asr_cpu_fallback(self) -> None:
        self.settings["asr_compute_device"] = "cpu"
        self.guard(self.persist)

    def quit(self) -> None:
        for cancel in self.chat_cancels.values():
            cancel.set()
        self.voice_cancel.set()
        self.record_cancel.set()
        self.asr_cancel.set()
        self.asr_install_cancel.set()
        self.tts_install_cancel.set()
        self.local_asr_server.stop()
        self.local_irodori_server.stop()
        cache_mode = str(self.settings.get("voice_cache_cleanup_mode", "on_exit"))
        if cache_mode == "on_exit":
            self.voice_cache.clear()
        elif cache_mode == "size_limit":
            self.voice_cache.trim()
        if self.chat_integration_server is not None:
            self.chat_integration_server.stop()
            self.chat_integration_server = None
        for window in self.chat_windows.values():
            window.close()
        super().quit()


def main() -> int:
    # Reuse the desktop shell's CLI parser for the composed application.
    return run_desktop_panel(CompanionControlPanel)


if __name__ == "__main__":
    raise SystemExit(main())
