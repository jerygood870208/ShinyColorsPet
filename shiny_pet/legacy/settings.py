"""Pure settings migration. Unmapped reference values remain recoverable."""

from __future__ import annotations

import calendar
import re
from copy import deepcopy
from datetime import datetime
from typing import Any


def _normalize_birthday(value: object) -> str:
    text = " ".join(str(value or "").strip().split())
    numeric = re.fullmatch(r"(\d{1,2})\s*(?:/|-|月)\s*(\d{1,2})\s*日?", text)
    if numeric:
        month, day = int(numeric.group(1)), int(numeric.group(2))
    else:
        names = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
        names.update(
            {name.casefold(): index for index, name in enumerate(calendar.month_abbr) if name}
        )
        english = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?", text, re.IGNORECASE)
        if not english or english.group(1).casefold() not in names:
            return text
        month, day = names[english.group(1).casefold()], int(english.group(2))
    try:
        datetime(2024, month, day)
    except ValueError:
        return text
    return f"{month:02d}-{day:02d}"


def migrate(payload: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(payload)
    version = result.get("settings_schema_version", 0)
    if type(version) is not int or version not in (0, 1, 2):
        raise ValueError(f"Unsupported settings schema: {version!r}")
    if version == 0:
        mapping = {
            "live2d_quality": "renderer_quality",
            "live2d_scale": "model_scale",
            "live2d_hit_alpha_threshold": "interaction_hit_alpha_threshold",
            "live2d_head_tracking_enabled": "interaction_gaze_enabled",
            "live2d_idle_actions_enabled": "interaction_idle_enabled",
            "live2d_random_actions_enabled": "interaction_random_enabled",
            "hide_live2d_model": "model_hidden",
        }
        archived = result.setdefault("legacy", {})
        if not isinstance(archived, dict):
            raise ValueError("legacy must be an object")
        for old in tuple(result):
            if old.startswith("live2d_") or old == "hide_live2d_model":
                value = result.pop(old)
                archived[old] = value
                if old in mapping:
                    result.setdefault(mapping[old], value)
        for old, new in (("fps", "renderer_fps"), ("vsync", "renderer_vsync")):
            if old in result:
                result.setdefault(new, result.pop(old))
        if result.get("pet_mode") == "live2d":
            archived["pet_mode"] = result.pop("pet_mode")
            result.setdefault("model_mode", "spine")
        # The reference uses 0 as auto scale, not a zero-sized window.
        if result.get("model_scale") == 0:
            result["model_scale"] = 1.0
    # Keep the on-disk marker compatible with the previous public build.  The
    # v2 change only added an idempotent birthday normalization and did not
    # introduce a representation that older readers cannot safely preserve.
    # Older builds reject an unknown schema before they get a chance to ignore
    # the newer optional keys, so writing v1 here permits side-by-side use.
    result["settings_schema_version"] = 1
    result.setdefault("ui_language", "zh-TW")
    result.setdefault("renderer_fps", 60)
    result.setdefault("renderer_vsync", True)
    result.setdefault("renderer_quality", "balanced")
    result.setdefault("model_scale", 1.0)
    result.setdefault("interaction_hit_test_mode", "auto")
    result.setdefault("interaction_debug_hit_areas", False)
    result.setdefault("interaction_gaze_enabled", True)
    result.setdefault("interaction_idle_enabled", True)
    result.setdefault("interaction_random_enabled", True)
    result.setdefault("interaction_random_interval_seconds", 30)
    result.setdefault("pets", [])
    result.setdefault("catalog", [])
    result.setdefault("asset_pack_roots", [])
    result.setdefault("character_default_outfits", {})
    result.setdefault("character_semantic_preferences", {})
    result.setdefault("chat_history_limit", 24)
    result.setdefault("chat_debug_enabled", False)
    # POV profiles were removed in favour of one local producer profile.
    result.pop("pov_name", None)
    result.setdefault("producer_name", "")
    result.setdefault("producer_birthday", "")
    result["producer_birthday"] = _normalize_birthday(result["producer_birthday"])
    result.setdefault("producer_age", 0)
    result.setdefault("producer_details", "")
    result.setdefault("llm_api_url", "")
    if result.get("llm_provider") not in {"openai_compatible", "openai_oauth_proxy"}:
        result["llm_provider"] = "openai_compatible"
    result.setdefault("openai_oauth_personal_use_accepted", False)
    result.pop("google_api_key_file", None)
    result.pop("google_model", None)
    result.setdefault("llm_model", "")
    result.setdefault("llm_api_key", "")
    result.setdefault("llm_temperature", 0.6)
    result.setdefault("llm_max_tokens", 512)
    result.setdefault("llm_timeout_seconds", 180)
    result.setdefault("tts_enabled", False)
    result.setdefault("tts_provider", "irodori_local")
    if result["tts_provider"] in {"auto", "qwen_local"}:
        result["tts_provider"] = "irodori_local"
    result.setdefault("tts_api_url", "")
    result.setdefault("tts_api_key", "")
    result.setdefault("tts_voice", "")
    result.setdefault("tts_model", "tts-1")
    result.setdefault("tts_reference_root", "audio_reference")
    result.setdefault("tts_language", "Japanese")
    result.setdefault("voice_cache_cleanup_mode", "on_exit")
    result.setdefault("voice_cache_max_gb", 2.0)
    result.setdefault("asr_enabled", False)
    result.setdefault("asr_api_url", "")
    result.setdefault("asr_api_key", "")
    result.setdefault(
        "asr_provider",
        "openai_compatible" if result["asr_api_url"].strip() else "local_whisper",
    )
    result.setdefault("asr_model", "Systran/faster-whisper-large-v3")
    if result["asr_provider"] == "local_whisper" and result["asr_model"] == "whisper-1":
        result["asr_model"] = "Systran/faster-whisper-large-v3"
    result.setdefault("asr_language", "")
    result.setdefault("asr_input_device", -1)
    result.setdefault("asr_compute_device", "auto")
    result.setdefault("asr_timeout_seconds", 600)
    result.setdefault("character_persona_presets", {})
    result.setdefault("character_persona_active", {})
    result.setdefault("souls_root", "souls")
    result.setdefault("screen_awareness_enabled", False)
    result.setdefault("screen_awareness_include_window_title", False)
    result.setdefault("screen_awareness_max_screenshot_width", 1280)
    result.setdefault("reminders", [])
    result.pop("agent_tasks", None)
    result.setdefault("character_weekly_routines", [])
    result.setdefault("character_calendar", [])
    result.setdefault("character_diaries", [])
    for retired_key in (
        "google_calendar_enabled",
        "google_calendar_credentials",
        "google_calendar_events",
        "google_calendar_last_sync",
    ):
        result.pop(retired_key, None)
    result.setdefault("mcp_servers", [])
    result.setdefault("chat_integration_enabled", False)
    result.setdefault("chat_integration_host", "127.0.0.1")
    result.setdefault("chat_integration_port", 17384)
    result.setdefault("chat_integration_token", "")
    # Compatibility for settings written by early desktop-supervisor builds.
    # build before the user-facing Q版/chibi terminology was fixed.
    if isinstance(result["pets"], list):
        for pet in result["pets"]:
            if isinstance(pet, dict) and pet.get("mode") == "pixel":
                pet["mode"] = "chibi"
    return result
