"""Merge bundled and local asset-pack catalogs into selectable desktop characters."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .asset_packs import (
    AssetPack,
    default_external_roots,
    discover_asset_packs,
    resolve_asset_ref,
)
from .manifest import load_manifest

_MANAGED_INDEX_SCHEMA = 1
_MANAGED_INDEX_NAME = "managed-catalog-index-v1.json"
_IDOL_CHARACTER_ID = re.compile(r"^idol-(\d{2})$")


@dataclass(frozen=True, slots=True)
class CatalogVariant:
    presentation: str
    costume_mode: str
    model_asset_ref: str
    manifest_asset_ref: str
    manifest_path: Path | None = None


@dataclass(frozen=True, slots=True)
class CatalogOutfit:
    outfit_id: str
    name_key: str
    sort_order: int
    variants: tuple[CatalogVariant, ...]


@dataclass(frozen=True, slots=True)
class CatalogCharacter:
    character_id: str
    name_key: str
    unit_ids: tuple[str, ...]
    default_outfit_id: str
    default_costume_mode: str
    outfits: tuple[CatalogOutfit, ...]
    enabled: bool
    ui_assets: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CatalogUnit:
    unit_id: str
    name_key: str
    sort_order: int
    member_character_ids: tuple[str, ...]
    enabled: bool
    ui_assets: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ModelSelection:
    character_id: str
    outfit_id: str
    presentation: str
    costume_mode: str
    manifest_path: Path


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _objects(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be an array of objects")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _text_mapping(value: object, label: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError(f"{label} must contain text values")
    return value


def _load_catalog(path: Path) -> tuple[list[CatalogUnit], list[CatalogCharacter]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("catalog must use schema version 1")
    units = [
        CatalogUnit(
            _text(item.get("id"), "unit id"),
            _text(item.get("name_key"), "unit name_key"),
            int(item.get("sort_order", 0)),
            tuple(_text(value, "member character id") for value in item.get(
                "member_character_ids", []
            )),
            item.get("enabled", True) is not False,
            _text_mapping(item.get("ui_assets"), "unit ui_assets"),
        )
        for item in _objects(payload.get("units"), "catalog units")
    ]
    characters: list[CatalogCharacter] = []
    for item in _objects(payload.get("characters"), "catalog characters"):
        outfits: list[CatalogOutfit] = []
        for outfit in _objects(item.get("outfits"), "character outfits"):
            variants = tuple(
                CatalogVariant(
                    _text(variant.get("presentation"), "variant presentation"),
                    _text(variant.get("costume_mode"), "variant costume mode"),
                    _text(variant.get("model_asset_ref"), "variant model asset"),
                    _text(variant.get("manifest_asset_ref"), "variant manifest asset"),
                )
                for variant in _objects(outfit.get("variants"), "outfit variants")
            )
            outfits.append(CatalogOutfit(
                _text(outfit.get("id"), "outfit id"),
                _text(outfit.get("name_key"), "outfit name_key"),
                int(outfit.get("sort_order", 0)),
                variants,
            ))
        characters.append(CatalogCharacter(
            _text(item.get("id"), "character id"),
            _text(item.get("name_key"), "character name_key"),
            tuple(_text(value, "character unit id") for value in item.get("unit_ids", [])),
            _text(item.get("default_outfit_id"), "character default outfit"),
            _text(item.get("default_costume_mode"), "character default costume mode"),
            tuple(outfits),
            item.get("enabled", True) is not False,
            _text_mapping(item.get("ui_assets"), "character ui_assets"),
        ))
    return units, characters


def _load_locale(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
    ):
        raise ValueError("locale must be an object containing text values")
    return payload


class RuntimeCatalog:
    def __init__(
        self,
        packs: Mapping[str, AssetPack],
        units: Sequence[CatalogUnit],
        characters: Sequence[CatalogCharacter],
        names: Mapping[str, str],
        errors: Mapping[str, str] | None = None,
    ) -> None:
        self.packs = dict(packs)
        self.units = {unit.unit_id: unit for unit in units}
        self.characters = {character.character_id: character for character in characters}
        if len(self.units) != len(units) or len(self.characters) != len(characters):
            raise ValueError("catalog contains duplicate unit or character IDs")
        self.names = dict(names)
        self.errors = dict(errors or {})
        self._selection_cache: dict[
            tuple[str, str, str], tuple[ModelSelection, ...]
        ] = {}

    def label(self, key: str) -> str:
        return self.names.get(key, key)

    def asset_path(self, reference: str | None) -> Path | None:
        if not reference:
            return None
        try:
            return resolve_asset_ref(reference, self.packs)
        except (OSError, ValueError):
            return None

    def ordered_units(self) -> tuple[CatalogUnit, ...]:
        return tuple(sorted(
            (unit for unit in self.units.values() if unit.enabled),
            key=lambda unit: (unit.sort_order, self.label(unit.name_key)),
        ))

    def characters_for_unit(self, unit_id: str) -> tuple[CatalogCharacter, ...]:
        unit = self.units.get(unit_id)
        if unit is None:
            return ()
        return tuple(
            character
            for character_id in unit.member_character_ids
            if (character := self.characters.get(character_id)) is not None and character.enabled
        )

    def available_selections(
        self, character_id: str, outfit_id: str, presentation: str
    ) -> tuple[ModelSelection, ...]:
        cache_key = (character_id, outfit_id, presentation)
        cached = self._selection_cache.get(cache_key)
        if cached is not None:
            return cached
        character = self.characters.get(character_id)
        if character is None:
            return ()
        outfit = next((item for item in character.outfits if item.outfit_id == outfit_id), None)
        if outfit is None:
            return ()
        result: list[ModelSelection] = []
        for variant in outfit.variants:
            if variant.presentation != presentation:
                continue
            try:
                if variant.manifest_path is not None:
                    manifest = variant.manifest_path
                else:
                    resolve_asset_ref(variant.model_asset_ref, self.packs)
                    manifest = resolve_asset_ref(variant.manifest_asset_ref, self.packs)
                load_manifest(manifest)
            except (OSError, ValueError):
                continue
            result.append(ModelSelection(
                character_id, outfit_id, presentation, variant.costume_mode, manifest
            ))
        selections = tuple(result)
        self._selection_cache[cache_key] = selections
        return selections

    def available_outfits(
        self, character_id: str, presentation: str
    ) -> tuple[CatalogOutfit, ...]:
        character = self.characters.get(character_id)
        if character is None:
            return ()
        return tuple(
            outfit
            for outfit in sorted(character.outfits, key=lambda item: item.sort_order)
            if any(variant.presentation == presentation for variant in outfit.variants)
        )

    def selection(
        self,
        character_id: str,
        outfit_id: str,
        presentation: str,
        costume_mode: str,
    ) -> ModelSelection | None:
        return next((
            item
            for item in self.available_selections(character_id, outfit_id, presentation)
            if item.costume_mode == costume_mode
        ), None)

    def default_selection(self, character_id: str, presentation: str) -> ModelSelection | None:
        character = self.characters.get(character_id)
        if character is None:
            return None
        outfits = list(self.available_outfits(character_id, presentation))
        idol_match = _IDOL_CHARACTER_ID.fullmatch(character_id)
        idol_number = int(idol_match.group(1)) if idol_match is not None else 0
        if 1 <= idol_number <= 28:
            preferred_outfit_id = f"card-1930{idol_number:02d}0010"

            def idol_outfit_key(outfit: CatalogOutfit) -> tuple[int, int | str]:
                enza_id = outfit.outfit_id.removeprefix("card-")
                return (0, int(enza_id)) if enza_id.isdigit() else (1, outfit.outfit_id)

            outfits.sort(key=lambda outfit: (
                outfit.outfit_id != preferred_outfit_id,
                idol_outfit_key(outfit),
            ))
        else:
            outfits.sort(key=lambda outfit: (
                outfit.outfit_id != character.default_outfit_id,
                outfit.sort_order,
            ))
        selections: tuple[ModelSelection, ...] = ()
        for outfit in outfits:
            selections = self.available_selections(
                character_id, outfit.outfit_id, presentation
            )
            if selections:
                break
        for preferred in (character.default_costume_mode, "normal"):
            match = next((item for item in selections if item.costume_mode == preferred), None)
            if match is not None:
                return match
        return selections[0] if selections else None


def discover_runtime_catalog(
    extra_roots: Sequence[Path] = (), *, root: Path | None = None, locale: str = "zh-TW",
    managed_manifest_root: Path | None = None,
) -> RuntimeCatalog:
    base = (root or application_root()).resolve()
    external = tuple(dict.fromkeys((
        *default_external_roots(base), *(path.resolve() for path in extra_roots)
    )))
    packs, errors = discover_asset_packs(base / "asset-packs", external)
    catalog_paths = [base / "data" / "catalog.json"]
    locale_paths = [base / "data" / "locales" / f"{locale}.json"]
    for pack in packs.values():
        if "catalog.json" in pack.files:
            catalog_paths.append(resolve_asset_ref(f"asset://{pack.pack_id}/catalog.json", packs))
        locale_file = f"locales/{locale}.json"
        if locale_file in pack.files:
            locale_paths.append(resolve_asset_ref(
                f"asset://{pack.pack_id}/{locale_file}", packs
            ))
    units: list[CatalogUnit] = []
    characters: list[CatalogCharacter] = []
    names: dict[str, str] = {}
    unit_ids: set[str] = set()
    character_ids: set[str] = set()
    for path in catalog_paths:
        if not path.is_file():
            continue
        try:
            next_units, next_characters = _load_catalog(path)
            duplicate_units = unit_ids.intersection(unit.unit_id for unit in next_units)
            duplicate_characters = character_ids.intersection(
                character.character_id for character in next_characters
            )
            if duplicate_units or duplicate_characters:
                raise ValueError(
                    "catalog fragment duplicates existing IDs: "
                    + ", ".join(sorted((*duplicate_units, *duplicate_characters)))
                )
            units.extend(next_units)
            characters.extend(next_characters)
            unit_ids.update(unit.unit_id for unit in next_units)
            character_ids.update(character.character_id for character in next_characters)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors[str(path)] = str(exc)
    for path in locale_paths:
        if not path.is_file():
            continue
        try:
            for key, value in _load_locale(path).items():
                if key in names and names[key] != value:
                    raise ValueError(f"duplicate locale key with different text: {key}")
                names[key] = value
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            errors[str(path)] = str(exc)
    if managed_manifest_root is not None:
        _merge_managed_manifests(
            managed_manifest_root, units, characters, names, unit_ids, character_ids, errors
        )
    return RuntimeCatalog(packs, units, characters, names, errors)


def _merge_managed_manifests(
    root: Path,
    units: list[CatalogUnit],
    characters: list[CatalogCharacter],
    names: dict[str, str],
    unit_ids: set[str],
    character_ids: set[str],
    errors: dict[str, str],
) -> None:
    """Merge the small catalog records embedded in LocalAppData manifests."""
    if not root.is_dir():
        return
    records: dict[str, dict[str, Any]] = {}
    managed_units: dict[str, dict[str, Any]] = {}
    for row in _managed_manifest_rows(root, errors):
        path = root
        try:
            filename = _text(row.get("filename"), "managed manifest filename")
            if Path(filename).name != filename or Path(filename).suffix not in {".yaml", ".yml"}:
                raise ValueError("managed manifest filename must be a local YAML file")
            path = root / filename
            character_id = _text(row.get("character_id"), "managed character id")
            display_name = _text(row.get("display_name"), "managed display name")
            unit_id = _text(row.get("unit_id"), "managed unit id")
            unit_name = _text(row.get("unit_name"), "managed unit name")
            outfit_id = _text(row.get("outfit_id"), "managed outfit id")
            outfit_name = _text(row.get("outfit_name"), "managed outfit name")
            presentation = _text(row.get("presentation"), "managed presentation")
            costume_mode = _text(row.get("costume_mode"), "managed costume mode")
            if presentation not in {"standard", "chibi"}:
                raise ValueError("managed presentation must be standard or chibi")
            if costume_mode not in {"normal", "performance"}:
                raise ValueError("managed costume mode must be normal or performance")
            ui_assets = _text_mapping(row.get("ui_assets"), "managed ui_assets")
            unit_ui_assets = _text_mapping(
                row.get("unit_ui_assets"), "managed unit_ui_assets"
            )
            if not unit_ui_assets and unit_id.startswith("unit-"):
                number_text = unit_id.removeprefix("unit-")
                if number_text.isdigit():
                    number = int(number_text)
                    icon_number = 0 if number == 81 else number
                    unit_ui_assets = {
                        "icon": (
                            "asset://shinycolors-ui-v1/ui/unit-icons/"
                            f"unit_icon_{icon_number:02d}.png"
                        )
                    }
            character = records.setdefault(character_id, {
                "display_name": display_name,
                "unit_ids": [],
                "ui_assets": ui_assets,
                "outfits": {},
            })
            if character["display_name"] != display_name:
                raise ValueError("managed character has inconsistent display names")
            if unit_id not in character["unit_ids"]:
                character["unit_ids"].append(unit_id)
            outfit = character["outfits"].setdefault(outfit_id, {
                "name": outfit_name,
                "sort_order": int(row.get("sort_order", 0)),
                "variants": [],
            })
            variant_key = (presentation, costume_mode)
            if any(
                (item.presentation, item.costume_mode) == variant_key
                for item in outfit["variants"]
            ):
                raise ValueError("managed outfit contains a duplicate model variant")
            outfit["variants"].append(CatalogVariant(
                presentation, costume_mode, "", "", path.resolve()
            ))
            unit = managed_units.setdefault(unit_id, {
                "name": unit_name, "members": [], "ui_assets": unit_ui_assets,
            })
            if unit["name"] != unit_name or unit["ui_assets"] != unit_ui_assets:
                raise ValueError("managed unit has inconsistent names or UI assets")
            if character_id not in unit["members"]:
                unit["members"].append(character_id)
        except (OSError, UnicodeError, ValueError) as exc:
            errors[str(path)] = str(exc)
    for unit_id, item in managed_units.items():
        if unit_id in unit_ids:
            errors[str(root)] = f"managed unit duplicates an installed catalog ID: {unit_id}"
            continue
        locale_key = f"managed.unit.{unit_id}.name"
        names[locale_key] = item["name"]
        units.append(CatalogUnit(
            unit_id, locale_key, 10_000 + len(units), tuple(item["members"]), True,
            item["ui_assets"],
        ))
        unit_ids.add(unit_id)
    for character_id, item in records.items():
        if character_id in character_ids:
            errors[str(root / f"{character_id}*.yaml")] = (
                f"managed character duplicates an installed catalog ID: {character_id}"
            )
            continue
        outfits: list[CatalogOutfit] = []
        for outfit_id, outfit in item["outfits"].items():
            locale_key = f"managed.outfit.{character_id}.{outfit_id}.name"
            names[locale_key] = outfit["name"]
            outfits.append(CatalogOutfit(
                outfit_id, locale_key, outfit["sort_order"], tuple(outfit["variants"])
            ))
        if not outfits:
            continue
        name_key = f"managed.character.{character_id}.name"
        names[name_key] = item["display_name"]
        outfits.sort(key=lambda value: value.sort_order)
        first_variant = outfits[0].variants[0]
        characters.append(CatalogCharacter(
            character_id, name_key, tuple(item["unit_ids"]), outfits[0].outfit_id,
            first_variant.costume_mode, tuple(outfits), True, item["ui_assets"],
        ))
        character_ids.add(character_id)


def _managed_manifest_snapshot(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        stat = path.stat()
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(b":")
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _managed_manifest_row(path: Path) -> dict[str, Any]:
    # The index describes the catalog only. Full file/version validation remains
    # lazy and is cached by RuntimeCatalog when a variant is actually selected.
    manifest = load_manifest(path, require_files=False)
    catalog = manifest.raw.get("catalog")
    if not isinstance(catalog, dict):
        raise ValueError("managed manifest is missing catalog metadata")
    return {
        "filename": path.name,
        "character_id": manifest.character_id,
        "display_name": manifest.display_name,
        "unit_id": _text(catalog.get("unit_id"), "managed unit id"),
        "unit_name": _text(catalog.get("unit_name"), "managed unit name"),
        "outfit_id": _text(catalog.get("outfit_id"), "managed outfit id"),
        "outfit_name": _text(catalog.get("outfit_name"), "managed outfit name"),
        "presentation": _text(catalog.get("presentation"), "managed presentation"),
        "costume_mode": _text(catalog.get("costume_mode"), "managed costume mode"),
        "sort_order": int(catalog.get("sort_order", 0)),
        "ui_assets": _text_mapping(catalog.get("ui_assets"), "managed ui_assets"),
        "unit_ui_assets": _text_mapping(
            catalog.get("unit_ui_assets"), "managed unit_ui_assets"
        ),
    }


def _write_managed_index(path: Path, payload: Mapping[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _managed_manifest_rows(root: Path, errors: dict[str, str]) -> list[dict[str, Any]]:
    paths = sorted((*root.glob("*.yaml"), *root.glob("*.yml")))
    try:
        snapshot = _managed_manifest_snapshot(paths)
    except OSError:
        snapshot = ""
    index_path = root.parent / _MANAGED_INDEX_NAME
    try:
        cached = json.loads(index_path.read_text(encoding="utf-8"))
        if (
            isinstance(cached, dict)
            and cached.get("schema_version") == _MANAGED_INDEX_SCHEMA
            and cached.get("snapshot") == snapshot
            and isinstance(cached.get("rows"), list)
            and isinstance(cached.get("errors"), dict)
        ):
            errors.update({str(root / name): str(message)
                           for name, message in cached["errors"].items()})
            return [row for row in cached["rows"] if isinstance(row, dict)]
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass

    rows: list[dict[str, Any]] = []
    indexed_errors: dict[str, str] = {}
    for path in paths:
        try:
            rows.append(_managed_manifest_row(path))
        except (OSError, UnicodeError, ValueError) as exc:
            indexed_errors[path.name] = str(exc)
            errors[str(path)] = str(exc)
    try:
        _write_managed_index(index_path, {
            "schema_version": _MANAGED_INDEX_SCHEMA,
            "snapshot": snapshot,
            "rows": rows,
            "errors": indexed_errors,
        })
    except OSError:
        # A read-only manifest location remains usable; it simply misses the
        # persistent startup optimization.
        pass
    return rows
