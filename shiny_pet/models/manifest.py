"""Versioned, path-safe character manifest loading."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ManifestError(ValueError):
    """A manifest cannot be loaded safely or does not satisfy schema v1."""


@dataclass(frozen=True, slots=True)
class SpineFiles:
    runtime: str
    skeleton: Path
    atlas: Path
    texture_preferred: Path | None = None
    texture_fallback: Path | None = None
    default_skin: str = "default"
    premultiplied_alpha: bool = False


@dataclass(frozen=True, slots=True)
class AnimationChoice:
    name: str
    weight: float = 1.0
    loop: bool = False


@dataclass(frozen=True, slots=True)
class Expression:
    animation: str
    channel: str
    driver: str = "animation_choice"
    slot: str = ""
    attachment: str = ""


@dataclass(frozen=True, slots=True)
class HitAreas:
    source: str = "alpha_mask"
    aliases: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Manifest:
    schema_version: int
    character_id: str
    display_name: str
    spine: SpineFiles
    channels: Mapping[str, int]
    animation_groups: Mapping[str, tuple[AnimationChoice, ...]]
    expressions: Mapping[str, Expression]
    hit_areas: HitAreas
    events: Mapping[str, str]
    raw: Mapping[str, Any]

    def animation_group(self, semantic_name: str) -> tuple[AnimationChoice, ...]:
        return self.animation_groups.get(semantic_name, ())


_CHARACTER_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_HIT_SOURCES = {"alpha_mask", "bounding_box_attachments", "model_bounds"}


def _required_text(mapping: Mapping[str, Any], key: str, *, label: str | None = None) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label or key} must be a non-empty string")
    return value.strip()


def _safe_asset_path(root: Path, value: str, key: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ManifestError(f"{key} must be relative to the manifest")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ManifestError(f"{key} escapes the manifest directory") from exc
    return resolved


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{label} must be a mapping")
    return value


def _parse_groups(
    payload: Any, channels: Mapping[str, int]
) -> dict[str, tuple[AnimationChoice, ...]]:
    if payload is None:
        return {}
    groups = _mapping(payload, "animation_groups")
    result: dict[str, tuple[AnimationChoice, ...]] = {}
    for group_name, choices_payload in groups.items():
        if not isinstance(group_name, str) or not group_name:
            raise ManifestError("animation group names must be non-empty strings")
        if not isinstance(choices_payload, list) or not choices_payload:
            raise ManifestError(f"animation_groups.{group_name} must be a non-empty list")
        choices: list[AnimationChoice] = []
        for index, item in enumerate(choices_payload):
            label = f"animation_groups.{group_name}[{index}]"
            item_map = _mapping(item, label)
            name = _required_text(item_map, "name", label=f"{label}.name")
            weight = item_map.get("weight", 1.0)
            loop = item_map.get("loop", False)
            if (
                isinstance(weight, bool)
                or not isinstance(weight, (int, float))
                or not math.isfinite(weight)
                or weight <= 0
            ):
                raise ManifestError(f"{label}.weight must be a positive number")
            if not isinstance(loop, bool):
                raise ManifestError(f"{label}.loop must be a boolean")
            choices.append(AnimationChoice(name=name, weight=float(weight), loop=loop))
        result[group_name] = tuple(choices)
    if result and "base" not in channels:
        raise ManifestError("channels.base is required when animation_groups are defined")
    return result


def _parse_expressions(payload: Any, channels: Mapping[str, int]) -> dict[str, Expression]:
    if payload is None:
        return {}
    expressions = _mapping(payload, "expressions")
    result: dict[str, Expression] = {}
    for semantic_name, item in expressions.items():
        if not isinstance(semantic_name, str) or not semantic_name:
            raise ManifestError("expression names must be non-empty strings")
        item_map = _mapping(item, f"expressions.{semantic_name}")
        driver = item_map.get("driver", "animation_choice")
        if driver == "slot_attachment":
            result[semantic_name] = Expression(
                "",
                "",
                driver,
                _required_text(item_map, "slot"),
                _required_text(item_map, "attachment"),
            )
            continue
        if driver != "animation_choice":
            raise ManifestError(f"unsupported expression driver: {driver}")
        animation = _required_text(item_map, "animation")
        channel = _required_text(item_map, "channel", label=f"expressions.{semantic_name}.channel")
        if channel not in channels:
            raise ManifestError(f"expressions.{semantic_name}.channel refers to unknown channel")
        result[semantic_name] = Expression(animation, channel)
    return result


def _validate_skeleton_version(skeleton_path: Path, expected_runtime: str) -> None:
    try:
        payload = json.loads(skeleton_path.read_text(encoding="utf-8-sig"))
        version = payload["skeleton"]["spine"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ManifestError(f"cannot read Spine skeleton version: {exc}") from exc
    if not isinstance(version, str) or "." not in version:
        raise ManifestError("Spine skeleton version is missing or invalid")
    major_minor = ".".join(version.split(".")[:2])
    if major_minor != expected_runtime:
        raise ManifestError(
            f"Spine skeleton version {version!r} does not match runtime {expected_runtime!r}"
        )


def load_manifest(path: Path, *, require_files: bool = True) -> Manifest:
    """Load manifest schema v1 and resolve every asset path beneath its directory."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ManifestError(f"cannot read manifest: {exc}") from exc
    root_payload = _mapping(payload, "manifest root")
    if root_payload.get("schema_version") != 1:
        raise ManifestError("unsupported schema_version; expected 1")
    character_id = _required_text(root_payload, "character_id")
    if not _CHARACTER_ID.fullmatch(character_id):
        raise ManifestError(
            "character_id must contain only lowercase letters, numbers, '.', '_' or '-'"
        )
    spine = _mapping(root_payload.get("spine"), "spine")
    runtime = _required_text(spine, "runtime", label="spine.runtime")
    if runtime != "3.6":
        raise ManifestError("ShinyColorsPet supports only Spine runtime 3.6")
    # User-managed manifests live together in LocalAppData while the downloaded
    # Spine files stay where the user extracted them.  The explicit root keeps
    # every individual asset reference relative and contained, while older
    # manifests continue to resolve beside themselves.
    asset_root = root_payload.get("asset_root")
    if asset_root is None:
        root = path.parent
    elif not isinstance(asset_root, str) or not asset_root.strip():
        raise ManifestError("asset_root must be a non-empty absolute path")
    else:
        root = Path(asset_root).expanduser()
        if not root.is_absolute():
            raise ManifestError("asset_root must be an absolute path")
        root = root.resolve()
    skeleton = _safe_asset_path(root, _required_text(spine, "skeleton"), "spine.skeleton")
    atlas = _safe_asset_path(root, _required_text(spine, "atlas"), "spine.atlas")

    def optional_path(key: str) -> Path | None:
        value = spine.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ManifestError(f"spine.{key} must be a non-empty string")
        return _safe_asset_path(root, value, f"spine.{key}")

    default_skin = spine.get("default_skin", "default")
    pma = spine.get("premultiplied_alpha", False)
    if not isinstance(default_skin, str) or not default_skin:
        raise ManifestError("spine.default_skin must be a non-empty string")
    if not isinstance(pma, bool):
        raise ManifestError("spine.premultiplied_alpha must be a boolean")
    viewport_padding = spine.get("viewport_padding", {})
    if not isinstance(viewport_padding, dict):
        raise ManifestError("spine.viewport_padding must be a mapping")
    for axis in ("x", "y"):
        value = viewport_padding.get(axis, 0.04)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not 0 <= value <= 1):
            raise ManifestError(f"spine.viewport_padding.{axis} must be between 0 and 1")
    files = SpineFiles(
        runtime,
        skeleton,
        atlas,
        optional_path("texture_preferred"),
        optional_path("texture_fallback"),
        default_skin,
        pma,
    )
    if require_files:
        missing = [str(item) for item in (files.skeleton, files.atlas) if not item.is_file()]
        if missing:
            raise ManifestError("missing required files: " + ", ".join(missing))
        _validate_skeleton_version(files.skeleton, runtime)

    channels_payload = root_payload.get("channels", {})
    if not isinstance(channels_payload, dict) or not all(
        isinstance(name, str)
        and bool(name)
        and isinstance(index, int)
        and not isinstance(index, bool)
        and index >= 0
        for name, index in channels_payload.items()
    ):
        raise ManifestError("channels must map names to non-negative integer track indexes")
    if len(set(channels_payload.values())) != len(channels_payload):
        raise ManifestError("channel track indexes must be unique")
    channels = dict(channels_payload)
    animation_policy = root_payload.get("animation_policy", {})
    if not isinstance(animation_policy, dict):
        raise ManifestError("animation_policy must be a mapping")
    if animation_policy.get("mode", "layered") not in {"layered", "exclusive"}:
        raise ManifestError("animation_policy.mode must be layered or exclusive")
    policy_mix = animation_policy.get("mix_seconds", 0.15)
    if (isinstance(policy_mix, bool) or not isinstance(policy_mix, (int, float))
            or not math.isfinite(policy_mix) or not 0 <= policy_mix <= 5):
        raise ManifestError("animation_policy.mix_seconds must be between 0 and 5")
    window = root_payload.get("window", {})
    if not isinstance(window, dict):
        raise ManifestError("window must be a mapping")
    for key, default in (("width", 640), ("height", 960)):
        value = window.get(key, default)
        if type(value) is not int or not 128 <= value <= 4096:
            raise ManifestError(f"window.{key} must be an integer between 128 and 4096")
    groups = _parse_groups(root_payload.get("animation_groups"), channels)
    expressions = _parse_expressions(root_payload.get("expressions"), channels)
    _validate_drivers(root_payload, channels)
    review = root_payload.get("review", {})
    if not isinstance(review, dict) or review.get("status", "approved") != "approved":
        raise ManifestError(
            "candidate manifest requires manual review: set review.status to approved"
        )

    hit_map = _mapping(root_payload.get("hit_areas", {}), "hit_areas")
    hit_source = hit_map.get("source", "alpha_mask")
    if hit_source not in _HIT_SOURCES:
        raise ManifestError(f"hit_areas.source must be one of {sorted(_HIT_SOURCES)}")
    aliases_payload = hit_map.get("aliases", {})
    if not isinstance(aliases_payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in aliases_payload.items()
    ):
        raise ManifestError("hit_areas.aliases must map strings to strings")
    events_payload = root_payload.get("events", {})
    if not isinstance(events_payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in events_payload.items()
    ):
        raise ManifestError("events must map semantic names to Spine event names")

    return Manifest(
        1,
        character_id,
        _required_text(root_payload, "display_name"),
        files,
        channels,
        groups,
        expressions,
        HitAreas(str(hit_source), dict(aliases_payload)),
        dict(events_payload),
        root_payload,
    )


def _validate_drivers(payload: Mapping[str, Any], channels: Mapping[str, int]) -> None:
    reserved = {"base", "gesture"}
    for expression in _mapping(payload.get("expressions", {}), "expressions").values():
        if expression.get("driver", "animation_choice") == "animation_choice":
            reserved.add(expression["channel"])
    for feature in ("lipsync", "gaze"):
        config = _mapping(payload.get(feature, {"driver": "disabled"}), feature)
        driver = config.get("driver")
        allowed = {"disabled", "animation_choice", "bone"}
        if feature == "lipsync":
            allowed.add("animation_mix")
        if driver not in allowed:
            raise ManifestError(f"unsupported {feature} driver: {driver}")
        if driver == "disabled":
            continue
        if driver == "bone":
            _required_text(config, "bone")
            for key in ("x_range", "y_range", "rotation_range"):
                value = config.get(key, 0)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ManifestError(f"{feature}.{key} must be finite")
            continue
        channel = _required_text(config, "channel")
        if channel not in channels:
            raise ManifestError(f"{feature}.channel refers to unknown channel")
        if channel in reserved:
            raise ManifestError(f"{feature}.channel must be independent of other semantic drivers")
        reserved.add(channel)
        if feature == "lipsync":
            candidates = config.get("candidates")
            if (
                not isinstance(candidates, list)
                or not candidates
                or not all(isinstance(name, str) and name for name in candidates)
            ):
                raise ManifestError("lipsync.candidates must be a non-empty string list")
        else:
            for key in ("center", "left", "right"):
                _required_text(config, key)
