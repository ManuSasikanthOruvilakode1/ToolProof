"""The agent loop (P3.4), written from scratch so every step can be measured.

One step is one LLM call. The loop stops at the first assistant message without a tool call
that the strategy accepts as final, or at the step limit, the time limit or an LLM error.
Malformed tool calls (arguments that are not a JSON object, unknown tools, arguments that do not
match the schema) are returned to the model as errors and counted; nothing is fixed silently.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from toolproof.agent.llm import LLMAdapter, LLMError, Message, TokenUsage
from toolproof.agent.strategies import FinalAnswer, Strategy
from toolproof.env.toolbox import ToolBox, ToolCallRecord
from toolproof.tracing import NullTracer, Tracer

Termination = Literal["final_answer", "step_limit", "time_limit", "llm_error"]
MALFORMED_CALL = "MalformedCall"


@dataclass(frozen=True)
class AgentLimits:
    max_steps: int = 15
    max_wall_seconds: float = 600.0  # safety net only; see DECISION in P3.7
    max_output_tokens: int = 1024


@dataclass
class AgentResult:
    final_answer: str | None
    termination: Termination
    steps: int
    messages: list[Message]
    tool_calls: list[ToolCallRecord]
    unparsed_calls: int  # tool calls whose arguments could not be read (never executed)
    malformed_calls: int  # unparsed + unknown tool + schema errors
    usage: TokenUsage = field(default_factory=TokenUsage)
    llm_seconds: float = 0.0
    wall_seconds: float = 0.0
    error: str | None = None
    context_limit_hits: int = 0  # LLM calls whose prompt filled the context window

    @property
    def total_calls(self) -> int:
        return len(self.tool_calls) + self.unparsed_calls

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tool_calls"] = [record.to_dict() for record in self.tool_calls]
        return data


def run_agent(
    task_prompt: str,
    toolbox: ToolBox,
    llm: LLMAdapter,
    strategy: Strategy,
    *,
    limits: AgentLimits | None = None,
    temperature: float = 0.7,
    seed: int = 0,
    tracer: Tracer | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> AgentResult:
    limits = limits or AgentLimits()
    tracer = tracer or NullTracer()
    session = strategy.new_session()
    messages: list[Message] = session.initial_messages(task_prompt)
    traced_upto = 0
    records: list[ToolCallRecord] = []
    unparsed = 0
    input_tokens = output_tokens = 0
    llm_seconds = 0.0
    context_limit_hits = 0
    steps = 0
    final_answer: str | None = None
    error: str | None = None
    started = clock()

    while True:
        if steps >= limits.max_steps:
            termination: Termination = "step_limit"
            break
        if clock() - started >= limits.max_wall_seconds:
            termination = "time_limit"
            break
        steps += 1
        tools = toolbox.schemas() if session.offer_tools() else []
        tracer.event(
            "llm_request",
            steps,
            {
                "new_messages": messages[traced_upto:],
                "n_messages": len(messages),
                "tools_offered": len(tools),
            },
        )
        try:
            response = llm.chat(
                messages,
                tools,
                temperature=temperature,
                seed=seed,
                max_tokens=limits.max_output_tokens,
            )
        except LLMError as exc:
            termination = "llm_error"
            error = str(exc)
            break

        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens
        llm_seconds += response.latency_seconds
        context_limit_hits += response.context_limit_hit
        tracer.event(
            "llm_response",
            steps,
            {
                "text": response.text,
                "tool_calls": [call.as_message_part() for call in response.tool_calls],
                "finish_reason": response.finish_reason,
                "context_limit_hit": response.context_limit_hit,
            },
            tokens={"input": response.usage.input_tokens, "output": response.usage.output_tokens},
            latency=response.latency_seconds,
        )
        messages.append(response.assistant_message())
        traced_upto = len(messages)

        if response.tool_calls:
            step_records: list[ToolCallRecord] = []
            for call in response.tool_calls:
                tracer.event(
                    "tool_call",
                    steps,
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "parse_error": call.parse_error,
                    },
                )
                if call.parse_error is not None:
                    unparsed += 1
                    message = (
                        f"Could not read the tool call: {call.parse_error}. "
                        "Send the arguments as a JSON object that matches the tool's parameters."
                    )
                    content = json.dumps({"error": {"type": MALFORMED_CALL, "message": message}})
                    tracer.event(
                        "tool_error",
                        steps,
                        {
                            "id": call.id,
                            "name": call.name,
                            "error_type": MALFORMED_CALL,
                            "error_message": message,
                            "injected": False,
                        },
                    )
                else:
                    record = toolbox.call(call.name, call.arguments)
                    step_records.append(record)
                    content = record.content_for_model()
                    tracer.event(
                        "tool_result" if record.ok else "tool_error",
                        steps,
                        {"id": call.id, **record.to_dict()},
                    )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": content}
                )
            records.extend(step_records)
            messages.extend(session.after_tool_results(step_records))
            continue

        decision = session.on_no_tool_call(response)
        if isinstance(decision, FinalAnswer):
            final_answer = decision.text
            termination = "final_answer"
            break
        messages.extend(decision.messages)

    malformed = unparsed + sum(record.malformed for record in records)
    result = AgentResult(
        final_answer=final_answer,
        termination=termination,
        steps=steps,
        messages=messages,
        tool_calls=records,
        unparsed_calls=unparsed,
        malformed_calls=malformed,
        usage=TokenUsage(input_tokens, output_tokens),
        llm_seconds=round(llm_seconds, 4),
        wall_seconds=round(clock() - started, 4),
        error=error,
        context_limit_hits=context_limit_hits,
    )
    tracer.event(
        "final",
        steps,
        {
            "termination": termination,
            "answer": final_answer,
            "error": error,
            "tool_calls": result.total_calls,
            "malformed_calls": malformed,
            "context_limit_hits": context_limit_hits,
        },
        tokens={"input": input_tokens, "output": output_tokens},
    )
    return result
