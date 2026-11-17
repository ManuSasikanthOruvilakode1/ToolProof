"""Pure tools: calculator (whitelisted AST evaluator, no eval/exec), get_date, add_days."""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, ClassVar

from pydantic import Field

from toolproof.env.tools.base import InvalidArgument, NoArgs, Tool, ToolArgs, ToolContext

Number = int | float

MAX_EXPRESSION_CHARS = 500
MAX_NODES = 200
MAX_EXPONENT = 100
MAX_ABS_RESULT = 1e18

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
}


def _check_number(value: Any) -> Number:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidArgument("The expression must evaluate to a number.")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidArgument("The result is not a finite number.")
    if abs(value) > MAX_ABS_RESULT:
        raise InvalidArgument("The result is too large.")
    return value


def _evaluate(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise InvalidArgument(f"Unsupported constant: {node.value!r}.")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _check_number(_evaluate(node.left))
        right = _check_number(_evaluate(node.right))
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise InvalidArgument(f"Exponents larger than {MAX_EXPONENT} are not allowed.")
        try:
            return _check_number(_BINARY_OPERATORS[type(node.op)](left, right))
        except ZeroDivisionError:
            raise InvalidArgument("Division by zero.") from None
        except OverflowError:
            raise InvalidArgument("The result is too large.") from None
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_check_number(_evaluate(node.operand)))
    if isinstance(node, ast.List | ast.Tuple):
        return [_check_number(_evaluate(element)) for element in node.elts]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
        and not node.keywords
    ):
        arguments = [_evaluate(argument) for argument in node.args]
        if (
            node.func.id == "round"
            and len(arguments) == 2
            and (not isinstance(arguments[1], int) or isinstance(arguments[1], bool))
        ):
            raise InvalidArgument("round() needs a whole number of digits.")
        try:
            return _FUNCTIONS[node.func.id](*arguments)
        except (TypeError, ValueError) as error:
            raise InvalidArgument(f"Invalid use of {node.func.id}(): {error}.") from None
    raise InvalidArgument(
        f"Unsupported syntax: {type(node).__name__}. Allowed: numbers, + - * / ** %, "
        "parentheses, round, min, max, sum, abs."
    )


def safe_calculate(expression: str) -> Number:
    """Evaluate an arithmetic expression without eval/exec (RULES 20)."""
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise InvalidArgument(f"The expression is longer than {MAX_EXPRESSION_CHARS} characters.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError:
        raise InvalidArgument("The expression is not valid arithmetic.") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise InvalidArgument("The expression is too long.")
    value = _check_number(_evaluate(tree.body))
    return round(value, 10) if isinstance(value, float) else value


class CalculatorArgs(ToolArgs):
    expression: str = Field(description="Arithmetic expression, e.g. round((89.5 + 12) * 0.1, 2).")


class Calculator(Tool[CalculatorArgs]):
    name = "calculator"
    args_model = CalculatorArgs
    descriptions: ClassVar[dict[str, str]] = {
        "minimal": "Calculate.",
        "standard": (
            "Evaluate an arithmetic expression exactly. Supports + - * / ** %, parentheses "
            "and round, min, max, sum, abs."
        ),
        "detailed": (
            "Evaluate an arithmetic expression and return the numeric result. Use this instead "
            "of doing arithmetic yourself. Supports numbers, + - * / ** % and parentheses, and "
            "the functions round(x, digits), min(...), max(...), sum([...]) and abs(x). "
            "Variables, other functions and text are not allowed. Example: "
            "round(sum([19.99, 45.5, 120]) * 0.1, 2)."
        ),
    }

    def run(self, ctx: ToolContext, args: CalculatorArgs) -> Any:
        return {"expression": args.expression, "result": safe_calculate(args.expression)}


def _describe_date(value: date) -> dict[str, str]:
    return {"date": value.isoformat(), "weekday": value.strftime("%A")}


class GetDate(Tool[NoArgs]):
    name = "get_date"
    args_model = NoArgs
    descriptions: ClassVar[dict[str, str]] = {
        "minimal": "Get the date.",
        "standard": "Get today's date (YYYY-MM-DD) and weekday.",
        "detailed": (
            "Get today's date in YYYY-MM-DD format and the day of the week. Use this for any "
            "question involving 'today', 'this month', or how long ago something happened."
        ),
    }

    def run(self, ctx: ToolContext, args: NoArgs) -> Any:
        return _describe_date(ctx.today)


class AddDaysArgs(ToolArgs):
    date: str = Field(description="Start date, YYYY-MM-DD.")
    days: int = Field(ge=-3650, le=3650, description="Days to add (negative to subtract).")


class AddDays(Tool[AddDaysArgs]):
    name = "add_days"
    args_model = AddDaysArgs
    descriptions: ClassVar[dict[str, str]] = {
        "minimal": "Add days to a date.",
        "standard": "Add (or subtract) a number of days to a YYYY-MM-DD date.",
        "detailed": (
            "Add a number of days to a date given as YYYY-MM-DD and return the new date and "
            "its weekday. Use a negative number to go back in time, e.g. date=2026-03-16, "
            "days=-30 gives the date 30 days earlier."
        ),
    }

    def run(self, ctx: ToolContext, args: AddDaysArgs) -> Any:
        try:
            start = date.fromisoformat(args.date)
        except ValueError:
            raise InvalidArgument(f"'{args.date}' is not a date in YYYY-MM-DD format.") from None
        try:
            return _describe_date(start + timedelta(days=args.days))
        except OverflowError:
            raise InvalidArgument("The resulting date is out of range.") from None
