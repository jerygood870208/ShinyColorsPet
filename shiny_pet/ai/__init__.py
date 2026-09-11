"""Renderer-neutral conversational AI building blocks."""

from .actions import ActionDirective, ParsedReply, parse_reply
from .llm import (
    ChatClient,
    LLMConfig,
    OpenAICompatibleClient,
    discover_openai_model,
    discover_openai_models,
)
from .persona import PersonaPreset, active_persona, normalize_personas

__all__ = [
    "ActionDirective",
    "ChatClient",
    "LLMConfig",
    "OpenAICompatibleClient",
    "ParsedReply",
    "PersonaPreset",
    "active_persona",
    "discover_openai_model",
    "discover_openai_models",
    "normalize_personas",
    "parse_reply",
]
