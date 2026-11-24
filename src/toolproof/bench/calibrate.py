"""Difficulty calibration on the dev split (P4.8).

Runs dev tasks on the pilot models and reports tasks that every model solves in every trial
(too easy) or that no model ever solves (too hard or broken). Calibration never touches the
test split (RULES 11); lessons are applied to test tasks by hand, before the lock.
"""

from __future__ import annotations

import json
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from toolproof.agent.llm import LLMAdapter, LLMError
from toolproof.agent.loop import AgentLimits
from toolproof.agent.strategies import get_strategy
from toolproof.bench.checkers import score_trial
from toolproof.bench.oracle import evidence_from_outcome
from toolproof.bench.schema import Task
from toolproof.env.docs_index import DocsIndex
from toolproof.pilot import model_slug
from toolproof.tracing import JsonlTracer, trace_path
from toolproof.trial import run_trial


class SplitNotAllowed(ValueError):
    pass


def run_calibration(
    tasks: list[Task],
    adapters: Mapping[str, Callable[[], LLMAdapter]],
    *,
    out_dir: Path,
    strategy_name: str = "plain",
    trials: int = 1,
    temperature: float = 0.7,
    limits: AgentLimits | None = None,
    base_db: Path | None = None,
    docs: DocsIndex | None = None,
    progress: Callable[[str], None] = lambda message: None,
) -> dict[str, Any]:
    if any(task.split != "dev" for task in tasks):
        raise SplitNotAllowed("calibration runs on dev tasks only (RULES 11)")
    strategy = get_strategy(strategy_name)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "rows.jsonl"
    rows: list[dict[str, Any]] = []
    models: dict[str, Any] = {}
    for model, factory in adapters.items():
        llm = factory()
        try:
            models[model] = llm.describe()
        except LLMError as error:
            models[model] = {"error": str(error)}
            progress(f"{model}: unavailable ({error})")
            continue
        slug = model_slug(model)
        for task in tasks:
            for trial in range(trials):
                run_id = f"{out_dir.name}/{slug}"
                tracer = JsonlTracer(
                    trace_path(out_dir.parent, run_id, task.id, trial), run_id, task.id, trial
                )
                with tempfile.TemporaryDirectory(prefix="toolproof-calibrate-") as workdir:
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
                score = score_trial(task, evidence_from_outcome(outcome))
                row = {
                    "model": model,
                    "category": task.category,
                    "difficulty": task.difficulty,
                    **outcome.summary(),
                    "success": score.success,
                    "failed_checks": score.failed_checks(),
                    "safety_violations": score.safety_violations,
                }
                rows.append(row)
                with rows_path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                progress(
                    f"{model} {task.id} t{trial}: {'PASS' if score.success else 'fail'} "
                    f"{score.failed_checks() or ''} ({row['wall_seconds']:.1f}s)"
                )
    summary = summarise_calibration(rows, [t.id for t in tasks], models, trials)
    summary.update(
        strategy=strategy_name,
        temperature=temperature,
        trials=trials,
        prompt_versions=strategy.prompt_versions(),
    )
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def summarise_calibration(
    rows: list[dict[str, Any]], task_ids: list[str], models: dict[str, Any], trials: int
) -> dict[str, Any]:
    ran = [m for m, info in models.items() if "error" not in info]
    wins: Counter[tuple[str, str]] = Counter()
    for row in rows:
        wins[(row["task_id"], row["model"])] += row["success"]
    per_task = {tid: {m: wins[(tid, m)] for m in ran} for tid in task_ids}
    by_model = {}
    for model in ran:
        model_rows = [r for r in rows if r["model"] == model]
        by_category: dict[str, list[int]] = {}
        for row in model_rows:
            by_category.setdefault(row["category"], []).append(int(row["success"]))
        by_model[model] = {
            "success_rate": round(sum(r["success"] for r in model_rows) / len(model_rows), 3)
            if model_rows
            else None,
            "by_category": {c: round(sum(v) / len(v), 3) for c, v in sorted(by_category.items())},
            "safety_violation_trials": sum(bool(r["safety_violations"]) for r in model_rows),
            "context_limit_hits": sum(r.get("context_limit_hits", 0) for r in model_rows),
        }
    all_solve = [
        t for t, counts in per_task.items() if ran and all(counts[m] == trials for m in ran)
    ]
    none_solve = [t for t, counts in per_task.items() if ran and all(counts[m] == 0 for m in ran)]
    return {
        "models": models,
        "by_model": by_model,
        "per_task": per_task,
        "solved_by_every_model": all_solve,
        "solved_by_no_model": none_solve,
    }
