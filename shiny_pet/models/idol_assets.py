"""Discover the externally supplied Shiny Colors idol Spine fixture layout."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .asset_audit import audit_assets

IDOL_VARIANTS = {
    "stand": "一般_通常服",
    "stand_costume": "一般_演出服",
    "cb": "Q版_通常服",
    "cb_costume": "Q版_演出服",
}
_FOLDER = re.compile(
    r"^spine__(idols|support_idols)__(stand|stand_costume|cb|cb_costume)__(\d+)__$"
)
_SUB_CHARACTER_FOLDER = re.compile(r"^spine__sub_characters__(stand|cb)__(.+)__$")
_KIND_PRIORITY = {"idols": 0, "sub_characters": 1, "support_idols": 2}


@dataclass(frozen=True, slots=True)
class IdolAsset:
    idol_id: str
    card_id: str
    variant: str
    variant_label: str
    directory: Path
    asset_kind: str = "idols"


def discover_idol_assets(root: Path) -> tuple[IdolAsset, ...]:
    """Return complete variant folders; unrelated/incomplete folders are ignored."""
    resolved_root = root.resolve()
    selected: dict[tuple[str, str], IdolAsset] = {}
    for skeleton in sorted(resolved_root.rglob("data.json")):
        directory = skeleton.parent
        if not (directory / "data.atlas").is_file():
            continue
        card_directory = directory.parent
        spine_directory = card_directory.parent
        idol_directory = spine_directory.parent
        try:
            idol_directory.relative_to(resolved_root)
        except ValueError:
            continue
        if (
            spine_directory.name != "spine"
            or not card_directory.name.isdigit()
            or not idol_directory.name.isdigit()
        ):
            continue
        match = _FOLDER.fullmatch(directory.name)
        sub_match = _SUB_CHARACTER_FOLDER.fullmatch(directory.name)
        if match is not None:
            asset_kind, variant, filename_card_id = match.groups()
            if filename_card_id != card_directory.name:
                continue
        elif sub_match is not None:
            variant, asset_name = sub_match.groups()
            # Sub-character exports encode the costume axis in the asset name
            # instead of the variant segment (for example luca_costume).  Treat
            # it as its own manifest variant instead of colliding with luca.
            if asset_name.endswith("_costume"):
                variant += "_costume"
            asset_kind = "sub_characters"
            filename_card_id = card_directory.name
        else:
            continue
        key = (filename_card_id, variant)
        # Scraped folders may use either two or three digits (26 or 026), while
        # profiles and dresses.json use the canonical two-digit character id.
        idol_id = str(int(idol_directory.name)).zfill(2)
        candidate = IdolAsset(
            idol_id, filename_card_id, variant, IDOL_VARIANTS[variant], directory, asset_kind
        )
        previous = selected.get(key)
        if previous is None or _KIND_PRIORITY[asset_kind] < _KIND_PRIORITY[previous.asset_kind]:
            selected[key] = candidate
        elif _KIND_PRIORITY[asset_kind] == _KIND_PRIORITY[previous.asset_kind]:
            raise ValueError(f"Duplicate idol asset variant: {filename_card_id}/{variant}")
    return tuple(sorted(
        selected.values(), key=lambda item: (item.idol_id, item.card_id, item.variant)
    ))


def audit_idol_assets(root: Path) -> dict[str, object]:
    assets = discover_idol_assets(root)
    rows = []
    for asset in assets:
        audit = audit_assets(asset.directory)
        rows.append({
            "idol_id": asset.idol_id,
            "card_id": asset.card_id,
            "variant": asset.variant,
            "variant_label": asset.variant_label,
            "asset_kind": asset.asset_kind,
            "relative_directory": asset.directory.relative_to(root.resolve()).as_posix(),
            "spine_version": audit["spine"]["export_version"],
            "size": [audit["spine"]["width"], audit["spine"]["height"]],
            "counts": audit["counts"],
            "attachment_types": audit["attachment_types"],
            "animation_features": audit["animation_features"],
            "animation_names": audit["animation_names"],
            "event_definitions": audit["event_definitions"],
            "missing_files": audit["missing_files"],
        })
    grouped: dict[str, list[str]] = {}
    for asset in assets:
        grouped.setdefault(asset.card_id, []).append(asset.variant)
    return {
        "schema_version": 1,
        "root": root.resolve().name,
        "variant_definitions": IDOL_VARIANTS,
        "asset_count": len(assets),
        "cards": {key: sorted(value) for key, value in sorted(grouped.items())},
        "assets": rows,
    }
