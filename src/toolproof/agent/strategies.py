"""Prompting strategies (P3.5): plain, react, plan_execute and reflect.

Prompts live in ``configs/prompts/<name>.md``. Each file starts with a version line
(``<!-- prompt-version: N -->``) and has sections introduced by ``## <section>``. Every strategy's
system prompt is ``base.md``'s system section followed by its own, so the strategy is the only
thing that differs between conditions. Strategies contain no task-specific hints.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from toolproof.agent.llm import LLMResponse, Message
from toolproof.env.toolbox import ToolCallRecord
from toolproof.paths import prompts_dir

VERSION_RE = re.compile(r"<!--\s*prompt-version:\s*(\S+)\s*-->")
FINAL_ANSWER_RE = re.compile(r"final answer\s*:\s*", re.IGNORECASE)


@dataclass(frozen=True)
class PromptFile:
    name: str
    version: str
    sha256: str
    sections: dict[str, str]


def load_prompt_file(path: Path) -> PromptFile:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = VERSION_RE.search(text.splitlines()[0] if text else "")
    if match is None:
        raise ValueError(f"{path} must start with '<!-- prompt-version: N -->'")
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines()[1:]:
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return PromptFile(
        name=path.stem,
        version=match.group(1),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        sections={name: "\n".join(lines).strip() for name, lines in sections.items()},
    )


@dataclass
class FinalAnswer:
    text: str


@dataclass
class Continue:
    messages: list[Message] = field(default_factory=list)


Decision = FinalAnswer | Continue


class StrategySession(ABC):
    """Per-trial state of a strategy. The loop calls these hooks."""

    def __init__(self, system_prompt: str, prompt: PromptFile) -> None:
        self.system_prompt = system_prompt
        self.prompt = prompt

    def initial_messages(self, task_prompt: str) -> list[Message]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task_prompt},
        ]

    def offer_tools(self) -> bool:
        return True

    def after_tool_results(self, records: Sequence[ToolCallRecord]) -> list[Message]:
        return []

    @abstractmethod
    def on_no_tool_call(self, response: LLMResponse) -> Decision:
        """The model replied without calling a tool: finish, or continue with extra messages."""


class Strategy(ABC):
    name: str

    def __init__(self, directory: Path | None = None) -> None:
        directory = directory or prompts_dir()
        self.base = load_prompt_file(directory / "base.md")
        self.prompt = load_prompt_file(directory / f"{self.name}.md")

    @property
    def system_prompt(self) -> str:
        parts = [self.base.sections.get("system", ""), self.prompt.sections.get("system", "")]
        return "\n\n".join(part for part in parts if part)

    def prompt_versions(self) -> dict[str, dict[str, str]]:
        """Versions and hashes of every prompt file used, for run manifests."""
        return {
            prompt.name: {"version": prompt.version, "sha256": prompt.sha256}
            for prompt in (self.base, self.prompt)
        }

    @abstractmethod
    def new_session(self) -> StrategySession: ...


# ------------------------------------------------------------------ plain


class PlainSession(StrategySession):
    def on_no_tool_call(self, response: LLMResponse) -> Decision:
        return FinalAnswer(response.text.strip())


class Plain(Strategy):
    name = "plain"

    def new_session(self) -> StrategySession:
        return PlainSession(self.system_prompt, self.prompt)


# ------------------------------------------------------------------ react


def extract_final_answer(text: str) -> str:
    """Text after the last 'Final answer:' marker, or the whole text if there is none."""
    parts = FINAL_ANSWER_RE.split(text)
    return parts[-1].strip() if len(parts) > 1 else text.strip()


class ReactSession(StrategySession):
    def on_no_tool_call(self, response: LLMResponse) -> Decision:
        return FinalAnswer(extract_final_answer(response.text))


class React(Strategy):
    name = "react"

    def new_session(self) -> StrategySession:
        return ReactSession(self.system_prompt, self.prompt)


# ------------------------------------------------------------------ plan_execute


class PlanExecuteSession(StrategySession):
    """First call has no tools and produces a plan; one re-plan is allowed after a tool error."""

    def __init__(self, system_prompt: str, prompt: PromptFile) -> None:
        super().__init__(system_prompt, prompt)
        self.planned = False
        self.replanned = False

    def offer_tools(self) -> bool:
        return self.planned

    def after_tool_results(self, records: Sequence[ToolCallRecord]) -> list[Message]:
        self.planned = True  # a model that calls tools before planning has moved on
        if not self.replanned and any(not record.ok for record in records):
            self.replanned = True
            return [{"role": "user", "content": self.prompt.sections["replan"]}]
        return []

    def on_no_tool_call(self, response: LLMResponse) -> Decision:
        if not self.planned:
            self.planned = True
            return Continue([{"role": "user", "content": self.prompt.sections["execute"]}])
        return FinalAnswer(response.text.strip())


class PlanExecute(Strategy):
    name = "plan_execute"

    def new_session(self) -> StrategySession:
        return PlanExecuteSession(self.system_prompt, self.prompt)


# ------------------------------------------------------------------ reflect


class ReflectSession(StrategySession):
    """The first answer triggers one self-check; the answer after the check is final."""

    def __init__(self, system_prompt: str, prompt: PromptFile) -> None:
        super().__init__(system_prompt, prompt)
        self.first_answer: str | None = None

    def on_no_tool_call(self, response: LLMResponse) -> Decision:
        if self.first_answer is None:
            self.first_answer = response.text.strip()
            return Continue([{"role": "user", "content": self.prompt.sections["check"]}])
        return FinalAnswer(response.text.strip() or self.first_answer)


class Reflect(Strategy):
    name = "reflect"

    def new_session(self) -> StrategySession:
        return ReflectSession(self.system_prompt, self.prompt)


STRATEGIES: dict[str, type[Strategy]] = {
    cls.name: cls for cls in (Plain, React, PlanExecute, Reflect)
}


def get_strategy(name: str, directory: Path | None = None) -> Strategy:
    try:
        return STRATEGIES[name](directory)
    except KeyError:
        raise ValueError(f"unknown strategy {name!r}; choose from {sorted(STRATEGIES)}") from None
