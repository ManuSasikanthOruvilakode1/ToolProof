"""Agent loop with a scripted LLM (P3.4, P3.8)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from toolproof.agent.llm import LLMResponse, Message, ToolSchema
from toolproof.agent.loop import MALFORMED_CALL, AgentLimits, run_agent
from toolproof.agent.scripted import ScriptedAdapter, call, say
from toolproof.agent.strategies import get_strategy
from toolproof.env.docs_index import DocsIndex
from toolproof.env.faults import ScheduledFault
from toolproof.env.sandbox import Sandbox
from toolproof.tracing import MemoryTracer
from toolproof.trial import TrialSpec, run_trial

PLAIN = get_strategy("plain")


def run(sandbox: Sandbox, script: list[object], **kwargs: object):  # type: ignore[no-untyped-def]
    llm = ScriptedAdapter(script)  # type: ignore[arg-type]
    result = run_agent("What happened to order 9031?", sandbox.toolbox, llm, PLAIN, **kwargs)  # type: ignore[arg-type]
    return result, llm


def last_tool_error(messages: list[Message]) -> dict[str, str]:
    tool_messages = [m for m in messages if m["role"] == "tool"]
    error: dict[str, str] = json.loads(tool_messages[-1]["content"])["error"]
    return error


def test_normal_path(sandbox: Sandbox) -> None:
    result, llm = run(sandbox, [call("get_order", {"order_id": 9031}), say("It was delivered.")])
    assert result.termination == "final_answer"
    assert result.final_answer == "It was delivered."
    assert result.steps == 2 and result.total_calls == 1 and result.malformed_calls == 0
    roles = [m["role"] for m in result.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    tool_message = result.messages[3]
    assert tool_message["tool_call_id"] == "call_0" and tool_message["name"] == "get_order"
    assert json.loads(tool_message["content"])["order_id"] == 9031
    assert llm.requests[0]["tool_names"][:2] == ["sql_query", "get_order"]
    assert llm.requests[0]["max_tokens"] == AgentLimits().max_output_tokens
    assert result.usage.input_tokens == 20


def test_malformed_json_is_counted_and_reported(sandbox: Sandbox) -> None:
    result, _ = run(
        sandbox,
        [call("get_order", "{order_id:", parse_error="arguments are not valid JSON"), say("ok")],
    )
    assert result.unparsed_calls == 1 and result.malformed_calls == 1
    assert result.tool_calls == []  # never executed
    assert last_tool_error(result.messages)["type"] == MALFORMED_CALL


def test_unknown_tool_is_counted(sandbox: Sandbox) -> None:
    result, _ = run(sandbox, [call("lookup_order", {"id": 9031}), say("ok")])
    assert result.malformed_calls == 1
    assert last_tool_error(result.messages)["type"] == "UnknownTool"


def test_missing_fields_are_counted_but_policy_errors_are_not(sandbox: Sandbox) -> None:
    result, _ = run(
        sandbox,
        [
            call("issue_refund", {"order_id": 9031}),
            call("issue_refund", {"order_id": 9031, "amount": 5000, "reason": "damaged"}),
            say("Could not refund."),
        ],
    )
    assert result.total_calls == 2
    assert result.malformed_calls == 1  # missing fields only; amount > total is a policy error


def test_repeated_identical_calls_hit_the_step_limit(sandbox: Sandbox) -> None:
    def same(messages: Sequence[Message], tools: Sequence[ToolSchema]) -> LLMResponse:
        return call("get_order", {"order_id": 9031})

    result, _ = run(sandbox, [same] * 50, limits=AgentLimits(max_steps=4))
    assert result.termination == "step_limit"
    assert result.steps == 4 and result.total_calls == 4
    assert result.final_answer is None


def test_time_limit(sandbox: Sandbox) -> None:
    ticks = iter([0.0, 0.0, 100.0, 200.0, 300.0])
    result, _ = run(
        sandbox,
        [call("get_date"), call("get_date"), say("never")],
        limits=AgentLimits(max_wall_seconds=150),
        clock=lambda: next(ticks),
    )
    assert result.termination == "time_limit"
    assert result.steps == 2


def test_llm_error_ends_the_trial(sandbox: Sandbox) -> None:
    result, _ = run(sandbox, [call("get_date")])  # script runs out on step 2
    assert result.termination == "llm_error"
    assert result.error is not None and "ran out" in result.error
    assert result.final_answer is None


def test_empty_reply_is_an_empty_final_answer(sandbox: Sandbox) -> None:
    result, _ = run(sandbox, [say("")])
    assert result.termination == "final_answer" and result.final_answer == ""


def test_multiple_calls_in_one_step(sandbox: Sandbox) -> None:
    both = LLMResponse(
        text="",
        tool_calls=(
            call("get_date").tool_calls[0],
            call("get_order", {"order_id": 9031}, call_id="call_1").tool_calls[0],
        ),
    )
    result, _ = run(sandbox, [both, say("done")])
    assert result.steps == 2 and result.total_calls == 2
    assert [m["tool_call_id"] for m in result.messages if m["role"] == "tool"] == [
        "call_0",
        "call_1",
    ]


def test_trace_events(sandbox: Sandbox) -> None:
    tracer = MemoryTracer("run", "task", 0, clock=lambda: "t")
    run(sandbox, [call("get_order", {"order_id": 1}), say("Not found.")], tracer=tracer)
    kinds = [event["event"] for event in tracer.events]
    assert kinds == [
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_error",
        "llm_request",
        "llm_response",
        "final",
    ]
    first_request = tracer.events[0]["payload"]
    assert [m["role"] for m in first_request["new_messages"]] == ["system", "user"]
    second_request = tracer.events[4]["payload"]
    assert [m["role"] for m in second_request["new_messages"]] == ["tool"]
    assert tracer.events[-1]["payload"]["termination"] == "final_answer"


# ------------------------------------------------------------------ trials


def test_run_trial_with_fault_and_refund(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    spec = TrialSpec(
        task_id="demo",
        prompt="Refund order 9053 for late delivery.",
        faults=(ScheduledFault(tool="get_order", call=1, error="ToolTimeout"),),
    )
    script = [
        call("get_order", {"order_id": 9053}),
        call("get_order", {"order_id": 9053}),
        call("issue_refund", {"order_id": 9053, "amount": 12.10, "reason": "late_delivery"}),
        say("Refunded $12.10."),
    ]
    outcome = run_trial(
        spec,
        llm=ScriptedAdapter(script),
        strategy=PLAIN,
        trial=2,
        workdir=tmp_path / "trial",
        base_db=base_db,
        docs=docs,
    )
    assert outcome.injected_faults == 1
    assert outcome.diff.changed_tables == ["refunds"]
    summary = outcome.summary()
    assert summary["trial"] == 2 and summary["tool_calls"] == 3
    assert summary["changed_tables"] == ["refunds"]


def test_trial_seed_defaults_to_trial_index(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    llm = ScriptedAdapter([say("hi")])
    run_trial(
        TrialSpec("t", "hello"),
        llm=llm,
        strategy=PLAIN,
        trial=4,
        workdir=tmp_path,
        base_db=base_db,
        docs=docs,
    )
    assert llm.requests[0]["seed"] == 4


@pytest.mark.parametrize("n_distractors", [0, 7, 15])
def test_trial_offers_distractors(
    base_db: Path, docs: DocsIndex, tmp_path: Path, n_distractors: int
) -> None:
    llm = ScriptedAdapter([say("hi")])
    run_trial(
        TrialSpec("t", "hello", n_distractors=n_distractors),
        llm=llm,
        strategy=PLAIN,
        trial=0,
        workdir=tmp_path,
        base_db=base_db,
        docs=docs,
    )
    assert len(llm.requests[0]["tool_names"]) == 9 + n_distractors
