"""Renderer-neutral reminder scheduling primitives."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class Reminder:
    id: str
    text: str
    at: datetime
    repeat_days: tuple[int, ...] = ()
    character: str = ""
    enabled: bool = True
    last_triggered: str = ""


def next_occurrence(reminder: Reminder, after: datetime) -> datetime | None:
    candidate = reminder.at.replace(second=0, microsecond=0)
    after = after.replace(microsecond=0)
    if not reminder.repeat_days:
        return candidate if candidate > after else None
    allowed = set(reminder.repeat_days)
    for offset in range(8):
        day = (after + timedelta(days=offset)).date()
        value = datetime.combine(day, candidate.time())
        if value > after and value.weekday() in allowed:
            return value
    return None


class ReminderQueue:
    def __init__(self, reminders: list[Reminder] | None = None) -> None:
        self.reminders = list(reminders or [])
        self.delivered: set[tuple[str, str]] = set()

    def due(self, now: datetime) -> list[Reminder]:
        result: list[Reminder] = []
        for index, reminder in enumerate(self.reminders):
            if not reminder.enabled:
                continue
            scheduled = reminder.at.replace(second=0, microsecond=0)
            occurrence: datetime | None = None
            if not reminder.repeat_days:
                occurrence = scheduled if scheduled <= now else None
            else:
                allowed = set(reminder.repeat_days)
                for offset in range(8):
                    day = (now - timedelta(days=offset)).date()
                    candidate = datetime.combine(day, scheduled.time())
                    if candidate <= now and candidate.weekday() in allowed:
                        occurrence = candidate
                        break
            occurrence_key = occurrence.isoformat(timespec="minutes") if occurrence else ""
            key = (reminder.id, occurrence_key)
            if (occurrence and reminder.last_triggered != occurrence_key
                    and key not in self.delivered):
                result.append(reminder)
                self.delivered.add(key)
                self.reminders[index] = replace(reminder, last_triggered=occurrence_key)
        return result
