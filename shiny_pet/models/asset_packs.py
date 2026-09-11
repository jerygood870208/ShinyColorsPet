"""Discover public and local-only asset packs without pack shadowing or path escape."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PACK_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_ASSET_REF = re.compile(r"^asset://(?P<pack>[a-z0-9][a-z0-9._-]*)/(?P<path>.+)$")


@dataclass(frozen=True, slots=True)
class AssetPack:
    pack_id: str
    root: Path
    manifest: Mapping[str, Any]
    bundled: bool
    files: Mapping[str, str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("asset pack file path must be a non-empty POSIX path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or Path(value).is_absolute():
        raise ValueError(f"asset pack contains an unsafe file path: {value!r}")
    return value


def default_external_roots(
    repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[Path, ...]:
    """Return development, installed-user, and explicitly configured local pack roots."""
    values = os.environ if environ is None else environ
    roots: list[Path] = []
    if repository_root is not None:
        roots.append(repository_root.resolve() / "local-assets" / "asset-packs")
    local_app_data = values.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        roots.append(Path(local_app_data).expanduser() / "ShinyColorsPet" / "asset-packs")
    configured = values.get("SHINY_PET_ASSET_ROOTS", "")
    roots.extend(
        Path(item).expanduser()
        for item in configured.split(os.pathsep)
        if item.strip()
    )
    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return tuple(unique)


def _load_pack(root: Path, *, bundled: bool) -> AssetPack:
    manifest_path = root / "asset-pack.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read asset pack manifest {manifest_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"asset pack manifest must be an object: {manifest_path}")
    pack_id = payload.get("pack_id")
    if not isinstance(pack_id, str) or not _PACK_ID.fullmatch(pack_id):
        raise ValueError(f"asset pack has an invalid pack_id: {manifest_path}")
    if root.name != pack_id:
        raise ValueError(f"asset pack directory must match pack_id {pack_id!r}: {root}")
    if payload.get("schema_version") != 1:
        raise ValueError(f"asset pack has an unsupported schema version: {manifest_path}")
    review = payload.get("review")
    if not isinstance(review, dict) or review.get("status") not in {"approved", "internal_only"}:
        raise ValueError(f"asset pack is not approved for local use: {manifest_path}")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise ValueError(f"asset pack files must be an array: {manifest_path}")
    files: dict[str, str] = {}
    for item in raw_files:
        if not isinstance(item, dict):
            raise ValueError(f"asset pack contains an invalid file record: {manifest_path}")
        relative = _safe_relative_path(item.get("path"))
        digest = item.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError(f"asset pack contains an invalid SHA-256: {relative}")
        if relative in files:
            raise ValueError(f"asset pack declares a duplicate file: {relative}")
        if not (root / relative).is_file():
            raise ValueError(f"asset pack is missing a declared file: {relative}")
        files[relative] = digest
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "asset-pack.json"
    }
    unexpected = sorted(actual_files.difference(files))
    if unexpected:
        raise ValueError(f"asset pack contains undeclared files: {', '.join(unexpected)}")
    return AssetPack(pack_id, root.resolve(), payload, bundled, files)


def discover_asset_packs(
    bundled_root: Path,
    external_roots: Sequence[Path] = (),
) -> tuple[dict[str, AssetPack], dict[str, str]]:
    """Discover packs in priority order; duplicate IDs are rejected instead of shadowed."""
    packs: dict[str, AssetPack] = {}
    errors: dict[str, str] = {}
    locations = [(bundled_root, True), *((root, False) for root in external_roots)]
    for parent, bundled in locations:
        if not parent.is_dir():
            continue
        for child in sorted(path for path in parent.iterdir() if path.is_dir()):
            try:
                pack = _load_pack(child, bundled=bundled)
                if pack.pack_id in packs:
                    raise ValueError(
                        f"duplicate asset pack ID {pack.pack_id!r}; refusing to shadow "
                        f"{packs[pack.pack_id].root}"
                    )
                packs[pack.pack_id] = pack
            except ValueError as exc:
                errors[str(child.resolve())] = str(exc)
    return packs, errors


def resolve_asset_ref(reference: str, packs: Mapping[str, AssetPack]) -> Path:
    match = _ASSET_REF.fullmatch(reference)
    if match is None:
        raise ValueError("asset reference must use asset://<pack-id>/<relative-path>")
    pack_id = match.group("pack")
    pack = packs.get(pack_id)
    if pack is None:
        raise FileNotFoundError(f"asset pack is not installed: {pack_id}")
    raw_path = match.group("path")
    _safe_relative_path(raw_path)
    if raw_path not in pack.files:
        raise FileNotFoundError(f"asset is not declared by its pack: {reference}")
    relative = Path(raw_path)
    resolved = (pack.root / relative).resolve()
    try:
        resolved.relative_to(pack.root)
    except ValueError as exc:
        raise ValueError("asset reference escapes its pack") from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"asset does not exist: {reference}")
    if _sha256(resolved) != pack.files[raw_path]:
        raise ValueError(f"asset checksum does not match its pack: {reference}")
    return resolved
