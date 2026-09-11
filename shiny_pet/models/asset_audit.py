"""Deterministic static audit for a Spine 3.6 JSON/atlas asset set."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any


def _walk_attachments(skins: Any) -> Iterator[Mapping[str, Any]]:
    if not isinstance(skins, dict):
        return
    for skin in skins.values():
        if not isinstance(skin, dict):
            continue
        for slot in skin.values():
            if not isinstance(slot, dict):
                continue
            for attachment in slot.values():
                if isinstance(attachment, dict):
                    yield attachment


def _atlas_pages(text: str) -> list[str]:
    lines = text.splitlines()
    pages: list[str] = []
    for index, line in enumerate(lines):
        name = line.strip()
        if not name or line[:1].isspace():
            continue
        following = next((item.strip() for item in lines[index + 1 :] if item.strip()), "")
        if following.startswith("size:"):
            pages.append(name)
    return pages


def _timeline_features(animations: Mapping[str, Any]) -> dict[str, bool]:
    serialized = json.dumps(animations, separators=(",", ":"))
    return {
        "deform": '"deform"' in serialized or '"ffd"' in serialized,
        "draw_order": '"drawOrder"' in serialized or '"draworder"' in serialized,
        "events": '"events"' in serialized,
    }


def audit_assets(
    asset_dir: Path,
    *,
    skeleton_name: str = "data.json",
    atlas_name: str = "data.atlas",
) -> dict[str, Any]:
    asset_dir = asset_dir.resolve()
    for filename in (skeleton_name, atlas_name):
        if Path(filename).is_absolute() or Path(filename).name != filename:
            raise ValueError("asset filenames must not contain a directory")
    skeleton_path = asset_dir / skeleton_name
    atlas_path = asset_dir / atlas_name
    required = [skeleton_path, atlas_path]
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing required asset files: " + ", ".join(missing))
    data = json.loads(skeleton_path.read_text(encoding="utf-8-sig"))
    atlas_text = atlas_path.read_text(encoding="utf-8-sig")
    pages = _atlas_pages(atlas_text)
    attachments = Counter(
        item.get("type", "region") for item in _walk_attachments(data.get("skins"))
    )
    animations = data.get("animations", {})
    if not isinstance(animations, dict):
        raise ValueError("animations must be a mapping")
    event_definitions = data.get("events", {})
    if not isinstance(event_definitions, dict):
        event_definitions = {}
    texture_missing = [page for page in pages if not (asset_dir / page).is_file()]
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(asset_dir.iterdir())
        if path.is_file()
    }
    spine = data.get("skeleton", {})
    return {
        "schema_version": 1,
        "asset_directory": asset_dir.name,
        "spine": {
            "export_version": spine.get("spine"),
            "width": spine.get("width"),
            "height": spine.get("height"),
        },
        "counts": {
            "animations": len(animations),
            "bones": len(data.get("bones", [])),
            "slots": len(data.get("slots", [])),
            "skins": len(data.get("skins", {})),
            "ik_constraints": len(data.get("ik", [])),
            "transform_constraints": len(data.get("transform", [])),
            "path_constraints": len(data.get("path", [])),
        },
        "animation_names": sorted(animations),
        "animation_features": _timeline_features(animations),
        "attachment_types": dict(sorted(attachments.items())),
        "event_definitions": sorted(event_definitions),
        "atlas_pages": pages,
        "missing_files": sorted(texture_missing),
        "files_sha256": hashes,
    }


def write_audit(asset_dir: Path, output: Path) -> dict[str, Any]:
    result = audit_assets(asset_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_dir", type=Path)
    parser.add_argument("--skeleton", default="data.json")
    parser.add_argument("--atlas", default="data.atlas")
    parser.add_argument("--output", type=Path, default=Path("asset-audit.json"))
    args = parser.parse_args()
    result = audit_assets(
        args.asset_dir,
        skeleton_name=args.skeleton,
        atlas_name=args.atlas,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
