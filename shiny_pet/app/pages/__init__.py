"""User-facing settings pages organized by navigation destination."""

from .core_registry import install_core_pages
from .registry import install_settings_pages

__all__ = ["install_core_pages", "install_settings_pages"]
