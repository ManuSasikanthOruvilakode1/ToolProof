"""sql_query, get_order and search_docs (P2.4)."""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from toolproof.env.tools.base import (
    InvalidArgument,
    NotFound,
    PermissionDenied,
    ToolContext,
    ToolTimeout,
)
from toolproof.env.tools.read import SQL_ROW_CAP, GetOrder, SearchDocs, SqlQuery


def sql(ctx: ToolContext, query: str) -> Any:
    return SqlQuery().invoke(ctx, {"query": query})


# ------------------------------------------------------------------ sql_query


def test_sql_select(ctx: ToolContext) -> None:
    result = sql(ctx, "SELECT COUNT(*) AS n FROM orders WHERE status = 'cancelled'")
    assert result["columns"] == ["n"]
    assert result["rows"][0][0] > 0
    assert result["truncated"] is False


def test_sql_row_cap(ctx: ToolContext) -> None:
    result = sql(ctx, "SELECT order_id FROM orders")
    assert result["row_count"] == SQL_ROW_CAP
    assert result["truncated"] is True


def test_sql_trailing_semicolon_is_fine(ctx: ToolContext) -> None:
    assert sql(ctx, "SELECT 1;")["rows"] == [[1]]


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM refunds",
        "UPDATE orders SET total = 0",
        "INSERT INTO outbox VALUES (1, 'a@b.c', 's', 'b', 'd')",
        "DROP TABLE orders",
        "PRAGMA table_info(orders)",
        "ATTACH DATABASE 'other.db' AS other",
        "SELECT * FROM approvals",
        "SELECT o.order_id FROM orders o JOIN approvals a ON a.order_id = o.order_id",
        "SELECT load_extension('x')",
    ],
)
def test_sql_rejects_writes_and_hidden_tables(ctx: ToolContext, query: str) -> None:
    with pytest.raises(PermissionDenied):
        sql(ctx, query)


def test_sql_rejects_multiple_statements(ctx: ToolContext) -> None:
    with pytest.raises(InvalidArgument):
        sql(ctx, "SELECT 1; SELECT 2")


@pytest.mark.parametrize("query", ["", "   ", "SELEC * FROM orders", "SELECT nope FROM orders"])
def test_sql_invalid_queries(ctx: ToolContext, query: str) -> None:
    with pytest.raises(InvalidArgument):
        sql(ctx, query)


def test_sql_too_long(ctx: ToolContext) -> None:
    with pytest.raises(InvalidArgument):
        sql(ctx, "SELECT " + "1 + " * 1500 + "1")


def test_sql_time_limit(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("toolproof.env.tools.read.SQL_TIME_LIMIT_SECONDS", 0.05)
    query = "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM n) SELECT COUNT(*) FROM n"
    with pytest.raises(ToolTimeout):
        sql(ctx, query)


def test_sql_does_not_change_world(ctx: ToolContext) -> None:
    before = ctx.world.snapshot()
    for query in ["SELECT * FROM refunds", "DELETE FROM refunds"]:
        with contextlib.suppress(PermissionDenied):
            sql(ctx, query)
    assert before.diff(ctx.world.snapshot()).is_empty


# ------------------------------------------------------------------ get_order


def test_get_order(ctx: ToolContext) -> None:
    order_id = ctx.world.connection.execute(
        "SELECT order_id FROM orders o WHERE status = 'delivered' AND EXISTS "
        "(SELECT 1 FROM order_items i WHERE i.order_id = o.order_id) LIMIT 1"
    ).fetchone()[0]
    result = GetOrder().invoke(ctx, {"order_id": order_id})
    assert result["order_id"] == order_id
    assert result["items"], "a delivered order with items"
    assert sum(item["line_total"] for item in result["items"]) == pytest.approx(result["total"])
    assert result["customer_name"].count(" ") >= 1


def test_get_order_includes_existing_refund(ctx: ToolContext) -> None:
    refund = ctx.world.connection.execute("SELECT order_id, amount FROM refunds LIMIT 1").fetchone()
    result = GetOrder().invoke(ctx, {"order_id": refund["order_id"]})
    assert result["refund"]["amount"] == refund["amount"]


def test_get_order_zero_items(ctx: ToolContext) -> None:
    order_id = ctx.world.connection.execute(
        "SELECT order_id FROM orders o WHERE NOT EXISTS "
        "(SELECT 1 FROM order_items i WHERE i.order_id = o.order_id) LIMIT 1"
    ).fetchone()[0]
    result = GetOrder().invoke(ctx, {"order_id": order_id})
    assert result["items"] == [] and result["total"] == 0


def test_get_order_not_found(ctx: ToolContext) -> None:
    with pytest.raises(NotFound):
        GetOrder().invoke(ctx, {"order_id": 1})


def test_get_order_string_id_is_coerced(ctx: ToolContext) -> None:
    assert GetOrder().invoke(ctx, {"order_id": "9001"})["order_id"] == 9001


@pytest.mark.parametrize("arguments", [{}, {"order_id": "abc"}, {"order_id": 9001, "x": 1}])
def test_get_order_invalid_arguments(ctx: ToolContext, arguments: dict[str, Any]) -> None:
    with pytest.raises(InvalidArgument):
        GetOrder().invoke(ctx, arguments)


# ------------------------------------------------------------------ search_docs


def test_search_docs_finds_policy(ctx: ToolContext) -> None:
    results = SearchDocs().invoke(ctx, {"query": "late delivery compensation"})["results"]
    assert results[0]["doc_id"] == "late-delivery"
    assert len(results) == 3


def test_search_docs_top_k(ctx: ToolContext) -> None:
    results = SearchDocs().invoke(ctx, {"query": "refund", "top_k": 5})["results"]
    assert len(results) == 5
    scores = [result["score"] for result in results]
    assert scores == sorted(scores, reverse=True)


def test_search_docs_no_match(ctx: ToolContext) -> None:
    assert SearchDocs().invoke(ctx, {"query": "zzzqqq"})["results"] == []


@pytest.mark.parametrize("arguments", [{"query": " "}, {"query": "refund", "top_k": 9}])
def test_search_docs_invalid(ctx: ToolContext, arguments: dict[str, Any]) -> None:
    with pytest.raises(InvalidArgument):
        SearchDocs().invoke(ctx, arguments)
