"""P3.7 pilot: a few requests x candidate models with one strategy.

Measures, per model: seconds and tokens per trial, how often the model makes native tool calls,
the malformed-call rate and how trials end. The ``sanity_pass`` column is a rough check written
next to each pilot request; it is not the benchmark's scoring, which arrives in P4.
"""

from __future__ import annotations

import json
import statistics
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from toolproof.agent.llm import LLMAdapter, LLMError, RecordingAdapter
from toolproof.agent.loop import AgentLimits
from toolproof.agent.strategies import get_strategy
from toolproof.env.docs_index import DocsIndex
from toolproof.env.faults import ScheduledFault
from toolproof.paths import configs_dir
from toolproof.tracing import JsonlTracer, trace_path
from toolproof.trial import TrialOutcome, TrialSpec, run_trial


class PilotExpect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_contains: list[str] = Field(default_factory=list)
    refund: dict[str, float] | None = None


class PilotTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prompt: str
    user_replies: list[str] = Field(default_factory=list)
    faults: list[ScheduledFault] = Field(default_factory=list)
    expect: PilotExpect = Field(default_factory=PilotExpect)

    def spec(self) -> TrialSpec:
        return TrialSpec(
            task_id=self.id,
            prompt=self.prompt.strip(),
            user_replies=tuple(self.user_replies),
            faults=tuple(self.faults),
        )


def load_pilot_tasks(path: Path | None = None) -> list[PilotTask]:
    path = path or configs_dir() / "pilot_tasks.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [PilotTask.model_validate(item) for item in raw]


def sanity_pass(task: PilotTask, outcome: TrialOutcome) -> bool:
    answer = (outcome.agent.final_answer or "").lower()
    if not all(fragment.lower() in answer for fragment in task.expect.answer_contains):
        return False
    refunds = outcome.diff.table("refunds").added
    if task.expect.refund is None:
        return not refunds
    expected = task.expect.refund
    return len(refunds) == 1 and all(
        abs(float(refunds[0][key]) - float(value)) < 0.005 for key, value in expected.items()
    )


def model_slug(model: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in model)


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    calls = sum(row["tool_calls"] for row in rows)
    return {
        "trials": len(rows),
        "median_seconds_per_trial": round(statistics.median(r["wall_seconds"] for r in rows), 2),
        "mean_tokens_per_trial": round(
            statistics.mean(r["input_tokens"] + r["output_tokens"] for r in rows), 1
        ),
        "share_trials_with_tool_calls": round(
            sum(r["tool_calls"] > 0 for r in rows) / len(rows), 3
        ),
        "malformed_call_rate": round(sum(r["malformed_calls"] for r in rows) / calls, 3)
        if calls
        else None,
        "median_steps": statistics.median(r["steps"] for r in rows),
        "terminations": dict(Counter(r["termination"] for r in rows)),
        "sanity_pass_rate": round(sum(r["sanity_pass"] for r in rows) / len(rows), 3),
    }


def run_pilot(
    tasks: list[PilotTask],
    adapters: Mapping[str, Callable[[], LLMAdapter]],
    *,
    out_dir: Path,
    strategy_name: str = "plain",
    trials: int = 1,
    temperature: float = 0.7,
    limits: AgentLimits | None = None,
    record: bool = False,
    base_db: Path | None = None,
    docs: DocsIndex | None = None,
    progress: Callable[[str], None] = lambda message: None,
) -> dict[str, Any]:
    """Run every task ``trials`` times per model; write traces, rows and a summary."""
    strategy = get_strategy(strategy_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "strategy": strategy_name,
        "prompt_versions": strategy.prompt_versions(),
        "temperature": temperature,
        "trials_per_task": trials,
        "limits": vars(limits or AgentLimits()),
        "models": {},
    }
    rows_path = out_dir / "rows.jsonl"
    for model, factory in adapters.items():
        slug = model_slug(model)
        llm = factory()
        if record:
            llm = RecordingAdapter(llm, out_dir / slug / "cassette.jsonl")
        try:
            described = llm.describe()
        except LLMError as error:
            summary["models"][model] = {"error": str(error)}
            progress(f"{model}: unavailable ({error})")
            continue
        rows = []
        for task in tasks:
            for trial in range(trials):
                tracer = JsonlTracer(
                    trace_path(out_dir.parent, f"{out_dir.name}/{slug}", task.id, trial),
                    run_id=f"{out_dir.name}/{slug}",
                    task_id=task.id,
                    trial=trial,
                )
                with tempfile.TemporaryDirectory(prefix="toolproof-pilot-") as workdir:
                    outcome = run_trial(
                        task.spec(),
                        llm=llm,
                        strategy=strategy,
                        trial=trial,
                        workdir=Path(workdir),
                        limits=limits,
                        temperature=temperature,
                        base_db=base_db,
                        docs=docs,
                        tracer=tracer,
                    )
                row = {
                    "model": model,
                    **outcome.summary(),
                    "sanity_pass": sanity_pass(task, outcome),
                }
                rows.append(row)
                with rows_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                progress(
                    f"{model} {task.id} t{trial}: {row['termination']}, "
                    f"{row['tool_calls']} calls, {row['wall_seconds']:.1f}s"
                )
        summary["models"][model] = {"describe": described, **summarise(rows)}
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary
