"""Tool base class, typed tool errors and the per-trial tool context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from toolproof.env.clock import TODAY

if TYPE_CHECKING:
    from toolproof.env.docs_index import DocsIndex
    from toolproof.env.world import World

DescriptionLevel = Literal["minimal", "standard", "detailed"]
DESCRIPTION_LEVELS: tuple[DescriptionLevel, ...] = ("minimal", "standard", "detailed")

NO_FURTHER_INFORMATION = "No further information is available."


# ------------------------------------------------------------------ errors


class ToolError(Exception):
    """An error the agent sees as a tool result. ``error_type`` is recorded in traces."""

    error_type: ClassVar[str] = "ToolError"

    def __init__(self, message: str, *, injected: bool = False, schema_error: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.injected = injected
        # True when the arguments did not match the tool's schema (missing, unknown or
        # wrongly typed fields). Counted as a malformed call, unlike policy errors.
        self.schema_error = schema_error


class NotFound(ToolError):
    error_type = "NotFound"


class InvalidArgument(ToolError):
    error_type = "InvalidArgument"


class PermissionDenied(ToolError):
    error_type = "PermissionDenied"


class ToolTimeout(ToolError):
    error_type = "ToolTimeout"


class RateLimited(ToolError):
    error_type = "RateLimited"


ERROR_CLASSES: dict[str, type[ToolError]] = {
    cls.error_type: cls
    for cls in (NotFound, InvalidArgument, PermissionDenied, ToolTimeout, RateLimited)
}


# ------------------------------------------------------------------ context


@dataclass
class ToolContext:
    """Everything a tool may touch during one trial."""

    world: World
    docs: DocsIndex
    today: date = TODAY
    user_replies: tuple[str, ...] = ()
    questions_asked: list[str] = field(default_factory=list)
    _replies_used: int = 0

    def next_user_reply(self) -> str:
        if self._replies_used < len(self.user_replies):
            reply = self.user_replies[self._replies_used]
            self._replies_used += 1
            return reply
        return NO_FURTHER_INFORMATION


# ------------------------------------------------------------------ tools


class ToolArgs(BaseModel):
    """Base for tool argument models. Unknown arguments are rejected."""

    model_config = ConfigDict(extra="forbid")


class NoArgs(ToolArgs):
    pass


def _strip_titles(node: Any, *, is_property_map: bool = False) -> Any:
    """Remove pydantic's auto-generated ``title`` annotations, keeping properties named title."""
    if isinstance(node, dict):
        return {
            key: _strip_titles(value, is_property_map=key == "properties" and not is_property_map)
            for key, value in node.items()
            if is_property_map or not (key == "title" and isinstance(value, str))
        }
    if isinstance(node, list):
        return [_strip_titles(value) for value in node]
    return node


def format_validation_error(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "arguments"
        parts.append(f"{location}: {item['msg']}")
    return "Invalid arguments: " + "; ".join(parts)


class Tool[ArgsT: ToolArgs](ABC):
    """A sandbox tool. Subclasses set ``name``, ``descriptions`` and ``args_model``."""

    name: ClassVar[str]
    descriptions: ClassVar[Mapping[str, str]]
    args_model: type[ArgsT]
    is_write: ClassVar[bool] = False
    is_distractor: ClassVar[bool] = False

    def description(self, level: DescriptionLevel = "standard") -> str:
        return self.descriptions[level]

    def parameters_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = _strip_titles(self.args_model.model_json_schema())
        schema.setdefault("properties", {})
        return schema

    def schema(self, level: DescriptionLevel = "standard") -> dict[str, Any]:
        """Function definition in the format used by Ollama and OpenAI-style APIs."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(level),
                "parameters": self.parameters_schema(),
            },
        }

    def invoke(self, ctx: ToolContext, arguments: Mapping[str, Any]) -> Any:
        try:
            args = self.args_model.model_validate(dict(arguments))
        except ValidationError as error:
            raise InvalidArgument(format_validation_error(error), schema_error=True) from None
        return self.run(ctx, args)

    @abstractmethod
    def run(self, ctx: ToolContext, args: ArgsT) -> Any:
        """Execute the tool. Must be deterministic given the world state and arguments."""
