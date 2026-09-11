"""Conservative local relationship updates; no model-specific dependency."""

from __future__ import annotations

from dataclasses import replace

from shiny_pet.chat.database import Relationship

_POSITIVE = ("謝謝", "喜歡", "開心", "愛你", "thank", "great", "happy", "love")
_NEGATIVE = ("討厭", "生氣", "難過", "hate", "angry", "sad")


def update_from_interaction(relationship: Relationship, text: str) -> Relationship:
    lowered = str(text).lower()
    positive = sum(term in lowered for term in _POSITIVE)
    negative = sum(term in lowered for term in _NEGATIVE)
    delta = min(3, positive) - min(3, negative)
    mood = "happy" if delta > 0 else "sad" if delta < 0 else relationship.mood
    return replace(relationship,
                   affection=max(0, min(100, relationship.affection + delta)), mood=mood)
