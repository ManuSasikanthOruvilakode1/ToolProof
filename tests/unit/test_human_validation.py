"""Human validation tooling (P4.7) with scripted input."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from toolproof.bench.human import agreement_report, record_attempt, run_attempt, validation_set
from toolproof.bench.schema import load_tasks
from toolproof.env.docs_index import DocsIndex

TASKS = {t.id: t for t in load_tasks()}


def scripted(lines: list[str]) -> tuple[Iterator[str], list[str]]:
    return iter(lines), []


def test_validation_set_is_fixed_and_stratified() -> None:
    chosen = validation_set(list(TASKS.values()))
    assert len(chosen) == 20 and len(set(chosen)) == 20
    assert chosen == validation_set(list(TASKS.values()))
    categories = {TASKS[t].category for t in chosen}
    assert len(categories) == 8


def run(task_id: str, lines: list[str], base_db: Path, docs: DocsIndex):  # type: ignore[no-untyped-def]
    replies = iter(lines)
    out: list[str] = []
    attempt = run_attempt(
        TASKS[task_id], lambda prompt: next(replies), out.append, base_db=base_db, docs=docs
    )
    return attempt, replies, out


def test_human_solves_a_task_and_records_it(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    task = TASKS["single-001"]
    call = task.oracle.calls[0]
    import json

    lines = [
        "tools",
        "bogus",
        f"call {call.tool} {{bad json",
        f"call {call.tool} {json.dumps(call.args)}",
        f"answer {task.oracle.final_answer}",
        "maybe",
        "y",
        "n",
        "Wording could be clearer.",
    ]
    attempt, replies, out = run("single-001", lines, base_db, docs)
    assert attempt is not None and attempt.score.success
    assert any("sql_query(" in line for line in out) and any(
        "not valid JSON" in line for line in out
    )
    listing = next(line for line in out if "sql_query(" in line)
    assert "order_items(order_id" in listing  # the table list is not cut off
    labels = tmp_path / "labels.csv"
    row = record_attempt(attempt, "rater_a", lambda prompt: next(replies), out.append, path=labels)
    assert row["rater_agrees"] is True and row["task_clear"] is False
    report = agreement_report(labels)
    assert report["attempts"] == 1 and report["agreement"] == 1.0
    assert report["flagged"] == {"single-001": ["rater_a found it unclear"]}


def test_quit_records_nothing(base_db: Path, docs: DocsIndex) -> None:
    attempt, _, _ = run("single-001", ["quit"], base_db, docs)
    assert attempt is None


def test_rater_ids_only(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    attempt, _, _ = run("single-001", ["answer no idea"], base_db, docs)
    assert attempt is not None and not attempt.score.success
    with pytest.raises(ValueError, match="RULES 1"):
        record_attempt(attempt, "Alice", lambda p: "y", lambda t: None, path=tmp_path / "x.csv")


def test_empty_report(tmp_path: Path) -> None:
    assert agreement_report(tmp_path / "missing.csv")["attempts"] == 0
