"""Qt WebEngine adapter for externally supplied Spine WebGL 3.6 assets."""

from __future__ import annotations

import importlib.util
import json
import logging
import math
import mimetypes
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QImage
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from shiny_pet.models import Manifest, load_manifest
from shiny_pet.models.abilities import Abilities, resolve_abilities
from shiny_pet.models.textures import resolve_textures

from .base import AlphaMask, EventSource, HitResult, ModelCapabilities, PlaybackToken, RendererEvent
from .hit_geometry import HitGeometry, HitPolygon


@dataclass(frozen=True, slots=True)
class WebEngineProbe:
    available: bool
    reasons: tuple[str, ...]
    runtime_script: Path | None
    spine_c_root: Path | None


def bundled_runtime_root() -> Path:
    """Return the packaged runtime, or the licensed source-checkout runtime."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "vendor" / "spine-runtime-3.6"
    project_root = Path(__file__).resolve().parents[2]
    packaged_layout = project_root / "vendor" / "spine-runtime-3.6"
    if packaged_layout.is_dir():
        return packaged_layout
    # The separately cloned Esoteric Software repository uses this directory
    # name during source development.  main.py previously ignored it unless
    # callers supplied --runtime-root explicitly, making every worker fail.
    return project_root / "spine-runtimes-3.6"


def probe_webengine(asset_dir: Path, runtime_root: Path | None = None) -> WebEngineProbe:
    reasons: list[str] = []
    if runtime_root is None:
        bundled = bundled_runtime_root()
        runtime_root = bundled if bundled.is_dir() else asset_dir.parent / "spine-runtimes-3.6"
    runtime = runtime_root / "spine-ts" / "build" / "spine-webgl.js"
    spine_c = runtime_root / "spine-c"
    if not runtime.is_file():
        reasons.append("Spine 3.6 runtime does not contain spine-ts/build/spine-webgl.js")
    if not (runtime_root / "spine-ts" / "README.md").is_file():
        reasons.append("Spine TypeScript runtime provenance files are missing")
    if importlib.util.find_spec("PySide6") is None:
        reasons.append("PySide6 is not installed")
    elif importlib.util.find_spec("PySide6.QtWebEngineWidgets") is None:
        reasons.append("PySide6.QtWebEngineWidgets is not installed")
    for filename in ("data.json", "data.atlas", "data.png"):
        if not (asset_dir / filename).is_file():
            reasons.append(f"asset set does not contain {filename}")
    return WebEngineProbe(
        not reasons,
        tuple(reasons),
        runtime if runtime.is_file() else None,
        spine_c if spine_c.is_dir() else None,
    )


class _AssetServer:
    def __init__(self, manifest: Manifest, runtime_script: Path, html: Path) -> None:
        self._manifest = manifest
        self._runtime = runtime_script.resolve()
        self._html = html.resolve()
        self._root = manifest.spine.atlas.parent.resolve()
        self._textures = resolve_textures(manifest, lambda p: not QImage(str(p)).isNull())
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def start(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                route = unquote(self.path.split("?", 1)[0])
                path: Path | None
                if route == "/":
                    path = owner._html
                elif route == "/runtime.js":
                    path = owner._runtime
                elif route == "/clip_boundaries.js":
                    path = owner._html.with_name("clip_boundaries.js")
                elif route == "/hit_geometry.js":
                    path = owner._html.with_name("hit_geometry.js")
                elif route == "/semantic_drivers.js":
                    path = owner._html.with_name("semantic_drivers.js")
                elif route == "/assets/skeleton.json":
                    path = owner._manifest.spine.skeleton
                elif route == "/assets/skeleton.atlas":
                    path = owner._manifest.spine.atlas
                elif route.startswith("/assets/"):
                    texture = owner._textures.get(route.removeprefix("/assets/"))
                    candidate = (owner._root / route.removeprefix("/assets/")).resolve()
                    try:
                        candidate.relative_to(owner._root)
                    except ValueError:
                        candidate = owner._root / "__blocked__"
                    path = texture or candidate
                else:
                    path = None
                if path is None or not path.is_file():
                    self.send_error(404)
                    return
                body = path.read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                )
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                del format, args

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host_value, port = self._httpd.server_address[:2]
        host = host_value.decode() if isinstance(host_value, bytes) else host_value
        self.url = f"http://{host}:{port}/"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


class _Bridge(QObject):
    def __init__(self, renderer: WebEngineSpine36Renderer) -> None:
        super().__init__(renderer)
        self._renderer = renderer

    @Slot(str)
    def ready(self, payload: str) -> None:
        self._renderer._receive_ready(payload)

    @Slot(str)
    def failed(self, payload: str) -> None:
        self._renderer._receive_failed(payload)

    @Slot(int)
    def completed(self, token: int) -> None:
        self._renderer._receive_completed(token)

    @Slot(str)
    def hitGeometry(self, payload: str) -> None:  # noqa: N802
        self._renderer.receive_hit_geometry(payload)

    @Slot(str)
    def spineEvent(self, payload: str) -> None:  # noqa: N802
        self._renderer._receive_event(payload)


class _LoggingPage(QWebEnginePage):
    console_message = Signal(str)

    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:
        self.console_message.emit(f"{level.name}: {message} ({source_id}:{line_number})")


class WebEngineSpine36Renderer(QWebEngineView):
    """A widget and renderer-neutral adapter for one Spine character."""

    ready = Signal(object)
    failed = Signal(str)
    playback_finished = Signal(object)
    spine_event = Signal(str)
    console_message = Signal(str)

    def __init__(self, runtime_root: Path | None = None, *, hit_test_mode: str = "auto") -> None:
        super().__init__()
        if hit_test_mode not in {"auto", "attachment", "model-bounds"}:
            raise ValueError("hit_test_mode must be auto, attachment, or model-bounds")
        self.hit_test_mode = hit_test_mode
        self.hit_geometry = HitGeometry()
        self._geometry_time = 0.0
        self._runtime_root = runtime_root
        self._manifest: Manifest | None = None
        self._abilities: Abilities | None = None
        self.capabilities = ModelCapabilities()
        self._events = EventSource()
        self._expression_channel: str | None = None
        self._server: _AssetServer | None = None
        self._loaded = False
        self._ready = False
        self._next_token = 1
        self._finished: set[PlaybackToken] = set()
        self._active: dict[str, PlaybackToken] = {}
        self._fps = 60
        self._vsync = True
        self._quality = "balanced"
        self._scale = 1.0
        self.setStyleSheet("background: transparent")
        page = _LoggingPage(self)
        page.setBackgroundColor(QColor(0, 0, 0, 0))
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        self.setPage(page)
        page.console_message.connect(self.console_message)
        self.loadFinished.connect(self._load_finished)
        self._channel = QWebChannel(page)
        self._bridge = _Bridge(self)
        self._channel.registerObject("bridge", self._bridge)
        page.setWebChannel(self._channel)

    @property
    def manifest(self) -> Manifest | None:
        return self._manifest

    @property
    def is_ready(self) -> bool:
        return self._ready

    def load_model(self, manifest_path: Path) -> ModelCapabilities:
        self.unload()
        self._abilities = resolve_abilities(load_manifest(manifest_path))
        manifest = self._abilities.manifest
        for warning in self._abilities.warnings:
            logging.getLogger(__name__).warning(warning)
        runtime_root = self._runtime_root or bundled_runtime_root()
        runtime = runtime_root / "spine-ts" / "build" / "spine-webgl.js"
        if not runtime.is_file():
            raise RuntimeError(f"Spine WebGL 3.6 runtime not found: {runtime}")
        server = _AssetServer(manifest, runtime, Path(__file__).with_name("webengine_spine36.html"))
        server.start()
        self._manifest = manifest
        self._server = server
        self._loaded = True
        page_url = QUrl(server.url)
        QTimer.singleShot(0, lambda: self._navigate(page_url))
        skeleton_data = json.loads(manifest.spine.skeleton.read_text(encoding="utf-8-sig"))
        has_boxes = any(
            attachment.get("type") == "boundingbox"
            for skin in skeleton_data.get("skins", {}).values()
            for slot in skin.values()
            for attachment in slot.values()
        )
        self.capabilities = ModelCapabilities(
            expressions=bool(manifest.expressions),
            lip_sync=self._abilities.lipsync["driver"] != "disabled",
            gaze=self._abilities.gaze["driver"] != "disabled",
            lip_sync_driver=self._abilities.lipsync["driver"],
            gaze_driver=self._abilities.gaze["driver"],
            expression_drivers=tuple(sorted({e.driver for e in manifest.expressions.values()})),
            diagnostics=self._abilities.warnings,
            skins=tuple(skeleton_data.get("skins", {})),
            semantic_hit_areas=has_boxes and self.hit_test_mode != "model-bounds",
            alpha_mask=self.hit_test_mode == "auto",
            events=tuple(manifest.events),
        )
        return self.capabilities

    def unload(self) -> None:
        self.hit_geometry = HitGeometry()
        self._geometry_time = 0.0
        if self._loaded:
            self.page().runJavaScript("window.shinyApi && window.shinyApi.dispose()")
            self.setHtml("<html><body></body></html>")
        if self._server is not None:
            self._server.stop()
        self._server = None
        self._manifest = None
        self._abilities = None
        self._expression_channel = None
        self.capabilities = ModelCapabilities()
        self._loaded = False
        self._ready = False
        self.clear()

    def set_frame_policy(self, fps: int, vsync: bool, quality: str) -> None:
        if fps <= 0:
            raise ValueError("fps must be positive")
        if quality not in {"low", "balanced", "high"}:
            raise ValueError("quality must be low, balanced, or high")
        self._fps, self._vsync, self._quality = fps, vsync, quality
        self._call("setFramePolicy", fps, vsync, quality)

    def set_scale(self, scale: float) -> None:
        if scale <= 0:
            raise ValueError("scale must be positive")
        self._scale = scale
        self._call("setScale", scale)

    def set_hit_test_mode(self, mode: str) -> None:
        if mode not in {"auto", "attachment", "model-bounds"}:
            raise ValueError("hit_test_mode must be auto, attachment, or model-bounds")
        self.hit_test_mode = mode

    def play(
        self, channel: str, animation: str, *, loop: bool, mix_seconds: float = 0.0
    ) -> PlaybackToken:
        self._require_loaded()
        if self._manifest is None or channel not in self._manifest.channels:
            raise ValueError(f"unknown channel: {channel}")
        if not animation:
            raise ValueError("animation must not be empty")
        if not self._ready:
            raise RuntimeError("model is not ready")
        if self._abilities is None or animation not in self._abilities.animations:
            raise ValueError(f"animation not found: {animation}")
        if mix_seconds < 0:
            raise ValueError("mix_seconds must not be negative")
        previous = self._active.get(channel)
        if previous is not None:
            self._finished.add(previous)
        token = PlaybackToken(self._next_token)
        self._next_token += 1
        self._active[channel] = token
        self._call(
            "play", self._manifest.channels[channel], animation, loop, mix_seconds, token.value
        )
        return token

    def clear(self, channel: str | None = None) -> None:
        if (
            channel is not None
            and self._manifest is not None
            and channel not in self._manifest.channels
        ):
            raise ValueError(f"unknown channel: {channel}")
        channels = list(self._active) if channel is None else [channel]
        for name in channels:
            token = self._active.pop(name, None)
            if token is not None:
                self._finished.add(token)
        if self._loaded:
            track = None if channel is None else self._manifest.channels[channel]  # type: ignore[union-attr]
            self._call("clear", track)

    def is_finished(self, token: PlaybackToken) -> bool:
        return token in self._finished

    def set_expression(self, semantic_name: str) -> bool:
        self._require_loaded()
        if not self._ready:
            return False
        expression = self._manifest.expressions.get(semantic_name)  # type: ignore[union-attr]
        if expression is None:
            return False
        if self._expression_channel and self._expression_channel != expression.channel:
            self.clear(self._expression_channel)
        self._expression_channel = expression.channel or None
        if expression.driver == "slot_attachment":
            self._call("setExpressionSlot", expression.slot, expression.attachment)
            return True
        self._call("clearExpressionSlots")
        self.play(expression.channel, expression.animation, loop=True, mix_seconds=0.15)
        return True

    def set_mouth(self, openness: float, form: float = 0.0) -> bool:
        self._require_loaded()
        if not 0 <= openness <= 1 or not -1 <= form <= 1:
            raise ValueError("mouth values are outside their normalized ranges")
        if not self.capabilities.lip_sync or not self._ready:
            return False
        self._call("setMouth", openness, form)
        return True

    def set_gaze(self, x: float, y: float) -> bool:
        self._require_loaded()
        if not -1 <= x <= 1 or not -1 <= y <= 1:
            raise ValueError("gaze values are outside the normalized range")
        if not self.capabilities.gaze or not self._ready:
            return False
        self._call("setGaze", x, y)
        return True

    def subscribe_events(self, callback: Callable[[RendererEvent], None]) -> Callable[[], None]:
        return self._events.subscribe(callback)

    def _receive_event(self, payload: str) -> None:
        if not self._ready or self._manifest is None:
            return
        data = json.loads(payload)
        channel = next(
            (key for key, value in self._manifest.channels.items() if value == data["track"]), ""
        )
        token = PlaybackToken(data["token"]) if data.get("token") else None
        for semantic, source in self._manifest.events.items():
            if source == data["name"]:
                self._events.emit(
                    RendererEvent(
                        semantic,
                        channel,
                        token,
                        float(data["time"]),
                        int(data.get("intValue", 0)),
                        float(data.get("floatValue", 0)),
                        str(data.get("stringValue") or ""),
                    )
                )
        self.spine_event.emit(payload)

    def hit_test(self, x: float, y: float) -> HitResult:
        self._require_loaded()
        if not (0 <= x < self.width() and 0 <= y < self.height()):
            return HitResult(False, source="alpha-mask")
        if self.hit_test_mode == "auto":
            image = self.grab().toImage()
            if not image.isNull() and image.hasAlphaChannel():
                dpr = image.devicePixelRatio() or 1.0
                px, py = int(x * dpr), int(y * dpr)
                if 0 <= px < image.width() and 0 <= py < image.height():
                    return HitResult(image.pixelColor(px, py).alpha() > 8, source="alpha-mask")
        if time.monotonic() - self._geometry_time > 1.0:
            return HitResult(False, source="none")
        return self.hit_geometry.hit_test(
            x / self.width(), y / self.height(), model_only=self.hit_test_mode == "model-bounds"
        )

    def receive_hit_geometry(self, payload: str) -> None:
        if not self._loaded:
            return
        try:
            data = json.loads(payload)

            def polygon(name: str, points: Any) -> HitPolygon:
                parsed = tuple((float(x), float(y)) for x, y in points)
                if len(parsed) < 3 or not all(math.isfinite(v) for p in parsed for v in p):
                    raise ValueError("invalid hit polygon")
                return HitPolygon(name, parsed)

            aliases = self._manifest.hit_areas.aliases if self._manifest is not None else {}
            attachments = tuple(
                polygon(aliases.get(item["name"], item["name"]), item["points"])
                for item in data["attachments"]
            )
            model = polygon("model", data["model"]) if data["model"] else None
            self.hit_geometry = HitGeometry(attachments, model)
            self._geometry_time = time.monotonic()
        except (ValueError, TypeError, KeyError):
            self.hit_geometry = HitGeometry()
            self._geometry_time = 0.0

    def snapshot_alpha_mask(self) -> AlphaMask | None:
        self._require_loaded()
        if self.hit_test_mode != "auto":
            return None
        image = self.grab().toImage()
        if image.isNull() or not image.hasAlphaChannel():
            return None
        image = image.convertToFormat(QImage.Format.Format_ARGB32)
        pixels = bytes(
            image.pixelColor(x, y).alpha()
            for y in range(image.height())
            for x in range(image.width())
        )
        return AlphaMask(image.width(), image.height(), pixels)

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        self.unload()
        super().closeEvent(event)

    def _call(self, method: str, *args: object) -> None:
        if self._loaded:
            arguments = ",".join(json.dumps(value) for value in args)
            self.page().runJavaScript(f"window.shinyApi && window.shinyApi.{method}({arguments})")

    def _navigate(self, url: QUrl) -> None:
        self.console_message.emit(f"navigate={url.toString()}")
        self.page().load(url)

    def _receive_ready(self, payload: str) -> None:
        self._ready = True
        self._call("setFramePolicy", self._fps, self._vsync, self._quality)
        self._call("setScale", self._scale)
        if self._manifest is not None:
            self._call("setPremultipliedAlpha", self._manifest.spine.premultiplied_alpha)
            self._call("setSkin", self._manifest.spine.default_skin)
            viewport = self._manifest.raw["spine"].get("viewport_padding", {})
            self._call(
                "setViewportPadding",
                float(viewport.get("x", 0.04)),
                float(viewport.get("y", 0.04)),
            )
            if self._abilities is not None:
                self._call(
                    "configureDrivers",
                    self._abilities.lipsync,
                    self._abilities.gaze,
                    self._manifest.channels,
                )
        self.ready.emit(json.loads(payload))

    def _load_finished(self, ok: bool) -> None:
        expected_url = self._server.url if self._server is not None else ""
        self.console_message.emit(f"loadFinished={ok} url={self.url().toString()}")
        if not ok and self._loaded and self.url().toString() == expected_url:
            self.failed.emit("WebEngine failed to load the local renderer page")

    def _receive_failed(self, payload: str) -> None:
        try:
            message = str(json.loads(payload).get("message", payload))
        except (json.JSONDecodeError, AttributeError):
            message = payload
        self.failed.emit(message)

    def _receive_completed(self, token_value: int) -> None:
        token = PlaybackToken(token_value)
        self._finished.add(token)
        for channel, active in tuple(self._active.items()):
            if active == token:
                del self._active[channel]
        self.playback_finished.emit(token)

    def _require_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("no model is loaded")
