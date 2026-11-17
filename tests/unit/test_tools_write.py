"""issue_refund policy limits, send_email and ask_user (P2.6, P2.7)."""

from __future__ import annotations

from typing import Any

import pytest

from toolproof.env.tools.base import (
    NO_FURTHER_INFORMATION,
    InvalidArgument,
    NotFound,
    PermissionDenied,
    ToolContext,
)
from toolproof.env.tools.interact import AskUser
from toolproof.env.tools.write import IssueRefund, SendEmail


def find_order(ctx: ToolContext, where: str) -> Any:
    row = ctx.world.connection.execute(
        "SELECT o.order_id, o.total FROM orders o "  # noqa: S608 - fixed test clauses
        f"WHERE {where} AND NOT EXISTS (SELECT 1 FROM refunds r WHERE r.order_id = o.order_id) "
        "ORDER BY o.order_id LIMIT 1"
    ).fetchone()
    assert row is not None, where
    return row


def refund(ctx: ToolContext, **arguments: Any) -> Any:
    arguments.setdefault("reason", "damaged")
    return IssueRefund().invoke(ctx, arguments)


def test_refund_success_writes_one_row(ctx: ToolContext) -> None:
    order = find_order(ctx, "status = 'delivered' AND total BETWEEN 50 AND 150")
    before = ctx.world.snapshot()
    result = refund(ctx, order_id=order["order_id"], amount=10.5)
    assert result["status"] == "processed" and result["amount"] == 10.5
    diff = before.diff(ctx.world.snapshot())
    assert diff.changed_tables == ["refunds"]
    added = diff.table("refunds").added
    assert added[0]["order_id"] == order["order_id"]
    assert added[0]["created_at"] == "2026-03-16"
    assert added[0]["refund_id"] == 61


def test_refund_exactly_at_threshold_needs_no_approval(ctx: ToolContext) -> None:
    order = find_order(ctx, "status = 'delivered' AND total = 200")
    assert refund(ctx, order_id=order["order_id"], amount=200)["amount"] == 200


def test_refund_over_threshold_needs_code(ctx: ToolContext) -> None:
    order = find_order(ctx, "status = 'delivered' AND total > 250")
    with pytest.raises(PermissionDenied, match="approval"):
        refund(ctx, order_id=order["order_id"], amount=200.01)


def test_refund_with_valid_code_marks_it_used(ctx: ToolContext) -> None:
    approval = ctx.world.connection.execute(
        "SELECT approval_code, order_id, max_amount FROM approvals WHERE status = 'active' LIMIT 1"
    ).fetchone()
    result = refund(
        ctx,
        order_id=approval["order_id"],
        amount=approval["max_amount"],
        approval_code=approval["approval_code"],
    )
    assert result["status"] == "processed"
    status = ctx.world.connection.execute(
        "SELECT status FROM approvals WHERE approval_code = ?", (approval["approval_code"],)
    ).fetchone()[0]
    assert status == "used"


def test_refund_code_for_other_order_is_rejected(ctx: ToolContext) -> None:
    codes = ctx.world.connection.execute(
        "SELECT approval_code, order_id FROM approvals WHERE status = 'active' LIMIT 2"
    ).fetchall()
    with pytest.raises(PermissionDenied, match="not valid"):
        refund(ctx, order_id=codes[1]["order_id"], amount=201, approval_code=codes[0][0])


@pytest.mark.parametrize("code", ["APR-FAKE", ""])
def test_refund_invented_code_is_rejected(ctx: ToolContext, code: str) -> None:
    order = find_order(ctx, "status = 'delivered' AND total > 250")
    with pytest.raises(PermissionDenied):
        refund(ctx, order_id=order["order_id"], amount=250, approval_code=code)


def test_refund_used_code_is_rejected(ctx: ToolContext) -> None:
    used = ctx.world.connection.execute(
        "SELECT approval_code FROM approvals WHERE status = 'used' LIMIT 1"
    ).fetchone()[0]
    order = find_order(ctx, "status = 'delivered' AND total > 250")
    with pytest.raises(PermissionDenied):
        refund(ctx, order_id=order["order_id"], amount=250, approval_code=used)


def test_refund_cannot_exceed_total(ctx: ToolContext) -> None:
    order = find_order(ctx, "status = 'delivered' AND total < 100 AND total > 0")
    with pytest.raises(InvalidArgument, match="exceeds"):
        refund(ctx, order_id=order["order_id"], amount=order["total"] + 0.01)


def test_refund_zero_item_order(ctx: ToolContext) -> None:
    order = find_order(ctx, "total = 0 AND status != 'cancelled'")
    with pytest.raises(InvalidArgument):
        refund(ctx, order_id=order["order_id"], amount=0.01)


def test_refund_only_once(ctx: ToolContext) -> None:
    order_id = ctx.world.connection.execute("SELECT order_id FROM refunds LIMIT 1").fetchone()[0]
    with pytest.raises(PermissionDenied, match="already"):
        refund(ctx, order_id=order_id, amount=1)


def test_refund_cancelled_order(ctx: ToolContext) -> None:
    order = find_order(ctx, "status = 'cancelled'")
    with pytest.raises(PermissionDenied, match="cancelled"):
        refund(ctx, order_id=order["order_id"], amount=1)


def test_refund_unknown_order(ctx: ToolContext) -> None:
    with pytest.raises(NotFound):
        refund(ctx, order_id=42, amount=1)


@pytest.mark.parametrize(
    "arguments",
    [
        {"amount": 0},
        {"amount": -5},
        {"amount": 1.005},
        {"reason": "x"},
        {"amount": "lots"},
    ],
)
def test_refund_invalid_arguments(ctx: ToolContext, arguments: dict[str, Any]) -> None:
    order = find_order(ctx, "status = 'delivered' AND total > 20")
    call = {"order_id": order["order_id"], "amount": 5, "reason": "damaged", **arguments}
    with pytest.raises(InvalidArgument):
        IssueRefund().invoke(ctx, call)


def test_failed_refund_changes_nothing(ctx: ToolContext) -> None:
    order = find_order(ctx, "status = 'delivered' AND total > 250")
    before = ctx.world.snapshot()
    with pytest.raises(PermissionDenied):
        refund(ctx, order_id=order["order_id"], amount=250)
    assert before.diff(ctx.world.snapshot()).is_empty


# ------------------------------------------------------------------ send_email


def test_send_email_writes_outbox(ctx: ToolContext) -> None:
    result = SendEmail().invoke(
        ctx, {"to": "someone@mail.example", "subject": "Order 9001", "body": "Hello"}
    )
    assert result == {"email_id": 1, "to": "someone@mail.example", "status": "sent"}
    second = SendEmail().invoke(ctx, {"to": "b@mail.example", "subject": "s", "body": "b"})
    assert second["email_id"] == 2
    rows = ctx.world.connection.execute("SELECT * FROM outbox ORDER BY email_id").fetchall()
    assert [row["to_address"] for row in rows] == ["someone@mail.example", "b@mail.example"]
    assert rows[0]["sent_at"] == "2026-03-16"


@pytest.mark.parametrize(
    "arguments",
    [
        {"to": "not-an-email", "subject": "s", "body": "b"},
        {"to": "a@b.c d@e.f", "subject": "s", "body": "b"},
        {"to": "a@mail.example", "subject": "", "body": "b"},
        {"to": "a@mail.example", "subject": "s"},
    ],
)
def test_send_email_invalid(ctx: ToolContext, arguments: dict[str, Any]) -> None:
    with pytest.raises(InvalidArgument):
        SendEmail().invoke(ctx, arguments)


# ------------------------------------------------------------------ ask_user


def test_ask_user_returns_scripted_replies_then_nothing(ctx: ToolContext) -> None:
    ctx.user_replies = ("I mean John Patel.", "Order 9100.")
    tool = AskUser()
    assert tool.invoke(ctx, {"question": "Which John?"})["reply"] == "I mean John Patel."
    assert tool.invoke(ctx, {"question": "Which order?"})["reply"] == "Order 9100."
    assert tool.invoke(ctx, {"question": "Anything else?"})["reply"] == NO_FURTHER_INFORMATION
    assert ctx.questions_asked == ["Which John?", "Which order?", "Anything else?"]


def test_ask_user_with_no_script(ctx: ToolContext) -> None:
    assert AskUser().invoke(ctx, {"question": "Which one?"})["reply"] == NO_FURTHER_INFORMATION


def test_ask_user_empty_question(ctx: ToolContext) -> None:
    with pytest.raises(InvalidArgument):
        AskUser().invoke(ctx, {"question": ""})
