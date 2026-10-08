"""Persistent three-level active conversation timing, independent of the UI."""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class ActiveChatState:
    level: int = 0
    next_at: str = ""
    sent_at: str = ""
    sent_level: int = 0
    event_key: str = ""

    def serialize(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def parse(cls, value: str) -> ActiveChatState:
        try:
            state = cls(**json.loads(value))
            if state.level not in range(4) or state.sent_level not in range(4):
                return cls()
            for text in (state.next_at, state.sent_at):
                if text:
                    datetime.fromisoformat(text)
            return state
        except (ValueError, TypeError):
            return cls()


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _schedule(level: int, anchor: datetime) -> ActiveChatState:
    # Draw once when scheduling and persist it, so ticks/restarts cannot redraw jitter.
    due = anchor + timedelta(seconds=random.uniform(level * 300 - 120, level * 300 + 120))
    return ActiveChatState(level, _iso(due), event_key=uuid.uuid4().hex)


def user_interaction(state: ActiveChatState, moment: datetime) -> ActiveChatState:
    level = 1
    if state.sent_at:
        elapsed = (moment - datetime.fromisoformat(state.sent_at)).total_seconds()
        if 0 <= elapsed <= state.sent_level * 300:
            level = 1 if elapsed <= 300 else 2 if elapsed <= 600 else 3
    return _schedule(level, moment)


def advance(state: ActiveChatState, moment: datetime) -> ActiveChatState:
    if not state.level or state.next_at or not state.sent_at:
        return state
    sent = datetime.fromisoformat(state.sent_at)
    if moment < sent + timedelta(minutes=state.sent_level * 5):
        return state
    if state.sent_level == 3:
        # Retain the last send time so a reply exactly at the deadline is order independent.
        return ActiveChatState(sent_at=state.sent_at, sent_level=state.sent_level)
    return replace(_schedule(state.sent_level + 1, sent),
                   sent_at=state.sent_at, sent_level=state.sent_level)


def message_sent(state: ActiveChatState, moment: datetime) -> ActiveChatState:
    return ActiveChatState(state.level, sent_at=_iso(moment), sent_level=state.level)
