"""One pet per process. Pipe EOF or missing heartbeats closes an orphan worker."""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from shiny_pet.i18n import set_locale, tr
from shiny_pet.settings.store import validate

from .protocol import COMMANDS, MAX_MESSAGE, decode, encode


def build_context_menu(window: QWidget, spec: dict[str, Any], report: Any) -> QMenu:
    """Build the compact sky-themed desktop character menu."""
    menu = QMenu(window)
    menu.setStyleSheet("""
        QMenu { background: white; color: #234757; border: 1px solid #cfe1e9;
            border-radius: 12px; padding: 8px; }
        QMenu::item { min-width: 150px; padding: 10px 16px; border-radius: 8px; }
        QMenu::item:selected { background: #dff6ff; color: #147fa8; }
        QMenu::separator { height: 1px; background: #dcecf3; margin: 5px 8px; }
    """)
    if spec["mode"] == "spine":
        menu.addAction(tr("聊天室"), lambda: report("ui_action", action="chat"))
        menu.addAction(tr("更換服裝"), lambda: report("ui_action", action="outfit"))
        menu.addAction(tr("動作與表情"), lambda: report("ui_action", action="actions"))
        menu.addSeparator()
    menu.addAction(tr("隱藏"), window.hide)
    menu.addAction(tr("關閉這隻寵物"), window.close)
    return menu


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--runtime-root", type=Path)
    args = parser.parse_args()
    spec = json.loads(args.spec)
    settings = validate(json.loads(args.settings))
    set_locale(str(settings.get("ui_language", "zh-TW")))
    # Import WebEngine before QApplication creation, and only in Spine workers.
    if spec["mode"] == "spine":
        from shiny_pet.window.pet_window import PetWindow
    else:
        from shiny_pet.window.chibi_window import ChibiWindow
    app = QApplication(sys.argv[:1])
    inbox: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=128)
    disconnected = threading.Event()

    def report(kind: str, **payload: Any) -> None:
        try:
            sys.stdout.buffer.write(encode(kind, **payload))
            sys.stdout.buffer.flush()
        except (BrokenPipeError, OSError):
            disconnected.set()

    def read_stdin() -> None:
        pending = b""
        try:
            while True:
                # Raw descriptor reads avoid BufferedReader's lock being held
                # by a daemon thread during Python interpreter finalization.
                chunk = os.read(sys.stdin.fileno(), 4096)
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    message = decode(line)
                    if message["kind"] not in COMMANDS:
                        raise ValueError("Unknown command")
                    inbox.put_nowait(message)
                    if message["kind"] == "quit":
                        return
                if len(pending) > MAX_MESSAGE:
                    raise ValueError("IPC message too large")
        except (OSError, ValueError, queue.Full):
            pass
        finally:
            disconnected.set()

    threading.Thread(target=read_stdin, daemon=True).start()
    window: Any
    try:
        if spec["mode"] == "spine":
            window = PetWindow(Path(spec["path"]), runtime_root=args.runtime_root,
                               fps=settings["renderer_fps"], vsync=settings["renderer_vsync"],
                               quality=settings["renderer_quality"], scale=settings["model_scale"],
                               hit_test_mode=settings["interaction_hit_test_mode"],
                               debug_hit_areas=settings["interaction_debug_hit_areas"],
                               gaze_enabled=settings["interaction_gaze_enabled"],
                               idle_enabled=settings["interaction_idle_enabled"],
                               random_enabled=settings["interaction_random_enabled"],
                               random_interval_seconds=settings[
                                   "interaction_random_interval_seconds"
                               ])
        else:
            window = ChibiWindow(Path(spec["path"]), Path(spec["frames"]),
                                 settings["model_scale"])
    except (OSError, ValueError, RuntimeError) as exc:
        report("error", message=str(exc))
        return 2
    last_ping = time.monotonic()
    last_position: tuple[int, int] | None = None

    def fail(message: str) -> None:
        report("error", message=message)
        window.close()
        app.exit(2)

    def ready() -> None:
        payload = {"mode": spec["mode"], "title": window.windowTitle()}
        if spec["mode"] == "spine":
            payload["capabilities"] = asdict(window.renderer.capabilities)
            payload["character_id"] = window.manifest.character_id
            payload["semantic_actions"] = sorted(window.manifest.animation_groups)
            payload["semantic_expressions"] = sorted(window.manifest.expressions)
        else:
            payload["character_id"] = Path(spec["path"]).stem
            payload["semantic_actions"] = sorted(window.renderer.animations)
            payload["semantic_expressions"] = []
        report("ready", **payload)

    window.renderer.failed.connect(fail)
    window.closed.connect(app.quit)
    if spec["mode"] == "spine":
        window.renderer.ready.connect(lambda _payload: ready())
    else:
        QTimer.singleShot(0, ready)

    def context(point: QPoint) -> None:
        menu = build_context_menu(window, spec, report)
        menu.exec(point)

    window.context_requested.connect(context)
    screen = app.primaryScreen()
    x, y = spec.get("x", 80), spec.get("y", 80)
    if screen and not any(s.availableGeometry().contains(QPoint(x, y)) for s in app.screens()):
        x, y = screen.availableGeometry().x(), screen.availableGeometry().y()
    window.move(x, y)
    window.show()

    def poll() -> None:
        nonlocal last_ping, last_position
        if disconnected.is_set() or time.monotonic() - last_ping > 15:
            window.close()
            app.quit()
            return
        for _ in range(32):
            try:
                message = inbox.get_nowait()
            except queue.Empty:
                break
            kind = message["kind"]
            try:
                if kind == "quit":
                    window.close()
                    app.quit()
                elif kind == "ping":
                    last_ping = time.monotonic()
                    report("pong", visible=window.isVisible())
                elif kind == "show":
                    window.show()
                elif kind == "hide":
                    window.hide()
                elif kind == "settings":
                    options = validate(message["settings"])
                    window.renderer.set_scale(options["model_scale"])
                    if spec["mode"] == "spine":
                        window.renderer.set_frame_policy(options["renderer_fps"],
                            options["renderer_vsync"], options["renderer_quality"])
                        window.apply_interaction_settings(
                            hit_test_mode=options["interaction_hit_test_mode"],
                            debug_hit_areas=options["interaction_debug_hit_areas"],
                            gaze_enabled=options["interaction_gaze_enabled"],
                            idle_enabled=options["interaction_idle_enabled"],
                            random_enabled=options["interaction_random_enabled"],
                            random_interval_seconds=options[
                                "interaction_random_interval_seconds"
                            ],
                        )
                    else:
                        window.adjustSize()
                elif kind == "gesture":
                    name = message.get("name")
                    if not isinstance(name, str):
                        raise ValueError("gesture name must be text")
                    if spec["mode"] == "spine":
                        if window.animation.play_gesture(name) is None:
                            raise ValueError(f"gesture semantic could not be applied: {name}")
                    else:
                        window.renderer.play(name)
                elif kind == "expression":
                    name = message.get("name")
                    if spec["mode"] != "spine" or not isinstance(name, str):
                        raise ValueError("expression requires a Spine pet and text name")
                    if name not in window.manifest.expressions:
                        raise ValueError(f"unknown expression semantic: {name}")
                    if not window.renderer.set_expression(name):
                        raise ValueError(f"expression semantic could not be applied: {name}")
                elif kind == "mouth":
                    if spec["mode"] != "spine":
                        continue
                    openness = message.get("openness", 0.0)
                    form = message.get("form", 0.0)
                    if (isinstance(openness, bool) or not isinstance(openness, (int, float))
                            or isinstance(form, bool) or not isinstance(form, (int, float))):
                        raise ValueError("mouth values must be numbers")
                    window.lipsync.update(float(openness), float(form))
                report("ack", command=kind, request_id=message.get("request_id"))
            except (KeyError, ValueError, TypeError, RuntimeError) as exc:
                report("command_error", message=str(exc), request_id=message.get("request_id"))
        position = (window.x(), window.y())
        if position != last_position:
            report("position", x=position[0], y=position[1])
            last_position = position

    timer = QTimer(app)
    timer.setInterval(100)
    timer.timeout.connect(poll)
    timer.start()
    app.aboutToQuit.connect(window.close)
    result = app.exec()
    timer.stop()
    window.lifecycle.close()
    report("closed")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
