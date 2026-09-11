# Application source map

The application package is organized by product responsibility rather than implementation phase.

## Composition and shell

- `shiny_pet/app/companion_app.py` composes chat, reminders, integrations, TTS, and ASR into the
  desktop application.
- `shiny_pet/app/desktop_panel.py` owns the navigation shell, pet-process supervision, catalog
  selection, model management, settings persistence, and system tray.
- `shiny_pet/app/pages/registry.py` registers settings and data pages in navigation order.
- `shiny_pet/app/pages/core_registry.py` registers the core character, model, display, activity,
  and about pages.

## Pages

Every navigation destination has one module under `shiny_pet/app/pages/`:

- Character lifecycle: `home_page.py`, `character_add.py`, `outfit_management.py`, and
  `actions_expressions.py`.
- Model and display management: `display_settings.py`, `window_settings.py`, and
  `asset_management.py`.
- Conversation and relationship data: `memory.py`, `relationship_guide.py`, `chat_history.py`,
  `memory_album.py`, and `statistics.py`.
- AI and external context: `llm_settings.py`, `persona_settings.py`, `producer_profile.py`,
  `screen_tools.py`, and `chat_integration.py`.
- Voice: `tts_settings.py` and `asr_settings.py`.
- Productivity and storage: `reminders.py` and `data_management.py`.
- Diagnostics and project information: `activity_log.py` and `about.py`.

Page modules build widgets and connect them to the control panel's public controller methods. Shared
card, heading, save-button, and character-selector helpers live in `pages/_shared.py`; product logic
belongs in the existing `chat`, `models`, `voice`, `process`, `renderer`, and `settings` packages.

Tests, QA records, generated screenshots, local fixtures, and migration utilities are maintained in
the separate `ShinyColorsPetDev` repository.
