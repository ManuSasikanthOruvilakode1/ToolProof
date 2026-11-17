"""World building, per-trial isolation, snapshots and diffs (P2.2)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from toolproof.env.clock import TODAY
from toolproof.env.world import ALL_TABLES, World, ensure_base_db, seed_fingerprint
from toolproof.paths import seed_dir


def test_base_db_has_all_tables(world: World) -> None:
    counts = {
        table: world.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        for table in ALL_TABLES
    }
    assert counts["customers"] == 300
    assert counts["orders"] == 1200
    assert counts["refunds"] == 60
    assert counts["outbox"] == 0


def test_types_are_loaded_correctly(world: World) -> None:
    row = world.connection.execute(
        "SELECT order_id, total, ship_date FROM orders WHERE status = 'cancelled' LIMIT 1"
    ).fetchone()
    assert isinstance(row["order_id"], int)
    assert isinstance(row["total"], float)
    assert row["ship_date"] is None


def test_frozen_clock(world: World) -> None:
    assert world.today == TODAY


def test_trials_are_isolated(base_db: Path, tmp_path: Path) -> None:
    with World.fresh(tmp_path / "a", base_db=base_db) as first:
        first.connection.execute("DELETE FROM refunds")
        first.connection.commit()
        with World.fresh(tmp_path / "b", base_db=base_db) as second:
            count = second.connection.execute("SELECT COUNT(*) FROM refunds").fetchone()[0]
            assert count == 60


def test_readonly_connection_rejects_writes(world: World) -> None:
    connection = world.readonly_connection()
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM refunds")
    finally:
        connection.close()


def test_diff_reports_added_removed_changed(world: World) -> None:
    before = world.snapshot()
    connection = world.connection
    connection.execute(
        "INSERT INTO outbox VALUES (1, 'a@mail.example', 'Hi', 'Body', '2026-03-16')"
    )
    connection.execute("DELETE FROM refunds WHERE refund_id = 1")
    connection.execute("UPDATE customers SET tier = 'gold' WHERE customer_id = 1001")
    connection.execute("UPDATE customers SET tier = 'standard' WHERE customer_id = 1001")
    connection.execute("UPDATE inventory SET quantity = quantity + 1 WHERE product_id = 501")
    connection.commit()
    diff = before.diff(world.snapshot())
    assert set(diff.changed_tables) == {"outbox", "refunds", "inventory"}
    assert diff.table("outbox").added[0]["to_address"] == "a@mail.example"
    assert diff.table("refunds").removed[0]["refund_id"] == 1
    changed = diff.table("inventory").changed
    assert len(changed) == 2  # both warehouses of product 501
    assert all(after["quantity"] == before_row["quantity"] + 1 for before_row, after in changed)
    assert diff.table("customers").is_empty  # changed and changed back
    assert set(diff.to_dict()) == {"outbox", "refunds", "inventory"}
    assert diff.table("no_such_table").is_empty


def test_no_change_gives_empty_diff(world: World) -> None:
    assert world.snapshot().diff(world.snapshot()).is_empty


def test_ensure_base_db_rebuilds_when_seed_changes(tmp_path: Path) -> None:
    seeds = tmp_path / "seed"
    shutil.copytree(seed_dir(), seeds)
    db_path = tmp_path / "world.sqlite"
    ensure_base_db(seeds, db_path)
    first_mtime = db_path.stat().st_mtime_ns
    assert ensure_base_db(seeds, db_path) == db_path
    assert db_path.stat().st_mtime_ns == first_mtime, "unchanged seed must not rebuild"

    old_fingerprint = seed_fingerprint(seeds)
    customers = seeds / "customers.csv"
    customers.write_text(customers.read_text(encoding="utf-8").replace("Sydney", "Sydney "))
    assert seed_fingerprint(seeds) != old_fingerprint
    ensure_base_db(seeds, db_path)
    with World(db_path) as rebuilt:
        city = rebuilt.connection.execute(
            "SELECT city FROM customers WHERE city LIKE 'Sydney%' LIMIT 1"
        ).fetchone()[0]
    assert city == "Sydney "
