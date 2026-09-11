"""cx_Freeze configuration for a deny-by-default public ShinyColorsPet build."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from cx_Freeze import Executable, setup

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build" / "ShinyColorsPet"


def _load_allowlisted_files(filename: str) -> list[tuple[str, str]]:
    payload = json.loads((ROOT / "packaging" / filename).read_text(encoding="utf-8"))
    result: list[tuple[str, str]] = []
    for item in payload["files"]:
        path = ROOT / item["path"]
        expected = str(item.get("sha256", "")).lower()
        if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"allowlisted file digest mismatch: {item['path']}")
        result.append((str(path), item["path"]))
    return result


def _load_allowlisted_directories(filename: str) -> list[tuple[str, str]]:
    payload = json.loads((ROOT / "packaging" / filename).read_text(encoding="utf-8"))
    result: list[tuple[str, str]] = []
    for relative in payload.get("directories", []):
        path = ROOT / relative
        if not path.is_dir():
            raise ValueError(f"allowlisted directory is missing: {relative}")
        result.append((str(path), relative))
    return result


def _load_asset_packs() -> list[tuple[str, str]]:
    payload = json.loads(
        (ROOT / "packaging" / "release-assets.json").read_text(encoding="utf-8")
    )
    result: list[tuple[str, str]] = []
    for pack_id in payload["approved_pack_ids"]:
        pack_root = ROOT / "asset-packs" / pack_id
        manifest_path = pack_root / "asset-pack.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result.append((str(manifest_path), f"asset-packs/{pack_id}/asset-pack.json"))
        result.extend(
            (
                str(pack_root / item["path"]),
                f"asset-packs/{pack_id}/{item['path']}",
            )
            for item in manifest["files"]
        )
    return result


include_files = [
    *_load_allowlisted_files("release-runtime.json"),
    *_load_allowlisted_directories("release-character-context.json"),
    *_load_allowlisted_files("release-character-context.json"),
    *_load_asset_packs(),
    (str(ROOT / "LICENSE"), "LICENSE"),
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "THIRD_PARTY_NOTICES.md"),
    (str(ROOT / "data" / "catalog.json"), "data/catalog.json"),
    (str(ROOT / "shiny_pet" / "locales"), "lib/shiny_pet/locales"),
    (str(ROOT / "assets" / "icon.png"), "assets/icon.png"),
    (
        str(ROOT / "shiny_pet" / "renderer" / "webengine_spine36.html"),
        "lib/shiny_pet/renderer/webengine_spine36.html",
    ),
    (
        str(ROOT / "shiny_pet" / "renderer" / "clip_boundaries.js"),
        "lib/shiny_pet/renderer/clip_boundaries.js",
    ),
    (
        str(ROOT / "shiny_pet" / "renderer" / "hit_geometry.js"),
        "lib/shiny_pet/renderer/hit_geometry.js",
    ),
    (
        str(ROOT / "shiny_pet" / "renderer" / "semantic_drivers.js"),
        "lib/shiny_pet/renderer/semantic_drivers.js",
    ),
]

setup(
    name="ShinyColorsPet",
    version="0.0.1",
    description="ShinyColorsPet desktop companion",
    options={
        "build_exe": {
            "build_exe": str(BUILD_ROOT),
            "include_files": include_files,
            # Qt 6.11 uses the Windows ICU shim. The Codex host PATH also contains Poppler's
            # unrelated ICU 78 DLLs; allowing cx_Freeze to collect those shadows System32 and
            # makes QtCore fail with ERROR_PROC_NOT_FOUND in the frozen app.
            "bin_excludes": [
                "icudt78.dll",
                "icuuc.dll",
                "libportaudio32bit-asio.dll",
                "libportaudio32bit.dll",
                "libportaudioarm64-asio.dll",
                "libportaudioarm64.dll",
            ],
            # screen_context imports Pillow lazily so startup survives unavailable capture.
            "packages": ["PIL", "numpy", "sounddevice", "soundfile"],
            "excludes": [
                "tkinter",
                "unittest",
                "ctypes.test",
                "numpy._core.tests",
                "sqlite3.test",
            ],
        }
    },
    executables=[Executable(
        str(ROOT / "main.py"),
        base="gui",
        target_name="ShinyColorsPet",
        icon=str(ROOT / "assets" / "icon.ico"),
    )],
)

# Some audio wheels ship repository metadata and binaries for other platforms.
# They are not used by the Windows x64 application and do not belong in a release.
for relative in (
    "lib/_sounddevice_data/portaudio-binaries/.github",
    "lib/_sounddevice_data/portaudio-binaries/README.md",
    "lib/_sounddevice_data/portaudio-binaries/libportaudio.dylib",
    "lib/_sounddevice_data/portaudio-binaries/libportaudio32bit-asio.dll",
    "lib/_sounddevice_data/portaudio-binaries/libportaudio32bit.dll",
    "lib/_sounddevice_data/portaudio-binaries/libportaudioarm64-asio.dll",
    "lib/_sounddevice_data/portaudio-binaries/libportaudioarm64.dll",
):
    target = BUILD_ROOT / relative
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink(missing_ok=True)
