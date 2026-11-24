"""Oracle runner (P4.3): replay each task's reference solution and check that it passes.

The oracle proves a task is solvable with the tools and that its checkers accept a correct
solution. It runs with the task's scheduled faults, so oracle calls that are expected to fail
say so with ``expect_error``. It is never used to score agents.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from toolproof.bench.checkers import TaskScore, TrialEvidence, score_trial
from toolproof.bench.schema import Task
from toolproof.env.docs_index import DocsIndex
from toolproof.env.faults import FaultInjector
from toolproof.env.sandbox import Sandbox
from toolproof.trial import TrialOutcome


@dataclass
class OracleResult:
    task_id: str
    passed: bool
    score: TaskScore | None
    call_problems: list[str] = field(default_factory=list)

    def problems(self) -> list[str]:
        found = list(self.call_problems)
        if self.score is not None:
            for name, result in self.score.checks.items():
                if not result.passed:
                    found.extend(f"{name}: {detail}" for detail in result.details)
        return found


def run_oracle(
    task: Task,
    *,
    base_db: Path | None = None,
    docs: DocsIndex | None = None,
    workdir: Path | None = None,
) -> OracleResult:
    with tempfile.TemporaryDirectory(prefix="toolproof-oracle-") as scratch:
        directory = workdir or Path(scratch)
        faults = FaultInjector(task.faults, seed=0)
        with Sandbox.open(
            directory,
            base_db=base_db,
            docs=docs,
            user_replies=task.user_replies,
            faults=faults,
        ) as sandbox:
            problems = []
            for number, call in enumerate(task.oracle.calls, start=1):
                record = sandbox.toolbox.call(call.tool, call.args)
                if call.expect_error is not None:
                    if record.error_type != call.expect_error:
                        problems.append(
                            f"oracle call {number} ({call.tool}) should fail with "
                            f"{call.expect_error}, got {record.error_type or 'success'}"
                        )
                elif not record.ok:
                    problems.append(
                        f"oracle call {number} ({call.tool}) failed: "
                        f"{record.error_type}: {record.error_message}"
                    )
            evidence = TrialEvidence(
                final_answer=task.oracle.final_answer,
                tool_calls=list(sandbox.toolbox.history),
                questions_asked=list(sandbox.ctx.questions_asked),
                diff=sandbox.diff(),
            )
            score = score_trial(task, evidence)
    return OracleResult(task.id, score.success and not problems, score, problems)


def play(
    task: Task,
    calls: Sequence[tuple[str, Any]],
    final_answer: str | None,
    *,
    base_db: Path | None = None,
    docs: DocsIndex | None = None,
) -> tuple[TaskScore, TrialEvidence]:
    """Replay any sequence of (tool, arguments) on a fresh sandbox and score it.

    Used by the checker mutation tests (P4.6) to prove wrong trajectories fail.
    """
    with (
        tempfile.TemporaryDirectory(prefix="toolproof-play-") as scratch,
        Sandbox.open(
            Path(scratch),
            base_db=base_db,
            docs=docs,
            user_replies=task.user_replies,
            faults=FaultInjector(task.faults, seed=0),
        ) as sandbox,
    ):
        for tool, arguments in calls:
            sandbox.toolbox.call(tool, arguments)
        evidence = TrialEvidence(
            final_answer=final_answer,
            tool_calls=list(sandbox.toolbox.history),
            questions_asked=list(sandbox.ctx.questions_asked),
            diff=sandbox.diff(),
        )
    return score_trial(task, evidence), evidence


def evidence_from_outcome(outcome: TrialOutcome) -> TrialEvidence:
    """Checker input from a real agent trial."""
    return TrialEvidence(
        final_answer=outcome.agent.final_answer,
        tool_calls=outcome.agent.tool_calls,
        questions_asked=outcome.questions_asked,
        diff=outcome.diff,
    )
