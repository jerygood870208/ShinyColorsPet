"""Character-scoped persona presets, adapted from BANDORI-PET-REV (GPL-3.0)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PersonaPreset:
    id: str
    title: str
    prompt: str
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _title(prompt: str) -> str:
    value = next((line.strip("# \t") for line in prompt.splitlines() if line.strip()), "Persona")
    return value[:32] + ("…" if len(value) > 32 else "")


def normalize_personas(value: Any) -> dict[str, tuple[PersonaPreset, ...]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, tuple[PersonaPreset, ...]] = {}
    for character, raw in value.items():
        key = str(character or "").strip()
        if not key or not isinstance(raw, list):
            continue
        presets: list[PersonaPreset] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict) or not str(item.get("prompt", "")).strip():
                continue
            prompt = str(item["prompt"]).strip()
            identifier = str(item.get("id", "")).strip() or uuid.uuid4().hex
            if identifier in seen:
                identifier = uuid.uuid4().hex
            created = str(item.get("created_at", "")).strip() or _now()
            presets.append(PersonaPreset(identifier, str(item.get("title", "")).strip()
                or _title(prompt), prompt, created,
                str(item.get("updated_at", "")).strip() or created))
            seen.add(identifier)
        if presets:
            result[key] = tuple(presets)
    return result


def active_persona(settings: dict[str, Any], character: str) -> str:
    active = settings.get("character_persona_active", {})
    identifier = active.get(character, "") if isinstance(active, dict) else ""
    for preset in normalize_personas(settings.get("character_persona_presets", {})).get(
        character, ()
    ):
        if preset.id == identifier:
            return preset.prompt
    return ""


def clear_persona_override(settings: dict[str, Any], character: str) -> bool:
    """Remove one character's local override so its bundled soul is used again."""
    changed = False
    for field in ("character_persona_active", "character_persona_presets"):
        configured = settings.get(field)
        if isinstance(configured, dict) and character in configured:
            configured.pop(character)
            changed = True
    return changed


def character_asset_key(character: str) -> str:
    """Map stable catalog or manifest ids to the same local soul/reference key."""
    value = str(character or "").strip()
    match = re.match(r"^idol[-_]([0-9]{2})(?:[-_]|$)", value)
    return match.group(1) if match else value


def soul_prompt(settings: dict[str, Any], character: str) -> str:
    configured = active_persona(settings, character)
    if configured:
        return configured
    root = Path(str(settings.get("souls_root", "souls"))).resolve()
    key = character_asset_key(character)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
        return ""
    path = (root / f"{key}.md").resolve()
    try:
        path.relative_to(root)
        raw = path.read_text(encoding="utf-8")[:64_000]
    except (OSError, UnicodeError, ValueError):
        return ""
    section = re.search(
        r"##\s*16\.\s*System Prompt.*?```(?:text)?\s*(.*?)```", raw, re.I | re.S
    )
    return section.group(1).strip() if section else raw[:12_000].strip()
