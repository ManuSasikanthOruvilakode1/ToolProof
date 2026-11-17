"""Tool fault injection: per-task schedules and a seeded random error rate (E6).

An injected error replaces the tool call entirely, so write tools have no side effect when a
fault fires. Every injected error is marked ``injected=True`` and recorded in traces.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from toolproof.env.tools.base import ERROR_CLASSES, ToolError

FaultErrorName = Literal[
    "NotFound", "InvalidArgument", "PermissionDenied", "ToolTimeout", "RateLimited"
]

INJECTED_MESSAGES: dict[str, str] = {
    "ToolTimeout": "The tool did not respond in time. The request was not completed.",
    "RateLimited": "Too many requests. The request was not completed; try again.",
    "NotFound": "The requested record could not be found.",
    "InvalidArgument": "The request was rejected as invalid.",
    "PermissionDenied": "The request was not permitted.",
}
TRANSIENT_ERRORS: tuple[FaultErrorName, ...] = ("ToolTimeout", "RateLimited")
DEFAULT_EXEMPT_TOOLS = frozenset({"ask_user"})


class ScheduledFault(BaseModel):
    """Fail the ``call``-th call (1-based) of ``tool`` with ``error``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str
    call: int = Field(ge=1)
    error: FaultErrorName = "ToolTimeout"


def make_injected_error(error: str) -> ToolError:
    return ERROR_CLASSES[error](INJECTED_MESSAGES[error], injected=True)


class FaultInjector:
    """Decides, before each tool call, whether the call fails."""

    def __init__(
        self,
        schedule: Sequence[ScheduledFault] = (),
        *,
        random_rate: float = 0.0,
        seed: int = 0,
        random_errors: Sequence[FaultErrorName] = TRANSIENT_ERRORS,
        exempt_tools: Iterable[str] = DEFAULT_EXEMPT_TOOLS,
    ) -> None:
        if not 0.0 <= random_rate <= 1.0:
            raise ValueError(f"random_rate must be between 0 and 1, got {random_rate}")
        if random_rate > 0 and not random_errors:
            raise ValueError("random_errors must not be empty when random_rate > 0")
        self.schedule = tuple(schedule)
        self.random_rate = random_rate
        self.seed = seed
        self.random_errors = tuple(random_errors)
        self.exempt_tools = frozenset(exempt_tools)
        self._rng = random.Random(seed)
        self._calls: Counter[str] = Counter()

    def check(self, tool_name: str) -> ToolError | None:
        """Register a call to ``tool_name``; return the error to raise, if any."""
        self._calls[tool_name] += 1
        call_number = self._calls[tool_name]
        for fault in self.schedule:
            if fault.tool == tool_name and fault.call == call_number:
                return make_injected_error(fault.error)
        if (
            self.random_rate > 0
            and tool_name not in self.exempt_tools
            and self._rng.random() < self.random_rate
        ):
            return make_injected_error(self._rng.choice(self.random_errors))
        return None

    def calls_made(self, tool_name: str) -> int:
        return self._calls[tool_name]
