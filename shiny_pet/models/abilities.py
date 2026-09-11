"""Resolve optional semantics against actual assets without importing a renderer."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any

from .manifest import Manifest


@dataclass(frozen=True)
class Abilities:
    manifest: Manifest
    animations: frozenset[str]
    lipsync: dict[str, Any]
    gaze: dict[str, Any]
    warnings: tuple[str, ...]


def resolve_abilities(manifest: Manifest) -> Abilities:
    data = json.loads(manifest.spine.skeleton.read_text(encoding="utf-8-sig"))
    animations = frozenset(data.get("animations", {}))
    bones = {item["name"] for item in data.get("bones", [])}
    slots = {item["name"] for item in data.get("slots", [])}
    skins = data.get("skins", {})
    attachments = dict(skins.get("default", {}))
    attachments.update(skins.get(manifest.spine.default_skin, {}))
    warnings: list[str] = []
    groups = {}
    for name, choices in manifest.animation_groups.items():
        groups[name] = tuple(c for c in choices if c.name in animations)
        for choice in choices:
            if choice.name not in animations:
                warnings.append(f"animation_groups.{name}: missing animation {choice.name}")
    expressions = {}
    for name, expression in manifest.expressions.items():
        if expression.driver == "slot_attachment":
            valid = expression.slot in slots and expression.attachment in attachments.get(
                expression.slot, {}
            )
        else:
            valid = expression.animation in animations
        if valid:
            expressions[name] = expression
        else:
            warnings.append(f"expressions.{name}: missing animation, slot or attachment; disabled")

    def driver(feature: str) -> dict[str, Any]:
        config = dict(manifest.raw.get(feature, {"driver": "disabled"}))
        kind = config["driver"]
        if kind == "disabled":
            return config
        valid = True
        if kind == "bone":
            valid = config["bone"] in bones
        elif feature == "lipsync":
            config["candidates"] = [n for n in config["candidates"] if n in animations]
            valid = bool(config["candidates"])
            if config["candidates"] != manifest.raw[feature]["candidates"]:
                warnings.append(f"{feature}: missing animation candidates removed")
        else:
            valid = all(config[key] in animations for key in ("left", "center", "right"))
        if not valid:
            warnings.append(f"{feature}: missing animation or bone; disabled")
            return {"driver": "disabled"}
        return config

    lipsync, gaze = driver("lipsync"), driver("gaze")
    events = {
        key: value for key, value in manifest.events.items() if value in data.get("events", {})
    }
    for name in manifest.events.keys() - events.keys():
        warnings.append(f"events.{name}: missing event; disabled")
    return Abilities(
        replace(manifest, animation_groups=groups, expressions=expressions, events=events),
        animations,
        lipsync,
        gaze,
        tuple(warnings),
    )
