"""Opt-in screen awareness and external-tool contracts."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit


class ScreenContextProvider(Protocol):
    def capture_text(self) -> str: ...


class ToolContextProvider(Protocol):
    def instructions(self, cancel: threading.Event) -> str: ...
    def execute(self, response: str, cancel: threading.Event) -> str | None: ...


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    call: Callable[[dict[str, Any]], str]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name or tool.name in self._tools:
            raise ValueError("tool name must be non-empty and unique")
        self._tools[tool.name] = tool

    def describe(self) -> tuple[dict[str, str], ...]:
        return tuple({"name": item.name, "description": item.description}
                     for item in self._tools.values())

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        try:
            tool = self._tools[name]
        except KeyError as exc:
            raise ValueError(f"unknown tool: {name}") from exc
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        return tool.call(arguments)


@dataclass(frozen=True, slots=True)
class ExternalMessage:
    source: str
    sender: str
    character: str
    text: str


class ExternalChatBridge:
    """Normalizes external chat events into the same text pipeline callback."""

    def __init__(self, send: Callable[[str, str], str]) -> None:
        self.send = send

    def receive(self, message: ExternalMessage) -> str:
        if not message.source.strip() or not message.sender.strip() or not message.text.strip():
            raise ValueError("external message requires source, sender and text")
        return self.send(message.character, message.text.strip())


class MCPHttpClient:
    """Minimal JSON-RPC MCP HTTP transport with cancellation and bounded output."""

    def __init__(self, url: str, *, token: str = "", timeout: float = 30.0) -> None:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("MCP HTTP URL must use http or https")
        if parts.username or parts.password:
            raise ValueError("MCP URL must not contain credentials")
        if parts.scheme == "http" and parts.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("remote MCP servers must use https")
        self.url, self.token, self.timeout = url, token, timeout
        self._next_id = 1
        self._session_id = ""
        self._initialized = False
        self._lock = threading.RLock()

    @staticmethod
    def _decode_response(raw: bytes, identifier: int | None) -> dict[str, Any]:
        text = raw.decode("utf-8").strip()
        if not text:
            return {}
        candidates: list[str]
        if text.startswith("data:") or "\ndata:" in text:
            candidates = [
                "\n".join(line[5:].lstrip() for line in block.splitlines()
                            if line.startswith("data:"))
                for block in text.replace("\r\n", "\n").split("\n\n")
            ]
        else:
            candidates = [text]
        for candidate in candidates:
            if not candidate or candidate == "[DONE]":
                continue
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            matches = identifier is None or (
                isinstance(payload, dict) and payload.get("id") == identifier
            )
            if isinstance(payload, dict) and matches:
                return payload
        raise RuntimeError("MCP returned invalid JSON or no matching SSE event")

    def _exchange(self, payload: dict[str, Any], identifier: int | None,
                  stopped: threading.Event) -> dict[str, Any]:
        if stopped.is_set():
            raise RuntimeError("MCP request cancelled")
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "ShinyColorsPet/0.0.1",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(self.url, body, headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                session_id = response.headers.get("Mcp-Session-Id", "").strip()
                if session_id:
                    self._session_id = session_id
                raw = response.read(1_048_577)
        except urllib.error.HTTPError as exc:
            detail = exc.read(512).decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP HTTP {exc.code}: {detail}") from exc
        except OSError as exc:
            raise RuntimeError(f"MCP request failed: {exc}") from exc
        if len(raw) > 1_048_576:
            raise RuntimeError("MCP response exceeds 1 MiB")
        if stopped.is_set():
            raise RuntimeError("MCP request cancelled")
        try:
            result = self._decode_response(raw, identifier)
        except UnicodeError as exc:
            raise RuntimeError("MCP returned invalid UTF-8") from exc
        if "error" in result:
            raise RuntimeError("MCP error: " + str(result["error"])[:500])
        return result

    def _initialize(self, stopped: threading.Event) -> None:
        if self._initialized:
            return
        identifier = self._next_id
        self._next_id += 1
        self._exchange({
            "jsonrpc": "2.0", "id": identifier, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ShinyColorsPet", "version": "0.0.1"},
            },
        }, identifier, stopped)
        self._exchange({
            "jsonrpc": "2.0", "method": "notifications/initialized", "params": {},
        }, None, stopped)
        self._initialized = True

    def request(self, method: str, params: dict[str, Any],
                cancel: threading.Event | None = None) -> Any:
        stopped = cancel or threading.Event()
        with self._lock:
            self._initialize(stopped)
            identifier = self._next_id
            self._next_id += 1
            payload = self._exchange({
                "jsonrpc": "2.0", "id": identifier, "method": method, "params": params,
            }, identifier, stopped)
            return payload.get("result")

    def list_tools(self, cancel: threading.Event | None = None) -> Any:
        return self.request("tools/list", {}, cancel)

    def call_tool(self, name: str, arguments: dict[str, Any],
                  cancel: threading.Event | None = None) -> Any:
        return self.request("tools/call", {"name": name, "arguments": arguments}, cancel)


@dataclass(frozen=True, slots=True)
class _MCPRoute:
    alias: str
    tool_name: str
    description: str
    client: MCPHttpClient


_MCP_CALL = re.compile(r"\A\s*<mcp-tool-call>(.{1,16384})</mcp-tool-call>\s*\Z", re.DOTALL)


class MCPToolRouter:
    """Expose only user-allowlisted MCP tools through a bounded one-call chat loop."""

    def __init__(self, servers: list[dict[str, Any]]) -> None:
        self.servers = [dict(item) for item in servers if isinstance(item, dict)]
        self._routes: dict[str, _MCPRoute] = {}
        self._cache_at = 0.0

    def _refresh(self, cancel: threading.Event) -> None:
        if self._routes and time.monotonic() - self._cache_at < 300:
            return
        routes: dict[str, _MCPRoute] = {}
        for index, server in enumerate(self.servers):
            if not bool(server.get("enabled", True)):
                continue
            url = str(server.get("url", "")).strip()
            allowed_value = server.get("allowed_tools", [])
            if not url or not isinstance(allowed_value, list):
                continue
            allowed = {str(item).strip() for item in allowed_value if str(item).strip()}
            if not allowed:
                continue
            token = str(server.get("token", ""))
            token_env = str(server.get("token_env", "")).strip()
            if token_env:
                token = os.getenv(token_env, token)
            try:
                client = MCPHttpClient(url, token=token,
                    timeout=max(5.0, min(120.0, float(server.get("timeout_seconds", 30)))))
                result = client.list_tools(cancel)
            except (OSError, RuntimeError, TypeError, ValueError):
                continue
            tools = result.get("tools", []) if isinstance(result, dict) else []
            server_name = str(server.get("name", f"server-{index + 1}")).strip()
            safe_server = re.sub(r"[^A-Za-z0-9_-]", "-", server_name)[:40] or f"server-{index + 1}"
            for item in tools:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if name not in allowed:
                    continue
                alias = safe_server + "/" + name
                routes[alias] = _MCPRoute(alias, name,
                    str(item.get("description", ""))[:500], client)
        self._routes = routes
        self._cache_at = time.monotonic()

    def instructions(self, cancel: threading.Event) -> str:
        self._refresh(cancel)
        if not self._routes:
            return ""
        descriptions = "\n".join(
            f"- {route.alias}: {route.description or 'No description supplied.'}"
            for route in self._routes.values()
        )
        return (
            "User-approved MCP tools are available below. Use at most one only when needed. "
            "To call one, output only <mcp-tool-call>{\"tool\":\"server/name\","
            "\"arguments\":{}}</mcp-tool-call>. Never put this tag in a normal reply.\n"
            + descriptions
        )

    def execute(self, response: str, cancel: threading.Event) -> str | None:
        match = _MCP_CALL.fullmatch(response)
        if match is None:
            return None
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise RuntimeError("MCP tool call is invalid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("arguments", {}), dict):
            raise RuntimeError("MCP tool call must contain an arguments object")
        alias = str(payload.get("tool", ""))
        route = self._routes.get(alias)
        if route is None:
            raise RuntimeError("MCP tool was not approved or advertised")
        result = route.client.call_tool(route.tool_name, payload.get("arguments", {}), cancel)
        serialized = json.dumps(result, ensure_ascii=False, default=str)
        if len(serialized) > 16000:
            serialized = serialized[:16000] + "…"
        return serialized
