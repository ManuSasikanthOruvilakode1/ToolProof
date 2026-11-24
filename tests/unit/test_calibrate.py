"""Dev-split calibration (P4.8) with scripted models."""

from __future__ import annotations

from pathlib import Path

import pytest

from toolproof.agent.scripted import ScriptedAdapter, say
from toolproof.bench.calibrate import SplitNotAllowed, run_calibration, summarise_calibration
from toolproof.bench.schema import load_tasks
from toolproof.env.docs_index import DocsIndex


def test_calibration_refuses_test_tasks(tmp_path: Path) -> None:
    test_task = load_tasks(split="test")[:1]
    with pytest.raises(SplitNotAllowed):
        run_calibration(test_task, {}, out_dir=tmp_path)


def test_calibration_with_oracle_and_silent_models(
    base_db: Path, docs: DocsIndex, tmp_path: Path
) -> None:
    from toolproof.agent.llm import LLMResponse, ToolCall

    task = next(t for t in load_tasks(split="dev") if t.category == "single" and not t.faults)
    oracle_script = [
        LLMResponse(text="", tool_calls=(ToolCall(f"c{i}", c.tool, dict(c.args)),))
        for i, c in enumerate(task.oracle.calls)
    ] + [say(task.oracle.final_answer)]
    summary = run_calibration(
        [task],
        {
            "oracle-bot": lambda: ScriptedAdapter(oracle_script, model="oracle-bot"),
            "silent-bot": lambda: ScriptedAdapter([say("No idea.")], model="silent-bot"),
        },
        out_dir=tmp_path / "runs" / "calibrate_test",
        base_db=base_db,
        docs=docs,
    )
    assert summary["per_task"][task.id] == {"oracle-bot": 1, "silent-bot": 0}
    assert summary["by_model"]["oracle-bot"]["success_rate"] == 1.0
    assert summary["solved_by_every_model"] == [] and summary["solved_by_no_model"] == []
    assert (tmp_path / "runs" / "calibrate_test" / "summary.json").exists()


def test_summary_flags_extremes() -> None:
    rows = [
        {"task_id": "a", "model": m, "success": True, "category": "single", "safety_violations": []}
        for m in ("x", "y")
    ] + [
        {
            "task_id": "b",
            "model": m,
            "success": False,
            "category": "single",
            "safety_violations": ["v"],
        }
        for m in ("x", "y")
    ]
    summary = summarise_calibration(rows, ["a", "b"], {"x": {}, "y": {}, "z": {"error": "down"}}, 1)
    assert summary["solved_by_every_model"] == ["a"]
    assert summary["solved_by_no_model"] == ["b"]
    assert summary["by_model"]["x"]["safety_violation_trials"] == 1
    assert "z" not in summary["by_model"]


def test_rescore_reproduces_verdicts_and_applies_new_checkers(
    base_db: Path, docs: DocsIndex, tmp_path: Path
) -> None:
    import json

    from toolproof.agent.llm import LLMResponse, ToolCall
    from toolproof.bench.calibrate import rescore_run

    task = next(t for t in load_tasks(split="dev") if t.category == "single" and not t.faults)
    script = [
        LLMResponse(text="", tool_calls=(ToolCall(f"c{i}", c.tool, dict(c.args)),))
        for i, c in enumerate(task.oracle.calls)
    ] + [say(task.oracle.final_answer)]
    run_dir = tmp_path / "runs" / "calibrate_x"
    run_calibration(
        [task],
        {"bot": lambda: ScriptedAdapter(script, model="bot")},
        out_dir=run_dir,
        base_db=base_db,
        docs=docs,
    )
    summary = rescore_run(run_dir, [task], base_db=base_db, docs=docs)
    assert summary["per_task"][task.id] == {"bot": 1} and summary["changed_verdicts"] == []

    rows_path = run_dir / "rows.jsonl"
    row = json.loads(rows_path.read_text(encoding="utf-8"))
    row["final_answer"] = "I have no idea."
    rows_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    summary = rescore_run(run_dir, [task], base_db=base_db, docs=docs)
    assert summary["changed_verdicts"] == [
        {"task_id": task.id, "model": "bot", "was": True, "now": False}
    ]
