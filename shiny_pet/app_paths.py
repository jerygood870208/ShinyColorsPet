"""Resolve and migrate the single ShinyColorsPet per-user data directory."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml


def application_data_root(generic_local_data: str) -> Path:
    """Return `<generic local data>/ShinyColorsPet` without organization duplication."""
    if not generic_local_data.strip():
        raise ValueError("系統未提供可用的本機 AppData 路徑")
    return Path(generic_local_data).expanduser().resolve() / "ShinyColorsPet"


def migrate_duplicated_data_root(root: Path) -> tuple[Path, ...]:
    """Move data from the former `ShinyColorsPet/ShinyColorsPet` layout when safe."""
    root = root.resolve()
    legacy = root / "ShinyColorsPet"
    if not legacy.is_dir():
        return ()
    root.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    for source in sorted(legacy.iterdir()):
        destination = root / source.name
        if destination.exists():
            continue
        os.replace(source, destination)
        moved.append(destination)
    _rewrite_moved_manifest_roots(root, legacy)
    try:
        legacy.rmdir()
    except OSError:
        pass
    return tuple(moved)


def _rewrite_moved_manifest_roots(root: Path, legacy: Path) -> None:
    manifests = root / "manifests"
    if not manifests.is_dir():
        return
    for path in (*manifests.glob("*.yaml"), *manifests.glob("*.yml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("asset_root"), str):
                continue
            old_asset_root = Path(payload["asset_root"]).resolve()
            relative = old_asset_root.relative_to(legacy)
        except (OSError, UnicodeError, yaml.YAMLError, ValueError):
            continue
        payload["asset_root"] = str(root / relative)
        fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                yaml.safe_dump(payload, stream, allow_unicode=True, sort_keys=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
