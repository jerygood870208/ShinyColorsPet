"""Idempotent resource teardown without a dependency on Qt or the UI."""

from collections.abc import Callable


class ModelLifecycleManager:
    def __init__(self, *cleanup: Callable[[], None]) -> None:
        self._cleanup = cleanup
        self.closed = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        error: Exception | None = None
        for callback in self._cleanup:
            try:
                callback()
            except Exception as exc:
                if error is None:
                    error = exc
        if error is not None:
            raise error
