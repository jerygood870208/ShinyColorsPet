"""Create LocalAppData manifests for user-selected external Spine assets."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .idol_assets import discover_idol_assets
from .manifest import ManifestError, load_manifest
from .semantic_animations import dialogue_animation_groups, dialogue_expressions, dialogue_gaze

_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_VARIANT_AXES = {
    "stand": ("standard", "normal"),
    "stand_costume": ("standard", "performance"),
    "cb": ("chibi", "normal"),
    "cb_costume": ("chibi", "performance"),
}


@dataclass(frozen=True, slots=True)
class ManagedModelInput:
    character_id: str
    display_name: str
    unit_id: str
    unit_name: str
    outfit_id: str
    outfit_name: str
    presentation: str
    costume_mode: str
    asset_directory: Path
    sort_order: int = 0
    ui_assets: Mapping[str, str] | None = None
    unit_ui_assets: Mapping[str, str] | None = None


def managed_manifest_root(app_data_root: Path) -> Path:
    return app_data_root / "manifests"


def _validate_id(value: str, label: str) -> str:
    value = value.strip().lower()
    if not _ID.fullmatch(value):
        raise ValueError(f"{label} 只能使用小寫英數、句點、底線或連字號")
    return value


def _asset_files(directory: Path) -> tuple[Path, Path]:
    directory = directory.expanduser().resolve()
    skeleton = directory / "data.json"
    atlas = directory / "data.atlas"
    if not skeleton.is_file() or not atlas.is_file():
        raise ValueError("所選 Spine 資產資料夾必須直接包含 data.json 與 data.atlas")
    return skeleton, atlas


def _candidate_payload(
    spec: ManagedModelInput, asset_directory: Path | None = None
) -> dict[str, Any]:
    managed_assets = (asset_directory or spec.asset_directory).resolve()
    skeleton, atlas = _asset_files(managed_assets)
    try:
        data = json.loads(skeleton.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"無法讀取 Spine skeleton：{exc}") from exc
    version = str(data.get("skeleton", {}).get("spine", ""))
    if ".".join(version.split(".")[:2]) != "3.6":
        raise ManifestError("目前只支援 Spine 3.6 資產")
    names = sorted(data.get("animations", {}))
    groups = dialogue_animation_groups(names)
    lips = [name for name in names if name.startswith("lip_")]
    default_skin = "normal" if spec.presentation == "chibi" and "normal" in data.get(
        "skins", {}
    ) else "default"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "character_id": _validate_id(spec.character_id, "人物 ID"),
        "display_name": spec.display_name.strip(),
        "asset_root": str(managed_assets),
        "review": {
            "status": "approved",
            "scope": "user_managed_autodetect",
            "notes": "Generated locally from the asset folder selected by the user.",
        },
        "catalog": {
            "unit_id": _validate_id(spec.unit_id, "團體 ID"),
            "unit_name": spec.unit_name.strip(),
            "outfit_id": _validate_id(spec.outfit_id, "服裝 ID"),
            "outfit_name": spec.outfit_name.strip(),
            "presentation": spec.presentation,
            "costume_mode": spec.costume_mode,
            "sort_order": spec.sort_order,
            "ui_assets": dict(spec.ui_assets or {}),
            "unit_ui_assets": dict(spec.unit_ui_assets or {}),
        },
        "spine": {
            "runtime": "3.6",
            "skeleton": skeleton.name,
            "atlas": atlas.name,
            "default_skin": default_skin,
            "premultiplied_alpha": False,
        },
        "channels": {"base": 0, "gesture": 1, "face": 2, "lipsync": 3, "gaze": 4},
        "animation_groups": groups,
        "expressions": dialogue_expressions(names),
        "lipsync": (
            {"driver": "animation_mix", "channel": "lipsync", "candidates": lips}
            if lips else {"driver": "disabled", "reason": "No lip_* candidates"}
        ),
        "gaze": dialogue_gaze(names),
        "hit_areas": {"source": "alpha_mask", "aliases": {}},
        "events": {name: name for name in sorted(data.get("events", {}))},
    }
    if spec.presentation == "chibi":
        payload["spine"]["viewport_padding"] = {"x": 0.24, "y": 0.25}
        payload["window"] = {"width": 640, "height": 1120}
        payload["animation_policy"] = {"mode": "exclusive", "mix_seconds": 0.0}
    return payload


def _atomic_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            yaml.safe_dump(dict(payload), stream, allow_unicode=True, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def update_managed_model(spec: ManagedModelInput, destination: Path) -> Path:
    """Create or replace one deterministic, locally managed manifest."""
    if not spec.display_name.strip() or not spec.unit_name.strip() or not spec.outfit_name.strip():
        raise ValueError("人物名稱、團體名稱與服裝名稱不可留白")
    if spec.presentation not in {"standard", "chibi"}:
        raise ValueError("顯示類型必須是 standard 或 chibi")
    if spec.costume_mode not in {"normal", "performance"}:
        raise ValueError("服裝類型必須是 normal 或 performance")
    character_id = _validate_id(spec.character_id, "人物 ID")
    outfit_id = _validate_id(spec.outfit_id, "服裝 ID")
    filename = "--".join((
        character_id,
        outfit_id,
        spec.presentation,
        spec.costume_mode,
    )) + ".yaml"
    source = spec.asset_directory.expanduser().resolve()
    _asset_files(source)
    # Build the YAML before copying so malformed source JSON cannot disturb an
    # already installed model.
    _candidate_payload(spec, source)
    destination = destination.resolve()
    asset_target = (
        destination.parent / "models" / character_id / outfit_id
        / f"{spec.presentation}-{spec.costume_mode}"
    )
    asset_target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=asset_target.name + ".", dir=asset_target.parent))
    backup = asset_target.with_name(asset_target.name + ".previous")
    installed = False
    try:
        # copytree with dirs_exist_ok copies every texture/page belonging to the
        # selected Spine set, not only the two entry files.
        shutil.copytree(source, staging, dirs_exist_ok=True)
        _asset_files(staging)
        if backup.exists():
            shutil.rmtree(backup)
        if asset_target.exists():
            os.replace(asset_target, backup)
        os.replace(staging, asset_target)
        installed = True
        output = destination / filename
        _atomic_yaml(output, _candidate_payload(spec, asset_target))
        load_manifest(output)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if installed and asset_target.exists():
            shutil.rmtree(asset_target)
        if backup.exists():
            os.replace(backup, asset_target)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    output = destination / filename
    return output


def _dress_metadata(asset_root: Path) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for path in sorted(asset_root.rglob("dresses.json")):
        if (
            path.parent.name != "spine"
            or not path.parent.parent.name.isdigit()
        ):
            continue
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, list):
            raise ValueError(f"dresses.json 格式錯誤：{path}")
        for row in payload:
            if not isinstance(row, dict):
                continue
            idol_id = str(row.get("idolId", "")).zfill(2)
            card_id = str(row.get("enzaId", ""))
            name = row.get("dressName")
            if idol_id and card_id and isinstance(name, str) and name.strip():
                result.setdefault((idol_id, card_id), name.strip())
    return result


def profile_character_ui_assets(profile: Mapping[str, Any]) -> dict[str, str]:
    idol_id = int(profile["idolId"])
    number = 790001 if idol_id == 91 else 700001 + idol_id * 1000
    chat_number = 90 if idol_id == 91 else idol_id
    prefix = "asset://shinycolors-ui-v1/ui"
    return {
        "portrait": f"{prefix}/character-portraits/cb_icon_stand_{number}.png",
        "profile_background": (
            f"{prefix}/profile-backgrounds/chain_profile_bg_{chat_number:02d}.png"
        ),
        "chat_background": (
            f"{prefix}/chat-backgrounds/chain_talk_bg_{chat_number:05d}.png"
        ),
        "chat_icon": f"{prefix}/chat-icons/ChainChrIcon_{chat_number:05d}.png",
    }


def profile_unit_ui_assets(profile: Mapping[str, Any]) -> dict[str, str]:
    unit_id = int(profile["unitId"])
    icon_number = 0 if unit_id == 81 else unit_id
    return {
        "icon": (
            "asset://shinycolors-ui-v1/ui/unit-icons/"
            f"unit_icon_{icon_number:02d}.png"
        )
    }


def _asset_root_from_selection(selected: Path) -> Path:
    selected = selected.expanduser().resolve()
    has_dresses = any(
        path.parent.name == "spine" and path.parent.parent.name.isdigit()
        for path in selected.rglob("dresses.json")
    )
    if has_dresses and discover_idol_assets(selected):
        return selected
    raise ValueError("所選資料夾中找不到可用的 dresses.json 與完整 Spine 3.6 資產")


def update_from_downloaded_folder(
    selected: Path,
    destination: Path,
    profiles: Mapping[str, Mapping[str, Any]] = {},
    progress: Callable[[int, int, str], None] | None = None,
) -> tuple[Path, ...]:
    """Generate manifests for every complete model described by the extracted folder."""
    asset_root = _asset_root_from_selection(selected)
    dress_names = _dress_metadata(asset_root)
    outputs: list[Path] = []
    assets = discover_idol_assets(asset_root)
    total = len(assets)
    if progress is not None:
        progress(0, total, "準備複製模型…")
    for index, asset in enumerate(assets):
        profile = profiles.get(asset.idol_id, {})
        character_name = str(profile.get("idolName") or f"偶像 {asset.idol_id}")
        unit_number = int(profile.get("unitId", 0))
        unit_id = f"unit-{unit_number:02d}" if unit_number else "unit-unassigned"
        unit_name = str(profile.get("unit", {}).get("unitName") or "未分類")
        presentation, costume_mode = _VARIANT_AXES[asset.variant]
        outfit_name = dress_names.get((asset.idol_id, asset.card_id), asset.card_id)
        outputs.append(update_managed_model(ManagedModelInput(
            character_id=f"idol-{int(asset.idol_id):02d}",
            display_name=character_name,
            unit_id=unit_id,
            unit_name=unit_name,
            outfit_id=f"card-{asset.card_id}",
            outfit_name=outfit_name,
            presentation=presentation,
            costume_mode=costume_mode,
            asset_directory=asset.directory,
            sort_order=index,
            ui_assets=profile_character_ui_assets(profile) if profile else {},
            unit_ui_assets=profile_unit_ui_assets(profile) if profile else {},
        ), destination))
        if progress is not None:
            progress(index + 1, total, f"{character_name} · {outfit_name} · {asset.variant_label}")
    return tuple(outputs)
