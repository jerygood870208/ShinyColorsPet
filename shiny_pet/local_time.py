"""Convert persisted UTC timestamps to the host computer's configured timezone."""

from __future__ import annotations

from datetime import datetime


def computer_local_now() -> datetime:
    # datetime.now() is the wall-clock value shown by the host computer.  Keep it
    # naive for the LLM prompt so an offset cannot be applied a second time.
    return datetime.now()


def as_computer_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.astimezone()
    return value.astimezone()


def format_stored_local(value: str) -> str:
    local = stored_as_computer_local(value)
    if local is None:
        return value
    offset = local.strftime("%z")
    suffix = f"{offset[:3]}:{offset[3:]}" if offset else ""
    return f"{local:%Y-%m-%d %H:%M:%S}{suffix}"


def stored_as_computer_local(value: str) -> datetime | None:
    """Parse a persisted timestamp and convert it to the computer's timezone."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return as_computer_local(parsed)


def describe_stored_local(value: str) -> str:
    """Describe a persisted message time as trusted computer-local metadata."""
    local = stored_as_computer_local(value)
    return describe_local(local) if local is not None else value


def describe_local(value: datetime) -> str:
    local = value.replace(tzinfo=None)
    return f"{local:%Y-%m-%d %H:%M:%S} ({local:%A}, computer wall-clock time)"
