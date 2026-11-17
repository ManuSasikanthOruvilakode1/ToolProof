#!/usr/bin/env python3
"""Generate the sandbox store's seed data as CSV files (deterministic, seed 42).

Usage:
    uv run python scripts/build_sandbox.py              # writes data/seed/*.csv
    uv run python scripts/build_sandbox.py --out DIR    # writes elsewhere (used by tests)

The generated files are committed. Running the script again must produce identical bytes;
a unit test checks this. Deliberate edge cases (see docs/DESIGN_NOTES.md):

- exactly three customers named John and two named Priya (ambiguity tasks);
- cancelled orders; orders whose total is exactly $200.00 (the refund approval threshold);
- orders with zero items (total $0.00);
- late deliveries (transit longer than the shipping zone's expected days);
- gift-card products, which are not refundable under store policy.
"""

from __future__ import annotations

import argparse
import csv
import random
import string
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from toolproof.env.clock import TODAY
from toolproof.paths import seed_dir

SEED = 42
N_CUSTOMERS = 300
N_PRODUCTS = 80
N_ORDERS = 1200
N_EXISTING_REFUNDS = 60
N_ACTIVE_APPROVALS = 12
N_ZERO_ITEM_ORDERS = 4
N_EXACT_LIMIT_ORDERS = 5
REFUND_APPROVAL_THRESHOLD = 200.00

ORDER_START = date(2025, 3, 1)
FIRST_ORDER_ID = 9001
FIRST_CUSTOMER_ID = 1001
FIRST_PRODUCT_ID = 501

# Fictional people. Common given and family names; no real individuals are represented.
FIRST_NAMES = [
    "Aarav",
    "Abigail",
    "Aiden",
    "Amelia",
    "Ava",
    "Benjamin",
    "Charlotte",
    "Chloe",
    "Daniel",
    "Elena",
    "Ella",
    "Ethan",
    "Fatima",
    "Grace",
    "Hannah",
    "Harper",
    "Henry",
    "Isla",
    "Jack",
    "Jacob",
    "James",
    "Jasmine",
    "Kai",
    "Leo",
    "Liam",
    "Lucas",
    "Mason",
    "Mei",
    "Mia",
    "Noah",
    "Oliver",
    "Olivia",
    "Omar",
    "Ruby",
    "Sakura",
    "Samuel",
    "Sofia",
    "Thomas",
    "Wei",
    "Zara",
]
FORCED_FIRST_NAMES = {"John": 3, "Priya": 2}
LAST_NAMES = [
    "Anderson",
    "Bennett",
    "Brown",
    "Campbell",
    "Chen",
    "Clarke",
    "Davies",
    "Edwards",
    "Evans",
    "Fischer",
    "Garcia",
    "Green",
    "Hall",
    "Harris",
    "Hughes",
    "Ito",
    "Jackson",
    "Johnson",
    "Kaur",
    "Kelly",
    "Khan",
    "Kim",
    "King",
    "Lee",
    "Lewis",
    "Martin",
    "Mitchell",
    "Moore",
    "Murphy",
    "Nguyen",
    "Novak",
    "O'Brien",
    "Patel",
    "Phillips",
    "Robinson",
    "Rossi",
    "Ryan",
    "Santos",
    "Scott",
    "Singh",
    "Smith",
    "Taylor",
    "Thompson",
    "Walker",
    "Wang",
    "White",
    "Williams",
    "Wilson",
    "Wright",
    "Young",
]

# (city, state, shipping zone)
CITIES = [
    ("Sydney", "NSW", "metro"),
    ("Melbourne", "VIC", "metro"),
    ("Brisbane", "QLD", "metro"),
    ("Perth", "WA", "metro"),
    ("Adelaide", "SA", "metro"),
    ("Newcastle", "NSW", "regional"),
    ("Geelong", "VIC", "regional"),
    ("Toowoomba", "QLD", "regional"),
    ("Ballarat", "VIC", "regional"),
    ("Wagga Wagga", "NSW", "regional"),
    ("Cairns", "QLD", "regional"),
    ("Alice Springs", "NT", "remote"),
    ("Broome", "WA", "remote"),
    ("Kalgoorlie", "WA", "remote"),
    ("Mount Isa", "QLD", "remote"),
]
CITY_WEIGHTS = [14, 13, 10, 8, 7, 5, 4, 4, 3, 3, 3, 2, 2, 1, 1]
ZONE_EXPECTED_DAYS = {"metro": 3, "regional": 6, "remote": 10}

CATEGORIES: dict[str, tuple[list[str], list[str], tuple[float, float]]] = {
    "kitchen": (
        ["Ceramic", "Copper", "Cast Iron", "Bamboo", "Glass", "Enamel"],
        ["Mixing Bowl Set", "Frying Pan", "Teapot", "Chopping Board", "Knife Block", "Kettle"],
        (8.0, 90.0),
    ),
    "home": (
        ["Linen", "Wool", "Velvet", "Rattan", "Walnut", "Cotton"],
        ["Throw Blanket", "Cushion Cover", "Floor Rug", "Wall Mirror", "Side Table", "Curtains"],
        (12.0, 180.0),
    ),
    "office": (
        ["Ergonomic", "Compact", "Adjustable", "Leather", "Recycled", "Steel"],
        ["Desk Organiser", "Office Chair", "Notebook Set", "Monitor Stand", "Filing Cabinet"],
        (6.0, 260.0),
    ),
    "outdoor": (
        ["Weatherproof", "Folding", "Solar", "Teak", "Hanging", "Portable"],
        ["Garden Lantern", "Deck Chair", "Planter Box", "Picnic Set", "Hammock"],
        (10.0, 220.0),
    ),
    "electronics": (
        ["Wireless", "Smart", "Bluetooth", "Rechargeable", "Noise-Cancelling", "Mini"],
        ["Speaker", "Headphones", "Desk Fan", "Power Bank", "Alarm Clock", "Webcam"],
        (15.0, 320.0),
    ),
}
# Fixed products that edge-case orders and policy documents rely on.
FIXED_PRODUCTS: list[tuple[str, str, float]] = [
    ("Gift Card $25", "gift_card", 25.00),
    ("Gift Card $50", "gift_card", 50.00),
    ("Gift Card $100", "gift_card", 100.00),
    ("Oak Bookshelf", "home", 200.00),
    ("Brass Desk Lamp", "office", 100.00),
]
WAREHOUSES = ["Sydney DC", "Melbourne DC"]
REFUND_REASONS = ["damaged", "late_delivery", "change_of_mind", "wrong_item", "missing_item"]


@dataclass
class Order:
    order_id: int
    customer_id: int
    order_date: date
    status: str
    ship_date: date | None
    delivery_date: date | None
    items: list[tuple[int, int, float]]  # (product_id, quantity, unit_price)

    @property
    def total(self) -> float:
        return round(sum(quantity * price for _, quantity, price in self.items), 2)


def random_date(rng: random.Random, start: date, end: date) -> date:
    """Uniform date in [start, end)."""
    return start + timedelta(days=rng.randrange((end - start).days))


def make_customers(rng: random.Random) -> list[dict[str, Any]]:
    first_names: list[str] = []
    for name, count in FORCED_FIRST_NAMES.items():
        first_names.extend([name] * count)
    first_names.extend(rng.choice(FIRST_NAMES) for _ in range(N_CUSTOMERS - len(first_names)))
    rng.shuffle(first_names)

    customers: list[dict[str, Any]] = []
    used_full_names: set[tuple[str, str]] = set()
    for index, first in enumerate(first_names):
        last = rng.choice(LAST_NAMES)
        while (first, last) in used_full_names:
            last = rng.choice(LAST_NAMES)
        used_full_names.add((first, last))
        customer_id = FIRST_CUSTOMER_ID + index
        city, state, zone = rng.choices(CITIES, weights=CITY_WEIGHTS)[0]
        local_part = f"{first}.{last}".lower().replace("'", "")
        customers.append(
            {
                "customer_id": customer_id,
                "first_name": first,
                "last_name": last,
                "email": f"{local_part}.{customer_id}@mail.example",
                "city": city,
                "state": state,
                "shipping_zone": zone,
                "tier": "gold" if rng.random() < 0.15 else "standard",
                "signup_date": random_date(rng, date(2023, 1, 1), ORDER_START).isoformat(),
            }
        )
    return customers


def make_products(rng: random.Random) -> list[dict[str, Any]]:
    rows: list[tuple[str, str, float]] = list(FIXED_PRODUCTS)
    used_names = {name for name, _, _ in rows}
    categories = list(CATEGORIES)
    while len(rows) < N_PRODUCTS:
        category = categories[len(rows) % len(categories)]
        adjectives, nouns, (low, high) = CATEGORIES[category]
        name = f"{rng.choice(adjectives)} {rng.choice(nouns)}"
        if name in used_names:
            continue
        used_names.add(name)
        price = round(max(low, round(rng.uniform(low, high))) - 0.01, 2)
        rows.append((name, category, price))
    return [
        {
            "product_id": FIRST_PRODUCT_ID + index,
            "name": name,
            "category": category,
            "price": f"{price:.2f}",
            "refundable": 0 if category == "gift_card" else 1,
        }
        for index, (name, category, price) in enumerate(rows)
    ]


def make_inventory(rng: random.Random, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for product in products:
        for warehouse in WAREHOUSES:
            quantity = 0 if rng.random() < 0.08 else rng.randint(1, 200)
            rows.append(
                {"product_id": product["product_id"], "warehouse": warehouse, "quantity": quantity}
            )
    return rows


def assign_fulfilment(
    rng: random.Random, order_date: date, zone: str, *, allow_cancel: bool
) -> tuple[str, date | None, date | None]:
    if allow_cancel and rng.random() < 0.06:
        return "cancelled", None, None
    ship_date = order_date + timedelta(days=rng.randint(1, 3))
    if ship_date >= TODAY:
        return "pending", None, None
    expected = ZONE_EXPECTED_DAYS[zone]
    late = allow_cancel and rng.random() < 0.12
    transit = expected + rng.randint(1, 7) if late else rng.randint(max(1, expected - 2), expected)
    delivery_date = ship_date + timedelta(days=transit)
    if delivery_date >= TODAY:
        return "shipped", ship_date, None
    return "delivered", ship_date, delivery_date


def make_orders(
    rng: random.Random, customers: list[dict[str, Any]], products: list[dict[str, Any]]
) -> list[Order]:
    by_name = {product["name"]: product for product in products}
    bookshelf = by_name["Oak Bookshelf"]
    lamp = by_name["Brass Desk Lamp"]
    # Some customers order much more often than others.
    customer_weights = [rng.choice([1, 1, 1, 2, 3, 6]) for _ in customers]
    special = rng.sample(range(N_ORDERS), N_ZERO_ITEM_ORDERS + N_EXACT_LIMIT_ORDERS)
    zero_item = set(special[:N_ZERO_ITEM_ORDERS])
    exact_limit = set(special[N_ZERO_ITEM_ORDERS:])

    orders: list[Order] = []
    for index in range(N_ORDERS):
        customer = rng.choices(customers, weights=customer_weights)[0]
        is_exact = index in exact_limit
        latest = TODAY - timedelta(days=30) if is_exact else TODAY
        order_date = random_date(rng, ORDER_START, latest)
        status, ship_date, delivery_date = assign_fulfilment(
            rng, order_date, customer["shipping_zone"], allow_cancel=not is_exact
        )
        items: list[tuple[int, int, float]]
        if index in zero_item:
            items = []
        elif is_exact:
            items = (
                [(bookshelf["product_id"], 1, 200.00)]
                if rng.random() < 0.5
                else [(lamp["product_id"], 2, 100.00)]
            )
        else:
            chosen = rng.sample(products, rng.choice([1, 1, 1, 2, 2, 3]))
            items = [
                (product["product_id"], rng.choice([1, 1, 1, 1, 2]), float(product["price"]))
                for product in chosen
            ]
        orders.append(
            Order(
                order_id=FIRST_ORDER_ID + index,
                customer_id=customer["customer_id"],
                order_date=order_date,
                status=status,
                ship_date=ship_date,
                delivery_date=delivery_date,
                items=items,
            )
        )
    return orders


def make_code(rng: random.Random, used: set[str]) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "APR-" + "".join(rng.choice(alphabet) for _ in range(4))
        if code not in used:
            used.add(code)
            return code


def make_refunds_and_approvals(
    rng: random.Random, orders: list[Order], protected: set[int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = [
        order
        for order in orders
        if order.status == "delivered" and order.total > 0 and order.order_id not in protected
    ]
    refunded = sorted(rng.sample(candidates, N_EXISTING_REFUNDS), key=lambda o: o.order_id)
    used_codes: set[str] = set()
    refunds: list[dict[str, Any]] = []
    approvals: list[dict[str, Any]] = []
    for refund_id, order in enumerate(refunded, start=1):
        if rng.random() < 0.5:
            amount = order.total
        else:
            amount = max(0.01, round(order.total * rng.uniform(0.1, 0.9), 2))
        code = None
        if amount > REFUND_APPROVAL_THRESHOLD:
            code = make_code(rng, used_codes)
            approvals.append(
                {
                    "approval_code": code,
                    "order_id": order.order_id,
                    "max_amount": f"{amount:.2f}",
                    "status": "used",
                }
            )
        if order.delivery_date is None:  # delivered orders always have one
            raise ValueError(f"delivered order {order.order_id} has no delivery date")
        created = min(order.delivery_date + timedelta(days=rng.randint(1, 20)), TODAY)
        refunds.append(
            {
                "refund_id": refund_id,
                "order_id": order.order_id,
                "amount": f"{amount:.2f}",
                "reason": rng.choice(REFUND_REASONS),
                "approval_code": code or "",
                "created_at": created.isoformat(),
            }
        )

    refunded_ids = {order.order_id for order in refunded}
    big_unrefunded = [
        order
        for order in orders
        if order.status == "delivered"
        and order.total > REFUND_APPROVAL_THRESHOLD
        and order.order_id not in refunded_ids
    ]
    for order in sorted(rng.sample(big_unrefunded, N_ACTIVE_APPROVALS), key=lambda o: o.order_id):
        approvals.append(
            {
                "approval_code": make_code(rng, used_codes),
                "order_id": order.order_id,
                "max_amount": f"{order.total:.2f}",
                "status": "active",
            }
        )
    approvals.sort(key=lambda row: row["approval_code"])
    return refunds, approvals


def order_rows(orders: list[Order]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    order_table = []
    item_table = []
    for order in orders:
        order_table.append(
            {
                "order_id": order.order_id,
                "customer_id": order.customer_id,
                "order_date": order.order_date.isoformat(),
                "status": order.status,
                "ship_date": order.ship_date.isoformat() if order.ship_date else "",
                "delivery_date": order.delivery_date.isoformat() if order.delivery_date else "",
                "total": f"{order.total:.2f}",
            }
        )
        for line_no, (product_id, quantity, price) in enumerate(order.items, start=1):
            item_table.append(
                {
                    "order_id": order.order_id,
                    "line_no": line_no,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": f"{price:.2f}",
                }
            )
    return order_table, item_table


def generate(seed: int = SEED) -> dict[str, list[dict[str, Any]]]:
    """Return every seed table as a list of row dicts, keyed by table name."""
    rng = random.Random(seed)
    customers = make_customers(rng)
    products = make_products(rng)
    inventory = make_inventory(rng, products)
    orders = make_orders(rng, customers, products)
    protected = {
        order.order_id
        for order in orders
        if order.total in (0.0, REFUND_APPROVAL_THRESHOLD) and order.status == "delivered"
    }
    refunds, approvals = make_refunds_and_approvals(rng, orders, protected)
    order_table, item_table = order_rows(orders)
    return {
        "customers": customers,
        "products": products,
        "inventory": inventory,
        "orders": order_table,
        "order_items": item_table,
        "refunds": refunds,
        "approvals": approvals,
    }


def write_tables(tables: dict[str, list[dict[str, Any]]], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, rows in tables.items():
        path = out_dir / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--out", type=Path, default=None, help="output directory")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    out_dir = args.out or seed_dir()
    tables = generate(args.seed)
    for path in write_tables(tables, out_dir):
        print(f"wrote {path} ({len(tables[path.stem])} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
