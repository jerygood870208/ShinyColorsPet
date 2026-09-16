"""Small cancel-aware OpenAI-compatible chat client."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit


class ChatClient(Protocol):
    def complete(self, messages: list[dict[str, str]], cancel: threading.Event) -> str: ...


def discover_openai_models(base_url: str) -> tuple[str, ...]:
    """Return chat-capable models advertised by an OpenAI-compatible endpoint."""
    parts = urlsplit(base_url if "://" in base_url else "http://" + base_url)
    path = parts.path.rstrip("/")
    if not path.endswith("/v1"):
        path += "/v1"
    url = urlunsplit((parts.scheme, parts.netloc, path + "/models", "", ""))
    request = urllib.request.Request(url, headers={"User-Agent": "ShinyColorsPet/0.0.1"})
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            payload: Any = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    models = payload.get("data", []) if isinstance(payload, dict) else []
    names = [str(item.get("id", "")).strip() for item in models if isinstance(item, dict)]
    return tuple(dict.fromkeys(name for name in names if name and "image" not in name.lower()))


def discover_openai_model(base_url: str) -> str:
    """Return the first chat model for callers that need a single fallback."""
    models = discover_openai_models(base_url)
    return next(
        (name for name in models if name.startswith("gpt-")),
        models[0] if models else "",
    )


@dataclass(frozen=True, slots=True)
class LLMConfig:
    api_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 60.0
    temperature: float = 0.6
    max_tokens: int = 256

    def endpoint(self) -> str:
        value = self.api_url.strip().rstrip("/")
        if not value:
            raise ValueError("LLM API URL is empty")
        parts = urlsplit(value if "://" in value else "http://" + value)
        path = parts.path.rstrip("/")
        if not path.endswith("/chat/completions"):
            direct = path.endswith(("/v1", "/openai"))
            path = path + ("/chat/completions" if direct else "/v1/chat/completions")
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def complete(self, messages: list[dict[str, str]], cancel: threading.Event) -> str:
        if cancel.is_set():
            raise RuntimeError("request cancelled")
        request_payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        headers = {"Content-Type": "application/json", "User-Agent": "ShinyColorsPet/0.0.1"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        for attempt in range(2):
            if attempt:
                request_payload = {
                    **request_payload,
                    "messages": [
                        *messages,
                        {
                            "role": "system",
                            "content": (
                                "The previous generation returned no assistant content. "
                                "Produce a non-empty response now and follow the existing output "
                                "or application-tool contract exactly."
                            ),
                        },
                    ],
                    "temperature": 0,
                }
            body = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(self.config.endpoint(), body, headers, method="POST")
            try:
                with urllib.request.urlopen(
                    request, timeout=self.config.timeout_seconds
                ) as response:
                    payload: Any = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read(512).decode("utf-8", errors="replace")
                raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"LLM request failed: {exc}") from exc
            if cancel.is_set():
                raise RuntimeError("request cancelled")
            try:
                choice = payload["choices"][0]
                message = choice["message"]
                content = message["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError("LLM response has no assistant message") from exc
            if isinstance(content, str) and content.strip():
                return content.strip()

            finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
            usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
            completion_tokens = (
                usage.get("completion_tokens") if isinstance(usage, dict) else None
            )
            message_fields = (
                ",".join(sorted(str(key) for key in message))
                if isinstance(message, dict)
                else type(message).__name__
            )
            diagnostics = (
                f"finish_reason={finish_reason!r}, completion_tokens={completion_tokens!r}, "
                f"content_type={type(content).__name__}, message_fields={message_fields or 'none'}"
            )
            retryable = (
                attempt == 0
                and finish_reason in (None, "stop")
                and completion_tokens in (None, 0)
                and isinstance(message, dict)
                and not message.get("refusal")
                and not message.get("tool_calls")
            )
            if not retryable:
                suffix = " after one retry" if attempt else ""
                raise RuntimeError(
                    f"LLM returned an empty assistant message{suffix} ({diagnostics})"
                )
        raise AssertionError("unreachable")

    def describe_image(self, data_url: str, prompt: str, cancel: threading.Event) -> str:
        if cancel.is_set():
            raise RuntimeError("request cancelled")
        body = json.dumps({
            "model": self.config.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            "stream": False,
            "temperature": 0.2,
            "max_tokens": min(384, self.config.max_tokens),
        }).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "ShinyColorsPet/0.0.1"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key
        request = urllib.request.Request(self.config.endpoint(), body, headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                payload: Any = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, IndexError,
                TypeError) as exc:
            raise RuntimeError(f"screen vision request failed: {exc}") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("screen vision returned no observation")
        return content.strip()
