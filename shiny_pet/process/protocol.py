"""Small explicit IPC vocabulary; no arbitrary method dispatch or pickle."""

from __future__ import annotations

import json
from typing import Any

PREFIX = b"SHINY1 "
MAX_MESSAGE = 65536
COMMANDS = {
    "quit", "show", "hide", "ping", "settings", "gesture",
    "expression", "mouth",
}


def encode(kind: str, **payload: Any) -> bytes:
    data = PREFIX + json.dumps({"version": 1, "kind": kind, **payload},
                               ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    if len(data) > MAX_MESSAGE:
        raise ValueError("IPC message too large")
    return data


def decode(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_MESSAGE or not data.startswith(PREFIX):
        raise ValueError("Invalid IPC envelope")
    value = json.loads(data[len(PREFIX):])
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Unsupported IPC version")
    if not isinstance(value.get("kind"), str):
        raise ValueError("Missing IPC kind")
    return value
