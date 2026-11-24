"""Prompting strategies and prompt files (P3.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from toolproof.agent.loop import run_agent
from toolproof.agent.scripted import ScriptedAdapter, call, say
from toolproof.agent.strategies import (
    STRATEGIES,
    extract_final_answer,
    get_strategy,
    load_prompt_file,
)
from toolproof.env.sandbox import Sandbox
from toolproof.env.tools import ALL_TOOLS
from toolproof.paths import prompts_dir


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_every_strategy_builds_on_the_base_prompt(name: str) -> None:
    strategy = get_strategy(name)
    base = load_prompt_file(prompts_dir() / "base.md").sections["system"]
    assert strategy.system_prompt.startswith(base)
    versions = strategy.prompt_versions()
    assert set(versions) == {"base", name}
    assert all(len(v["sha256"]) == 64 and v["version"] for v in versions.values())


def test_prompts_contain_no_tool_names_or_task_details() -> None:
    tool_names = {cls.name for cls in ALL_TOOLS}
    for path in prompts_dir().glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for name in tool_names:
            assert name not in text, f"{path.name} names the tool {name}"
        assert not any(char.isdigit() for char in text.split("-->", 1)[1]), path.name


def test_prompt_file_needs_version_line(tmp_path: Path) -> None:
    bad = tmp_path / "x.md"
    bad.write_text("## system\nhello\n", encoding="utf-8")
    with pytest.raises(ValueError, match="prompt-version"):
        load_prompt_file(bad)


def test_unknown_strategy() -> None:
    with pytest.raises(ValueError, match="unknown strategy"):
        get_strategy("tree_of_thought")


def test_strategies_differ() -> None:
    prompts = {name: get_strategy(name).system_prompt for name in STRATEGIES}
    assert prompts["plain"] == prompts["reflect"]  # reflect differs only by its check message
    assert len({prompts["plain"], prompts["react"], prompts["plan_execute"]}) == 3


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Thought: done.\nFinal answer: 80 orders were cancelled.", "80 orders were cancelled."),
        ("final ANSWER:  yes", "yes"),
        ("No marker here.", "No marker here."),
        ("Final answer: a\nFinal answer: b", "b"),
    ],
)
def test_extract_final_answer(text: str, expected: str) -> None:
    assert extract_final_answer(text) == expected


def test_react_strips_thoughts(sandbox: Sandbox) -> None:
    llm = ScriptedAdapter(
        [
            call("get_date", text="Thought: I need the date."),
            say("Thought: I have it.\nFinal answer: Today is 2026-03-16."),
        ]
    )
    result = run_agent("What day is it?", sandbox.toolbox, llm, get_strategy("react"))
    assert result.final_answer == "Today is 2026-03-16."


def test_plan_execute_plans_without_tools_then_executes(sandbox: Sandbox) -> None:
    llm = ScriptedAdapter(
        [
            say("1. Look up the order.\n2. Answer."),
            call("get_order", {"order_id": 9031}),
            say("It was delivered."),
        ]
    )
    result = run_agent("Status of 9031?", sandbox.toolbox, llm, get_strategy("plan_execute"))
    assert llm.requests[0]["tool_names"] == []
    assert llm.requests[1]["tool_names"] != []
    execute = get_strategy("plan_execute").prompt.sections["execute"]
    assert llm.requests[1]["messages"][-1] == {"role": "user", "content": execute}
    assert result.final_answer == "It was delivered."
    assert result.steps == 3


def test_plan_execute_replans_once_after_errors(sandbox: Sandbox) -> None:
    llm = ScriptedAdapter(
        [
            say("1. Look up the order."),
            call("get_order", {"order_id": 1}),
            call("get_order", {"order_id": 2}),
            say("Neither order exists."),
        ]
    )
    result = run_agent("Find order 1", sandbox.toolbox, llm, get_strategy("plan_execute"))
    replan = get_strategy("plan_execute").prompt.sections["replan"]
    replans = [m for m in result.messages if m.get("content") == replan]
    assert len(replans) == 1


def test_plan_execute_moves_on_if_model_calls_tools_while_planning(sandbox: Sandbox) -> None:
    llm = ScriptedAdapter([call("get_date"), say("done")])
    result = run_agent("Date?", sandbox.toolbox, llm, get_strategy("plan_execute"))
    assert result.final_answer == "done"
    assert llm.requests[1]["tool_names"] != []


def test_reflect_checks_once(sandbox: Sandbox) -> None:
    llm = ScriptedAdapter([say("First answer."), call("get_date"), say("Checked answer.")])
    result = run_agent("Date?", sandbox.toolbox, llm, get_strategy("reflect"))
    check = get_strategy("reflect").prompt.sections["check"]
    assert llm.requests[1]["messages"][-1] == {"role": "user", "content": check}
    assert result.final_answer == "Checked answer."
    assert result.steps == 3


def test_reflect_keeps_first_answer_if_second_is_empty(sandbox: Sandbox) -> None:
    llm = ScriptedAdapter([say("First answer."), say("")])
    result = run_agent("Date?", sandbox.toolbox, llm, get_strategy("reflect"))
    assert result.final_answer == "First answer."
