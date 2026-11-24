"""Task schema, YAML loader and validation (P4.1, P4.5). Specification: PLAN.md section 8."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from toolproof.env.faults import ScheduledFault
from toolproof.env.tools import ALL_TOOLS, DISTRACTOR_TOOLS
from toolproof.env.tools.base import DescriptionLevel
from toolproof.env.world import ALL_TABLES
from toolproof.paths import PROJECT_ROOT, docs_dir
from toolproof.trial import TrialSpec

Category = Literal["single", "chain", "calc", "docs", "recover", "unans", "ambig", "policy"]
Split = Literal["dev", "test"]
Difficulty = Literal["easy", "medium", "hard"]

CATEGORIES: tuple[str, ...] = (
    "single",
    "chain",
    "calc",
    "docs",
    "recover",
    "unans",
    "ambig",
    "policy",
)
SPLITS: tuple[str, ...] = ("dev", "test")
# PLAN.md section 8.2
PLANNED_COUNTS: dict[str, dict[str, int]] = {
    "single": {"dev": 7, "test": 13},
    "chain": {"dev": 7, "test": 13},
    "calc": {"dev": 6, "test": 12},
    "docs": {"dev": 6, "test": 12},
    "recover": {"dev": 6, "test": 12},
    "unans": {"dev": 6, "test": 12},
    "ambig": {"dev": 6, "test": 12},
    "policy": {"dev": 6, "test": 14},
}
TASK_ID_RE = re.compile(r"^(?P<category>[a-z]+)-(?P<number>\d{3})$")
TOOL_NAMES = frozenset(cls.name for cls in ALL_TOOLS)
DISTRACTOR_NAMES = frozenset(cls.name for cls in DISTRACTOR_TOOLS)


def tasks_dir() -> Path:
    return PROJECT_ROOT / "tasks"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NumericCheck(Strict):
    value: float
    tolerance: float = Field(default=0.01, ge=0)


class AnswerCheck(Strict):
    exact: str | None = None
    numeric: NumericCheck | None = None
    contains_any: list[str] = Field(default_factory=list)
    contains_all: list[str] = Field(default_factory=list)
    regex: str | None = None
    not_contains: list[str] = Field(default_factory=list)
    # The numeric value and contains_all items that are not in the prompt must also appear in a
    # successful tool result, so a correct-looking answer made up without the tools fails.
    grounded: bool = True

    @model_validator(mode="after")
    def _not_empty(self) -> AnswerCheck:
        if not (
            self.exact
            or self.numeric
            or self.contains_any
            or self.contains_all
            or self.regex
            or self.not_contains
        ):
            raise ValueError("an answer check needs at least one option")
        if self.regex is not None:
            re.compile(self.regex)
        return self


class RowExpectation(Strict):
    """Columns to match. A value is compared for equality (numbers within 0.005, text
    case-insensitively) unless it is ``{"contains": text}``."""

    table: str
    match: dict[str, Any] = Field(default_factory=dict)


class StateCheck(Strict):
    expect_rows: list[RowExpectation] = Field(default_factory=list)
    expect_no_rows: list[RowExpectation] = Field(default_factory=list)
    unchanged_tables: list[str] = Field(default_factory=list)


class ForbiddenArgs(Strict):
    tool: str
    match: dict[str, Any] = Field(default_factory=dict)


class SafetyCheck(Strict):
    forbidden_tools: list[str] = Field(default_factory=list)
    forbidden_args: list[ForbiddenArgs] = Field(default_factory=list)
    max_refund_amount: float | None = None
    no_cross_customer_data: bool = False


class ClarificationCheck(Strict):
    must_ask: bool = False
    must_ask_before_write: bool = False
    must_not_ask: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> ClarificationCheck:
        if self.must_not_ask and (self.must_ask or self.must_ask_before_write):
            raise ValueError("must_not_ask contradicts must_ask / must_ask_before_write")
        return self


class Checks(Strict):
    answer: AnswerCheck | None = None
    # None means the world must be completely unchanged (read-only and refusal tasks).
    state: StateCheck | None = None
    safety: SafetyCheck | None = None
    clarification: ClarificationCheck | None = None


class OracleCall(Strict):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    expect_error: str | None = None  # e.g. ToolTimeout for a scheduled fault


class Oracle(Strict):
    calls: list[OracleCall] = Field(min_length=1)
    final_answer: str = Field(min_length=1)


class Task(Strict):
    id: str
    version: int = Field(ge=1)
    split: Split
    category: Category
    difficulty: Difficulty
    prompt: str = Field(min_length=10)
    user_replies: list[str] = Field(default_factory=list)
    faults: list[ScheduledFault] = Field(default_factory=list)
    policy: list[str] = Field(default_factory=list)  # policy documents the task depends on
    distractor_sensitive: bool = False
    checks: Checks
    oracle: Oracle
    notes: str = ""

    @model_validator(mode="after")
    def _id_matches_category(self) -> Task:
        match = TASK_ID_RE.match(self.id)
        if match is None or match.group("category") != self.category:
            raise ValueError(f"id {self.id!r} must look like '{self.category}-NNN'")
        return self

    def features(self) -> list[str]:
        """Difficulty features from PLAN.md section 8.3."""
        found = []
        if self.policy:
            found.append("policy_rule")
        if self.faults:
            found.append("fault")
        clarification = self.checks.clarification
        if self.category == "ambig" or (
            clarification is not None
            and (clarification.must_ask or clarification.must_ask_before_write)
        ):
            found.append("ambiguity")
        if self.distractor_sensitive:
            found.append("distractor_sensitive")
        return found

    def computed_difficulty(self) -> Difficulty:
        calls = len(self.oracle.calls)
        features = len(self.features())
        if calls >= 5 or features >= 2:
            return "hard"
        if calls >= 3 or features == 1:
            return "medium"
        return "easy"

    def spec(
        self,
        *,
        n_distractors: int = 0,
        description_level: DescriptionLevel = "standard",
        random_fault_rate: float = 0.0,
    ) -> TrialSpec:
        return TrialSpec(
            task_id=self.id,
            prompt=self.prompt.strip(),
            user_replies=tuple(self.user_replies),
            faults=tuple(self.faults),
            random_fault_rate=random_fault_rate,
            n_distractors=n_distractors,
            description_level=description_level,
        )


# ------------------------------------------------------------------ loading


class TaskLoadError(Exception):
    pass


def task_files(root: Path | None = None, split: str | None = None) -> list[Path]:
    root = root or tasks_dir()
    splits = [split] if split else list(SPLITS)
    files: list[Path] = []
    for name in splits:
        files.extend(sorted((root / name).glob("*.yaml")))
    return files


def load_task(path: Path) -> Task:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Task.model_validate(raw)
    except (yaml.YAMLError, ValidationError) as error:
        raise TaskLoadError(f"{path.name}: {error}") from error


def load_tasks(root: Path | None = None, split: str | None = None) -> list[Task]:
    return [load_task(path) for path in task_files(root, split)]


# ------------------------------------------------------------------ validation


def _tables_in(task: Task) -> list[str]:
    state = task.checks.state
    if state is None:
        return []
    return [
        *(row.table for row in state.expect_rows),
        *(row.table for row in state.expect_no_rows),
        *state.unchanged_tables,
    ]


def _tools_in(task: Task) -> list[str]:
    tools = [call.tool for call in task.oracle.calls] + [fault.tool for fault in task.faults]
    if task.checks.safety:
        tools += task.checks.safety.forbidden_tools
        tools += [item.tool for item in task.checks.safety.forbidden_args]
    return tools


def validate_task(task: Task, path: Path | None = None) -> list[str]:
    """Problems with one task beyond what the schema checks."""
    problems: list[str] = []
    if path is not None:
        if path.stem != task.id:
            problems.append(f"file name {path.name} does not match id {task.id}")
        if path.parent.name != task.split:
            problems.append(f"task is split '{task.split}' but stored in {path.parent.name}/")
    for table in _tables_in(task):
        if table not in ALL_TABLES:
            problems.append(f"unknown table {table!r}")
    for tool in _tools_in(task):
        if tool not in TOOL_NAMES:
            problems.append(f"unknown tool {tool!r}")
    for call in task.oracle.calls:
        if call.tool in DISTRACTOR_NAMES:
            problems.append(f"oracle uses distractor tool {call.tool!r} (RULES 29)")
    for name in TOOL_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", task.prompt):
            problems.append(f"prompt names the tool {name!r} (RULES 27)")
    known_docs = {path.stem for path in docs_dir().glob("*.md")}
    for doc in task.policy:
        if doc not in known_docs:
            problems.append(f"unknown policy document {doc!r}")
    if task.difficulty != task.computed_difficulty():
        problems.append(
            f"difficulty is '{task.difficulty}' but the rules give '{task.computed_difficulty()}'"
            f" ({len(task.oracle.calls)} oracle calls, features {task.features()})"
        )
    if task.category == "ambig" and not task.user_replies:
        problems.append("ambiguous tasks need scripted user_replies")
    return problems


def validate_all(
    root: Path | None = None, *, strict_counts: bool = False
) -> tuple[list[Task], dict[str, list[str]]]:
    """Load and validate every task. Returns the tasks and problems keyed by file name."""
    problems: dict[str, list[str]] = {}
    tasks: list[Task] = []
    seen: dict[str, str] = {}
    for path in task_files(root):
        try:
            task = load_task(path)
        except TaskLoadError as error:
            problems.setdefault(path.name, []).append(str(error))
            continue
        tasks.append(task)
        found = validate_task(task, path)
        if task.id in seen:
            found.append(f"duplicate id (also in {seen[task.id]})")
        seen[task.id] = f"{path.parent.name}/{path.name}"
        if found:
            problems.setdefault(path.name, []).extend(found)
    if strict_counts:
        counts: Counter[tuple[str, str]] = Counter((task.category, task.split) for task in tasks)
        for category, planned in PLANNED_COUNTS.items():
            for split, expected in planned.items():
                actual = counts.get((category, split), 0)
                if actual != expected:
                    problems.setdefault("(counts)", []).append(
                        f"{category}/{split}: {actual} tasks, plan says {expected}"
                    )
    return tasks, problems
