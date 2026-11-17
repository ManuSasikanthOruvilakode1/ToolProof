"""The sandbox world: a SQLite database built from ``data/seed/*.csv``.

The base database is built once (and rebuilt automatically when the seed files or schema
change). Every trial works on its own copy, so trials can never affect each other
(RULES 23). ``snapshot()`` and ``WorldDiff`` let checkers compare the state before and after a
trial.
"""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import TracebackType
from typing import Any

from toolproof.env.clock import TODAY
from toolproof.paths import base_db_path, seed_dir

SCHEMA_SQL = """
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    city          TEXT NOT NULL,
    state         TEXT NOT NULL,
    shipping_zone TEXT NOT NULL,
    tier          TEXT NOT NULL,
    signup_date   TEXT NOT NULL
);
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    category   TEXT NOT NULL,
    price      REAL NOT NULL,
    refundable INTEGER NOT NULL
);
CREATE TABLE inventory (
    product_id INTEGER NOT NULL REFERENCES products (product_id),
    warehouse  TEXT NOT NULL,
    quantity   INTEGER NOT NULL,
    PRIMARY KEY (product_id, warehouse)
);
CREATE TABLE orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers (customer_id),
    order_date    TEXT NOT NULL,
    status        TEXT NOT NULL,
    ship_date     TEXT,
    delivery_date TEXT,
    total         REAL NOT NULL
);
CREATE TABLE order_items (
    order_id   INTEGER NOT NULL REFERENCES orders (order_id),
    line_no    INTEGER NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products (product_id),
    quantity   INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
CREATE TABLE refunds (
    refund_id     INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL UNIQUE REFERENCES orders (order_id),
    amount        REAL NOT NULL,
    reason        TEXT NOT NULL,
    approval_code TEXT,
    created_at    TEXT NOT NULL
);
CREATE TABLE approvals (
    approval_code TEXT PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders (order_id),
    max_amount    REAL NOT NULL,
    status        TEXT NOT NULL
);
CREATE TABLE outbox (
    email_id   INTEGER PRIMARY KEY,
    to_address TEXT NOT NULL,
    subject    TEXT NOT NULL,
    body       TEXT NOT NULL,
    sent_at    TEXT NOT NULL
);
"""

SEED_TABLES = (
    "customers",
    "products",
    "inventory",
    "orders",
    "order_items",
    "refunds",
    "approvals",
)
ALL_TABLES = (*SEED_TABLES, "outbox")

Row = dict[str, Any]
RowKey = tuple[Any, ...]


# ------------------------------------------------------------------ building


def seed_fingerprint(seed_directory: Path) -> str:
    """Hash of the schema and every seed CSV (line endings normalised)."""
    digest = hashlib.sha256(SCHEMA_SQL.encode("utf-8"))
    for table in SEED_TABLES:
        content = (seed_directory / f"{table}.csv").read_bytes().replace(b"\r\n", b"\n")
        digest.update(table.encode("utf-8") + b"\0" + content + b"\0")
    return digest.hexdigest()


def _fingerprint_path(db_path: Path) -> Path:
    return db_path.with_name(db_path.name + ".sha256")


def build_base_db(seed_directory: Path, out_path: Path) -> Path:
    """Build the world database from CSV files, atomically replacing ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    building = out_path.with_name(out_path.name + ".building")
    building.unlink(missing_ok=True)
    connection = sqlite3.connect(building)
    try:
        connection.executescript(SCHEMA_SQL)
        for table in SEED_TABLES:
            with (seed_directory / f"{table}.csv").open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                columns = list(reader.fieldnames or [])
                rows = [tuple(row[c] if row[c] != "" else None for c in columns) for row in reader]
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",  # noqa: S608
                rows,
            )
        connection.commit()
    finally:
        connection.close()
    os.replace(building, out_path)
    _fingerprint_path(out_path).write_text(seed_fingerprint(seed_directory), encoding="utf-8")
    return out_path


def ensure_base_db(seed_directory: Path | None = None, db_path: Path | None = None) -> Path:
    """Return the base database path, building it first if missing or out of date."""
    seed_directory = seed_directory or seed_dir()
    db_path = db_path or base_db_path()
    expected = seed_fingerprint(seed_directory)
    marker = _fingerprint_path(db_path)
    if db_path.exists() and marker.exists() and marker.read_text(encoding="utf-8") == expected:
        return db_path
    return build_base_db(seed_directory, db_path)


# ------------------------------------------------------------------ snapshots


@dataclass(frozen=True)
class TableDiff:
    added: list[Row] = field(default_factory=list)
    removed: list[Row] = field(default_factory=list)
    changed: list[tuple[Row, Row]] = field(default_factory=list)  # (before, after)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": self.added,
            "removed": self.removed,
            "changed": [{"before": before, "after": after} for before, after in self.changed],
        }


@dataclass(frozen=True)
class WorldDiff:
    tables: dict[str, TableDiff]

    @property
    def is_empty(self) -> bool:
        return all(diff.is_empty for diff in self.tables.values())

    @property
    def changed_tables(self) -> list[str]:
        return [name for name, diff in self.tables.items() if not diff.is_empty]

    def table(self, name: str) -> TableDiff:
        return self.tables.get(name, TableDiff())

    def to_dict(self) -> dict[str, Any]:
        return {name: self.tables[name].to_dict() for name in self.changed_tables}


@dataclass(frozen=True)
class Snapshot:
    tables: dict[str, dict[RowKey, Row]]

    def diff(self, after: Snapshot) -> WorldDiff:
        """Changes from this snapshot (before) to ``after``."""
        result: dict[str, TableDiff] = {}
        for name in sorted(set(self.tables) | set(after.tables)):
            old = self.tables.get(name, {})
            new = after.tables.get(name, {})
            result[name] = TableDiff(
                added=[new[key] for key in sorted(new.keys() - old.keys())],
                removed=[old[key] for key in sorted(old.keys() - new.keys())],
                changed=[
                    (old[key], new[key])
                    for key in sorted(old.keys() & new.keys())
                    if old[key] != new[key]
                ],
            )
        return WorldDiff(result)


# ------------------------------------------------------------------ world


class World:
    """One trial's private copy of the store database."""

    def __init__(self, path: Path, today: date = TODAY) -> None:
        self.path = path
        self.today = today
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    @classmethod
    def fresh(cls, workdir: Path, base_db: Path | None = None) -> World:
        """Copy the base database into ``workdir`` and open the copy."""
        source = base_db or ensure_base_db()
        workdir.mkdir(parents=True, exist_ok=True)
        target = workdir / "world.sqlite"
        shutil.copyfile(source, target)
        return cls(target)

    @property
    def connection(self) -> sqlite3.Connection:
        """Read-write connection, for write tools and checkers only."""
        return self._connection

    def readonly_connection(self) -> sqlite3.Connection:
        """A new connection that cannot modify the database."""
        uri = self.path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        return connection

    def snapshot(self) -> Snapshot:
        tables: dict[str, dict[RowKey, Row]] = {}
        for table in ALL_TABLES:
            info = self._connection.execute(f"PRAGMA table_info({table})").fetchall()
            key_columns = [
                row["name"] for row in sorted(info, key=lambda r: r["pk"]) if row["pk"] > 0
            ]
            rows: dict[RowKey, Row] = {}
            for record in self._connection.execute(f"SELECT * FROM {table}"):  # noqa: S608
                row = dict(record)
                rows[tuple(row[column] for column in key_columns)] = row
            tables[table] = rows
        return Snapshot(tables)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> World:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
