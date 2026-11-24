"""One interface over LLM backends: Ollama (live), Recording and Replay (CI cassettes).

Messages use a small provider-neutral format; each adapter translates it:

- ``{"role": "system" | "user", "content": str}``
- ``{"role": "assistant", "content": str, "tool_calls": [{"id", "name", "arguments"}]}``
- ``{"role": "tool", "tool_call_id": str, "name": str, "content": str}``

Adapters never repair model output. A tool call whose arguments are not a JSON object is
returned with ``parse_error`` set, so the loop can count it as malformed.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

Message = dict[str, Any]
ToolSchema = dict[str, Any]

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class LLMError(Exception):
    """The backend failed (connection, HTTP error, unparseable response, missing cassette)."""


class CassetteMiss(LLMError):
    """Replay was asked for a request that was never recorded."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Any  # a dict when well-formed; the raw value otherwise
    parse_error: str | None = None

    def as_message_part(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_seconds: float = 0.0
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def assistant_message(self) -> Message:
        message: Message = {"role": "assistant", "content": self.text}
        if self.tool_calls:
            message["tool_calls"] = [call.as_message_part() for call in self.tool_calls]
        return message

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LLMResponse:
        return cls(
            text=data["text"],
            tool_calls=tuple(ToolCall(**call) for call in data.get("tool_calls", [])),
            usage=TokenUsage(**data.get("usage", {})),
            latency_seconds=data.get("latency_seconds", 0.0),
            finish_reason=data.get("finish_reason"),
            raw=data.get("raw", {}),
        )


class LLMAdapter(Protocol):
    model: str

    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        temperature: float,
        seed: int,
        max_tokens: int,
    ) -> LLMResponse: ...

    def describe(self) -> dict[str, Any]:
        """Facts for the run manifest: backend, model, digest, server version."""
        ...


def parse_tool_arguments(raw: Any) -> tuple[Any, str | None]:
    """Return (arguments, parse_error). Strings are decoded as JSON; nothing else is fixed."""
    if isinstance(raw, dict):
        return raw, None
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as error:
            return raw, f"arguments are not valid JSON ({error.msg})"
        if isinstance(decoded, dict):
            return decoded, None
        return decoded, "arguments are not a JSON object"
    if raw is None:
        return {}, None
    return raw, "arguments are not a JSON object"


# ------------------------------------------------------------------ Ollama


def to_ollama_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message["role"]
        if role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": message.get("content", "")}
            calls = message.get("tool_calls") or []
            if calls:
                entry["tool_calls"] = [
                    {
                        "function": {
                            "name": call["name"],
                            "arguments": call["arguments"]
                            if isinstance(call["arguments"], dict)
                            else {},
                        }
                    }
                    for call in calls
                ]
            converted.append(entry)
        elif role == "tool":
            converted.append(
                {"role": "tool", "content": message["content"], "tool_name": message["name"]}
            )
        else:
            converted.append({"role": role, "content": message["content"]})
    return converted


class OllamaAdapter:
    """Native tool calling through Ollama's ``/api/chat`` (non-streaming)."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout_seconds: float = 300.0,
        client: httpx.Client | None = None,
        extra_options: dict[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self.extra_options = dict(extra_options or {})

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise LLMError(f"Ollama {path} failed: {error}") from error
        return data

    def _get(self, path: str) -> dict[str, Any]:
        try:
            response = self._client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise LLMError(f"Ollama {path} failed: {error}") from error
        return data

    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        temperature: float,
        seed: int,
        max_tokens: int,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": to_ollama_messages(messages),
            "stream": False,
            "options": {
                "temperature": temperature,
                "seed": seed,
                "num_predict": max_tokens,
                **self.extra_options,
            },
        }
        if tools:
            payload["tools"] = list(tools)
        started = time.perf_counter()
        data = self._post("/api/chat", payload)
        latency = time.perf_counter() - started
        message = data.get("message")
        if not isinstance(message, dict):
            raise LLMError(f"Ollama response has no message: {str(data)[:200]}")
        calls = []
        for index, raw_call in enumerate(message.get("tool_calls") or []):
            function = raw_call.get("function") if isinstance(raw_call, dict) else None
            if not isinstance(function, dict):
                calls.append(ToolCall(f"call_{index}", "", raw_call, "tool call has no function"))
                continue
            arguments, error = parse_tool_arguments(function.get("arguments"))
            name = function.get("name")
            if not isinstance(name, str) or not name:
                error = error or "tool call has no name"
                name = ""
            calls.append(ToolCall(raw_call.get("id") or f"call_{index}", name, arguments, error))
        return LLMResponse(
            text=message.get("content") or "",
            tool_calls=tuple(calls),
            usage=TokenUsage(
                input_tokens=int(data.get("prompt_eval_count") or 0),
                output_tokens=int(data.get("eval_count") or 0),
            ),
            latency_seconds=round(latency, 4),
            finish_reason=data.get("done_reason"),
            raw=data,
        )

    def describe(self) -> dict[str, Any]:
        version = self._get("/api/version").get("version")
        digest = None
        for entry in self._get("/api/tags").get("models", []):
            if entry.get("name") in (self.model, f"{self.model}:latest"):
                digest = entry.get("digest")
        show = self._post("/api/show", {"model": self.model})
        return {
            "backend": "ollama",
            "model": self.model,
            "digest": digest,
            "server_version": version,
            "capabilities": show.get("capabilities", []),
            "parameter_size": (show.get("details") or {}).get("parameter_size"),
            "options": self.extra_options,
        }


# ------------------------------------------------------------------ recording and replay


def request_key(
    model: str,
    messages: Sequence[Message],
    tools: Sequence[ToolSchema],
    temperature: float,
    seed: int,
    max_tokens: int,
) -> str:
    """Stable hash of everything that determines a response."""
    payload = {
        "model": model,
        "messages": list(messages),
        "tools": list(tools),
        "temperature": temperature,
        "seed": seed,
        "max_tokens": max_tokens,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RecordingAdapter:
    """Wraps another adapter and appends every request/response pair to a cassette (JSONL)."""

    def __init__(self, inner: LLMAdapter, cassette: Path) -> None:
        self.inner = inner
        self.model = inner.model
        self.cassette = cassette
        cassette.parent.mkdir(parents=True, exist_ok=True)

    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        temperature: float,
        seed: int,
        max_tokens: int,
    ) -> LLMResponse:
        response = self.inner.chat(
            messages, tools, temperature=temperature, seed=seed, max_tokens=max_tokens
        )
        key = request_key(self.model, messages, tools, temperature, seed, max_tokens)
        record = {"key": key, "model": self.model, "response": response.to_dict()}
        with self.cassette.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return response

    def describe(self) -> dict[str, Any]:
        return {**self.inner.describe(), "recording_to": self.cassette.name}


class ReplayAdapter:
    """Serves recorded responses by request hash. No model and no network needed."""

    def __init__(self, cassette: Path, *, model: str | None = None) -> None:
        self.cassette = cassette
        self._responses: dict[str, list[LLMResponse]] = {}
        self._served: dict[str, int] = {}
        models: set[str] = set()
        for line in cassette.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            models.add(record["model"])
            self._responses.setdefault(record["key"], []).append(
                LLMResponse.from_dict(record["response"])
            )
        if model is None and len(models) > 1:
            raise ValueError(f"cassette holds several models {sorted(models)}; pass model=")
        self.model = model or (models.pop() if models else "replay")

    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        temperature: float,
        seed: int,
        max_tokens: int,
    ) -> LLMResponse:
        key = request_key(self.model, messages, tools, temperature, seed, max_tokens)
        recorded = self._responses.get(key)
        if not recorded:
            raise CassetteMiss(f"no recorded response for request {key[:12]} in {self.cassette}")
        index = self._served.get(key, 0)
        self._served[key] = index + 1
        return recorded[min(index, len(recorded) - 1)]

    def describe(self) -> dict[str, Any]:
        return {"backend": "replay", "model": self.model, "cassette": self.cassette.name}
