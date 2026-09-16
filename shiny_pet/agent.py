"""Headless proactive scheduling and birthday helpers."""

from __future__ import annotations

import calendar
import json
import re
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import CancelledError
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shiny_pet.chat.coordinator import ChatCoordinator
from shiny_pet.chat.database import ChatDatabase, ScheduleState
from shiny_pet.chat.service import ChatResult, ChatService, TriggerContext

_BIRTHDAY_WORDS = re.compile(
    r"生日\s*(?:快樂|快乐)|生快|happy\s+b(?:irth)?day|(?:お誕生日|誕生日)\s*おめでとう",
    re.IGNORECASE,
)
_MONTHS = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.casefold(): index for index, name in enumerate(calendar.month_abbr) if name})
_TIER_INTERVALS = {"quiet": 72, "normal": 24, "clingy": 8}


def normalize_month_day(value: object) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    numeric = re.fullmatch(r"(\d{1,2})\s*(?:/|-|月)\s*(\d{1,2})\s*日?", text)
    if numeric:
        month, day = int(numeric.group(1)), int(numeric.group(2))
    else:
        english = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?", text, re.IGNORECASE)
        if not english or english.group(1).casefold() not in _MONTHS:
            return text
        month, day = _MONTHS[english.group(1).casefold()], int(english.group(2))
    try:
        datetime(2024, month, day)
    except ValueError:
        return text
    return f"{month:02d}-{day:02d}"


def month_day(value: object) -> tuple[int, int] | None:
    normalized = normalize_month_day(value)
    match = re.fullmatch(r"(\d{2})-(\d{2})", normalized)
    return (int(match.group(1)), int(match.group(2))) if match else None


def is_birthday_wish(text: str) -> bool:
    return _BIRTHDAY_WORDS.search(text) is not None


def load_idol_birthdays(path: Path) -> dict[str, tuple[int, int, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
    result: dict[str, tuple[int, int, str]] = {}
    for item in profiles:
        if not isinstance(item, dict) or type(item.get("idolId")) is not int:
            continue
        parsed = month_day(item.get("birthday"))
        if parsed:
            result[f"idol-{int(item['idolId']):02d}"] = (*parsed, str(item.get("idolName", "")))
    return result


def producer_birthday_context(
    settings: Mapping[str, object], state: ScheduleState, now: datetime
) -> int:
    birthday = month_day(settings.get("producer_birthday", ""))
    local = now.astimezone()
    if birthday == (local.month, local.day) and state.last_producer_birthday_year != local.year:
        return local.year
    return 0


def _parse_time(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


def _outside_quiet(moment: datetime, state: ScheduleState) -> datetime:
    start_h, start_m = _parse_time(state.quiet_hours_start)
    end_h, end_m = _parse_time(state.quiet_hours_end)
    start = moment.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = moment.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    overnight = (start_h, start_m) >= (end_h, end_m)
    quiet = (moment >= start or moment < end) if overnight else start <= moment < end
    if not quiet:
        return moment
    if overnight and moment >= start:
        end += timedelta(days=1)
    return end


class AgentScheduler:
    def __init__(
        self,
        database: ChatDatabase,
        coordinator: ChatCoordinator,
        service_factory: Callable[[], ChatService],
        idol_birthdays: Mapping[str, tuple[int, int, str]],
        *,
        external_events: Callable[[str], list[dict[str, object]]] | None = None,
        capabilities: Callable[[str], tuple[set[str], set[str]]] | None = None,
        on_result: Callable[[str, ChatResult], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> None:
        self.database = database
        self.coordinator = coordinator
        self.service_factory = service_factory
        self.idol_birthdays = dict(idol_birthdays)
        self.external_events = external_events or (lambda _character: [])
        self.capabilities = capabilities or (lambda _character: (set(), set()))
        self.on_result = on_result or (lambda _character, _result: None)
        self.on_error = on_error or (lambda _character, _error: None)
        self._cancel = threading.Event()

    @staticmethod
    def _iso(moment: datetime) -> str:
        return moment.astimezone(timezone.utc).isoformat(timespec="seconds")

    def _submit(self, character: str, trigger: TriggerContext, log_id: int) -> None:
        actions, expressions = self.capabilities(character)
        try:
            service = self.service_factory()
        except (OSError, RuntimeError, ValueError) as exc:
            self.database.fail_schedule_event(log_id, str(exc))
            self.on_error(character, str(exc))
            return
        future = self.coordinator.submit_trigger(
            service,
            character,
            trigger,
            actions=actions,
            expressions=expressions,
            cancel=self._cancel,
            schedule_log_id=log_id,
        )

        def done(completed: object) -> None:
            try:
                result = future.result()
            except CancelledError:
                return
            except (OSError, RuntimeError, ValueError) as exc:
                self.database.fail_schedule_event(log_id, str(exc))
                self.on_error(character, str(exc))
            else:
                self.on_result(character, result)

        future.add_done_callback(done)

    def tick(self, now: datetime | None = None) -> None:
        current = (now or datetime.now().astimezone()).astimezone()
        now_iso = self._iso(current)
        for state in self.database.schedule_states(enabled_only=True):
            self._birthday_candidate(state, current, now_iso)
            self._calendar_candidates(state, current, now_iso)
            self._checkin_candidate(state, current, now_iso)
            self.database.update_last_checked(state.character_id, now_iso)

    def _birthday_candidate(self, state: ScheduleState, now: datetime, now_iso: str) -> None:
        profile = self.idol_birthdays.get(state.character_id)
        if profile is None:
            return
        month, day, name = profile
        candidates = [now.year, now.year - 1]
        due: datetime | None = None
        year = 0
        for candidate_year in candidates:
            try:
                candidate = now.replace(
                    year=candidate_year,
                    month=month,
                    day=day,
                    hour=21,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            except ValueError:
                continue
            if candidate <= now:
                due, year = candidate, candidate_year
                break
        if due is None or state.idol_birthday_ack_year == year:
            return
        birthday_start = due.replace(hour=0, minute=0, second=0, microsecond=0)
        existing_messages = self.database.user_messages_between(
            state.character_id, self._iso(birthday_start), self._iso(due)
        )
        if any(is_birthday_wish(message) for message in existing_messages):
            self.database.set_schedule_year(state.character_id, "idol_birthday_ack_year", year)
            return
        key = f"idol-birthday:{year}"
        if now - due > timedelta(days=7):
            self.database.record_skipped_event(
                state.character_id,
                "idol_birthday",
                key,
                self._iso(due),
                "birthday catch-up window expired",
            )
            return
        trigger = TriggerContext(
            "idol_birthday",
            key,
            {
                "birthday_subject": "character",
                "character_name": name,
                "instruction": "Ask playfully whether the producer forgot what day today is.",
            },
            self._iso(due),
        )
        log_id = self.database.claim_schedule_event(
            state.character_id,
            trigger.event_type,
            trigger.event_key,
            trigger.scheduled_for,
            now_iso,
        )
        if log_id:
            self._submit(state.character_id, trigger, log_id)

    def _calendar_candidates(self, state: ScheduleState, now: datetime, now_iso: str) -> None:
        for event in self.external_events(state.character_id):
            identifier = str(event.get("id", "")).strip()
            title = str(event.get("title", "")).strip()
            start_text = str(event.get("start_at", "")).strip()
            if not identifier or not title or "T" not in start_text:
                continue
            try:
                start = datetime.fromisoformat(start_text).astimezone()
                end_text = str(event.get("end_at", "")).strip()
                end = datetime.fromisoformat(end_text).astimezone() if "T" in end_text else None
            except ValueError:
                continue
            candidates = [("pre_event", start - timedelta(minutes=15))]
            if end is not None:
                candidates.append(("post_event", end))
            for event_type, due in candidates:
                if due > now or now - due > timedelta(days=7):
                    continue
                scheduled = self._iso(due)
                trigger = TriggerContext(
                    event_type,
                    f"{event_type}:{identifier}",
                    {
                        "title": title,
                        "start_at": start_text,
                        "end_at": end_text,
                        "description": str(event.get("description") or event.get("notes") or ""),
                        "instruction": (
                            "Briefly encourage the producer before this event."
                            if event_type == "pre_event"
                            else "Naturally ask how the event went."
                        ),
                    },
                    scheduled,
                )
                log_id = self.database.claim_schedule_event(
                    state.character_id,
                    event_type,
                    trigger.event_key,
                    scheduled,
                    now_iso,
                )
                if log_id:
                    self._submit(state.character_id, trigger, log_id)

    def _checkin_candidate(self, state: ScheduleState, now: datetime, now_iso: str) -> None:
        if not state.last_interaction_at:
            return
        last = datetime.fromisoformat(state.last_interaction_at).astimezone()
        latest = self.database.latest_checkin_anchor(state.character_id)
        if latest:
            last = max(last, datetime.fromisoformat(latest).astimezone())
        hours = _TIER_INTERVALS.get(state.proactive_tier, 24)
        due = _outside_quiet(last + timedelta(hours=hours), state)
        if now < due or _outside_quiet(now, state) != now:
            return
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        if (
            self.database.sent_event_count(
                state.character_id, "checkin", self._iso(day_start), self._iso(day_end)
            )
            >= state.daily_proactive_cap
        ):
            return
        scheduled = self._iso(due)
        trigger = TriggerContext(
            "checkin",
            "checkin:" + scheduled,
            {
                "hours_since_user_interaction": max(0, round((now - last).total_seconds() / 3600)),
                "instruction": "Start a brief, natural check-in without claiming the user spoke.",
            },
            scheduled,
        )
        log_id = self.database.claim_schedule_event(
            state.character_id,
            trigger.event_type,
            trigger.event_key,
            scheduled,
            now_iso,
        )
        if log_id:
            self._submit(state.character_id, trigger, log_id)

    def shutdown(self) -> None:
        self._cancel.set()
