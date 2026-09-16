"""Synthesized voice cache with configurable on-disk cleanup."""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from pathlib import Path


class VoiceCache:
    def __init__(self, root: Path, max_bytes: int | None = 2 * 1024**3) -> None:
        self.root = root
        self.max_bytes = max_bytes if max_bytes is None else max(1, int(max_bytes))
        self._timestamp_lock = threading.Lock()
        self._last_timestamp = 0

    def store(self, audio: bytes, media_type: str) -> str:
        if not audio:
            raise ValueError("voice cache requires audio")
        self.root.mkdir(parents=True, exist_ok=True)
        suffix = ".mp3" if "mpeg" in media_type or "mp3" in media_type else ".wav"
        with self._timestamp_lock:
            timestamp = max(time.time_ns(), self._last_timestamp + 1)
            self._last_timestamp = timestamp
        key = f"{timestamp:020d}-{uuid.uuid4().hex}{suffix}"
        path = self.root / key
        path.write_bytes(audio)
        self.trim()
        return key

    def load(self, key: str) -> tuple[bytes, str] | None:
        path = self.root / Path(key).name
        if not path.is_file():
            return None
        try:
            media_type = "audio/mpeg" if path.suffix.lower() == ".mp3" else "audio/wav"
            return path.read_bytes(), media_type
        except OSError:
            return None

    def contains(self, key: str) -> bool:
        return (self.root / Path(key).name).is_file()

    def timestamped_entries(self) -> list[tuple[str, float]]:
        """Return cache keys with generation times encoded in current filenames."""
        if not self.root.is_dir():
            return []
        entries: list[tuple[str, float]] = []
        for path in self.root.iterdir():
            if not path.is_file() or path.suffix.lower() not in {".wav", ".mp3"}:
                continue
            try:
                timestamp = int(path.name.split("-", 1)[0]) / 1_000_000_000
            except (ValueError, IndexError):
                try:
                    timestamp = path.stat().st_mtime
                except OSError:
                    continue
            entries.append((path.name, timestamp))
        return entries

    def trim(self) -> None:
        if self.max_bytes is None or not self.root.is_dir():
            return
        # Filenames begin with a fixed-width creation timestamp, making ordering
        # deterministic even on filesystems with coarse or unusual mtime behavior.
        files = sorted(path for path in self.root.iterdir() if path.is_file())
        total = sum(path.stat().st_size for path in files)
        for path in files:
            if total <= self.max_bytes:
                break
            try:
                size = path.stat().st_size
                path.unlink()
                total -= size
            except OSError:
                continue

    def configure(self, max_bytes: int | None) -> None:
        """Apply a new size budget; ``None`` keeps all generated audio."""
        self.max_bytes = max_bytes if max_bytes is None else max(1, int(max_bytes))
        self.trim()

    def clear(self) -> None:
        if self.root.is_dir():
            shutil.rmtree(self.root, ignore_errors=True)

    def age(self, key: str) -> float | None:
        path = self.root / Path(key).name
        return time.time() - path.stat().st_mtime if path.is_file() else None
