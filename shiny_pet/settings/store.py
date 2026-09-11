"""Backup-before-migration and atomic replace, adapted from BANDORI-PET-REV (GPL-3.0)."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

from shiny_pet.i18n import SUPPORTED_LANGUAGES
from shiny_pet.legacy.settings import migrate


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    result = migrate(payload)
    if result["ui_language"] not in dict(SUPPORTED_LANGUAGES):
        raise ValueError("ui_language must be one of the supported locales")
    fps = result["renderer_fps"]
    scale = result["model_scale"]
    if type(fps) is not int or not 1 <= fps <= 120:
        raise ValueError("renderer_fps must be 1–120")
    if (isinstance(scale, bool) or not isinstance(scale, (int, float))
            or not math.isfinite(scale) or not 0.1 <= scale <= 4):
        raise ValueError("model_scale must be 0.1–4")
    if type(result["renderer_vsync"]) is not bool:
        raise ValueError("renderer_vsync must be boolean")
    if result["renderer_quality"] not in ("low", "balanced", "high"):
        raise ValueError("Unknown renderer_quality")
    if result["interaction_hit_test_mode"] not in ("auto", "attachment", "model-bounds"):
        raise ValueError("unknown interaction_hit_test_mode")
    random_interval = result["interaction_random_interval_seconds"]
    if type(random_interval) is not int or not 5 <= random_interval <= 600:
        raise ValueError("interaction_random_interval_seconds must be 5–600")
    for key in ("pets", "catalog", "asset_pack_roots"):
        if not isinstance(result[key], list):
            raise ValueError(f"{key} must be a list")
    history_limit = result["chat_history_limit"]
    if type(history_limit) is not int or not 1 <= history_limit <= 1_000_000:
        raise ValueError("chat_history_limit must be 1–1000000")
    temperature = result["llm_temperature"]
    if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature) or not 0 <= temperature <= 2):
        raise ValueError("llm_temperature must be between 0 and 2")
    max_tokens = result["llm_max_tokens"]
    if type(max_tokens) is not int or not 16 <= max_tokens <= 1_000_000:
        raise ValueError("llm_max_tokens must be 16–1000000")
    timeout = result["llm_timeout_seconds"]
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 5 <= timeout <= 600):
        raise ValueError("llm_timeout_seconds must be between 5 and 600")
    for key in (
        "llm_api_url", "llm_provider", "llm_model", "llm_api_key",
        "tts_provider", "tts_api_url", "tts_api_key", "tts_voice",
        "tts_model", "tts_reference_root", "tts_language", "souls_root",
        "asr_api_url", "asr_api_key", "asr_model", "asr_language", "asr_provider",
        "asr_compute_device",
        "chat_integration_host", "chat_integration_token",
        "producer_name", "producer_birthday", "producer_details",
    ):
        if not isinstance(result[key], str):
            raise ValueError(f"{key} must be text")
    if result["llm_provider"] not in {"openai_compatible", "openai_oauth_proxy"}:
        raise ValueError("unknown llm_provider")
    producer_age = result["producer_age"]
    if type(producer_age) is not int or not 0 <= producer_age <= 150:
        raise ValueError("producer_age must be 0–150")
    if result["tts_provider"] not in {"irodori_local", "openai_compatible"}:
        raise ValueError("tts_provider must be irodori_local or openai_compatible")
    if result["voice_cache_cleanup_mode"] not in {"never", "size_limit", "on_exit"}:
        raise ValueError("unknown voice_cache_cleanup_mode")
    voice_cache_max_gb = result["voice_cache_max_gb"]
    if (
        isinstance(voice_cache_max_gb, bool)
        or not isinstance(voice_cache_max_gb, (int, float))
        or not math.isfinite(voice_cache_max_gb)
        or not 0.1 <= voice_cache_max_gb <= 1000
    ):
        raise ValueError("voice_cache_max_gb must be between 0.1 and 1000")
    if result["asr_provider"] not in {"local_whisper", "openai_compatible"}:
        raise ValueError("asr_provider must be local_whisper or openai_compatible")
    if result["asr_compute_device"] not in {"auto", "cpu"}:
        raise ValueError("asr_compute_device must be auto or cpu")
    for key in (
        "tts_enabled", "asr_enabled", "screen_awareness_enabled",
        "screen_awareness_include_window_title", "chat_integration_enabled",
        "openai_oauth_personal_use_accepted",
        "interaction_debug_hit_areas", "interaction_gaze_enabled",
        "interaction_idle_enabled", "interaction_random_enabled",
        "chat_debug_enabled",
    ):
        if type(result[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    input_device = result["asr_input_device"]
    if type(input_device) is not int or input_device < -1:
        raise ValueError("asr_input_device must be -1 or a non-negative device index")
    asr_timeout = result["asr_timeout_seconds"]
    if (isinstance(asr_timeout, bool) or not isinstance(asr_timeout, (int, float))
            or not math.isfinite(asr_timeout) or not 5 <= asr_timeout <= 1200):
        raise ValueError("asr_timeout_seconds must be between 5 and 1200")
    for key in ("reminders", "mcp_servers"):
        if not isinstance(result[key], list):
            raise ValueError(f"{key} must be a list")
    screenshot_width = result["screen_awareness_max_screenshot_width"]
    if type(screenshot_width) is not int or not 640 <= screenshot_width <= 1920:
        raise ValueError("screen_awareness_max_screenshot_width must be 640-1920")
    if result["chat_integration_host"] not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("chat_integration_host must be a loopback address")
    integration_port = result["chat_integration_port"]
    if type(integration_port) is not int or not 1024 <= integration_port <= 65535:
        raise ValueError("chat_integration_port must be 1024-65535")
    for item in result["catalog"]:
        if not isinstance(item, str):
            raise ValueError("catalog entries must be manifest paths")
    for item in result["asset_pack_roots"]:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("asset_pack_roots entries must be non-empty paths")
    default_outfits = result["character_default_outfits"]
    if not isinstance(default_outfits, dict):
        raise ValueError("character_default_outfits must be an object")
    for character_id, presentations in default_outfits.items():
        if not isinstance(character_id, str) or not character_id.strip():
            raise ValueError("character_default_outfits keys must be character ids")
        if not isinstance(presentations, dict):
            raise ValueError("character default outfits must be grouped by presentation")
        for presentation, selection in presentations.items():
            if presentation not in ("standard", "chibi") or not isinstance(selection, dict):
                raise ValueError("invalid character default outfit presentation")
            if set(selection) != {"outfit_id", "costume_mode"}:
                raise ValueError("character default outfit requires outfit_id and costume_mode")
            if not all(isinstance(selection[key], str) and selection[key].strip()
                       for key in ("outfit_id", "costume_mode")):
                raise ValueError("character default outfit values must be non-empty text")
    for pet in result["pets"]:
        if not isinstance(pet, dict) or pet.get("mode") not in ("spine", "chibi"):
            raise ValueError("Invalid pet record")
        catalog_fields = ("character_id", "outfit_id", "presentation", "costume_mode")
        is_catalog_pet = all(isinstance(pet.get(key), str) and pet[key] for key in catalog_fields)
        if not is_catalog_pet and (not isinstance(pet.get("path"), str) or not pet["path"]):
            raise ValueError("Pet requires a path or complete catalog selection")
        if pet["mode"] == "chibi" and not isinstance(pet.get("frames"), str):
            raise ValueError("Q版模式 requires frames")
        for key in ("x", "y"):
            if key in pet and type(pet[key]) is not int:
                raise ValueError(f"Pet {key} must be an integer")
    return result


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return validate({})
        original = self.path.read_bytes()
        payload = json.loads(original.decode("utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("Settings must contain an object")
        result = validate(payload)
        if payload.get("settings_schema_version", 0) == 0:
            backup = self.path.with_name(self.path.name + ".pre-v1.bak")
            # Never replace a previous migration backup.
            if not backup.exists():
                with backup.open("xb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
            self.save(result)
        return result

    def save(self, payload: dict[str, Any]) -> None:
        result = validate(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp",
                                         dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
