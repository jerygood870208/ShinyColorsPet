"""Register external reviewed manifests without copying third-party assets."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .abilities import resolve_abilities
from .manifest import load_manifest
from .textures import resolve_textures


@dataclass(frozen=True)
class CatalogEntry:
    path: Path
    character_id: str
    display_name: str
    diagnostics: tuple[str, ...]


class ModelCatalog:
    def __init__(self, decodable: Callable[[Path], bool]) -> None:
        self.decodable = decodable

    def inspect(self, path: Path) -> CatalogEntry:
        manifest = load_manifest(path)
        abilities = resolve_abilities(manifest)
        resolve_textures(manifest, self.decodable)
        return CatalogEntry(path.resolve(), manifest.character_id, manifest.display_name,
                            abilities.warnings)

    def scan(self, root: Path) -> tuple[list[CatalogEntry], dict[str, str]]:
        entries = []
        errors = {}
        for path in sorted(root.rglob("*.yaml")):
            try:
                entries.append(self.inspect(path))
            except (OSError, ValueError) as exc:
                errors[str(path)] = str(exc)
        return entries, errors
