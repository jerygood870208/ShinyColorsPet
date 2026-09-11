"""QProcess supervisor, following BANDORI-PET-REV's isolated-worker pattern (GPL-3.0).

The MVP needs only parent/child control, so bounded JSON pipes replace the
reference application's multi-consumer shared-memory chat queues.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .protocol import MAX_MESSAGE, PREFIX, decode, encode


def worker_entrypoint(
    *, frozen: bool | None = None, executable: str | None = None
) -> tuple[str, list[str], Path]:
    """Return a worker program, argument prefix, and working directory."""
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    program = executable or sys.executable
    if is_frozen:
        return program, ["--internal-worker"], Path(program).resolve().parent
    return program, ["-m", "shiny_pet.process.worker"], Path(__file__).resolve().parents[2]


@dataclass
class Worker:
    process: QProcess
    spec: dict[str, Any]
    state: str = "starting"
    buffer: bytes = b""
    diagnostics: bytes = b""
    last_seen: float = field(default_factory=time.monotonic)
    started: float = field(default_factory=time.monotonic)
    stop_deadline: float = 0
    semantic_actions: frozenset[str] = frozenset()
    semantic_expressions: frozenset[str] = frozenset()
    character_id: str = ""


class ProcessManager(QObject):
    changed = Signal()
    message_received = Signal(str, object)
    error = Signal(str)

    def __init__(self, runtime_root: Path | None) -> None:
        super().__init__()
        self.runtime_root = runtime_root
        self.workers: dict[str, Worker] = {}
        self.closing = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def start(self, spec: dict[str, Any], settings: dict[str, Any]) -> str:
        if self.closing:
            raise RuntimeError("Supervisor is shutting down")
        pet_id = uuid.uuid4().hex[:12]
        process = QProcess(self)
        worker = Worker(process, dict(spec))
        self.workers[pet_id] = worker
        program, prefix, working_directory = worker_entrypoint()
        process.setProgram(program)
        options = {key: settings[key] for key in (
            "renderer_fps", "renderer_vsync", "renderer_quality", "model_scale",
            "interaction_hit_test_mode", "interaction_debug_hit_areas",
            "interaction_gaze_enabled", "interaction_idle_enabled",
            "interaction_random_enabled", "interaction_random_interval_seconds",
        )}
        args = [*prefix, "--spec", json.dumps(spec), "--settings", json.dumps(options)]
        if self.runtime_root:
            args += ["--runtime-root", str(self.runtime_root.resolve())]
        process.setArguments(args)
        process.setWorkingDirectory(str(working_directory))
        process.readyReadStandardOutput.connect(lambda: self.read(pet_id))
        process.readyReadStandardError.connect(lambda: self.read_errors(pet_id))
        process.finished.connect(lambda code, status: self.finished(pet_id, code))
        process.errorOccurred.connect(lambda error: self.process_error(pet_id))
        process.start()
        self.changed.emit()
        return pet_id

    def read_errors(self, pet_id: str) -> None:
        worker = self.workers[pet_id]
        worker.diagnostics = (worker.diagnostics
                              + worker.process.readAllStandardError().data())[-16384:]

    def process_error(self, pet_id: str) -> None:
        worker = self.workers[pet_id]
        worker.state = "failed"
        self.error.emit(f"{pet_id}: {worker.process.errorString()}")
        self.changed.emit()

    def read(self, pet_id: str) -> None:
        worker = self.workers[pet_id]
        worker.buffer += worker.process.readAllStandardOutput().data()
        while b"\n" in worker.buffer:
            line, worker.buffer = worker.buffer.split(b"\n", 1)
            if not line.startswith(PREFIX):
                continue
            try:
                message = decode(line)
            except ValueError as exc:
                self.error.emit(f"{pet_id}: {exc}")
                continue
            worker.last_seen = time.monotonic()
            kind = message["kind"]
            if kind == "ready":
                worker.state = "ready"
                if isinstance(message.get("character_id"), str):
                    worker.character_id = message["character_id"]
                actions = message.get("semantic_actions", [])
                expressions = message.get("semantic_expressions", [])
                if isinstance(actions, list) and all(isinstance(item, str) for item in actions):
                    worker.semantic_actions = frozenset(actions)
                if isinstance(expressions, list) and all(
                    isinstance(item, str) for item in expressions
                ):
                    worker.semantic_expressions = frozenset(expressions)
                self.changed.emit()
            elif kind == "error":
                worker.state = "failed"
                self.error.emit(f"{pet_id}: {message.get('message')}")
                self.changed.emit()
            elif kind == "position":
                for key in ("x", "y"):
                    if type(message.get(key)) is int:
                        worker.spec[key] = message[key]
            self.message_received.emit(pet_id, message)
        if len(worker.buffer) > MAX_MESSAGE:
            worker.buffer = b""
            self.error.emit(f"{pet_id}: oversized worker output discarded")

    def send(self, pet_id: str, kind: str, **payload: Any) -> bool:
        worker = self.workers[pet_id]
        if worker.process.state() != QProcess.ProcessState.Running:
            return False
        if worker.process.bytesToWrite() > MAX_MESSAGE:
            return False
        data = encode(kind, **payload)
        return worker.process.write(data) == len(data)

    def semantic(self, pet_id: str, kind: str, key: str) -> bool:
        """Send only a renderer-neutral key advertised by that worker."""
        worker = self.workers[pet_id]
        available = (worker.semantic_expressions if kind == "expression"
                     else worker.semantic_actions if kind == "gesture" else frozenset())
        if key not in available:
            self.error.emit(f"{pet_id}: unknown semantic {kind} key ignored: {key}")
            return False
        return self.send(pet_id, kind, name=key)

    def stop(self, pet_id: str) -> None:
        worker = self.workers[pet_id]
        if worker.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.send(pet_id, "quit")
        worker.state = "stopping"
        worker.stop_deadline = time.monotonic() + 5
        if not self.closing:
            self.changed.emit()

    def finished(self, pet_id: str, code: int) -> None:
        worker = self.workers[pet_id]
        self.read(pet_id)
        failed = code != 0 or worker.state == "failed"
        worker.state = "failed" if failed else "stopped"
        if failed and worker.diagnostics:
            self.error.emit(worker.diagnostics.decode("utf-8", errors="replace"))
        self.message_received.emit(pet_id, {"kind": "exit", "code": code})
        if not self.closing:
            self.changed.emit()

    def tick(self) -> None:
        now = time.monotonic()
        for pet_id, worker in tuple(self.workers.items()):
            if worker.process.state() == QProcess.ProcessState.NotRunning:
                continue
            if worker.stop_deadline:
                if now > worker.stop_deadline:
                    worker.process.kill()
                continue
            if ((worker.state == "starting" and now - worker.started > 45)
                    or now - worker.last_seen > 20):
                self.error.emit(f"{pet_id}: worker timed out")
                self.stop(pet_id)
            else:
                self.send(pet_id, "ping")

    def shutdown(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.timer.stop()
        for pet_id in self.workers:
            self.stop(pet_id)
        deadline = time.monotonic() + 5
        for worker in self.workers.values():
            process = worker.process
            if process.state() == QProcess.ProcessState.NotRunning:
                continue
            process.waitForFinished(max(1, int((deadline - time.monotonic()) * 1000)))
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
                process.waitForFinished(2000)
