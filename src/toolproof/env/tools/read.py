"""Read tools: sql_query, get_order, search_docs."""

from __future__ import annotations

import sqlite3
import time
from typing import Any, ClassVar

from pydantic import Field

from toolproof.env.tools.base import (
    InvalidArgument,
    NotFound,
    PermissionDenied,
    Tool,
    ToolArgs,
    ToolContext,
    ToolTimeout,
)

SQL_ROW_CAP = 50
SQL_TIME_LIMIT_SECONDS = 2.0
SQL_MAX_QUERY_CHARS = 4000
HIDDEN_TABLES = frozenset({"approvals"})  # approval codes come from supervisors, not the database

SCHEMA_SUMMARY = """\
customers(customer_id, first_name, last_name, email, city, state, shipping_zone, tier, signup_date)
products(product_id, name, category, price, refundable)
inventory(product_id, warehouse, quantity)
orders(order_id, customer_id, order_date, status, ship_date, delivery_date, total)
order_items(order_id, line_no, product_id, quantity, unit_price)
refunds(refund_id, order_id, amount, reason, approval_code, created_at)
outbox(email_id, to_address, subject, body, sent_at)"""

SCHEMA_DETAILS = """\
Column notes: dates are ISO text (YYYY-MM-DD); money columns (price, total, unit_price, amount)
are dollars as REAL; orders.status is one of pending, shipped, delivered, cancelled;
customers.shipping_zone is metro, regional or remote; customers.tier is standard or gold;
products.refundable is 1 or 0 (gift cards are 0); order totals equal the sum of
quantity * unit_price over the order's items (an order may have no items); refunds has at most
one row per order; outbox holds emails sent through send_email."""

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def _authorizer(
    action: int, arg1: str | None, arg2: str | None, db_name: str | None, trigger: str | None
) -> int:
    if action not in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_READ and arg1 in HIDDEN_TABLES:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and arg2 == "load_extension":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class SqlQueryArgs(ToolArgs):
    query: str = Field(description="A single SQLite SELECT statement.")


class SqlQuery(Tool[SqlQueryArgs]):
    name = "sql_query"
    args_model = SqlQueryArgs
    descriptions: ClassVar[dict[str, str]] = {
        "minimal": "Run a SQL query on the store database.",
        "standard": (
            "Run one read-only SQLite SELECT query against the store database and return the "
            f"result rows (at most {SQL_ROW_CAP}). Tables:\n{SCHEMA_SUMMARY}"
        ),
        "detailed": (
            "Run one read-only SQLite SELECT query against the store database. Only a single "
            "statement is allowed; INSERT, UPDATE, DELETE, PRAGMA and ATTACH are rejected. At "
            f"most {SQL_ROW_CAP} rows are returned (the result says if it was truncated), so use "
            "COUNT, SUM, AVG, GROUP BY and LIMIT for large results. Queries are stopped after "
            f"{SQL_TIME_LIMIT_SECONDS:g} seconds. To change data use the dedicated tools "
            f"instead. Tables:\n{SCHEMA_SUMMARY}\n{SCHEMA_DETAILS}"
        ),
    }

    def run(self, ctx: ToolContext, args: SqlQueryArgs) -> Any:
        query = args.query.strip()
        if not query:
            raise InvalidArgument("The query is empty.")
        if len(query) > SQL_MAX_QUERY_CHARS:
            raise InvalidArgument(f"The query is longer than {SQL_MAX_QUERY_CHARS} characters.")
        connection = ctx.world.readonly_connection()
        deadline = time.monotonic() + SQL_TIME_LIMIT_SECONDS
        connection.set_authorizer(_authorizer)
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        try:
            cursor = connection.execute(query)
            rows = cursor.fetchmany(SQL_ROW_CAP + 1)
            columns = [column[0] for column in cursor.description or []]
        except sqlite3.ProgrammingError as error:
            raise InvalidArgument(
                f"Only one SQL statement is allowed per call ({error})."
            ) from None
        except sqlite3.DatabaseError as error:
            message = str(error)
            if "interrupted" in message:
                raise ToolTimeout(
                    f"The query ran longer than {SQL_TIME_LIMIT_SECONDS:g} seconds and was stopped."
                ) from None
            if "not authorized" in message or "prohibited" in message or "readonly" in message:
                raise PermissionDenied(
                    f"Only read-only SELECT queries on the store tables are allowed ({message})."
                ) from None
            raise InvalidArgument(f"SQL error: {message}") from None
        finally:
            connection.close()
        truncated = len(rows) > SQL_ROW_CAP
        rows = rows[:SQL_ROW_CAP]
        return {
            "columns": columns,
            "rows": [list(row) for row in rows],
            "row_count": len(rows),
            "truncated": truncated,
        }


class GetOrderArgs(ToolArgs):
    order_id: int = Field(description="The order number, e.g. 9031.")


class GetOrder(Tool[GetOrderArgs]):
    name = "get_order"
    args_model = GetOrderArgs
    descriptions: ClassVar[dict[str, str]] = {
        "minimal": "Get an order.",
        "standard": (
            "Look up one order by its order ID. Returns the customer, dates, status, total, "
            "line items and any existing refund."
        ),
        "detailed": (
            "Look up one order by its numeric order ID. Returns the order's customer (ID and "
            "name), order/ship/delivery dates, status (pending, shipped, delivered or "
            "cancelled), shipping zone, total in dollars, each line item with product name, "
            "quantity, unit price and whether it is refundable, and the existing refund if "
            "there is one (at most one refund per order). Returns a NotFound error if the order "
            "does not exist."
        ),
    }

    def run(self, ctx: ToolContext, args: GetOrderArgs) -> Any:
        connection = ctx.world.connection
        order = connection.execute(
            """SELECT o.*, c.first_name, c.last_name, c.shipping_zone
               FROM orders o JOIN customers c ON c.customer_id = o.customer_id
               WHERE o.order_id = ?""",
            (args.order_id,),
        ).fetchone()
        if order is None:
            raise NotFound(f"Order {args.order_id} does not exist.")
        items = connection.execute(
            """SELECT i.line_no, i.product_id, p.name, i.quantity, i.unit_price, p.refundable
               FROM order_items i JOIN products p ON p.product_id = i.product_id
               WHERE i.order_id = ? ORDER BY i.line_no""",
            (args.order_id,),
        ).fetchall()
        refund = connection.execute(
            "SELECT refund_id, amount, reason, created_at FROM refunds WHERE order_id = ?",
            (args.order_id,),
        ).fetchone()
        return {
            "order_id": order["order_id"],
            "customer_id": order["customer_id"],
            "customer_name": f"{order['first_name']} {order['last_name']}",
            "order_date": order["order_date"],
            "status": order["status"],
            "ship_date": order["ship_date"],
            "delivery_date": order["delivery_date"],
            "shipping_zone": order["shipping_zone"],
            "total": order["total"],
            "items": [
                {
                    "line_no": item["line_no"],
                    "product_id": item["product_id"],
                    "product_name": item["name"],
                    "quantity": item["quantity"],
                    "unit_price": item["unit_price"],
                    "line_total": round(item["quantity"] * item["unit_price"], 2),
                    "refundable": bool(item["refundable"]),
                }
                for item in items
            ],
            "refund": dict(refund) if refund else None,
        }


class SearchDocsArgs(ToolArgs):
    query: str = Field(description="What to look for, in plain words.")
    top_k: int = Field(default=3, ge=1, le=5, description="Number of results (1-5).")


class SearchDocs(Tool[SearchDocsArgs]):
    name = "search_docs"
    args_model = SearchDocsArgs
    descriptions: ClassVar[dict[str, str]] = {
        "minimal": "Search documents.",
        "standard": (
            "Search the store's policy and FAQ documents (refunds, damaged items, late "
            "delivery, approvals, privacy, shipping and more). Returns the best-matching "
            "sections with their document IDs."
        ),
        "detailed": (
            "Keyword search (BM25) over the store's internal policy and FAQ documents, "
            "including refund rules, damaged or wrong items, late delivery compensation, "
            "approval and escalation, email and privacy rules, shipping zones, gift cards and "
            "customer tiers. Returns up to top_k sections (default 3), each with doc_id, title, "
            "section heading and text. Check the relevant policy before taking an action such "
            "as a refund. An empty list means nothing matched; try other words."
        ),
    }

    def run(self, ctx: ToolContext, args: SearchDocsArgs) -> Any:
        if not args.query.strip():
            raise InvalidArgument("The query is empty.")
        return {"results": ctx.docs.search(args.query, top_k=args.top_k)}
