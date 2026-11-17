"""Tool registry.

- 8 core tools, used by benchmark tasks;
- ``ask_user``, always offered (it is how the agent clarifies ambiguous requests);
- 15 distractor tools, added in experiment E3 (8 -> 15 -> 23 tools, plus ask_user).
"""

from __future__ import annotations

from typing import Any

from toolproof.env.tools.base import Tool
from toolproof.env.tools.distractors import (
    BookCourier,
    CheckInventorySupplier,
    ConvertCurrency,
    CreateCalendarEvent,
    GenerateCoupon,
    GetExchangeRate,
    GetHolidayList,
    GetNews,
    GetStockPrice,
    GetStoreHours,
    GetWeather,
    LookupPostcode,
    SummariseText,
    TranslateText,
    ValidateEmail,
)
from toolproof.env.tools.interact import AskUser
from toolproof.env.tools.pure import AddDays, Calculator, GetDate
from toolproof.env.tools.read import GetOrder, SearchDocs, SqlQuery
from toolproof.env.tools.write import IssueRefund, SendEmail

CORE_TOOLS: tuple[type[Tool[Any]], ...] = (
    SqlQuery,
    GetOrder,
    SearchDocs,
    Calculator,
    GetDate,
    AddDays,
    IssueRefund,
    SendEmail,
)
INTERACTION_TOOLS: tuple[type[Tool[Any]], ...] = (AskUser,)
# Order matters: E3's 15-tool condition uses the first 7 distractors.
DISTRACTOR_TOOLS: tuple[type[Tool[Any]], ...] = (
    GetWeather,
    ConvertCurrency,
    CreateCalendarEvent,
    ValidateEmail,
    GenerateCoupon,
    GetStoreHours,
    CheckInventorySupplier,
    TranslateText,
    GetStockPrice,
    LookupPostcode,
    GetExchangeRate,
    SummariseText,
    GetNews,
    BookCourier,
    GetHolidayList,
)
ALL_TOOLS = CORE_TOOLS + INTERACTION_TOOLS + DISTRACTOR_TOOLS


def make_tools(n_distractors: int = 0) -> list[Tool[Any]]:
    """Core tools + ask_user + the first ``n_distractors`` distractor tools."""
    if not 0 <= n_distractors <= len(DISTRACTOR_TOOLS):
        raise ValueError(f"n_distractors must be between 0 and {len(DISTRACTOR_TOOLS)}")
    classes = CORE_TOOLS + INTERACTION_TOOLS + DISTRACTOR_TOOLS[:n_distractors]
    return [cls() for cls in classes]


def tool_names(classes: tuple[type[Tool[Any]], ...]) -> list[str]:
    return [cls.name for cls in classes]


__all__ = [
    "ALL_TOOLS",
    "CORE_TOOLS",
    "DISTRACTOR_TOOLS",
    "INTERACTION_TOOLS",
    "make_tools",
    "tool_names",
]
