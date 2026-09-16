"""Resolve user-maintained weekly routines and dated character events."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any


def _routine_minutes(item: dict[str, Any]) -> tuple[int, int]:
    start = int(item.get("start_minute", int(item.get("start_hour", -1)) * 60))
    end = int(item.get("end_minute", int(item.get("end_hour", -1)) * 60))
    if not 0 <= start < end <= 24 * 60:
        raise ValueError("weekly routine time is invalid")
    return start, end


def _weekly_period(
    item: dict[str, Any], start: datetime, end: datetime
) -> dict[str, Any]:
    return {
        "title": str(item.get("title", ""))[:300],
        "notes": str(item.get("notes", ""))[:500],
        "weekday": int(item.get("weekday", -1)),
        "start_at": start.isoformat(timespec="minutes"),
        "end_at": end.isoformat(timespec="minutes"),
    }


def weekly_schedule_context(
    settings: dict[str, Any], character: str, moment: datetime
) -> dict[str, Any]:
    """Return the previous, current, and next recurring weekly periods around a moment."""
    local = moment.astimezone()
    weekday = (local.weekday() + 1) % 7
    sunday = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=weekday
    )
    occurrences: list[tuple[datetime, datetime, dict[str, Any]]] = []
    for item in settings.get("character_weekly_routines", []):
        if not isinstance(item, dict) or item.get("character") != character:
            continue
        try:
            routine_weekday = int(item.get("weekday", -1))
            start_minute, end_minute = _routine_minutes(item)
            if not 0 <= routine_weekday <= 6:
                continue
        except (TypeError, ValueError):
            continue
        for week_offset in (-7, 0, 7):
            start = sunday + timedelta(
                days=routine_weekday + week_offset, minutes=start_minute
            )
            end = sunday + timedelta(days=routine_weekday + week_offset, minutes=end_minute)
            occurrences.append((start, end, item))
    occurrences.sort(key=lambda occurrence: (occurrence[0], occurrence[1]))

    active = [occurrence for occurrence in occurrences if occurrence[0] <= local < occurrence[1]]
    current = max(active, key=lambda occurrence: occurrence[0]) if active else None
    previous_items = [occurrence for occurrence in occurrences if occurrence[1] <= local]
    next_items = [occurrence for occurrence in occurrences if occurrence[0] > local]
    previous = max(previous_items, key=lambda occurrence: occurrence[1], default=None)
    next_period = min(next_items, key=lambda occurrence: occurrence[0], default=None)

    def serialize(
        occurrence: tuple[datetime, datetime, dict[str, Any]] | None,
    ) -> dict[str, Any] | None:
        if occurrence is None:
            return None
        start, end, item = occurrence
        return _weekly_period(item, start, end)

    return {
        "as_of": local.isoformat(timespec="minutes"),
        "previous": serialize(previous),
        "current": serialize(current),
        "next": serialize(next_period),
    }


def character_activity_at(
    settings: dict[str, Any], character: str, moment: datetime
) -> dict[str, Any]:
    """Return dated events first, then matching weekly routines for a local time."""
    local = moment.astimezone()
    dated: list[dict[str, Any]] = []
    for item in settings.get("character_calendar", []):
        if not isinstance(item, dict) or item.get("character") != character:
            continue
        try:
            start = datetime.fromisoformat(str(item.get("start_at", ""))).astimezone()
            end_text = str(item.get("end_at", ""))
            end = (
                datetime.fromisoformat(end_text).astimezone()
                if end_text
                else start + timedelta(hours=1)
            )
        except ValueError:
            continue
        if start <= local < end:
            dated.append(dict(item))

    # Stored weekday uses Sunday=0 through Saturday=6 for the settings UI.
    weekday = (local.weekday() + 1) % 7
    routines: list[dict[str, Any]] = []
    for item in settings.get("character_weekly_routines", []):
        if not isinstance(item, dict) or item.get("character") != character:
            continue
        try:
            start_minute, end_minute = _routine_minutes(item)
            matches = (
                int(item.get("weekday", -1)) == weekday
                and start_minute <= local.hour * 60 + local.minute < end_minute
            )
        except (TypeError, ValueError):
            matches = False
        if matches:
            routines.append(dict(item))
    return {
        "at": local.isoformat(timespec="minutes"),
        "dated_events": dated,
        "weekly_routines": routines,
        "resolved_source": (
            "dated_event" if dated else "weekly_routine" if routines else "unspecified"
        ),
        "activity": (
            str(dated[0].get("title", ""))
            if dated
            else str(routines[0].get("title", ""))
            if routines
            else "unspecified"
        ),
    }


def character_schedule_on(
    settings: dict[str, Any], character: str, day: date
) -> dict[str, Any]:
    """Return every dated event and weekly routine that occurs on a local calendar day."""
    local_zone = datetime.now().astimezone().tzinfo
    day_start = datetime.combine(day, time.min, tzinfo=local_zone)
    day_end = day_start + timedelta(days=1)
    dated: list[dict[str, Any]] = []
    for item in settings.get("character_calendar", []):
        if not isinstance(item, dict) or item.get("character") != character:
            continue
        try:
            start = datetime.fromisoformat(str(item.get("start_at", ""))).astimezone()
            end_text = str(item.get("end_at", ""))
            end = (
                datetime.fromisoformat(end_text).astimezone()
                if end_text
                else start + timedelta(hours=1)
            )
        except ValueError:
            continue
        if start < day_end and end > day_start:
            dated.append(dict(item))
    dated.sort(key=lambda item: str(item.get("start_at", "")))

    weekday = (day.weekday() + 1) % 7
    routines: list[dict[str, Any]] = []
    for item in settings.get("character_weekly_routines", []):
        if not isinstance(item, dict) or item.get("character") != character:
            continue
        try:
            if int(item.get("weekday", -1)) != weekday:
                continue
            start_minute, end_minute = _routine_minutes(item)
        except (TypeError, ValueError):
            continue
        normalized = dict(item)
        normalized["start_time"] = f"{start_minute // 60:02d}:{start_minute % 60:02d}"
        normalized["end_time"] = f"{end_minute // 60:02d}:{end_minute % 60:02d}"
        routines.append(normalized)
    routines.sort(
        key=lambda item: int(
            item.get("start_minute", int(item.get("start_hour", -1)) * 60)
        )
    )
    return {
        "date": day.isoformat(),
        "dated_events": dated,
        "weekly_routines": routines,
    }
