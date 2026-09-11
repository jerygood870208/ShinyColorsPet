"""Register every user-facing settings page."""

from __future__ import annotations

from typing import Any

from shiny_pet.i18n import tr

from .asr_settings import _install_asr
from .chat_history import _install_chat_history
from .data_management import _install_data_management
from .llm_settings import _install_llm
from .memory import _install_memory
from .memory_album import _install_memory_album
from .persona_settings import _install_persona
from .producer_profile import _install_producer_profile
from .relationship_guide import _install_relationship_guide
from .statistics import _install_statistics
from .tts_settings import _install_tts
from .window_settings import _install_floating

# Unfinished public navigation pages are kept in source for continued development.
# from .chat_integration import _install_chat_integration
# from .reminders import _install_reminders
# from .screen_tools import _install_screen_tools


def install_settings_pages(panel: Any) -> None:
    """Install navigation destinations in their intended display order."""
    panel.nav_buttons["home"].setText(tr("角色列表"))
    panel.nav_buttons["actions"].setText(tr("角色行為"))
    panel.nav_buttons["assets"].setText(tr("模型與資產"))

    _install_memory(panel)
    _install_relationship_guide(panel)
    # _install_reminders(panel)  # Alarm / Pomodoro is not release-ready yet.
    _install_chat_history(panel)
    _install_memory_album(panel)
    _install_statistics(panel)
    _install_llm(panel)
    _install_floating(panel)
    # _install_screen_tools(panel)  # MCP and screen tools are not release-ready yet.
    _install_tts(panel)
    _install_asr(panel)
    _install_producer_profile(panel)
    _install_persona(panel)
    # _install_chat_integration(panel)  # Chat-platform integration is not release-ready yet.
    _install_data_management(panel)
    for key in ("add", "outfit", "activity"):
        panel.nav_buttons[key].hide()
    display = panel.nav_buttons["display"]
    panel.nav_layout.removeWidget(display)
    floating_index = panel.nav_layout.indexOf(panel.nav_buttons["floating"])
    panel.nav_layout.insertWidget(floating_index + 1, display)
    panel.translate_widgets()
