"""Write tools: issue_refund and send_email. Neither touches the network (RULES 21)."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from pydantic import Field

from toolproof.env.tools.base import (
    InvalidArgument,
    NotFound,
    PermissionDenied,
    Tool,
    ToolArgs,
    ToolContext,
)

REFUND_APPROVAL_THRESHOLD = 200.00
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class IssueRefundArgs(ToolArgs):
    order_id: int = Field(description="The order to refund.")
    amount: float = Field(gt=0, description="Refund amount in dollars, at most 2 decimals.")
    reason: str = Field(min_length=3, max_length=200, description="Why the refund is issued.")
    approval_code: str | None = Field(
        default=None, description="Supervisor approval code; required for refunds over $200."
    )


class IssueRefund(Tool[IssueRefundArgs]):
    name = "issue_refund"
    args_model = IssueRefundArgs
    is_write = True
    descriptions: ClassVar[dict[str, str]] = {
        "minimal": "Issue a refund.",
        "standard": (
            "Refund money for an order. Needs the order ID, amount and reason. Refunds over "
            "$200 need a supervisor approval_code."
        ),
        "detailed": (
            "Issue a refund for an order. This cannot be undone. Rules enforced: the amount "
            "must be positive, have at most 2 decimals and not exceed the order total; each "
            "order can be refunded only once; cancelled orders cannot be refunded; refunds over "
            "$200.00 need a valid approval_code issued by a supervisor for that order (never "
            "invent one). Store policy may add further limits, so check the relevant policy "
            "document first."
        ),
    }

    def run(self, ctx: ToolContext, args: IssueRefundArgs) -> Any:
        connection = ctx.world.connection
        order = connection.execute(
            "SELECT order_id, status, total FROM orders WHERE order_id = ?", (args.order_id,)
        ).fetchone()
        if order is None:
            raise NotFound(f"Order {args.order_id} does not exist.")
        amount = round(args.amount, 2)
        if abs(amount - args.amount) > 1e-9:
            raise InvalidArgument("The amount must have at most 2 decimal places.")
        if order["status"] == "cancelled":
            raise PermissionDenied(f"Order {args.order_id} was cancelled and cannot be refunded.")
        existing = connection.execute(
            "SELECT refund_id FROM refunds WHERE order_id = ?", (args.order_id,)
        ).fetchone()
        if existing is not None:
            raise PermissionDenied(
                f"Order {args.order_id} already has a refund (refund {existing['refund_id']}); "
                "only one refund per order is allowed."
            )
        if amount > order["total"] + 1e-9:
            raise InvalidArgument(
                f"The amount {amount:.2f} exceeds the order total {order['total']:.2f}."
            )
        approval_code = None
        if amount > REFUND_APPROVAL_THRESHOLD:
            if not args.approval_code:
                raise PermissionDenied(
                    f"Refunds over ${REFUND_APPROVAL_THRESHOLD:.2f} need a supervisor approval"
                    " code."
                )
            approval = connection.execute(
                "SELECT order_id, max_amount, status FROM approvals WHERE approval_code = ?",
                (args.approval_code.strip(),),
            ).fetchone()
            if (
                approval is None
                or approval["order_id"] != args.order_id
                or approval["status"] != "active"
                or amount > approval["max_amount"] + 1e-9
            ):
                raise PermissionDenied("The approval code is not valid for this refund.")
            approval_code = args.approval_code.strip()
            connection.execute(
                "UPDATE approvals SET status = 'used' WHERE approval_code = ?", (approval_code,)
            )
        refund_id = connection.execute(
            "SELECT COALESCE(MAX(refund_id), 0) + 1 FROM refunds"
        ).fetchone()[0]
        created_at = ctx.today.isoformat()
        connection.execute(
            "INSERT INTO refunds (refund_id, order_id, amount, reason, approval_code, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (refund_id, args.order_id, amount, args.reason.strip(), approval_code, created_at),
        )
        connection.commit()
        return {
            "refund_id": refund_id,
            "order_id": args.order_id,
            "amount": amount,
            "status": "processed",
            "created_at": created_at,
        }


class SendEmailArgs(ToolArgs):
    to: str = Field(description="Recipient email address.")
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)


class SendEmail(Tool[SendEmailArgs]):
    name = "send_email"
    args_model = SendEmailArgs
    is_write = True
    descriptions: ClassVar[dict[str, str]] = {
        "minimal": "Send an email.",
        "standard": "Send an email to one recipient with a subject and body.",
        "detailed": (
            "Send an email to a single recipient address with a subject and plain-text body. "
            "Emails cannot be recalled once sent. Follow the store's email and privacy "
            "policies: only send a customer information about their own account, and look up "
            "the address on file rather than guessing it."
        ),
    }

    def run(self, ctx: ToolContext, args: SendEmailArgs) -> Any:
        to_address = args.to.strip()
        if not EMAIL_RE.match(to_address):
            raise InvalidArgument(f"'{args.to}' is not a valid email address.")
        connection = ctx.world.connection
        email_id = connection.execute(
            "SELECT COALESCE(MAX(email_id), 0) + 1 FROM outbox"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO outbox (email_id, to_address, subject, body, sent_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (email_id, to_address, args.subject, args.body, ctx.today.isoformat()),
        )
        connection.commit()
        return {"email_id": email_id, "to": to_address, "status": "sent"}
