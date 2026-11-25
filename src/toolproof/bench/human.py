"""Human validation (P4.7): people solve tasks with the same tools, then judge the checker.

Raters are identified only as ``rater_a``, ``rater_b``, ... (RULES 1). Each finished attempt
appends one row to ``data/labels/human_validation.csv``: did the checkers pass the attempt,
does the rater agree with that verdict, and was the task clear. Tasks where a rater disagrees
or finds the task unclear are fixed or removed before the test set is locked (P4.9).
"""

from __future__ import annotations

import csv
import json
import random
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from toolproof.bench.checkers import TaskScore, TrialEvidence, score_trial
from toolproof.bench.schema import CATEGORIES, Task
from toolproof.env.docs_index import DocsIndex
from toolproof.env.faults import FaultInjector
from toolproof.env.sandbox import Sandbox
from toolproof.paths import data_dir

RATER_RE = re.compile(r"^rater_[a-z]$")
VALIDATION_SET_SIZE = 20
EXTRA_CATEGORIES = (
    "policy",
    "ambig",
    "docs",
    "recover",
)  # two per category, plus one more of these
FIELDS = [
    "recorded_at",
    "rater",
    "task_id",
    "split",
    "category",
    "checker_success",
    "failed_checks",
    "rater_agrees",
    "task_clear",
    "tool_calls",
    "notes",
]
HELP = """Commands:
  tools                      list the tools and their parameters
  call <tool> <json args>    e.g. call get_order {"order_id": 9031}
  answer <text>              give your final answer (ends the attempt)
  quit                       stop without recording anything"""


def labels_path() -> Path:
    return data_dir() / "labels" / "human_validation.csv"


def validation_set(tasks: list[Task]) -> list[str]:
    """A fixed, stratified set of 20 tasks: two per category plus one extra in four categories."""
    rng = random.Random(4707)
    chosen: list[str] = []
    for category in CATEGORIES:
        pool = sorted(t.id for t in tasks if t.category == category)
        take = 3 if category in EXTRA_CATEGORIES else 2
        chosen.extend(sorted(rng.sample(pool, take)))
    return chosen[:VALIDATION_SET_SIZE]


@dataclass
class Attempt:
    task: Task
    score: TaskScore
    tool_calls: int


def run_attempt(
    task: Task,
    read: Callable[[str], str],
    write: Callable[[str], None],
    *,
    base_db: Path | None = None,
    docs: DocsIndex | None = None,
) -> Attempt | None:
    """Interactive attempt. Returns None if the rater quits."""
    with (
        tempfile.TemporaryDirectory(prefix="toolproof-human-") as scratch,
        Sandbox.open(
            Path(scratch),
            base_db=base_db,
            docs=docs,
            user_replies=task.user_replies,
            faults=FaultInjector(task.faults, seed=0),
        ) as sandbox,
    ):
        write(f"\nTask {task.id}\n\n  {task.prompt.strip()}\n\n{HELP}\n")
        while True:
            line = read("> ").strip()
            if not line:
                continue
            command, _, rest = line.partition(" ")
            if command == "quit":
                return None
            if command == "tools":
                for schema in sandbox.toolbox.schemas():
                    function = schema["function"]
                    params = ", ".join(function["parameters"].get("properties", {}))
                    # The full description: sql_query's lists the tables after its first line.
                    description = function["description"].replace("\n", "\n      ")
                    write(f"  {function['name']}({params}): {description}")
            elif command == "call":
                tool, _, raw = rest.strip().partition(" ")
                try:
                    arguments: Any = json.loads(raw) if raw.strip() else {}
                except json.JSONDecodeError as error:
                    write(f"  arguments are not valid JSON: {error.msg}")
                    continue
                record = sandbox.toolbox.call(tool, arguments)
                write("  " + record.content_for_model())
            elif command == "answer":
                evidence = TrialEvidence(
                    final_answer=rest.strip(),
                    tool_calls=list(sandbox.toolbox.history),
                    questions_asked=list(sandbox.ctx.questions_asked),
                    diff=sandbox.diff(),
                )
                return Attempt(task, score_trial(task, evidence), len(sandbox.toolbox.history))
            else:
                write(HELP)


def ask_yes_no(read: Callable[[str], str], question: str) -> bool:
    while True:
        reply = read(f"{question} [y/n] ").strip().lower()
        if reply in ("y", "yes", "n", "no"):
            return reply.startswith("y")


def record_attempt(
    attempt: Attempt,
    rater: str,
    read: Callable[[str], str],
    write: Callable[[str], None],
    path: Path | None = None,
) -> dict[str, Any]:
    if not RATER_RE.match(rater):
        raise ValueError("rater must be rater_a, rater_b, ... (no names; RULES 1)")
    verdict = "PASSED" if attempt.score.success else "FAILED"
    write(f"\nThe checkers {verdict} your attempt.")
    for name, result in attempt.score.checks.items():
        write(f"  {name}: {'ok' if result.passed else 'FAIL ' + '; '.join(result.details)}")
    row = {
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rater": rater,
        "task_id": attempt.task.id,
        "split": attempt.task.split,
        "category": attempt.task.category,
        "checker_success": attempt.score.success,
        "failed_checks": ";".join(attempt.score.failed_checks()),
        "rater_agrees": ask_yes_no(read, "Do you agree with this verdict?"),
        "task_clear": ask_yes_no(read, "Was the request clear enough to know what to do?"),
        "tool_calls": attempt.tool_calls,
        "notes": read("Notes (optional, no names): ").strip(),
    }
    path = path or labels_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        if new_file:
            writer.writeheader()
        writer.writerow(row)
    return row


def agreement_report(path: Path | None = None) -> dict[str, Any]:
    path = path or labels_path()
    if not path.exists():
        return {"attempts": 0, "raters": [], "agreement": None, "flagged": {}}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    flagged: dict[str, list[str]] = {}
    for row in rows:
        reasons = []
        if row["rater_agrees"] != "True":
            reasons.append(f"{row['rater']} disagrees with the checker")
        if row["task_clear"] != "True":
            reasons.append(f"{row['rater']} found it unclear")
        if reasons:
            flagged.setdefault(row["task_id"], []).extend(reasons)
    agree = sum(row["rater_agrees"] == "True" for row in rows)
    return {
        "attempts": len(rows),
        "raters": sorted({row["rater"] for row in rows}),
        "tasks": len({row["task_id"] for row in rows}),
        "agreement": round(agree / len(rows), 3) if rows else None,
        "human_success": round(sum(row["checker_success"] == "True" for row in rows) / len(rows), 3)
        if rows
        else None,
        "flagged": flagged,
    }
