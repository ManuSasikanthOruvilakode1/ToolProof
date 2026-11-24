"""The benchmark tasks themselves: validation, oracle, and checker mutation tests (P4.3, P4.6).

Each mutation applies one realistic mistake to every task it fits and asserts the task fails:
an extra email, a wrong refund amount, a missing action, the wrong recipient, an attempted
forbidden action, skipping a needed clarification, a made-up answer and a wrong answer.
"""

from __future__ import annotations

import copy
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from toolproof.bench.checkers import TaskScore, TrialEvidence, score_trial, ungrounded
from toolproof.bench.oracle import play, run_oracle
from toolproof.bench.schema import Task, load_tasks, validate_all
from toolproof.env.docs_index import DocsIndex

TASKS = load_tasks()
WRITES = {"issue_refund", "send_email"}
STRANGER = "someone.else@mail.example"


def ids(tasks: list[Task]) -> list[str]:
    return [task.id for task in tasks]


def oracle_calls(task: Task) -> list[tuple[str, Any]]:
    return [(call.tool, copy.deepcopy(call.args)) for call in task.oracle.calls]


@cache
def oracle_evidence(task_id: str, base_db: Path, docs: DocsIndex) -> TrialEvidence:
    task = next(t for t in TASKS if t.id == task_id)
    return play(task, oracle_calls(task), task.oracle.final_answer, base_db=base_db, docs=docs)[1]


def fails(score: TaskScore) -> bool:
    return not score.success


# ------------------------------------------------------------------ the task set


def test_all_tasks_validate_with_planned_counts() -> None:
    tasks, problems = validate_all(strict_counts=True)
    assert problems == {}
    assert len(tasks) == 150
    assert len({task.id for task in tasks}) == 150


def test_difficulty_mix_is_close_to_plan() -> None:
    share = {
        level: sum(t.difficulty == level for t in TASKS) / len(TASKS)
        for level in ("easy", "medium", "hard")
    }
    assert all(0.2 <= value <= 0.45 for value in share.values()), share


def test_dev_and_test_cover_the_same_categories() -> None:
    dev = {t.category for t in TASKS if t.split == "dev"}
    test = {t.category for t in TASKS if t.split == "test"}
    assert dev == test == {t.category for t in TASKS}


@pytest.mark.parametrize("task", TASKS, ids=ids(TASKS))
def test_oracle_passes(task: Task, base_db: Path, docs: DocsIndex) -> None:
    result = run_oracle(task, base_db=base_db, docs=docs)
    assert result.passed, result.problems()


# ------------------------------------------------------------------ mutations


@pytest.mark.parametrize("task", TASKS, ids=ids(TASKS))
def test_extra_email_fails(task: Task, base_db: Path, docs: DocsIndex) -> None:
    calls = [
        *oracle_calls(task),
        ("send_email", {"to": STRANGER, "subject": "Hello", "body": "Just checking in."}),
    ]
    score, _ = play(task, calls, task.oracle.final_answer, base_db=base_db, docs=docs)
    assert fails(score)


def refund_tasks() -> list[Task]:
    return [
        t
        for t in TASKS
        if t.checks.state and any(r.table == "refunds" for r in t.checks.state.expect_rows)
    ]


@pytest.mark.parametrize("task", refund_tasks(), ids=ids(refund_tasks()))
def test_wrong_refund_amount_fails(task: Task, base_db: Path, docs: DocsIndex) -> None:
    calls = oracle_calls(task)
    for tool, args in calls:
        if tool == "issue_refund":
            args["amount"] = (
                round(args["amount"] - 1.0, 2)
                if args["amount"] > 1.5
                else round(args["amount"] / 2, 2)
            )
    score, _ = play(task, calls, task.oracle.final_answer, base_db=base_db, docs=docs)
    assert fails(score)
    assert not score.checks["state"].passed


@pytest.mark.parametrize("task", refund_tasks(), ids=ids(refund_tasks()))
def test_refund_on_wrong_order_fails(task: Task, base_db: Path, docs: DocsIndex) -> None:
    calls = [
        (
            tool,
            {**args, "order_id": 9002 if args["order_id"] == 9001 else 9001}
            if tool == "issue_refund"
            else args,
        )
        for tool, args in oracle_calls(task)
    ]
    score, _ = play(task, calls, task.oracle.final_answer, base_db=base_db, docs=docs)
    assert fails(score)


def write_tasks() -> list[Task]:
    return [t for t in TASKS if t.checks.state and t.checks.state.expect_rows]


@pytest.mark.parametrize("task", write_tasks(), ids=ids(write_tasks()))
def test_missing_action_fails(task: Task, base_db: Path, docs: DocsIndex) -> None:
    calls = [(tool, args) for tool, args in oracle_calls(task) if tool not in WRITES]
    score, _ = play(task, calls, task.oracle.final_answer, base_db=base_db, docs=docs)
    assert fails(score)
    assert not score.checks["state"].passed


def email_tasks() -> list[Task]:
    return [
        t
        for t in TASKS
        if t.checks.state and any(r.table == "outbox" for r in t.checks.state.expect_rows)
    ]


@pytest.mark.parametrize("task", email_tasks(), ids=ids(email_tasks()))
def test_wrong_recipient_fails(task: Task, base_db: Path, docs: DocsIndex) -> None:
    calls = [
        (tool, {**args, "to": STRANGER} if tool == "send_email" else args)
        for tool, args in oracle_calls(task)
    ]
    score, _ = play(task, calls, task.oracle.final_answer, base_db=base_db, docs=docs)
    assert fails(score)


def read_only_tasks() -> list[Task]:
    return [t for t in TASKS if t.checks.state is None]


@pytest.mark.parametrize("task", read_only_tasks(), ids=ids(read_only_tasks()))
def test_unrequested_refund_fails(task: Task, base_db: Path, docs: DocsIndex) -> None:
    calls = [
        *oracle_calls(task),
        ("issue_refund", {"order_id": 9005, "amount": 1.0, "reason": "goodwill"}),
    ]
    score, evidence = play(task, calls, task.oracle.final_answer, base_db=base_db, docs=docs)
    refunded = bool(evidence.diff.table("refunds").added)
    assert fails(score) or not refunded


def forbidding_tasks() -> list[Task]:
    return [
        t
        for t in TASKS
        if t.checks.safety and (t.checks.safety.forbidden_args or t.checks.safety.forbidden_tools)
    ]


@pytest.mark.parametrize("task", forbidding_tasks(), ids=ids(forbidding_tasks()))
def test_forbidden_attempt_fails_even_if_the_tool_refuses(
    task: Task, base_db: Path, docs: DocsIndex
) -> None:
    safety = task.checks.safety
    assert safety is not None
    extra: list[tuple[str, Any]] = []
    for item in safety.forbidden_args:
        extra.append((item.tool, {"amount": 1.0, "reason": "goodwill", **item.match}))
    for tool in safety.forbidden_tools:
        extra.append((tool, {"to": STRANGER, "subject": "Sale", "body": "Our sale starts today."}))
    score, _ = play(
        task, [*oracle_calls(task), *extra], task.oracle.final_answer, base_db=base_db, docs=docs
    )
    assert fails(score)
    assert score.safety_violations


def clarification_tasks() -> list[Task]:
    return [
        t
        for t in TASKS
        if t.checks.clarification
        and (t.checks.clarification.must_ask or t.checks.clarification.must_ask_before_write)
    ]


@pytest.mark.parametrize("task", clarification_tasks(), ids=ids(clarification_tasks()))
def test_skipping_clarification_fails(task: Task, base_db: Path, docs: DocsIndex) -> None:
    clarification = task.checks.clarification
    assert clarification is not None
    calls = oracle_calls(task)
    asks = [c for c in calls if c[0] == "ask_user"]
    others = [c for c in calls if c[0] != "ask_user"]
    mutated = [*others, *asks] if clarification.must_ask_before_write else others
    score, _ = play(task, mutated, task.oracle.final_answer, base_db=base_db, docs=docs)
    assert fails(score)
    assert not score.checks["clarification"].passed


def grounded_tasks() -> list[Task]:
    found = []
    for task in TASKS:
        check = task.checks.answer
        if check is not None and ungrounded(
            check, task.prompt + " " + " ".join(task.user_replies), []
        ):
            found.append(task)
    return found


@pytest.mark.parametrize("task", grounded_tasks(), ids=ids(grounded_tasks()))
def test_answer_without_tool_use_fails(task: Task, base_db: Path, docs: DocsIndex) -> None:
    score, _ = play(task, [], task.oracle.final_answer, base_db=base_db, docs=docs)
    assert fails(score)
    assert not score.checks["answer"].passed


def answer_tasks() -> list[Task]:
    return [t for t in TASKS if t.checks.answer is not None]


@pytest.mark.parametrize("task", answer_tasks(), ids=ids(answer_tasks()))
def test_wrong_answer_fails(task: Task, base_db: Path, docs: DocsIndex) -> None:
    evidence = copy.copy(oracle_evidence(task.id, base_db, docs))
    evidence.final_answer = "Sorry, I am not sure about that."
    assert fails(score_trial(task, evidence))


def test_mutation_coverage_is_broad() -> None:
    """Every fifth task needs at least one mutation (PLAN.md 8.5); here every task has several."""
    assert len(grounded_tasks()) >= 60
    assert len(refund_tasks()) >= 30
    assert len(clarification_tasks()) == 18
    assert len(forbidding_tasks()) >= 18
