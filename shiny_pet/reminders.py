"""Renderer-neutral reminder scheduling primitives."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta


@dataclass(frozen=True, slots=True)
class Reminder:
    id: str
    text: str
    at: datetime
    repeat_days: tuple[int, ...] = ()
    character: str = ""
    enabled: bool = True
    last_triggered: str = ""


def _local_aware(value: datetime) -> datetime:
    """Interpret legacy naive values as local wall-clock time for safe comparison."""
    return value.astimezone()


def _after(left: datetime, right: datetime) -> bool:
    return _local_aware(left) > _local_aware(right)


def _at_or_before(left: datetime, right: datetime) -> bool:
    return _local_aware(left) <= _local_aware(right)


def _clock(value: datetime) -> time:
    return value.timetz() if value.utcoffset() is not None else value.time()


def next_occurrence(reminder: Reminder, after: datetime) -> datetime | None:
    candidate = reminder.at.replace(second=0, microsecond=0)
    after = after.replace(microsecond=0)
    if not reminder.repeat_days:
        return candidate if _after(candidate, after) else None
    allowed = set(reminder.repeat_days)
    for offset in range(8):
        day = (after + timedelta(days=offset)).date()
        value = datetime.combine(day, _clock(candidate))
        if _after(value, after) and value.weekday() in allowed:
            return value
    return None


class ReminderQueue:
    def __init__(self, reminders: list[Reminder] | None = None) -> None:
        self.reminders = list(reminders or [])
        self.delivered: set[tuple[str, str]] = set()

    def upcoming(
        self, now: datetime, horizon: timedelta = timedelta(seconds=30)
    ) -> list[tuple[Reminder, datetime]]:
        """Return enabled occurrences strictly after now and within the horizon."""
        end = now + horizon
        result: list[tuple[Reminder, datetime]] = []
        for reminder in self.reminders:
            if not reminder.enabled:
                continue
            occurrence = next_occurrence(reminder, now)
            if occurrence is None or _after(occurrence, end):
                continue
            key = (reminder.id, occurrence.isoformat(timespec="minutes"))
            if key not in self.delivered and reminder.last_triggered != key[1]:
                result.append((reminder, occurrence))
        return result

    def due(self, now: datetime) -> list[Reminder]:
        result: list[Reminder] = []
        for index, reminder in enumerate(self.reminders):
            if not reminder.enabled:
                continue
            scheduled = reminder.at.replace(second=0, microsecond=0)
            occurrence: datetime | None = None
            if not reminder.repeat_days:
                occurrence = scheduled if _at_or_before(scheduled, now) else None
            else:
                allowed = set(reminder.repeat_days)
                for offset in range(8):
                    day = (now - timedelta(days=offset)).date()
                    candidate = datetime.combine(day, _clock(scheduled))
                    if _at_or_before(candidate, now) and candidate.weekday() in allowed:
                        occurrence = candidate
                        break
            occurrence_key = occurrence.isoformat(timespec="minutes") if occurrence else ""
            key = (reminder.id, occurrence_key)
            if (
                occurrence
                and reminder.last_triggered != occurrence_key
                and key not in self.delivered
            ):
                result.append(reminder)
                self.delivered.add(key)
                self.reminders[index] = replace(reminder, last_triggered=occurrence_key)
        return result
