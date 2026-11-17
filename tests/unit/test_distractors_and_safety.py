"""Distractor tools (P2.9), sandbox safety rules (RULES 20, 21) and determinism (P2.11)."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from toolproof.env.docs_index import DocsIndex
from toolproof.env.faults import FaultInjector, ScheduledFault
from toolproof.env.sandbox import Sandbox
from toolproof.env.tools import DISTRACTOR_TOOLS
from toolproof.env.tools.base import InvalidArgument, ToolContext

ENV_SOURCE = Path(__file__).resolve().parents[2] / "src" / "toolproof" / "env"

DISTRACTOR_ARGS: dict[str, dict[str, Any]] = {
    "get_weather": {"city": "Sydney"},
    "translate_text": {"text": "Your refund is processed", "target_language": "French"},
    "convert_currency": {"amount": 100, "from_currency": "AUD", "to_currency": "USD"},
    "get_stock_price": {"ticker": "ACME"},
    "create_calendar_event": {"title": "Review", "date": "2026-03-20", "time": "14:30"},
    "lookup_postcode": {"postcode": "2000"},
    "get_exchange_rate": {"base": "AUD", "quote": "EUR"},
    "summarise_text": {"text": "one two three four five six seven", "max_words": 5},
    "get_news": {"topic": "retail"},
    "check_inventory_supplier": {"product_name": "Oak Bookshelf"},
    "book_courier": {"pickup_address": "1 Example St, Sydney", "parcel_weight_kg": 2.5},
    "get_holiday_list": {"country": "Australia", "year": 2026},
    "validate_email": {"address": "a@mail.example"},
    "generate_coupon": {"percent_off": 10},
    "get_store_hours": {"location": "Sydney"},
}


def test_every_distractor_has_sample_args() -> None:
    assert sorted(DISTRACTOR_ARGS) == sorted(cls.name for cls in DISTRACTOR_TOOLS)


@pytest.mark.parametrize("tool_class", DISTRACTOR_TOOLS, ids=lambda cls: cls.name)
def test_distractor_is_deterministic_and_stateless(tool_class: type, ctx: ToolContext) -> None:
    tool = tool_class()
    assert tool.is_distractor and not tool.is_write
    before = ctx.world.snapshot()
    first = tool.invoke(ctx, DISTRACTOR_ARGS[tool.name])
    second = tool.invoke(ctx, DISTRACTOR_ARGS[tool.name])
    assert first == second and first
    json.dumps(first)
    assert before.diff(ctx.world.snapshot()).is_empty


def test_distractor_outputs_vary_with_arguments(ctx: ToolContext) -> None:
    weather = DISTRACTOR_TOOLS[0]()
    outputs = {json.dumps(weather.invoke(ctx, {"city": city})) for city in ["A", "B", "C", "D"]}
    assert len(outputs) > 1


@pytest.mark.parametrize(
    "arguments",
    [{"title": "x", "date": "tomorrow"}, {"title": "x", "date": "2026-03-20", "time": "25:00"}],
)
def test_calendar_event_validation(ctx: ToolContext, arguments: dict[str, Any]) -> None:
    tool = next(cls for cls in DISTRACTOR_TOOLS if cls.name == "create_calendar_event")()
    with pytest.raises(InvalidArgument):
        tool.invoke(ctx, arguments)


def test_summarise_marks_truncation(ctx: ToolContext) -> None:
    tool = next(cls for cls in DISTRACTOR_TOOLS if cls.name == "summarise_text")()
    assert tool.invoke(ctx, DISTRACTOR_ARGS["summarise_text"])["summary"].endswith("...")
    short = tool.invoke(ctx, {"text": "just a few words", "max_words": 5})
    assert short["summary"] == "just a few words"


# ------------------------------------------------------------------ safety


def _env_modules() -> list[Path]:
    return sorted(ENV_SOURCE.rglob("*.py"))


NETWORK_MODULES = {"socket", "http", "urllib", "requests", "httpx", "aiohttp", "ftplib", "smtplib"}


@pytest.mark.parametrize("path", _env_modules(), ids=lambda p: p.name)
def test_env_never_imports_network_libraries(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert name.split(".")[0] not in NETWORK_MODULES, f"{path.name} imports {name}"


@pytest.mark.parametrize("path", _env_modules(), ids=lambda p: p.name)
def test_env_never_calls_eval_or_exec(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"eval", "exec", "compile", "__import__"}, path.name


@pytest.mark.parametrize("path", _env_modules(), ids=lambda p: p.name)
def test_env_never_reads_the_real_clock(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for forbidden in ("date.today(", "datetime.now(", "datetime.today(", "time.time("):
        assert forbidden not in source, f"{path.name} uses {forbidden}"


# ------------------------------------------------------------------ determinism

CALL_SEQUENCE: list[tuple[str, dict[str, Any]]] = [
    ("get_date", {}),
    (
        "sql_query",
        {"query": "SELECT customer_id, first_name FROM customers WHERE first_name = 'John'"},
    ),
    ("get_order", {"order_id": 9031}),
    ("get_order", {"order_id": 9031}),  # scheduled fault fires on the 2nd call
    ("search_docs", {"query": "damaged item refund"}),
    ("calculator", {"expression": "round(123.45 * 0.1, 2)"}),
    ("add_days", {"date": "2026-03-16", "days": -60}),
    ("issue_refund", {"order_id": 9031, "amount": 1.0, "reason": "damaged"}),
    ("send_email", {"to": "c@mail.example", "subject": "Order 9031", "body": "Refunded"}),
    ("ask_user", {"question": "Anything else?"}),
    ("get_weather", {"city": "Perth"}),
    ("no_such_tool", {}),
]


def run_sequence(base_db: Path, docs: DocsIndex, workdir: Path) -> str:
    faults = FaultInjector([ScheduledFault(tool="get_order", call=2)], random_rate=0.2, seed=3)
    with Sandbox.open(
        workdir, base_db=base_db, docs=docs, faults=faults, n_distractors=15, user_replies=["No"]
    ) as box:
        for name, arguments in CALL_SEQUENCE:
            box.toolbox.call(name, arguments)
        payload = {
            "calls": [record.to_dict() for record in box.toolbox.history],
            "diff": box.diff().to_dict(),
        }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def test_same_calls_give_identical_outputs(base_db: Path, docs: DocsIndex, tmp_path: Path) -> None:
    assert run_sequence(base_db, docs, tmp_path / "one") == run_sequence(
        base_db, docs, tmp_path / "two"
    )
