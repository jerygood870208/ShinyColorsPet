"""Semantic, weighted playback with independent channel queues and priorities."""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass

from shiny_pet.models import Manifest
from shiny_pet.renderer import PetRenderer, PlaybackToken


@dataclass(frozen=True)
class Request:
    semantic_name: str
    channel: str
    priority: int
    mix_seconds: float


class AnimationController:
    def __init__(
        self, renderer: PetRenderer, manifest: Manifest, *, rng: random.Random | None = None,
        idle_enabled: bool = True, random_enabled: bool = True,
    ) -> None:
        self._renderer = renderer
        self._manifest = manifest
        self._rng = rng or random.Random()
        self._active: dict[str, tuple[PlaybackToken, Request]] = {}
        self._queues: dict[str, list[Request]] = {}
        policy = manifest.raw.get("animation_policy", {})
        self._exclusive = policy.get("mode", "layered") == "exclusive"
        self._policy_mix = float(policy.get("mix_seconds", 0.15))
        self._drag_token: PlaybackToken | None = None
        self._idle_enabled = idle_enabled
        self._random_enabled = random_enabled

    def start_idle(self) -> PlaybackToken | None:
        if not self._idle_enabled:
            return None
        return self.play_group(
            "idle", channel="base", priority=-1, mix_seconds=self._policy_mix
        )

    def ensure_idle(self) -> PlaybackToken | None:
        return None if "base" in self._active else self.start_idle()

    def play_random(self) -> PlaybackToken | None:
        if not self._random_enabled:
            return None
        if any(request.priority >= 0 for _token, request in self._active.values()):
            return None
        return self.play_group(
            "random", channel="base", priority=-1, mix_seconds=self._policy_mix
        )

    def set_behavior(self, *, idle_enabled: bool, random_enabled: bool) -> None:
        self._idle_enabled = idle_enabled
        self._random_enabled = random_enabled
        active = self._active.get("base")
        if not idle_enabled and active is not None and active[1].semantic_name == "idle":
            self._active.pop("base", None)
            self._renderer.clear("base")

    def play_gesture(
        self,
        semantic_name: str,
        *,
        priority: int = 0,
        queue: bool = False,
        mix_seconds: float = 0.1,
    ) -> PlaybackToken | None:
        channel = (
            "base"
            if self._exclusive
            else "gesture" if "gesture" in self._manifest.channels else "base"
        )
        if self._exclusive:
            mix_seconds = self._policy_mix
        return self.play_group(
            semantic_name, channel=channel, priority=priority, queue=queue, mix_seconds=mix_seconds
        )

    def start_drag(self) -> PlaybackToken | None:
        if not self._manifest.animation_group("drag"):
            return None
        self._drag_token = self.play_group(
            "drag", channel="base", priority=100, mix_seconds=0.0
        )
        return self._drag_token

    def finish_drag(self) -> None:
        if self._drag_token is None:
            return
        active = self._active.get("base")
        if active is not None and active[0] == self._drag_token:
            self._active.pop("base", None)
            self._queues.pop("base", None)
            self._renderer.clear("base")
            self.start_idle()
        self._drag_token = None

    def play_group(
        self,
        semantic_name: str,
        *,
        channel: str,
        priority: int = 0,
        queue: bool = False,
        mix_seconds: float = 0.1,
    ) -> PlaybackToken | None:
        if not math.isfinite(mix_seconds) or mix_seconds < 0:
            raise ValueError("mix_seconds must be finite and non-negative")
        if channel not in self._manifest.channels or not self._manifest.animation_group(
            semantic_name
        ):
            logging.getLogger(__name__).warning("Unavailable semantic action: %s", semantic_name)
            return None
        request = Request(semantic_name, channel, priority, mix_seconds)
        active = self._active.get(channel)
        if active and (queue or priority < active[1].priority):
            pending = self._queues.setdefault(channel, [])
            if len(pending) >= 32:
                logging.getLogger(__name__).warning("Animation queue full: %s", channel)
                return None
            pending.append(request)
            return None
        return self._play(request)

    def _play(self, request: Request) -> PlaybackToken:
        choices = self._manifest.animation_group(request.semantic_name)
        choice = self._rng.choices(choices, weights=[c.weight for c in choices], k=1)[0]
        token = self._renderer.play(
            request.channel, choice.name, loop=choice.loop, mix_seconds=request.mix_seconds
        )
        self._active[request.channel] = (token, request)
        return token

    def playback_finished(self, token: PlaybackToken) -> None:
        for channel, (active, _request) in tuple(self._active.items()):
            if token != active:
                continue
            del self._active[channel]
            pending = self._queues.get(channel, [])
            if pending:
                index = max(range(len(pending)), key=lambda i: pending[i].priority)
                self._play(pending.pop(index))
            else:
                self._renderer.clear(channel)
                if channel in {"base", "gesture"}:
                    self.start_idle()
            break

    def stop(self, channel: str | None = None) -> None:
        self._drag_token = None
        for name in list(self._active) if channel is None else [channel]:
            self._active.pop(name, None)
            self._queues.pop(name, None)
        self._renderer.clear(channel)
