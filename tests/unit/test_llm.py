"""LLM adapters: Ollama request/response handling, recording and replay (P3.1, P3.3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from toolproof.agent.llm import (
    CassetteMiss,
    LLMError,
    LLMResponse,
    OllamaAdapter,
    RecordingAdapter,
    ReplayAdapter,
    TokenUsage,
    ToolCall,
    parse_tool_arguments,
    request_key,
    to_ollama_messages,
)
from toolproof.agent.scripted import ScriptedAdapter, call, say

TOOLS = [{"type": "function", "function": {"name": "get_order", "parameters": {}}}]
MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]


# ------------------------------------------------------------------ argument parsing


@pytest.mark.parametrize(
    ("raw", "expected", "has_error"),
    [
        ({"order_id": 1}, {"order_id": 1}, False),
        ('{"order_id": 1}', {"order_id": 1}, False),
        ("", {}, False),
        (None, {}, False),
        ("{order_id: 1}", "{order_id: 1}", True),
        ("[1, 2]", [1, 2], True),
        (42, 42, True),
    ],
)
def test_parse_tool_arguments(raw: Any, expected: Any, has_error: bool) -> None:
    arguments, error = parse_tool_arguments(raw)
    assert arguments == expected
    assert (error is not None) == has_error


def test_to_ollama_messages() -> None:
    converted = to_ollama_messages(
        [
            *MESSAGES,
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "name": "get_order", "arguments": {"order_id": 9001}},
                    {"id": "c2", "name": "bad", "arguments": "not json"},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "get_order", "content": "{}"},
        ]
    )
    assert converted[0] == {"role": "system", "content": "sys"}
    calls = converted[2]["tool_calls"]
    assert calls[0]["function"] == {"name": "get_order", "arguments": {"order_id": 9001}}
    assert calls[1]["function"]["arguments"] == {}  # Ollama needs an object
    assert converted[3] == {"role": "tool", "content": "{}", "tool_name": "get_order"}


# ------------------------------------------------------------------ Ollama adapter


def mock_ollama(chat_reply: dict[str, Any], seen: list[dict[str, Any]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        seen.append({"path": request.url.path, "body": body})
        if request.url.path == "/api/chat":
            return httpx.Response(200, json=chat_reply)
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.35.1"})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:8b", "digest": "sha256-abc123"}]}
            )
        if request.url.path == "/api/show":
            return httpx.Response(
                200,
                json={"capabilities": ["completion", "tools"], "details": {"parameter_size": "8B"}},
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_chat_request_and_parsing() -> None:
    seen: list[dict[str, Any]] = []
    reply = {
        "message": {
            "role": "assistant",
            "content": "Looking it up.",
            "tool_calls": [
                {"function": {"name": "get_order", "arguments": {"order_id": 9031}}},
                {"function": {"name": "sql_query", "arguments": '{"query": "SELECT 1"}'}},
                {"function": {"name": "get_order", "arguments": "{broken"}},
                {"function": {"arguments": {}}},
            ],
        },
        "prompt_eval_count": 120,
        "eval_count": 30,
        "done_reason": "stop",
    }
    adapter = OllamaAdapter("qwen3:8b", client=mock_ollama(reply, seen))
    response = adapter.chat(MESSAGES, TOOLS, temperature=0.7, seed=3, max_tokens=256)

    body = seen[0]["body"]
    assert seen[0]["path"] == "/api/chat"
    assert body["model"] == "qwen3:8b" and body["stream"] is False
    assert body["options"] == {"temperature": 0.7, "seed": 3, "num_predict": 256}
    assert body["tools"] == TOOLS

    assert response.text == "Looking it up."
    assert response.usage == TokenUsage(120, 30)
    assert response.finish_reason == "stop"
    first, second, broken, nameless = response.tool_calls
    assert first == ToolCall("call_0", "get_order", {"order_id": 9031}, None)
    assert second.arguments == {"query": "SELECT 1"} and second.parse_error is None
    assert broken.parse_error is not None
    assert nameless.parse_error == "tool call has no name"


def test_ollama_omits_tools_when_none_offered() -> None:
    seen: list[dict[str, Any]] = []
    adapter = OllamaAdapter("m", client=mock_ollama({"message": {"content": "plan"}}, seen))
    assert adapter.chat(MESSAGES, [], temperature=0, seed=0, max_tokens=10).text == "plan"
    assert "tools" not in seen[0]["body"]


def test_ollama_describe() -> None:
    adapter = OllamaAdapter("qwen3:8b", client=mock_ollama({}, []))
    info = adapter.describe()
    assert info["digest"] == "sha256-abc123"
    assert info["server_version"] == "0.35.1"
    assert "tools" in info["capabilities"]
    assert info["parameter_size"] == "8B"


@pytest.mark.parametrize(
    "transport",
    [
        httpx.MockTransport(lambda request: httpx.Response(500, json={"error": "boom"})),
        httpx.MockTransport(lambda request: httpx.Response(200, json={"no": "message"})),
        httpx.MockTransport(lambda request: httpx.Response(200, content=b"not json")),
    ],
)
def test_ollama_errors_become_llm_errors(transport: httpx.MockTransport) -> None:
    adapter = OllamaAdapter("m", client=httpx.Client(transport=transport))
    with pytest.raises(LLMError):
        adapter.chat(MESSAGES, [], temperature=0, seed=0, max_tokens=10)


def test_ollama_connection_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    adapter = OllamaAdapter("m", client=httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(LLMError, match="refused"):
        adapter.describe()


# ------------------------------------------------------------------ recording and replay


def test_request_key_is_stable_and_sensitive() -> None:
    key = request_key("m", MESSAGES, TOOLS, 0.7, 1, 100)
    assert key == request_key("m", [dict(m) for m in MESSAGES], TOOLS, 0.7, 1, 100)
    assert key != request_key("m", MESSAGES, TOOLS, 0.7, 2, 100)
    assert key != request_key("other", MESSAGES, TOOLS, 0.7, 1, 100)


def test_record_then_replay(tmp_path: Path) -> None:
    cassette = tmp_path / "c.jsonl"
    recorder = RecordingAdapter(
        ScriptedAdapter([call("get_order", {"order_id": 1}), say("x")]), cassette
    )
    first = recorder.chat(MESSAGES, TOOLS, temperature=0.7, seed=0, max_tokens=50)
    second_messages = [*MESSAGES, first.assistant_message()]
    second = recorder.chat(second_messages, TOOLS, temperature=0.7, seed=0, max_tokens=50)

    replay = ReplayAdapter(cassette)
    assert replay.model == "scripted"
    assert replay.chat(MESSAGES, TOOLS, temperature=0.7, seed=0, max_tokens=50) == first
    assert replay.chat(second_messages, TOOLS, temperature=0.7, seed=0, max_tokens=50) == second
    with pytest.raises(CassetteMiss):
        replay.chat(MESSAGES, TOOLS, temperature=0.0, seed=0, max_tokens=50)
    assert recorder.describe()["recording_to"] == "c.jsonl"
    assert replay.describe()["backend"] == "replay"


def test_replay_serves_repeated_requests_in_order(tmp_path: Path) -> None:
    cassette = tmp_path / "c.jsonl"
    recorder = RecordingAdapter(ScriptedAdapter([say("one"), say("two")]), cassette)
    for _ in range(2):
        recorder.chat(MESSAGES, [], temperature=0, seed=0, max_tokens=5)
    replay = ReplayAdapter(cassette)
    texts = [replay.chat(MESSAGES, [], temperature=0, seed=0, max_tokens=5).text for _ in range(3)]
    assert texts == ["one", "two", "two"]


def test_replay_rejects_mixed_models(tmp_path: Path) -> None:
    cassette = tmp_path / "c.jsonl"
    for model in ("a", "b"):
        RecordingAdapter(ScriptedAdapter([say(model)], model=model), cassette).chat(
            MESSAGES, [], temperature=0, seed=0, max_tokens=5
        )
    with pytest.raises(ValueError, match="several models"):
        ReplayAdapter(cassette)
    assert (
        ReplayAdapter(cassette, model="b")
        .chat(MESSAGES, [], temperature=0, seed=0, max_tokens=5)
        .text
        == "b"
    )


def test_response_round_trip() -> None:
    response = LLMResponse(
        text="t",
        tool_calls=(ToolCall("c", "n", "{bad", "error"),),
        usage=TokenUsage(1, 2),
        latency_seconds=0.5,
        finish_reason="stop",
    )
    assert LLMResponse.from_dict(response.to_dict()) == response
    assert response.usage.total == 3


def test_scripted_adapter_runs_out() -> None:
    adapter = ScriptedAdapter([say("only")])
    adapter.chat(MESSAGES, TOOLS, temperature=0, seed=0, max_tokens=5)
    assert adapter.requests[0]["tool_names"] == ["get_order"]
    with pytest.raises(LLMError, match="ran out"):
        adapter.chat(MESSAGES, TOOLS, temperature=0, seed=0, max_tokens=5)
