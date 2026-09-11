"""Authenticated loopback-only HTTP intake for external chat messages."""

from __future__ import annotations

import hmac
import json
import socket
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from shiny_pet.integrations import ExternalMessage


class _LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _LoopbackServerV6(_LoopbackServer):
    address_family = socket.AF_INET6


class LocalChatIntegrationServer:
    def __init__(self, host: str, port: int, token: str,
                 on_message: Callable[[ExternalMessage], dict[str, Any]]) -> None:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("chat integration may bind only to a loopback address")
        if not token:
            raise ValueError("chat integration requires a token")
        if int(port) != 0 and not 1024 <= int(port) <= 65535:
            raise ValueError("chat integration port must be 1024-65535")
        self.host = "127.0.0.1" if host == "localhost" else host
        self.port = int(port)
        self.token = token
        self.on_message = on_message
        self._server: _LoopbackServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        token = self.token
        callback = self.on_message

        class Handler(BaseHTTPRequestHandler):
            server_version = "ShinyColorsPetChat/1.0"

            def log_message(self, _format: str, *args: Any) -> None:
                return

            def _json(self, status: int, value: dict[str, Any]) -> None:
                payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(payload)

            def _authorized(self) -> bool:
                supplied = self.headers.get("Authorization", "")
                return hmac.compare_digest(supplied, "Bearer " + token)

            def do_GET(self) -> None:  # noqa: N802
                if urlsplit(self.path).path == "/health":
                    self._json(200, {"ok": True, "service": "ShinyColorsPet chat integration"})
                else:
                    self._json(404, {"ok": False, "error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if urlsplit(self.path).path != "/v1/chat/messages":
                    self._json(404, {"ok": False, "error": "not found"})
                    return
                if not self._authorized():
                    self._json(401, {"ok": False, "error": "unauthorized"})
                    return
                if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                    self._json(415, {"ok": False, "error": "application/json required"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if not 0 < length <= 65536:
                    self._json(413, {"ok": False, "error": "body must be 1-65536 bytes"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("JSON body must be an object")
                    message = ExternalMessage(
                        str(payload.get("source", "external"))[:80],
                        str(payload.get("sender", "local-user"))[:200],
                        str(payload.get("character", ""))[:200],
                        str(payload.get("text", ""))[:8000],
                    )
                    if not message.character.strip() or not message.text.strip():
                        raise ValueError("character and text are required")
                    result = callback(message)
                except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                    self._json(400, {"ok": False, "error": str(exc)})
                    return
                except Exception:
                    self._json(500, {"ok": False, "error": "message delivery failed"})
                    return
                self._json(202, {"ok": True, "result": result})

        server_type = _LoopbackServerV6 if self.host == "::1" else _LoopbackServer
        self._server = server_type((self.host, self.port), Handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever,
            name=f"shiny-chat-integration:{self.port}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        server, thread = self._server, self._thread
        if server is None:
            return
        self._server = None
        self._thread = None
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=2)
