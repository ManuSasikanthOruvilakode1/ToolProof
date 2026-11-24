"""One trial: a fresh sandbox, fault injection, the agent loop and the resulting world diff."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from toolproof.agent.llm import LLMAdapter
from toolproof.agent.loop import AgentLimits, AgentResult, run_agent
from toolproof.agent.strategies import Strategy
from toolproof.env.docs_index import DocsIndex
from toolproof.env.faults import FaultInjector, ScheduledFault
from toolproof.env.sandbox import Sandbox
from toolproof.env.tools.base import DescriptionLevel
from toolproof.env.world import WorldDiff
from toolproof.tracing import Tracer


@dataclass(frozen=True)
class TrialSpec:
    task_id: str
    prompt: str
    user_replies: Sequence[str] = ()
    faults: Sequence[ScheduledFault] = ()
    random_fault_rate: float = 0.0
    n_distractors: int = 0
    description_level: DescriptionLevel = "standard"


@dataclass
class TrialOutcome:
    spec: TrialSpec
    trial: int
    agent: AgentResult
    diff: WorldDiff
    questions_asked: list[str] = field(default_factory=list)

    @property
    def injected_faults(self) -> int:
        return sum(record.injected for record in self.agent.tool_calls)

    def summary(self) -> dict[str, Any]:
        agent = self.agent
        return {
            "task_id": self.spec.task_id,
            "trial": self.trial,
            "termination": agent.termination,
            "final_answer": agent.final_answer,
            "steps": agent.steps,
            "tool_calls": agent.total_calls,
            "malformed_calls": agent.malformed_calls,
            "injected_faults": self.injected_faults,
            "input_tokens": agent.usage.input_tokens,
            "output_tokens": agent.usage.output_tokens,
            "llm_seconds": agent.llm_seconds,
            "wall_seconds": agent.wall_seconds,
            "changed_tables": self.diff.changed_tables,
            "questions_asked": len(self.questions_asked),
            "error": agent.error,
        }


def run_trial(
    spec: TrialSpec,
    *,
    llm: LLMAdapter,
    strategy: Strategy,
    trial: int,
    workdir: Path,
    limits: AgentLimits | None = None,
    temperature: float = 0.7,
    seed: int | None = None,
    base_db: Path | None = None,
    docs: DocsIndex | None = None,
    tracer: Tracer | None = None,
) -> TrialOutcome:
    """Run one trial. The sampling and fault seed default to the trial index."""
    seed = trial if seed is None else seed
    faults = FaultInjector(spec.faults, random_rate=spec.random_fault_rate, seed=seed)
    with Sandbox.open(
        workdir,
        base_db=base_db,
        docs=docs,
        user_replies=spec.user_replies,
        faults=faults,
        n_distractors=spec.n_distractors,
        description_level=spec.description_level,
    ) as sandbox:
        result = run_agent(
            spec.prompt,
            sandbox.toolbox,
            llm,
            strategy,
            limits=limits,
            temperature=temperature,
            seed=seed,
            tracer=tracer,
        )
        return TrialOutcome(
            spec=spec,
            trial=trial,
            agent=result,
            diff=sandbox.diff(),
            questions_asked=list(sandbox.ctx.questions_asked),
        )
