"""Verify the deny-by-default release asset allowlist and every declared file hash."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def validate_release(repository: Path) -> list[str]:
    repository = repository.resolve()
    errors: list[str] = []
    try:
        allowlist = _load_object(repository / "packaging" / "release-assets.json")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        return [f"cannot read release allowlist: {exc}"]
    raw_ids = allowlist.get("approved_pack_ids")
    if not isinstance(raw_ids, list) or not all(isinstance(item, str) for item in raw_ids):
        return ["approved_pack_ids must be an array of strings"]
    if len(set(raw_ids)) != len(raw_ids):
        errors.append("approved_pack_ids contains duplicates")

    packs_root = repository / "asset-packs"
    existing_ids = {
        path.name for path in packs_root.iterdir() if path.is_dir()
    } if packs_root.is_dir() else set()
    unlisted = sorted(existing_ids - set(raw_ids))
    if unlisted:
        errors.append("asset pack directories are not allowlisted: " + ", ".join(unlisted))

    for pack_id in raw_ids:
        pack_root = packs_root / pack_id
        manifest_path = pack_root / "asset-pack.json"
        try:
            manifest = _load_object(manifest_path)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
            errors.append(f"cannot read asset pack {pack_id}: {exc}")
            continue
        if manifest.get("pack_id") != pack_id:
            errors.append(f"asset pack directory/manifest ID mismatch: {pack_id}")
        review = manifest.get("review")
        if not isinstance(review, dict) or review.get("status") != "approved":
            errors.append(f"asset pack is not approved: {pack_id}")
        elif review.get("redistribution_scope") not in {"packaged_only", "source_and_packaged"}:
            errors.append(f"asset pack is not approved for packaged redistribution: {pack_id}")
        raw_files = manifest.get("files")
        if not isinstance(raw_files, list):
            errors.append(f"asset pack files must be an array: {pack_id}")
            continue

        declared: set[Path] = set()
        for index, entry in enumerate(raw_files):
            if not isinstance(entry, dict):
                errors.append(f"asset pack {pack_id} files[{index}] must be an object")
                continue
            relative = entry.get("path")
            expected_hash = entry.get("sha256")
            if not isinstance(relative, str) or "\\" in relative:
                errors.append(f"asset pack {pack_id} files[{index}] has an invalid path")
                continue
            if any(part in {"", ".", ".."} for part in relative.split("/")):
                errors.append(f"asset pack {pack_id} files[{index}] has an unsafe path")
                continue
            relative_path = Path(relative)
            if relative_path.is_absolute():
                errors.append(f"asset pack {pack_id} files[{index}] has an unsafe path")
                continue
            target = (pack_root / relative_path).resolve()
            try:
                target.relative_to(pack_root.resolve())
            except ValueError:
                errors.append(f"asset pack {pack_id} files[{index}] escapes its pack")
                continue
            if target in declared:
                errors.append(f"asset pack {pack_id} declares a duplicate path: {relative}")
                continue
            declared.add(target)
            if not target.is_file():
                errors.append(f"asset pack {pack_id} is missing: {relative}")
            elif not isinstance(expected_hash, str) or _sha256(target) != expected_hash:
                errors.append(f"asset pack {pack_id} hash mismatch: {relative}")

        actual = {
            path.resolve()
            for path in pack_root.rglob("*")
            if path.is_file() and path.name != "asset-pack.json"
        }
        extras = sorted(path.relative_to(pack_root).as_posix() for path in actual - declared)
        if extras:
            errors.append(f"asset pack {pack_id} has undeclared files: " + ", ".join(extras))

    try:
        runtime_allowlist = _load_object(repository / "packaging" / "release-runtime.json")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        errors.append(f"cannot read runtime allowlist: {exc}")
        return errors
    runtime_entries = runtime_allowlist.get("files")
    if not isinstance(runtime_entries, list):
        errors.append("runtime allowlist files must be an array")
        return errors
    declared_runtime: set[Path] = set()
    for index, entry in enumerate(runtime_entries):
        if not isinstance(entry, dict):
            errors.append(f"runtime allowlist files[{index}] must be an object")
            continue
        relative = entry.get("path")
        expected_hash = entry.get("sha256")
        if not isinstance(relative, str) or "\\" in relative or any(
            part in {"", ".", ".."} for part in relative.split("/")
        ):
            errors.append(f"runtime allowlist files[{index}] has an unsafe path")
            continue
        target = (repository / relative).resolve()
        vendor_root = (repository / "vendor" / "spine-runtime-3.6").resolve()
        try:
            target.relative_to(vendor_root)
        except ValueError:
            errors.append(f"runtime allowlist path is outside the minimal runtime: {relative}")
            continue
        if target in declared_runtime:
            errors.append(f"runtime allowlist declares a duplicate path: {relative}")
            continue
        declared_runtime.add(target)
        if not target.is_file():
            errors.append(f"runtime allowlist file is missing: {relative}")
        elif not isinstance(expected_hash, str) or _sha256(target) != expected_hash:
            errors.append(f"runtime allowlist hash mismatch: {relative}")
    actual_runtime = {
        path.resolve()
        for path in (repository / "vendor" / "spine-runtime-3.6").rglob("*")
        if path.is_file()
    }
    runtime_extras = sorted(
        path.relative_to(repository).as_posix() for path in actual_runtime - declared_runtime
    )
    if runtime_extras:
        errors.append("minimal runtime has undeclared files: " + ", ".join(runtime_extras))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args(argv)
    errors = validate_release(args.repository)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("release asset/runtime allowlists and hashes are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
