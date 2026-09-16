"""Serialize user and scheduled chat turns per character."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any

from .service import ChatResult, ChatService, TriggerContext

_STOP = object()


@dataclass(frozen=True, slots=True)
class _Work:
    future: Future[Any]
    function: Callable[[], Any]


class _DaemonExecutor:
    """Small shared executor whose blocked network calls cannot hold app shutdown open."""

    def __init__(self, max_workers: int) -> None:
        self._queue: Queue[object] = Queue()
        self._closed = False
        self._lock = threading.Lock()
        self._threads = [
            threading.Thread(target=self._worker, name=f"shiny-chat-{index + 1}", daemon=True)
            for index in range(max_workers)
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, function: Any) -> Future[Any]:
        future: Future[Any] = Future()
        with self._lock:
            if self._closed:
                raise RuntimeError("chat coordinator is shut down")
            self._queue.put(_Work(future, function))
        return future

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            if not isinstance(item, _Work):
                continue
            if not item.future.set_running_or_notify_cancel():
                continue
            try:
                item.future.set_result(item.function())
            except BaseException as exc:
                item.future.set_exception(exc)

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            while True:
                try:
                    item = self._queue.get_nowait()
                except Empty:
                    break
                if isinstance(item, _Work):
                    item.future.cancel()
            for _thread in self._threads:
                self._queue.put(_STOP)


class ChatCoordinator:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = _DaemonExecutor(max_workers)
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _character_lock(self, character: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(character, threading.Lock())

    def submit_user(
        self, service: ChatService, character: str, text: str, **kwargs: Any
    ) -> Future[ChatResult]:
        def run() -> ChatResult:
            with self._character_lock(character):
                return service.send(character, text, **kwargs)

        return self._executor.submit(run)

    def submit_trigger(
        self, service: ChatService, character: str, trigger: TriggerContext, **kwargs: Any
    ) -> Future[ChatResult]:
        def run() -> ChatResult:
            with self._character_lock(character):
                return service.dispatch_trigger(character, trigger, **kwargs)

        return self._executor.submit(run)

    def submit_work(self, character: str, function: Callable[[], Any]) -> Future[Any]:
        """Run internal character work under the same lock as chat and scheduler turns."""

        def run() -> Any:
            with self._character_lock(character):
                return function()

        return self._executor.submit(run)

    def shutdown(self) -> None:
        self._executor.shutdown()
