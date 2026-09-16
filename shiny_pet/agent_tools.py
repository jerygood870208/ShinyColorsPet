"""Strict text-tool fallback for reminders, character events, and diary entries."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

_CALL = re.compile(r"\A\s*<agent-tool-call>(.{1,16384})</agent-tool-call>\s*\Z", re.DOTALL)
_DATING = re.compile(r"約會|デート|\b(?:date|dating)\b", re.IGNORECASE)
_SHARED_APPOINTMENT = re.compile(
    r"(?:我們|咱們).{0,60}(?:一起|一塊|去|來|看|吃|玩|約會)|"
    r"(?:跟|和|與)你.{0,40}(?:一起|去|來)|"
    r"(?:私たち|僕たち|俺たち).{0,40}一緒に|あなたと.{0,40}(?:一緒に|行く|来る)|"
    r"\bwe\b.{0,60}\btogether\b|\bwith you\b",
    re.IGNORECASE,
)
_UNCERTAIN = re.compile(
    r"可能|也許|或許|有空|看情況|想要|できたら|かもしれない|"
    r"\b(?:maybe|perhaps|might|if possible)\b",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[月/]\d{1,2}日?|"
    r"今天|明天|後天|今日|明日|明後日|週[一二三四五六日天]|星期[一二三四五六日天]|"
    r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_TIME = re.compile(
    r"(?:[01]?\d|2[0-3]):[0-5]\d|\d{1,2}\s*[點点時时]|\d{1,2}\s*(?:am|pm)\b", re.IGNORECASE
)


class AgentToolRouter:
    """Expose application-owned tools without relying on native function calling."""

    def __init__(
        self,
        character: str,
        execute_tool: Callable[[str, str, dict[str, Any]], Any],
        *,
        now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ) -> None:
        self.character = character
        self.execute_tool = execute_tool
        self.now = now
        self.user_message = ""

    def prepare(self, user_message: str) -> None:
        self.user_message = str(user_message)

    def instructions(self, _cancel: threading.Event) -> str:
        current = self.now().isoformat(timespec="seconds")
        return (
            "Application tools are available. When the user asks to create, update, complete, "
            "or inspect a reminder, shared plan, character schedule, or diary, output only "
            '<agent-tool-call>{"tool":"NAME","arguments":{}}</agent-tool-call>. '
            "Use exactly one tool. Resolve relative or ambiguous times to an ISO 8601 local time "
            "with UTC offset; choose the nearest future occurrence (for example, 8:00 said at "
            "19:53 means 20:00 today). Current local time: " + current + ". Tools:\n"
            "- create_reminder: {text, at}\n"
            "There is no user task or todo tool. Never claim that a task was saved. The only "
            "thing this character may store on the user's behalf is a clock-time reminder.\n"
            "- get_character_activity: {at} (read-only; use only when the user explicitly asks "
            "to inspect or verify the schedule at one specific clock time. Do not call it for "
            "casual first-person conversation such as 'what are you doing?', '巡也洗好澡了嗎？', "
            "or similar questions about the character's present state; the current weekly context "
            "is already available in the prompt. A returned recurring routine is a likely plan "
            "rather than live sensor data. A dated event still overrides a weekly routine.)\n"
            "- get_character_day_schedule: {date} (read-only; date must be YYYY-MM-DD. Use when "
            "the user asks what activities or schedule the character has on a date or day; "
            "never replace a whole-day query with an arbitrary clock time.)\n"
            "- add_dating_event: {title, start_at?, end_at?, date?, all_day?, notes?}. Use only "
            "when the user's "
            "message explicitly describes a shared appointment with you (for example, "
            "'we will do something together') AND contains a definite date. If a definite clock "
            "time is also present, use start_at and optionally end_at. If the date is definite but "
            "the time is missing, choose exactly one behavior: ask the user for the time in a "
            "normal reply, or save it now by calling this tool with date=YYYY-MM-DD and "
            "all_day=true. Never merely agree without either asking or saving. Never create "
            "other character events.\n"
            "- write_diary: {date, title, content}\n"
            "- read_diary: {date?}"
        )

    def execute(self, response: str, _cancel: threading.Event) -> str | None:
        match = _CALL.fullmatch(response)
        if match is None:
            return None
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Agent tool call is invalid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("arguments", {}), dict):
            raise RuntimeError("Agent tool call requires an arguments object")
        tool = str(payload.get("tool", ""))
        if tool == "add_dating_event" and not (
            (_DATING.search(self.user_message) or _SHARED_APPOINTMENT.search(self.user_message))
            and _DATE.search(self.user_message)
            and not _UNCERTAIN.search(self.user_message)
        ):
            raise RuntimeError("約會行程必須由使用者明確提供共同計畫與日期")
        if tool == "add_dating_event":
            has_time = _TIME.search(self.user_message) is not None
            arguments = payload["arguments"]
            if has_time and not str(arguments.get("start_at", "")).strip():
                raise RuntimeError("有明確時間的約會行程必須提供 start_at")
            if not has_time and not (
                str(arguments.get("date", "")).strip() and arguments.get("all_day") is True
            ):
                raise RuntimeError("沒有明確時間的約會行程必須以整天行程儲存")
        result = self.execute_tool(self.character, tool, payload["arguments"])
        return str(json.dumps(result, ensure_ascii=False, default=str))[:16000]


class ToolChain:
    def __init__(self, *routers: Any) -> None:
        self.routers = tuple(router for router in routers if router is not None)

    def instructions(self, cancel: threading.Event) -> str:
        return "\n\n".join(filter(None, (router.instructions(cancel) for router in self.routers)))

    def prepare(self, user_message: str) -> None:
        for router in self.routers:
            prepare = getattr(router, "prepare", None)
            if callable(prepare):
                prepare(user_message)

    def execute(self, response: str, cancel: threading.Event) -> str | None:
        for router in self.routers:
            result = router.execute(response, cancel)
            if result is not None:
                return str(result)
        return None
