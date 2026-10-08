"""Suspend-aware heartbeat timing for both sides of the worker pipe."""

from __future__ import annotations

import time

RESUME_GAP_SECONDS = 10.0


class PollGap:
    def __init__(self) -> None:
        self.monotonic = time.monotonic()
        self.wall = time.time()

    def observe(self, now: float | None = None, wall: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        current_wall = time.time() if wall is None else wall
        resumed = max(current - self.monotonic, current_wall - self.wall) > RESUME_GAP_SECONDS
        self.monotonic, self.wall = current, current_wall
        return resumed


class WorkerHeartbeat:
    def __init__(self) -> None:
        self.last_ping = time.monotonic()
        self.gap = PollGap()

    def received(self) -> None:
        self.last_ping = time.monotonic()

    def expired(self) -> bool:
        now = time.monotonic()
        if self.gap.observe(now):
            self.last_ping = now
        return now - self.last_ping > 15
