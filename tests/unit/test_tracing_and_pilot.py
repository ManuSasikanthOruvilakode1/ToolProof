"""Traces, exact replay of a recorded trial, `trace show`, and the pilot (P3.3, P3.6, P3.7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from toolproof.agent.llm import RecordingAdapter, ReplayAdapter
from toolproof.agent.scripted import ScriptedAdapter, call, say
from toolproof.agent.strategies import STRATEGIES, get_strategy
from toolproof.cli import app
from toolproof.env.docs_index import DocsIndex
from toolproof.env.faults import ScheduledFault
from toolproof.pilot import PilotTask, load_pilot_tasks, run_pilot, summarise
from toolproof.tracing import (
    JsonlTracer,
    MemoryTracer,
    comparable,
    format_trace,
    read_trace,
    trace_path,
)
from toolproof.trial import TrialSpec, run_trial

SCRIPT = [
    call("get_order", {"order_id": 9031}, text="Thought: look it up."),
    call("get_order", {"order_id": 9031}),
    call("search_docs", {"query": "late delivery"}),
    say("Plan done.\nFinal answer: Order 9031 was delivered on 2025-04-14."),
    say("Final answer: Order 9031 was delivered on 2025-04-14."),
    say("Order 9031 was delivered on 2025-04-14."),
]
SPEC = TrialSpec(
    task_id="replay-demo",
    prompt="When was order 9031 delivered?",
    faults=(ScheduledFault(tool="get_order", call=1, error="ToolTimeout"),),
)


def record_and_replay(
    strategy_name: str, base_db: Path, docs: DocsIndex, tmp_path: Path
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    cassette = tmp_path / f"{strategy_name}.jsonl"
    traces = []
    for index, llm in enumerate(
        [
            lambda: RecordingAdapter(ScriptedAdapter(SCRIPT), cassette),
            lambda: ReplayAdapter(cassette),
        ]
    ):
        tracer = JsonlTracer(tmp_path / f"{strategy_name}-{index}.jsonl", "run", SPEC.task_id, 0)
        run_trial(
            SPEC,
            llm=llm(),
            strategy=get_strategy(strategy_name),
            trial=0,
            workdir=tmp_path / f"w-{strategy_name}-{index}",
            base_db=base_db,
            docs=docs,
            tracer=tracer,
        )
        traces.append(read_trace(tracer.path))
    return traces[0], traces[1]


@pytest.mark.parametrize("strategy_name", sorted(STRATEGIES))
def test_recorded_trace_replays_exactly(
    strategy_name: str, base_db: Path, docs: DocsIndex, tmp_path: Path
) -> None:
    recorded, replayed = record_and_replay(strategy_name, base_db, docs, tmp_path)
    assert comparable(recorded) == comparable(replayed)
    assert recorded[-1]["event"] == "final"
    assert recorded[-1]["payload"]["termination"] == "final_answer"  # type: ignore[index]


def test_memory_tracer_rejects_unknown_events() -> None:
    with pytest.raises(ValueError):
        MemoryTracer().event("thinking", 1, {})


def test_format_trace_marks_errors_and_injected_faults(
    base_db: Path, docs: DocsIndex, tmp_path: Path
) -> None:
    recorded, _ = record_and_replay("plain", base_db, docs, tmp_path)
    text = "\n".join(format_trace(recorded))  # type: ignore[arg-type]
    assert "USER" in text and "SYSTEM" in text
    assert "CALL      get_order" in text
    assert "ERROR     ToolTimeout" in text and "[injected]" in text
    assert "END       final_answer" in text


def test_trace_show_cli(
    base_db: Path, docs: DocsIndex, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOOLPROOF_RESULTS_DIR", str(tmp_path / "results"))
    path = trace_path(tmp_path / "results" / "runs", "run1", "replay-demo", 0)
    tracer = JsonlTracer(path, "run1", "replay-demo", 0)
    run_trial(
        SPEC,
        llm=ScriptedAdapter(SCRIPT),
        strategy=get_strategy("plain"),
        trial=0,
        workdir=tmp_path / "w",
        base_db=base_db,
        docs=docs,
        tracer=tracer,
    )
    runner = CliRunner()
    result = runner.invoke(app, ["trace", "show", "run1", "replay-demo", "0"])
    assert result.exit_code == 0, result.output
    assert "END       final_answer" in result.output
    missing = runner.invoke(app, ["trace", "show", "run1", "nope", "0"])
    assert missing.exit_code == 1


# ------------------------------------------------------------------ pilot


def test_pilot_tasks_load() -> None:
    tasks = load_pilot_tasks()
    assert [task.id for task in tasks] == [f"pilot-00{i}" for i in range(1, 6)]
    assert tasks[1].faults[0].tool == "get_order"
    assert tasks[4].expect.refund == {"order_id": 9053, "amount": 12.10}


def test_run_pilot_with_scripted_models(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    tasks = [
        PilotTask(
            id="p1",
            prompt="How many orders have been cancelled?",
            expect={"answer_contains": ["80"]},
        ),  # type: ignore[arg-type]
        PilotTask(
            id="p2",
            prompt="Refund order 9053 for lateness.",
            expect={"refund": {"order_id": 9053, "amount": 12.10}},
        ),  # type: ignore[arg-type]
    ]
    good = [
        call("sql_query", {"query": "SELECT COUNT(*) FROM orders WHERE status='cancelled'"}),
        say("80 orders were cancelled."),
        call("issue_refund", {"order_id": 9053, "amount": 12.10, "reason": "late_delivery"}),
        say("Refunded $12.10."),
    ]
    bad = [say("About 100."), call("refund", "{x", parse_error="bad json"), say("Done.")]
    summary = run_pilot(
        tasks,
        {
            "good": lambda: ScriptedAdapter(good, model="good"),
            "bad": lambda: ScriptedAdapter(bad, model="bad"),
        },
        out_dir=tmp_path / "runs" / "pilot_test",
        base_db=base_db,
        docs=docs,
        record=True,
    )
    good_stats, bad_stats = summary["models"]["good"], summary["models"]["bad"]
    assert good_stats["sanity_pass_rate"] == 1.0
    assert good_stats["share_trials_with_tool_calls"] == 1.0
    assert good_stats["malformed_call_rate"] == 0.0
    assert bad_stats["sanity_pass_rate"] == 0.0
    assert bad_stats["malformed_call_rate"] == 1.0
    assert bad_stats["share_trials_with_tool_calls"] == 0.5
    out = tmp_path / "runs" / "pilot_test"
    assert json.loads((out / "summary.json").read_text(encoding="utf-8"))["strategy"] == "plain"
    assert len((out / "rows.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    assert (out / "good" / "traces" / "p1__t0.jsonl").exists()
    assert (out / "good" / "cassette.jsonl").exists()


def test_pilot_reports_unavailable_models(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    class Down(ScriptedAdapter):
        def describe(self) -> dict[str, object]:
            from toolproof.agent.llm import LLMError

            raise LLMError("connection refused")

    summary = run_pilot(
        [PilotTask(id="p", prompt="hi")],
        {"down": lambda: Down([])},
        out_dir=tmp_path / "pilot",
        base_db=base_db,
        docs=docs,
    )
    assert "connection refused" in summary["models"]["down"]["error"]


def test_summarise_handles_no_calls() -> None:
    row = {
        "wall_seconds": 1.0,
        "input_tokens": 5,
        "output_tokens": 5,
        "tool_calls": 0,
        "malformed_calls": 0,
        "steps": 1,
        "termination": "final_answer",
        "sanity_pass": True,
    }
    stats = summarise([row])
    assert stats["malformed_call_rate"] is None and stats["trials"] == 1


def test_models_cli_without_server(monkeypatch: pytest.MonkeyPatch) -> None:
    result = CliRunner().invoke(app, ["models", "--base-url", "http://127.0.0.1:9"])
    assert result.exit_code == 1


class FakeOllama(ScriptedAdapter):
    """Stands in for OllamaAdapter in CLI tests: answers every request with a short reply."""

    def __init__(self, model: str, base_url: str = "") -> None:
        super().__init__([say("A reply.")] * 20, model=model)

    def describe(self) -> dict[str, object]:
        return {
            "backend": "fake",
            "model": self.model,
            "digest": "sha256-0123456789ab",
            "capabilities": ["completion", "tools"],
            "parameter_size": "8B",
        }


def test_pilot_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOLPROOF_RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setattr("toolproof.cli.OllamaAdapter", FakeOllama)
    result = CliRunner().invoke(app, ["pilot", "--model", "fake:8b", "--max-steps", "3"])
    assert result.exit_code == 0, result.output
    assert "fake:8b" in result.output
    summaries = list((tmp_path / "results" / "runs").glob("pilot_*/summary.json"))
    assert len(summaries) == 1
    bad = CliRunner().invoke(app, ["pilot", "--model", "x", "--strategy", "nope"])
    assert bad.exit_code == 1


def test_models_cli_lists_tool_support(monkeypatch: pytest.MonkeyPatch) -> None:
    class Tags:
        def json(self) -> dict[str, object]:
            return {"models": [{"name": "fake:8b", "size": 5_000_000_000}]}

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: Tags())
    monkeypatch.setattr("toolproof.cli.OllamaAdapter", FakeOllama)
    result = CliRunner().invoke(app, ["models"])
    assert result.exit_code == 0, result.output
    assert "fake:8b" in result.output and "yes" in result.output
