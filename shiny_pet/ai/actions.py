"""Parse model output without exposing renderer-specific animation names."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

_TAG = re.compile(
    r"[\[【]\s*(?:(action|expression)\s*:\s*)?([a-z0-9_.-]+)\s*[\]】]", re.I
)
_THINK = re.compile(r"<think>.*?</think>", re.I | re.S)
_LANGUAGE_BLOCKS = {
    language: re.compile(fr"<{language}>\s*(.*?)\s*</{language}>", re.I | re.S)
    for language in ("zh-TW", "zh-CN", "ja-JP", "en-US")
}
_JA_JP = _LANGUAGE_BLOCKS["ja-JP"]
_MEMORY_BLOCK = re.compile(r"<memory>\s*(.*?)\s*</memory>", re.I | re.S)
_LANGUAGE_BLOCK = re.compile(r"</?(?:zh-tw|zh-cn|ja-jp|en-us|memory)>", re.I)
_JAPANESE_KANA = re.compile(r"[\u3040-\u30ff]")
_DONE = {"done", "end"}
_MEMORY_CATEGORIES = {
    "identity", "preference", "relationship", "routine", "goal", "important_event",
}


@dataclass(frozen=True, slots=True)
class ActionDirective:
    kind: str
    key: str


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    category: str
    content: str


@dataclass(frozen=True, slots=True)
class ParsedReply:
    text: str
    speech_text: str
    directives: tuple[ActionDirective, ...]
    unknown: tuple[str, ...]
    memories: tuple[MemoryCandidate, ...]


def is_japanese_speech(value: str) -> bool:
    """Require kana so mislabeled Traditional Chinese is never sent to Japanese TTS."""
    return bool(_JAPANESE_KANA.search(str(value or "")))


def parse_reply(
    value: str,
    *,
    actions: set[str] | frozenset[str],
    expressions: set[str] | frozenset[str],
    display_language: str = "zh-TW",
) -> ParsedReply:
    """Strip action tags and retain only manifest-advertised semantic keys."""
    directives: list[ActionDirective] = []
    unknown: list[str] = []
    seen: set[tuple[str, str]] = set()
    memories: list[MemoryCandidate] = []
    seen_memories: set[str] = set()

    visible = _THINK.sub("", str(value or ""))
    for match in _MEMORY_BLOCK.finditer(visible):
        try:
            payload = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(payload, dict):
            continue
        category = str(payload.get("category", "")).strip().lower()
        content = re.sub(r"\s+", " ", str(payload.get("content", ""))).strip()
        normalized = content.casefold()
        if (
            category not in _MEMORY_CATEGORIES
            or not 4 <= len(content) <= 300
            or normalized in seen_memories
            or len(memories) >= 2
        ):
            continue
        memories.append(MemoryCandidate(category, content))
        seen_memories.add(normalized)
    visible = _MEMORY_BLOCK.sub("", visible)
    for match in _TAG.finditer(visible):
        explicit, key = (match.group(1) or "").lower(), match.group(2).lower()
        if key in _DONE:
            continue
        kind = explicit
        if not kind:
            kind = "expression" if key in expressions else "action"
        available = expressions if kind == "expression" else actions
        if key not in available and explicit:
            alternate_kind = "action" if kind == "expression" else "expression"
            alternate = actions if alternate_kind == "action" else expressions
            if key in alternate:
                logging.getLogger(__name__).warning(
                    "AI semantic key %s:%s corrected to %s:%s",
                    kind, key, alternate_kind, key,
                )
                kind, available = alternate_kind, alternate
        if key not in available:
            unknown.append(f"{kind}:{key}")
            logging.getLogger(__name__).warning("Unknown AI semantic key ignored: %s:%s", kind, key)
            continue
        item = (kind, key)
        if item not in seen:
            directives.append(ActionDirective(*item))
            seen.add(item)

    display_pattern = _LANGUAGE_BLOCKS.get(display_language, _LANGUAGE_BLOCKS["zh-TW"])
    display_match = display_pattern.search(visible)
    ja_match = _JA_JP.search(visible)
    if display_match:
        text = display_match.group(1)
    elif any(pattern.search(visible) for pattern in _LANGUAGE_BLOCKS.values()):
        # A structured reply in the wrong language must be repaired by the caller,
        # not silently shown after the user changes the interface language.
        text = ""
    else:
        text = _LANGUAGE_BLOCK.sub("", _TAG.sub("", visible))
    speech_text = ja_match.group(1) if ja_match else ""
    text = re.sub(r"[ \t]+\n", "\n", _TAG.sub("", text)).strip()
    speech_text = re.sub(r"[ \t]+\n", "\n", _TAG.sub("", speech_text)).strip()
    if not is_japanese_speech(speech_text):
        speech_text = ""
    return ParsedReply(
        text, speech_text, tuple(directives), tuple(unknown), tuple(memories)
    )
