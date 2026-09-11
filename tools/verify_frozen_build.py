"""Verify a cx_Freeze build before packaged UI/model smoke testing."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

BANNED_DLLS = {
    "icudt78.dll",
    "icuuc.dll",
    "libportaudio32bit-asio.dll",
    "libportaudio32bit.dll",
    "libportaudioarm64-asio.dll",
    "libportaudioarm64.dll",
}
BANNED_DIRECTORIES = {
    ".github",
    "local-assets",
    "test",
    "tests",
    "test_spine_data",
    "spine-runtimes-3.6",
    "Qwen3TTS-1.7b-API",
}
BANNED_MODEL_SUFFIXES = {".atlas", ".moc", ".moc3", ".skel"}
SUPPORTED_LOCALES = ("zh-TW", "zh-CN", "ja-JP", "en-US")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(repository: Path, build_root: Path) -> list[str]:
    repository = repository.resolve()
    build_root = build_root.resolve()
    errors: list[str] = []
    executable = build_root / "ShinyColorsPet.exe"
    if not executable.is_file():
        return [f"frozen executable is missing: {executable}"]

    for path in build_root.rglob("*"):
        if path.is_dir() and path.name in BANNED_DIRECTORIES:
            errors.append(f"frozen build contains prohibited directory: {path.name}")
        elif path.is_file() and path.name.lower() in BANNED_DLLS:
            errors.append(f"frozen build contains incompatible host DLL: {path.name}")
        elif path.is_file() and path.suffix.lower() in BANNED_MODEL_SUFFIXES:
            errors.append(f"frozen build contains a non-public model file: {path.name}")

    for allowlist_name in ("release-runtime.json", "release-character-context.json"):
        allowlist = json.loads(
            (repository / "packaging" / allowlist_name).read_text(encoding="utf-8")
        )
        for entry in allowlist["files"]:
            target = build_root / entry["path"]
            if not target.is_file():
                errors.append(f"frozen build is missing allowlisted file: {entry['path']}")
            elif _sha256(target) != entry["sha256"]:
                errors.append(f"frozen allowlisted file hash mismatch: {entry['path']}")
        for relative in allowlist.get("directories", []):
            source_root = repository / relative
            target_root = build_root / relative
            source_files = {
                path.relative_to(source_root): _sha256(path)
                for path in source_root.rglob("*")
                if path.is_file()
            }
            target_files = {
                path.relative_to(target_root): _sha256(path)
                for path in target_root.rglob("*")
                if path.is_file()
            } if target_root.is_dir() else {}
            if source_files != target_files:
                errors.append(
                    f"frozen allowlisted directory differs from source: {relative}"
                )

    for locale_name in SUPPORTED_LOCALES:
        source = repository / "shiny_pet" / "locales" / f"{locale_name}.json"
        target = build_root / "lib" / "shiny_pet" / "locales" / f"{locale_name}.json"
        if not target.is_file():
            errors.append(f"frozen build is missing locale catalog: {locale_name}")
        elif _sha256(source) != _sha256(target):
            errors.append(f"frozen locale catalog hash mismatch: {locale_name}")

    try:
        result = subprocess.run(
            [str(executable), "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        errors.append(f"frozen QtCore import/CLI smoke failed: {exc}")
    else:
        output = result.stdout + result.stderr
        if result.returncode != 0 or "usage: ShinyColorsPet" not in output:
            errors.append(
                "frozen QtCore import/CLI smoke failed: "
                f"exit={result.returncode}, output={output.strip()!r}"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_root", type=Path)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors = verify(args.repository, args.build_root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("frozen build runtime, QtCore import, and exclusion checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
