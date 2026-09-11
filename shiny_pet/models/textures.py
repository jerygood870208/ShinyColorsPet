"""Resolve decodable atlas pages, with single-page preferred/PNG fallback."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .asset_audit import _atlas_pages
from .manifest import Manifest, ManifestError


def resolve_textures(manifest: Manifest, decodable: Callable[[Path], bool]) -> dict[str, Path]:
    root = manifest.spine.atlas.parent.resolve()
    pages = _atlas_pages(manifest.spine.atlas.read_text(encoding="utf-8-sig"))
    if not pages:
        raise ManifestError("atlas has no texture pages")
    result = {}
    for page in pages:
        actual = (root / page).resolve()
        if not actual.is_relative_to(root):
            raise ManifestError("atlas texture page escapes its directory")
        candidates = (
            [manifest.spine.texture_preferred, actual, manifest.spine.texture_fallback]
            if len(pages) == 1
            else [actual]
        )
        selected = next((p for p in candidates if p and p.is_file() and decodable(p)), None)
        if selected is None:
            raise ManifestError(f"texture unavailable or undecodable: {page}")
        result[page] = selected
    return result
