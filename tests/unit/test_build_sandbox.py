"""The seed data generator is deterministic and contains the planned edge cases (P2.1)."""

from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from toolproof.paths import seed_dir

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_sandbox.py"


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_sandbox", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_sandbox"] = module
    spec.loader.exec_module(module)
    return module


generator = load_generator()


@pytest.fixture(scope="module")
def tables() -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = generator.generate()
    return result


def test_regenerating_matches_committed_csvs(tmp_path: Path) -> None:
    generator.main(["--out", str(tmp_path)])
    committed = sorted(path.name for path in seed_dir().glob("*.csv"))
    assert committed == sorted(path.name for path in tmp_path.glob("*.csv"))
    for name in committed:
        fresh = (tmp_path / name).read_bytes()
        stored = (seed_dir() / name).read_bytes().replace(b"\r\n", b"\n")
        assert fresh == stored, f"{name} differs from a fresh generation"


def test_row_counts(tables: dict[str, list[dict[str, Any]]]) -> None:
    assert len(tables["customers"]) == generator.N_CUSTOMERS
    assert len(tables["products"]) == generator.N_PRODUCTS
    assert len(tables["orders"]) == generator.N_ORDERS
    assert len(tables["refunds"]) == generator.N_EXISTING_REFUNDS


def test_name_edge_cases(tables: dict[str, list[dict[str, Any]]]) -> None:
    first_names = Counter(row["first_name"] for row in tables["customers"])
    assert first_names["John"] == 3
    assert first_names["Priya"] == 2
    full_names = [(row["first_name"], row["last_name"]) for row in tables["customers"]]
    assert len(full_names) == len(set(full_names))
    emails = [row["email"] for row in tables["customers"]]
    assert len(emails) == len(set(emails))


def test_order_edge_cases(tables: dict[str, list[dict[str, Any]]]) -> None:
    orders = tables["orders"]
    statuses = Counter(row["status"] for row in orders)
    assert statuses["cancelled"] > 0 and statuses["pending"] > 0 and statuses["shipped"] > 0
    with_items = {row["order_id"] for row in tables["order_items"]}
    zero_item = [row for row in orders if row["order_id"] not in with_items]
    assert len(zero_item) == generator.N_ZERO_ITEM_ORDERS
    assert all(float(row["total"]) == 0 for row in zero_item)
    exact = [row for row in orders if float(row["total"]) == 200.0]
    assert len(exact) >= generator.N_EXACT_LIMIT_ORDERS
    assert sum(row["status"] == "delivered" for row in exact) >= generator.N_EXACT_LIMIT_ORDERS


def test_totals_match_items(tables: dict[str, list[dict[str, Any]]]) -> None:
    sums: Counter[int] = Counter()
    for item in tables["order_items"]:
        sums[item["order_id"]] += item["quantity"] * float(item["unit_price"])
    for order in tables["orders"]:
        assert float(order["total"]) == pytest.approx(round(sums[order["order_id"]], 2))


def test_dates_are_consistent(tables: dict[str, list[dict[str, Any]]]) -> None:
    for order in tables["orders"]:
        ordered = date.fromisoformat(order["order_date"])
        assert ordered < generator.TODAY
        if order["status"] in ("cancelled", "pending"):
            assert order["ship_date"] == "" and order["delivery_date"] == ""
        elif order["status"] == "shipped":
            assert order["ship_date"] and order["delivery_date"] == ""
        else:
            shipped = date.fromisoformat(order["ship_date"])
            delivered = date.fromisoformat(order["delivery_date"])
            assert ordered < shipped < delivered < generator.TODAY


def test_refunds_respect_policy(tables: dict[str, list[dict[str, Any]]]) -> None:
    orders = {row["order_id"]: row for row in tables["orders"]}
    approvals = {row["approval_code"]: row for row in tables["approvals"]}
    refunded = [row["order_id"] for row in tables["refunds"]]
    assert len(refunded) == len(set(refunded)), "one refund per order"
    for refund in tables["refunds"]:
        order = orders[refund["order_id"]]
        assert order["status"] == "delivered"
        assert 0 < float(refund["amount"]) <= float(order["total"])
        if float(refund["amount"]) > 200:
            approval = approvals[refund["approval_code"]]
            assert approval["order_id"] == refund["order_id"]
            assert approval["status"] == "used"
        else:
            assert refund["approval_code"] == ""
    active = [row for row in tables["approvals"] if row["status"] == "active"]
    assert len(active) == generator.N_ACTIVE_APPROVALS
    for approval in active:
        assert approval["order_id"] not in refunded
        assert float(orders[approval["order_id"]]["total"]) > 200


def test_historical_refunds_follow_policy_docs(tables: dict[str, list[dict[str, Any]]]) -> None:
    """Seed refunds must not contradict data/docs (gift cards, late-delivery formula, reasons)."""
    orders = {row["order_id"]: row for row in tables["orders"]}
    zones = {row["customer_id"]: row["shipping_zone"] for row in tables["customers"]}
    gift_cards = {p["product_id"] for p in tables["products"] if p["category"] == "gift_card"}
    lines: dict[int, list[float]] = {}
    has_gift_card: set[int] = set()
    for item in tables["order_items"]:
        lines.setdefault(item["order_id"], []).append(
            round(item["quantity"] * float(item["unit_price"]), 2)
        )
        if item["product_id"] in gift_cards:
            has_gift_card.add(item["order_id"])
    allowed_reasons = {"damaged", "wrong_item", "missing_item", "change_of_mind", "late_delivery"}
    for refund in tables["refunds"]:
        order = orders[refund["order_id"]]
        amount = float(refund["amount"])
        total = float(order["total"])
        assert refund["order_id"] not in has_gift_card
        assert refund["reason"] in allowed_reasons
        if refund["reason"] == "late_delivery":
            transit = date.fromisoformat(order["delivery_date"]) - date.fromisoformat(
                order["ship_date"]
            )
            assert transit.days > generator.ZONE_EXPECTED_DAYS[zones[order["customer_id"]]]
            assert amount == pytest.approx(min(round(total * 0.10, 2), 50.00))
        else:
            assert amount == pytest.approx(total) or amount in lines[refund["order_id"]]
        days_after_delivery = (
            date.fromisoformat(refund["created_at"]) - date.fromisoformat(order["delivery_date"])
        ).days
        assert 0 < days_after_delivery <= 30


def test_gift_cards_are_not_refundable(tables: dict[str, list[dict[str, Any]]]) -> None:
    for product in tables["products"]:
        assert product["refundable"] == (0 if product["category"] == "gift_card" else 1)
