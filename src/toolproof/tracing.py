"""Per-trial traces: one JSON line per event (P3.6).

Events: ``llm_request``, ``llm_response``, ``tool_call``, ``tool_result``, ``tool_error`` and
``final``. Each line holds the run ID, task ID, trial, step, timestamp, event, payload, tokens
and latency. ``ts`` is the only field that differs when a recorded trial is replayed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

EVENT_KINDS = ("llm_request", "llm_response", "tool_call", "tool_result", "tool_error", "final")
VOLATILE_FIELDS = ("ts",)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def trace_path(runs_directory: Path, run_id: str, task_id: str, trial: int) -> Path:
    return runs_directory / run_id / "traces" / f"{task_id}__t{trial}.jsonl"


class Tracer(Protocol):
    def event(
        self,
        kind: str,
        step: int,
        payload: dict[str, Any],
        *,
        tokens: dict[str, int] | None = None,
        latency: float | None = None,
    ) -> None: ...


class NullTracer:
    def event(
        self,
        kind: str,
        step: int,
        payload: dict[str, Any],
        *,
        tokens: dict[str, int] | None = None,
        latency: float | None = None,
    ) -> None:
        return None


class MemoryTracer:
    """Keeps events in a list (tests, pilot summaries)."""

    def __init__(
        self,
        run_id: str = "-",
        task_id: str = "-",
        trial: int = 0,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.run_id = run_id
        self.task_id = task_id
        self.trial = trial
        self.clock = clock
        self.events: list[dict[str, Any]] = []

    def event(
        self,
        kind: str,
        step: int,
        payload: dict[str, Any],
        *,
        tokens: dict[str, int] | None = None,
        latency: float | None = None,
    ) -> None:
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown trace event {kind!r}")
        record = {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "trial": self.trial,
            "step": step,
            "ts": self.clock(),
            "event": kind,
            "payload": json.loads(json.dumps(payload, default=str)),
            "tokens": tokens,
            "latency": latency,
        }
        self.events.append(record)
        self._write(record)

    def _write(self, record: dict[str, Any]) -> None:
        return None


class JsonlTracer(MemoryTracer):
    """Appends each event to ``path`` as it happens, so a crash leaves a partial trace."""

    def __init__(
        self,
        path: Path,
        run_id: str,
        task_id: str,
        trial: int,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        super().__init__(run_id, task_id, trial, clock)
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def _write(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_trace(path: Path) -> list[dict[str, Any]]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def comparable(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Events without fields that legitimately differ between a recording and its replay."""
    return [{k: v for k, v in event.items() if k not in VOLATILE_FIELDS} for event in events]


def _short(value: Any, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_trace(events: list[dict[str, Any]]) -> list[str]:
    """Human-readable timeline, one or two lines per event."""
    lines: list[str] = []
    for event in events:
        step = f"[{event['step']:>2}]"
        payload = event["payload"]
        kind = event["event"]
        if kind == "llm_request":
            for message in payload.get("new_messages", []):
                if message["role"] in ("system", "user"):
                    lines.append(
                        f"{step} {message['role'].upper():<9} {_short(message['content'])}"
                    )
            lines.append(f"{step} -> model ({payload.get('tools_offered', 0)} tools offered)")
        elif kind == "llm_response":
            tokens = event.get("tokens") or {}
            latency = event.get("latency") or 0.0
            meta = f"{tokens.get('input', 0)}+{tokens.get('output', 0)} tok, {latency:.2f}s"
            if payload.get("text"):
                lines.append(f"{step} ASSISTANT {_short(payload['text'])}  ({meta})")
            else:
                lines.append(f"{step} ASSISTANT (no text)  ({meta})")
        elif kind == "tool_call":
            flag = f"  !! {payload['parse_error']}" if payload.get("parse_error") else ""
            lines.append(
                f"{step} CALL      {payload['name']}({_short(payload['arguments'])}){flag}"
            )
        elif kind == "tool_result":
            lines.append(f"{step} RESULT    {_short(payload.get('result'))}")
        elif kind == "tool_error":
            injected = "  [injected]" if payload.get("injected") else ""
            message = payload.get("error_message") or payload.get("message")
            error_type = payload.get("error_type")
            lines.append(f"{step} ERROR     {error_type}: {_short(message)}{injected}")
        elif kind == "final":
            lines.append(
                f"{step} END       {payload['termination']}: {_short(payload.get('answer') or '')}"
            )
    return lines
