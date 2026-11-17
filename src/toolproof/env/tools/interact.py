"""ask_user: the agent's only channel back to the (scripted) user."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field

from toolproof.env.tools.base import Tool, ToolArgs, ToolContext


class AskUserArgs(ToolArgs):
    question: str = Field(min_length=1, max_length=500, description="The question to ask.")


class AskUser(Tool[AskUserArgs]):
    name = "ask_user"
    args_model = AskUserArgs
    descriptions: ClassVar[dict[str, str]] = {
        "minimal": "Ask the user.",
        "standard": "Ask the user a clarifying question and get their reply.",
        "detailed": (
            "Ask the user a clarifying question when the request is ambiguous or information "
            "you need is missing, for example when several customers match a name. Ask before "
            "taking any action you are unsure about. Returns the user's reply."
        ),
    }

    def run(self, ctx: ToolContext, args: AskUserArgs) -> Any:
        ctx.questions_asked.append(args.question)
        return {"reply": ctx.next_user_reply()}
