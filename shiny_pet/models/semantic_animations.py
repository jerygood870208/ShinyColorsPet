"""Map Shiny Colors Spine animation names to dialogue-safe semantics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# These names were verified against the stand rigs for idols 01, 03 and 91.
# Every generated group is filtered against the current skeleton, so outfits
# with a smaller animation set never advertise an unavailable action.
_GESTURE_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    "happy": ("smile1", "smile2", "smile3", "smile4"),
    "sad": ("sad1", "sad2"),
    "angry": ("anger1", "anger2", "anger3"),
    "surprised": ("surp1", "surp2"),
    "shy": ("shy1", "shy2", "shy3"),
    "thinking": ("think",),
    "agree": ("yes", "yes2"),
    "disagree": ("no", "no2"),
    "sleepy": ("sleep1", "sleep2", "sleep3"),
}

_EXPRESSION_CANDIDATES: Mapping[str, tuple[str, ...]] = {
    "neutral": ("face_wait",),
    "happy": ("face_smile", "face_smile1", "face_smile2", "face_smile3"),
    "sad": ("face_sad", "face_sad2"),
    "angry": ("face_anger", "face_anger2", "face_anger3"),
    "surprised": ("face_surp", "face_surp2"),
    "shy": ("face_shy", "face_shy2"),
    "crying": ("face_cry",),
    "serious": ("face_serious",),
}


def dialogue_animation_groups(names: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """Return only semantic gesture groups supported by this skeleton."""
    available = set(names)
    groups: dict[str, list[dict[str, Any]]] = {}
    idle = sorted(name for name in available if name.startswith("wait"))
    base_groups: Sequence[tuple[str, Sequence[str], bool]] = (
        ("idle", idle, True),
        ("random", idle, False),
        ("click", ("touch",), False),
        ("greeting", ("hello",), False),
        *((semantic, candidates, False)
          for semantic, candidates in _GESTURE_CANDIDATES.items()),
    )
    for semantic, candidates, loop in base_groups:
        selected = [name for name in candidates if name in available]
        if selected:
            groups[semantic] = [
                {"name": name, "weight": 1.0, "loop": loop} for name in selected
            ]
    return groups


def dialogue_expressions(names: Iterable[str]) -> dict[str, dict[str, str]]:
    """Keep raw face names and add stable semantic aliases for the chat model."""
    available = set(names)
    expressions = {
        name.removeprefix("face_"): {"animation": name, "channel": "face"}
        for name in sorted(available)
        if name.startswith("face_")
    }
    for semantic, candidates in _EXPRESSION_CANDIDATES.items():
        animation = next((name for name in candidates if name in available), None)
        if animation is not None:
            expressions[semantic] = {"animation": animation, "channel": "face"}
    return expressions


def dialogue_gaze(names: Iterable[str]) -> dict[str, str]:
    """Use the common Shiny Colors eye-direction animations when all are present."""
    available = set(names)
    required = {"eye_left", "eye_front", "eye_right"}
    if not required.issubset(available):
        return {"driver": "disabled", "reason": "No complete eye direction animation set"}
    return {
        "driver": "animation_choice",
        "channel": "gaze",
        "left": "eye_left",
        "center": "eye_front",
        "right": "eye_right",
    }
