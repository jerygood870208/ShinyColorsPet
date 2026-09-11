"""Validate cross-record invariants in a ShinyColorsPet catalog.

This complements JSON Schema. It intentionally uses only the Python standard library so the
publication gate can run before the application dependencies are installed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_ASSET_REF = re.compile(r"^asset://(?P<pack>[a-z0-9][a-z0-9._-]*)/(?P<path>.+)$")
_PRESENTATIONS = {"standard", "chibi"}
_COSTUME_MODES = {"normal", "performance"}


def _objects(value: Any, label: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{label} must be an array")
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
        else:
            result.append(item)
    return result


def _index(items: list[dict[str, Any]], label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not _ID.fullmatch(item_id):
            errors.append(f"{label}[{index}].id is invalid")
            continue
        if item_id in result:
            errors.append(f"duplicate {label} id: {item_id}")
        result[item_id] = item
    return result


def _check_asset_ref(value: Any, label: str, packs: set[str], errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        errors.append(f"{label} must be a string")
        return
    match = _ASSET_REF.fullmatch(value)
    if match is None:
        errors.append(f"{label} must use asset://<pack-id>/<relative-path>")
        return
    parts = match.group("path").split("/")
    if any(part in {"", ".", ".."} for part in parts) or "\\" in match.group("path"):
        errors.append(f"{label} contains an unsafe asset path")
    if match.group("pack") not in packs:
        errors.append(f"{label} refers to undeclared asset pack: {match.group('pack')}")


def validate_catalog(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["catalog root must be an object"]
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    raw_packs = payload.get("asset_packs")
    if not isinstance(raw_packs, list) or not all(
        isinstance(item, str) and _ID.fullmatch(item) for item in raw_packs
    ):
        errors.append("asset_packs must contain valid pack IDs")
        packs: set[str] = set()
    else:
        packs = set(raw_packs)
        if len(packs) != len(raw_packs):
            errors.append("asset_packs contains duplicate IDs")

    units = _index(_objects(payload.get("units"), "units", errors), "unit", errors)
    characters = _index(
        _objects(payload.get("characters"), "characters", errors), "character", errors
    )

    for unit_id, unit in units.items():
        members = unit.get("member_character_ids")
        if not isinstance(members, list) or not all(isinstance(item, str) for item in members):
            errors.append(f"unit {unit_id} member_character_ids must be an array of IDs")
            continue
        if len(set(members)) != len(members):
            errors.append(f"unit {unit_id} has duplicate member IDs")
        for character_id in members:
            character = characters.get(character_id)
            if character is None:
                errors.append(f"unit {unit_id} refers to missing character: {character_id}")
            elif unit_id not in character.get("unit_ids", []):
                errors.append(
                    f"unit {unit_id} and character {character_id} membership is not bidirectional"
                )
        for role, asset_ref in unit.get("ui_assets", {}).items():
            _check_asset_ref(asset_ref, f"unit {unit_id} ui_assets.{role}", packs, errors)

    for character_id, character in characters.items():
        unit_ids = character.get("unit_ids")
        if not isinstance(unit_ids, list) or not unit_ids or not all(
            isinstance(item, str) for item in unit_ids
        ):
            errors.append(f"character {character_id} unit_ids must be a non-empty array of IDs")
            unit_ids = []
        if len(set(unit_ids)) != len(unit_ids):
            errors.append(f"character {character_id} has duplicate unit IDs")
        for unit_id in unit_ids:
            unit = units.get(unit_id)
            if unit is None:
                errors.append(f"character {character_id} refers to missing unit: {unit_id}")
            elif character_id not in unit.get("member_character_ids", []):
                errors.append(
                    f"character {character_id} and unit {unit_id} membership is not bidirectional"
                )

        outfits = _objects(character.get("outfits"), f"character {character_id} outfits", errors)
        outfit_index = _index(outfits, f"character {character_id} outfit", errors)
        default_outfit = character.get("default_outfit_id")
        if default_outfit not in outfit_index:
            errors.append(
                f"character {character_id} default outfit does not exist: {default_outfit}"
            )
        default_mode = character.get("default_costume_mode")
        if default_mode not in _COSTUME_MODES:
            errors.append(f"character {character_id} has invalid default_costume_mode")

        for role, asset_ref in character.get("ui_assets", {}).items():
            _check_asset_ref(asset_ref, f"character {character_id} ui_assets.{role}", packs, errors)
        for outfit_id, outfit in outfit_index.items():
            variants = _objects(
                outfit.get("variants"),
                f"character {character_id} outfit {outfit_id} variants",
                errors,
            )
            seen_pairs: set[tuple[Any, Any]] = set()
            for index, variant in enumerate(variants):
                presentation = variant.get("presentation")
                mode = variant.get("costume_mode")
                if presentation not in _PRESENTATIONS:
                    errors.append(
                        f"character {character_id} outfit {outfit_id} variant {index} "
                        "has invalid presentation"
                    )
                if mode not in _COSTUME_MODES:
                    errors.append(
                        f"character {character_id} outfit {outfit_id} variant {index} "
                        "has invalid costume_mode"
                    )
                pair = (presentation, mode)
                if pair in seen_pairs:
                    errors.append(
                        f"character {character_id} outfit {outfit_id} has duplicate variant "
                        f"{presentation}/{mode}"
                    )
                seen_pairs.add(pair)
                for field in ("model_asset_ref", "manifest_asset_ref"):
                    _check_asset_ref(
                        variant.get(field),
                        f"character {character_id} outfit {outfit_id} variant {index}.{field}",
                        packs,
                        errors,
                    )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.catalog.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"cannot read catalog: {exc}", file=sys.stderr)
        return 2
    errors = validate_catalog(payload)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"catalog is valid: {args.catalog}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
