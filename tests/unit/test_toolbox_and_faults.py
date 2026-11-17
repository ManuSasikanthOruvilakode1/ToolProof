"""ToolBox dispatch and recording, tool schemas, fault injection (P2.3, P2.8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from toolproof.env.docs_index import DocsIndex
from toolproof.env.faults import FaultInjector, ScheduledFault
from toolproof.env.sandbox import Sandbox
from toolproof.env.toolbox import UNKNOWN_TOOL, ToolBox
from toolproof.env.tools import ALL_TOOLS, CORE_TOOLS, DISTRACTOR_TOOLS, make_tools
from toolproof.env.tools.base import DESCRIPTION_LEVELS, ToolContext

# ------------------------------------------------------------------ registry and schemas


def test_tool_counts() -> None:
    assert len(CORE_TOOLS) == 8
    assert len(DISTRACTOR_TOOLS) == 15
    assert len(make_tools()) == 9  # core + ask_user
    assert len(make_tools(7)) == 16
    assert len(make_tools(15)) == 24
    names = [cls.name for cls in ALL_TOOLS]
    assert len(names) == len(set(names))
    with pytest.raises(ValueError):
        make_tools(16)


@pytest.mark.parametrize("tool_class", ALL_TOOLS, ids=lambda cls: cls.name)
def test_every_tool_has_three_description_levels(tool_class: type) -> None:
    tool = tool_class()
    texts = [tool.description(level) for level in DESCRIPTION_LEVELS]
    assert all(texts)
    assert len(texts[0]) < len(texts[1]) < len(texts[2]), "minimal < standard < detailed"
    schema = tool.schema("standard")
    assert schema["type"] == "function"
    assert schema["function"]["name"] == tool.name
    parameters = schema["function"]["parameters"]
    assert parameters["type"] == "object"
    assert all("title" not in spec for spec in parameters["properties"].values())
    assert "title" not in parameters
    assert set(parameters.get("required", [])) <= set(parameters["properties"])


def test_duplicate_tool_names_rejected(ctx: ToolContext) -> None:
    tools = make_tools()
    with pytest.raises(ValueError, match="duplicate"):
        ToolBox([*tools, tools[0]], ctx)


# ------------------------------------------------------------------ dispatch


def test_toolbox_records_success(sandbox: Sandbox) -> None:
    record = sandbox.toolbox.call("get_order", {"order_id": 9001})
    assert record.ok and record.index == 1 and not record.is_write
    assert json.loads(record.content_for_model())["order_id"] == 9001
    assert sandbox.toolbox.history == [record]


def test_toolbox_unknown_tool(sandbox: Sandbox) -> None:
    record = sandbox.toolbox.call("delete_customer", {"customer_id": 1001})
    assert not record.ok and record.error_type == UNKNOWN_TOOL
    assert "get_order" in (record.error_message or "")
    assert json.loads(record.content_for_model())["error"]["type"] == UNKNOWN_TOOL


@pytest.mark.parametrize("arguments", [None, "9001", [9001]])
def test_toolbox_non_object_arguments(sandbox: Sandbox, arguments: object) -> None:
    record = sandbox.toolbox.call("get_order", arguments)
    assert record.error_type == "InvalidArgument"


def test_toolbox_tool_error_is_recorded(sandbox: Sandbox) -> None:
    record = sandbox.toolbox.call("get_order", {"order_id": 1})
    assert record.error_type == "NotFound" and record.injected is False


def test_toolbox_schema_levels(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    with Sandbox.open(tmp_path, base_db=base_db, docs=docs, description_level="minimal") as box:
        assert (
            box.toolbox.schemas()[0]["function"]["description"]
            == "Run a SQL query on the store database."
        )
        assert box.toolbox.get("sql_query") is not None
        assert box.toolbox.get("nope") is None
        assert box.toolbox.names[:2] == ["sql_query", "get_order"]


def test_sandbox_diff_tracks_writes(sandbox: Sandbox) -> None:
    sandbox.toolbox.call("send_email", {"to": "x@mail.example", "subject": "s", "body": "b"})
    assert sandbox.diff().changed_tables == ["outbox"]


def test_sandbox_user_replies(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    with Sandbox.open(tmp_path, base_db=base_db, docs=docs, user_replies=["yes"]) as box:
        assert box.toolbox.call("ask_user", {"question": "ok?"}).result == {"reply": "yes"}


# ------------------------------------------------------------------ faults


def test_scheduled_fault_fires_on_the_right_call(
    base_db: Path, docs: DocsIndex, tmp_path: Path
) -> None:
    faults = FaultInjector([ScheduledFault(tool="get_order", call=2, error="RateLimited")])
    with Sandbox.open(tmp_path, base_db=base_db, docs=docs, faults=faults) as box:
        first = box.toolbox.call("get_order", {"order_id": 9001})
        second = box.toolbox.call("get_order", {"order_id": 9001})
        third = box.toolbox.call("get_order", {"order_id": 9001})
    assert first.ok and third.ok
    assert second.error_type == "RateLimited" and second.injected
    assert faults.calls_made("get_order") == 3


def test_injected_fault_prevents_write(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    faults = FaultInjector([ScheduledFault(tool="send_email", call=1)])
    with Sandbox.open(tmp_path, base_db=base_db, docs=docs, faults=faults) as box:
        record = box.toolbox.call(
            "send_email", {"to": "a@mail.example", "subject": "s", "body": "b"}
        )
        assert record.error_type == "ToolTimeout" and record.injected
        assert box.diff().is_empty


def test_random_faults_are_seeded() -> None:
    def pattern(seed: int) -> list[str | None]:
        injector = FaultInjector(random_rate=0.3, seed=seed)
        results = [injector.check("sql_query") for _ in range(200)]
        return [error.error_type if error else None for error in results]

    first = pattern(7)
    assert first == pattern(7)
    assert first != pattern(8)
    rate = sum(item is not None for item in first) / len(first)
    assert 0.2 < rate < 0.4
    assert {item for item in first if item} == {"ToolTimeout", "RateLimited"}


def test_random_faults_skip_exempt_tools() -> None:
    injector = FaultInjector(random_rate=1.0, seed=1)
    assert injector.check("ask_user") is None
    error = injector.check("get_order")
    assert error is not None and error.injected


@pytest.mark.parametrize("rate", [-0.1, 1.5])
def test_fault_rate_validated(rate: float) -> None:
    with pytest.raises(ValueError):
        FaultInjector(random_rate=rate)


def test_fault_needs_error_types() -> None:
    with pytest.raises(ValueError):
        FaultInjector(random_rate=0.5, random_errors=())


def test_scheduled_fault_validation() -> None:
    with pytest.raises(ValueError):
        ScheduledFault(tool="get_order", call=0)
    with pytest.raises(ValueError):
        ScheduledFault.model_validate({"tool": "get_order", "call": 1, "error": "Boom"})
