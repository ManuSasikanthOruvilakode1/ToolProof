"""A scripted LLM adapter for tests and dry runs (P3.8). It never calls a model."""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from typing import Any

from toolproof.agent.llm import (
    LLMError,
    LLMResponse,
    Message,
    TokenUsage,
    ToolCall,
    ToolSchema,
)

ScriptStep = LLMResponse | Callable[[Sequence[Message], Sequence[ToolSchema]], LLMResponse]


def say(text: str) -> LLMResponse:
    """A response with text and no tool call."""
    return LLMResponse(text=text, usage=TokenUsage(10, len(text.split())), latency_seconds=0.01)


def call(
    name: str,
    arguments: Any = None,
    *,
    text: str = "",
    parse_error: str | None = None,
    call_id: str = "call_0",
) -> LLMResponse:
    """A response with one tool call."""
    return LLMResponse(
        text=text,
        tool_calls=(ToolCall(call_id, name, {} if arguments is None else arguments, parse_error),),
        usage=TokenUsage(10, 5),
        latency_seconds=0.01,
    )


class ScriptedAdapter:
    """Returns the scripted responses in order; raises LLMError when the script runs out."""

    def __init__(self, script: Sequence[ScriptStep], model: str = "scripted") -> None:
        self.script = list(script)
        self.model = model
        self.requests: list[dict[str, Any]] = []

    def chat(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema],
        *,
        temperature: float,
        seed: int,
        max_tokens: int,
    ) -> LLMResponse:
        self.requests.append(
            {
                "messages": copy.deepcopy(list(messages)),
                "tool_names": [tool["function"]["name"] for tool in tools],
                "temperature": temperature,
                "seed": seed,
                "max_tokens": max_tokens,
            }
        )
        index = len(self.requests) - 1
        if index >= len(self.script):
            raise LLMError("scripted adapter ran out of responses")
        step = self.script[index]
        return step(messages, tools) if callable(step) else step

    def describe(self) -> dict[str, Any]:
        return {"backend": "scripted", "model": self.model}
