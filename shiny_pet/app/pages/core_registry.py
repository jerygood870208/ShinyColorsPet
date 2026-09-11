"""Register the core navigation pages."""

from __future__ import annotations

from typing import Any

from .about import build_about_page
from .actions_expressions import build_actions_expressions_page
from .activity_log import build_activity_log_page
from .asset_management import build_asset_management_page
from .character_add import build_character_add_page
from .display_settings import build_display_settings_page
from .home_page import build_home_page
from .outfit_management import build_outfit_management_page


def install_core_pages(panel: Any, settings: dict[str, Any]) -> None:
    """Build core pages in navigation order."""
    build_home_page(panel, settings)
    build_character_add_page(panel, settings)
    build_outfit_management_page(panel, settings)
    build_actions_expressions_page(panel, settings)
    build_display_settings_page(panel, settings)
    build_asset_management_page(panel, settings)
    build_activity_log_page(panel, settings)
    build_about_page(panel, settings)
