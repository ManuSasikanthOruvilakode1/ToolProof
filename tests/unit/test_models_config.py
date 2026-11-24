"""configs/models.yaml and context-window detection (P3.7)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from toolproof.agent.llm import LLMResponse, OllamaAdapter, TokenUsage
from toolproof.agent.loop import AgentLimits, run_agent
from toolproof.agent.scripted import ScriptedAdapter, say
from toolproof.agent.strategies import get_strategy
from toolproof.env.sandbox import Sandbox
from toolproof.models_config import digest_matches, load_models_config


def test_models_config_loads() -> None:
    config = load_models_config()
    assert [config.models[k].name for k in ("small", "medium", "large")] == [
        "qwen2.5:3b",
        "qwen2.5:7b",
        "qwen2.5:14b",
    ]
    assert config.defaults.num_ctx == 8192
    assert config.defaults.limits() == AgentLimits(
        max_steps=15, max_wall_seconds=600, max_output_tokens=1024
    )
    assert config.defaults.limits() == AgentLimits()  # code defaults agree with the config


def test_resolve_by_role_or_name() -> None:
    config = load_models_config()
    assert config.resolve("medium") == config.resolve("qwen2.5:7b")
    with pytest.raises(KeyError):
        config.resolve("llama3:70b")
    adapter = config.adapter("large")
    assert adapter.model == "qwen2.5:14b" and adapter.extra_options == {"num_ctx": 8192}


def test_digest_matches() -> None:
    entry = load_models_config().resolve("small")
    assert digest_matches(entry, entry.digest)
    assert digest_matches(entry, "sha256:" + entry.digest)
    assert not digest_matches(entry, "0" * 64)
    assert not digest_matches(entry, None)


def ollama_with_prompt_tokens(tokens: int, seen: list[dict[str, Any]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"content": "ok"}, "prompt_eval_count": tokens, "eval_count": 3}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("num_ctx", "prompt_tokens", "hit"),
    [(None, 3000, False), (None, 3100, True), (8192, 3100, False), (8192, 7200, True)],
)
def test_context_limit_detection(num_ctx: int | None, prompt_tokens: int, hit: bool) -> None:
    seen: list[dict[str, Any]] = []
    options = {"num_ctx": num_ctx} if num_ctx else None
    adapter = OllamaAdapter(
        "m", client=ollama_with_prompt_tokens(prompt_tokens, seen), extra_options=options
    )
    response = adapter.chat(
        [{"role": "user", "content": "x"}], [], temperature=0, seed=0, max_tokens=1000
    )
    assert response.context_limit_hit is hit
    if num_ctx:
        assert seen[0]["options"]["num_ctx"] == num_ctx


def test_loop_counts_context_limit_hits(sandbox: Sandbox) -> None:
    full = LLMResponse(text="partial view", usage=TokenUsage(8000, 10), context_limit_hit=True)
    result = run_agent("hi", sandbox.toolbox, ScriptedAdapter([full]), get_strategy("plain"))
    assert result.context_limit_hits == 1
    clean = run_agent("hi", sandbox.toolbox, ScriptedAdapter([say("fine")]), get_strategy("plain"))
    assert clean.context_limit_hits == 0
