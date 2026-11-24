"""The set of tools offered in one trial, and the record of every call made to them."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from toolproof.env.faults import FaultInjector
from toolproof.env.tools.base import DescriptionLevel, InvalidArgument, Tool, ToolContext, ToolError

UNKNOWN_TOOL = "UnknownTool"


@dataclass
class ToolCallRecord:
    index: int
    tool: str
    arguments: Any
    ok: bool
    result: Any = None
    error_type: str | None = None
    error_message: str | None = None
    injected: bool = False
    is_write: bool = False
    schema_error: bool = False

    @property
    def malformed(self) -> bool:
        """Unknown tool or arguments that do not match the schema (not policy errors)."""
        return self.error_type == UNKNOWN_TOOL or self.schema_error

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def content_for_model(self) -> str:
        """The tool message the agent sees."""
        if self.ok:
            return json.dumps(self.result, ensure_ascii=False)
        return json.dumps({"error": {"type": self.error_type, "message": self.error_message}})


class ToolBox:
    def __init__(
        self,
        tools: Sequence[Tool[Any]],
        ctx: ToolContext,
        *,
        faults: FaultInjector | None = None,
        description_level: DescriptionLevel = "standard",
    ) -> None:
        names = [tool.name for tool in tools]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate tool names: {duplicates}")
        self._tools = {tool.name: tool for tool in tools}
        self.ctx = ctx
        self.faults = faults
        self.description_level: DescriptionLevel = description_level
        self.history: list[ToolCallRecord] = []

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def get(self, name: str) -> Tool[Any] | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema(self.description_level) for tool in self._tools.values()]

    def call(self, name: str, arguments: Any) -> ToolCallRecord:
        record = ToolCallRecord(
            index=len(self.history) + 1, tool=name, arguments=arguments, ok=False
        )
        tool = self._tools.get(name)
        if tool is None:
            record.error_type = UNKNOWN_TOOL
            record.error_message = (
                f"Unknown tool '{name}'. Available tools: {', '.join(sorted(self._tools))}."
            )
        else:
            record.is_write = tool.is_write
            try:
                if not isinstance(arguments, Mapping):
                    raise InvalidArgument("Arguments must be a JSON object.", schema_error=True)
                fault = self.faults.check(name) if self.faults else None
                if fault is not None:
                    raise fault
                result = tool.invoke(self.ctx, arguments)
                record.result = json.loads(json.dumps(result))  # plain JSON types only
                record.ok = True
            except ToolError as error:
                record.error_type = error.error_type
                record.error_message = error.message
                record.injected = error.injected
                record.schema_error = error.schema_error
        self.history.append(record)
        return record
