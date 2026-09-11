"""Dependency-free runtime localization backed by public JSON catalogs."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

SUPPORTED_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("zh-TW", "繁體中文"),
    ("zh-CN", "简体中文"),
    ("ja-JP", "日本語"),
    ("en-US", "English"),
)


def _locale_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "lib" / "shiny_pet" / "locales"
    return Path(__file__).resolve().parent / "locales"


def _load_catalog(locale_name: str) -> Mapping[str, str]:
    path = _locale_root() / f"{locale_name}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
    ):
        raise ValueError(f"invalid locale catalog: {path}")
    return payload


_TRANSLATIONS: Mapping[str, Mapping[str, str]] = {
    code: _load_catalog(code) for code, _label in SUPPORTED_LANGUAGES
}
_locale = "zh-TW"


def set_locale(locale_name: str) -> str:
    """Set and return a supported locale, falling back to Traditional Chinese."""
    global _locale
    _locale = locale_name if locale_name in dict(SUPPORTED_LANGUAGES) else "zh-TW"
    return _locale


def locale() -> str:
    return _locale


def tr(text: str, *, language: str | None = None) -> str:
    """Translate an exact UI string."""
    selected = language if language in dict(SUPPORTED_LANGUAGES) else _locale
    if selected == "zh-TW":
        return text
    catalog = _TRANSLATIONS[selected]
    return catalog.get(text, text)


def tr_dynamic(text: str, *, language: str | None = None) -> str:
    """Translate exact or known fragments in generated status text."""
    selected = language if language in dict(SUPPORTED_LANGUAGES) else _locale
    exact = tr(text, language=selected)
    if exact != text or selected == "zh-TW":
        return exact
    catalog = _TRANSLATIONS[selected]
    translated = text
    for source in sorted(catalog, key=len, reverse=True):
        target = catalog[source]
        if len(source.strip()) >= 2 and source in translated and target != source:
            translated = translated.replace(source, target)
    return translated


def trf(text: str, /, *, language: str | None = None, **values: object) -> str:
    """Translate a format template before substituting its named values."""
    return tr(text, language=language).format(**values)
