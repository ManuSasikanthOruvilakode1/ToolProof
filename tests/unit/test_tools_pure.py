"""calculator, get_date and add_days (P2.5)."""

from __future__ import annotations

from typing import Any

import pytest

from toolproof.env.tools.base import InvalidArgument, ToolContext
from toolproof.env.tools.pure import AddDays, Calculator, GetDate, safe_calculate


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("10 / 4", 2.5),
        ("2 ** 10", 1024),
        ("17 % 5", 2),
        ("-3 + +5", 2),
        ("0.1 + 0.2", 0.3),
        ("round(89.456, 2)", 89.46),
        ("round(2.5)", 2),
        ("min(3, 1, 2)", 1),
        ("max([4, 9, 2])", 9),
        ("sum([19.99, 45.5, 120])", 185.49),
        ("abs(-12.5)", 12.5),
        ("round(sum([10, 20]) * 0.1, 2)", 3.0),
    ],
)
def test_calculator_valid(expression: str, expected: float) -> None:
    assert safe_calculate(expression) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "open('x')",
        "x + 1",
        "(1).__class__",
        "lambda: 1",
        "[1, 2]",
        "'a' * 3",
        "True + 1",
        "1 if 1 else 2",
        "round(1.5, 1.5)",
        "round(1.5, ndigits=1)",
        "min()",
        "sum(1)",
        "1 / 0",
        "5 % 0",
        "10 ** 1000",
        "9.9 ** 100 ** 1",
        "(-8) ** 0.5",
        "1 +",
        "1" * 600,
        "+".join(["1"] * 150),
    ],
)
def test_calculator_rejects(expression: str) -> None:
    with pytest.raises(InvalidArgument):
        safe_calculate(expression)


def test_calculator_tool_output(ctx: ToolContext) -> None:
    result = Calculator().invoke(ctx, {"expression": "2 + 2"})
    assert result == {"expression": "2 + 2", "result": 4}


def test_get_date_uses_frozen_clock(ctx: ToolContext) -> None:
    assert GetDate().invoke(ctx, {}) == {"date": "2026-03-16", "weekday": "Monday"}


def test_get_date_rejects_arguments(ctx: ToolContext) -> None:
    with pytest.raises(InvalidArgument):
        GetDate().invoke(ctx, {"timezone": "UTC"})


@pytest.mark.parametrize(
    ("start", "days", "expected"),
    [
        ("2026-03-16", -30, "2026-02-14"),
        ("2026-02-27", 2, "2026-03-01"),
        ("2024-02-28", 1, "2024-02-29"),
    ],
)
def test_add_days(ctx: ToolContext, start: str, days: int, expected: str) -> None:
    assert AddDays().invoke(ctx, {"date": start, "days": days})["date"] == expected


@pytest.mark.parametrize(
    "arguments",
    [
        {"date": "16/03/2026", "days": 1},
        {"date": "2026-03-16", "days": 4000},
        {"date": "2026-03-16"},
        {"date": "0001-01-01", "days": -1},
    ],
)
def test_add_days_invalid(ctx: ToolContext, arguments: dict[str, Any]) -> None:
    with pytest.raises(InvalidArgument):
        AddDays().invoke(ctx, arguments)
