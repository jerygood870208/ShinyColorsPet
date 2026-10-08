"""Verify emotional mouth commands through the frozen worker entry point."""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from shiny_pet.process.protocol import PREFIX, decode, encode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--source", action="store_true", help="Treat executable as Python")
    parser.add_argument("--chibi-frames", type=Path)
    args = parser.parse_args(argv)
    executable = args.executable.resolve()
    model = args.model.resolve()
    if args.chibi_frames is None:
        spec = {"mode": "spine", "path": str(model), "x": 80, "y": 80}
    else:
        spec = {
            "mode": "chibi",
            "path": str(model),
            "frames": str(args.chibi_frames.resolve()),
            "x": 80,
            "y": 80,
        }
    entrypoint = ["-m", "shiny_pet.process.worker"] if args.source else ["--internal-worker"]
    process = subprocess.Popen(
        [
            str(executable),
            *entrypoint,
            "--spec",
            json.dumps(spec),
            "--settings",
            "{}",
        ],
        cwd=executable.parent,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    messages: queue.Queue[dict[str, object]] = queue.Queue()
    diagnostics: list[str] = []

    def read_output() -> None:
        for line in process.stdout:
            if line.startswith(PREFIX):
                messages.put(decode(line.rstrip(b"\r\n")))
            else:
                diagnostics.append(line.decode("utf-8", errors="replace").rstrip())

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    deadline = time.monotonic() + args.timeout
    next_ping = time.monotonic() + 5
    ready: dict[str, object] | None = None
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                message = messages.get(timeout=0.1)
            except queue.Empty:
                message = None
            if message is not None:
                if message.get("kind") == "error":
                    print(json.dumps(message, ensure_ascii=False), file=sys.stderr)
                    break
                if message.get("kind") == "ready":
                    ready = message
                    break
            if time.monotonic() >= next_ping:
                process.stdin.write(encode("ping"))
                process.stdin.flush()
                next_ping = time.monotonic() + 5
        if ready is None:
            print(
                f"frozen worker did not become ready; exit={process.poll()}, "
                f"diagnostics={diagnostics[-20:]!r}",
                file=sys.stderr,
            )
            return 1
        for index, emotion in enumerate(("happy", "sad", "angry", "shy", "surprised", "neutral")):
            for openness in (0.8, 0.0):
                request_id = f"mouth-{index}-{openness}"
                process.stdin.write(encode("mouth", openness=openness, form=0.0,
                                           emotion=emotion, request_id=request_id))
                process.stdin.flush()
                until = time.monotonic() + 3
                acknowledged = False
                while time.monotonic() < until:
                    try:
                        message = messages.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if message.get("kind") in {"error", "command_error"}:
                        raise RuntimeError(str(message))
                    if message.get("kind") == "ack" and message.get("request_id") == request_id:
                        acknowledged = True
                        break
                if not acknowledged:
                    raise RuntimeError(f"missing mouth acknowledgement: {emotion}/{openness}")
        print("Frozen worker ready; all 12 emotional speaking/stop commands acknowledged")
        return 0
    finally:
        if process.poll() is None:
            try:
                process.stdin.write(encode("quit"))
                process.stdin.flush()
                process.wait(timeout=10)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()
        reader.join(timeout=1)


if __name__ == "__main__":
    raise SystemExit(main())
