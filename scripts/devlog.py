#!/usr/bin/env python3
"""Append-only helper for PROCESS_LOG.md.

The process log is a permanent record. This script only ever appends to it and
checks that nothing already written has been changed.

Commands
--------
add      Append a new entry with the next LOG ID and a timestamp, then re-seal.
tail     Print the last N entries (default 5).
issues   List ISSUE entries that no RESOLVED entry references yet.
verify   Check that the log content up to the last seal is unchanged.
seal     Record the current log as trusted (first-time setup, or after a manual
         append). Refuses if content that was already sealed has been changed.

How the seal works
------------------
`.process_log.seal` stores the length and SHA-256 of the log (with line endings
normalised to LF) at the last trusted point. `verify` re-hashes that many bytes
of the current log. Appending keeps the prefix identical, so it passes; editing
or deleting anything that was already sealed changes the prefix, so it fails.

Examples
--------
python scripts/devlog.py add --type DONE --task P1.1 \
    --summary "Initialised git repository" --files .gitignore .gitattributes \
    --next "P1.2 uv init"
python scripts/devlog.py add --type ISSUE --task P3.7 --summary "Model X has no tool calling"
python scripts/devlog.py add --type RESOLVED --ref LOG-0012 --summary "Replaced model X with Y"
python scripts/devlog.py tail -n 3
python scripts/devlog.py issues
python scripts/devlog.py verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG = PROJECT_ROOT / "PROCESS_LOG.md"
SEAL_NAME = ".process_log.seal"

ENTRY_TYPES = (
    "DECISION",
    "EDIT",
    "DONE",
    "FINDING",
    "ISSUE",
    "RESOLVED",
    "EXPERIMENT",
    "CHECKPOINT",
    "RECOVERY",
    "CORRECTION",
    "NOTE",
)
TYPES_NEEDING_REF = {"RESOLVED", "CORRECTION"}

HEADING_RE = re.compile(r"^### (LOG-(\d{4,})) \| ([^|]+?) \| ([A-Z]+) \| (.+?)\s*$", re.MULTILINE)
REFS_RE = re.compile(r"^- \*\*Refs:\*\* (.+)$", re.MULTILINE)
SUMMARY_RE = re.compile(r"^\*\*Summary:\*\* (.+)$", re.MULTILINE)
LOG_ID_RE = re.compile(r"LOG-\d{4,}")


class LogIntegrityError(Exception):
    """Raised when sealed log content has been modified or removed."""


@dataclass
class Entry:
    log_id: str
    number: int
    timestamp: str
    entry_type: str
    task: str
    text: str
    refs: list[str] = field(default_factory=list)
    summary: str = ""


# --------------------------------------------------------------------------- io


def read_normalised(log_path: Path) -> bytes:
    """Return the log as bytes with CRLF/CR line endings normalised to LF."""
    raw = log_path.read_bytes()
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def seal_path_for(log_path: Path) -> Path:
    return log_path.parent / SEAL_NAME


def load_seal(log_path: Path) -> dict[str, object] | None:
    path = seal_path_for(log_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_seal(log_path: Path, content: bytes) -> dict[str, object]:
    entries = parse_entries(content.decode("utf-8"))
    seal = {
        "file": log_path.name,
        "length": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "last_entry": entries[-1].log_id if entries else None,
        "sealed_at": now_stamp(),
    }
    target = seal_path_for(log_path)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(seal, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, target)
    return seal


def now_stamp() -> str:
    now = datetime.now().astimezone()
    offset = now.strftime("%z")  # e.g. +1100
    return f"{now:%Y-%m-%d %H:%M} {offset[:3]}:{offset[3:]}"


# ---------------------------------------------------------------------- parsing


def parse_entries(text: str) -> list[Entry]:
    text = text.replace("\r\n", "\n")
    matches = list(HEADING_RE.finditer(text))
    entries: list[Entry] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.start() : end].rstrip()
        if body.endswith("---"):
            body = body[: -len("---")].rstrip()
        refs_match = REFS_RE.search(body)
        summary_match = SUMMARY_RE.search(body)
        entries.append(
            Entry(
                log_id=match.group(1),
                number=int(match.group(2)),
                timestamp=match.group(3).strip(),
                entry_type=match.group(4),
                task=match.group(5).strip(),
                text=body,
                refs=LOG_ID_RE.findall(refs_match.group(1)) if refs_match else [],
                summary=summary_match.group(1).strip() if summary_match else "",
            )
        )
    return entries


# -------------------------------------------------------------------- integrity


def check_integrity(log_path: Path) -> tuple[bytes, dict[str, object] | None, int]:
    """Verify the sealed prefix. Returns (content, seal, bytes appended since seal)."""
    content = read_normalised(log_path)
    seal = load_seal(log_path)
    if seal is None:
        return content, None, len(content)
    sealed_length = int(seal["length"])  # type: ignore[arg-type]
    if len(content) < sealed_length:
        raise LogIntegrityError(
            f"The log is shorter than when it was sealed ({len(content)} < {sealed_length} bytes): "
            "sealed content was deleted."
        )
    prefix_hash = hashlib.sha256(content[:sealed_length]).hexdigest()
    if prefix_hash != seal["sha256"]:
        raise LogIntegrityError(
            "Sealed content of the log was modified (hash mismatch on the first "
            f"{sealed_length} bytes; last sealed entry {seal.get('last_entry')})."
        )
    return content, seal, len(content) - sealed_length


def integrity_help() -> str:
    return (
        "Existing entries must never be edited. To recover:\n"
        "  1. Save a copy of any NEW entries you added after the last seal.\n"
        "  2. Restore the log from git:   git checkout HEAD -- PROCESS_LOG.md\n"
        "     (or `git log -p -- PROCESS_LOG.md` to find the last good version).\n"
        "  3. Re-append the new entries, then run:  python scripts/devlog.py seal\n"
        "  4. Record what happened with a RECOVERY entry.\n"
        "See CHECKPOINT.md, recovery step R3."
    )


# --------------------------------------------------------------------- commands


def format_field(label: str, values: list[str] | None) -> str:
    if not values:
        return ""
    cleaned = [value.strip() for value in values if value.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return f"- **{label}:** {cleaned[0]}\n"
    items = "".join(f"  - {value}\n" for value in cleaned)
    return f"- **{label}:**\n{items}"


def build_entry(args: argparse.Namespace, log_id: str) -> str:
    task = args.task or "-"
    lines = [f"### {log_id} | {now_stamp()} | {args.type} | {task}\n", "\n"]
    lines.append(f"**Summary:** {args.summary.strip()}\n")
    fields = (
        format_field("Refs", [", ".join(args.ref)] if args.ref else None)
        + format_field("Files", [", ".join(f"`{f}`" for f in args.files)] if args.files else None)
        + format_field("Details", args.details)
        + format_field("Findings", args.findings)
        + format_field("Issues", args.issues)
        + format_field("Next", args.next)
    )
    if fields:
        lines.append("\n")
        lines.append(fields)
    return "".join(lines)


def cmd_add(args: argparse.Namespace) -> int:
    log_path: Path = args.log
    if args.type in TYPES_NEEDING_REF and not args.ref:
        print(f"error: {args.type} entries need --ref LOG-NNNN", file=sys.stderr)
        return 2
    for ref in args.ref or []:
        if not LOG_ID_RE.fullmatch(ref):
            print(f"error: --ref must look like LOG-0001, got {ref!r}", file=sys.stderr)
            return 2

    content, seal, _ = check_integrity(log_path)
    if seal is None:
        print(
            "error: the log has no seal yet. Review it, then run `python scripts/devlog.py seal`.",
            file=sys.stderr,
        )
        return 2

    text = content.decode("utf-8")
    entries = parse_entries(text)
    known_ids = {entry.log_id for entry in entries}
    for ref in args.ref or []:
        if ref not in known_ids:
            print(f"error: --ref {ref} does not exist in the log", file=sys.stderr)
            return 2

    next_number = max((entry.number for entry in entries), default=0) + 1
    log_id = f"LOG-{next_number:04d}"
    entry_text = build_entry(args, log_id)

    separator = "" if text.endswith("\n") else "\n"
    block = f"{separator}\n---\n\n{entry_text}"

    if args.dry_run:
        print(block)
        return 0

    with open(log_path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(block)
        handle.flush()
        os.fsync(handle.fileno())

    new_content, _, _ = check_integrity(log_path)  # confirm the append kept the prefix intact
    write_seal(log_path, new_content)
    print(f"Appended {log_id} ({args.type}) and re-sealed the log.")
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    entries = parse_entries(args.log.read_text(encoding="utf-8"))
    if args.type:
        entries = [entry for entry in entries if entry.entry_type == args.type]
    for entry in entries[-args.n :]:
        print(entry.text)
        print("\n---\n")
    if not entries:
        print("(no entries)")
    return 0


def cmd_issues(args: argparse.Namespace) -> int:
    entries = parse_entries(args.log.read_text(encoding="utf-8"))
    resolved = {ref for entry in entries if entry.entry_type == "RESOLVED" for ref in entry.refs}
    open_issues = [e for e in entries if e.entry_type == "ISSUE" and e.log_id not in resolved]
    if not open_issues:
        print("No open issues.")
        return 0
    print(f"{len(open_issues)} open issue(s):")
    for entry in open_issues:
        print(f"  {entry.log_id}  [{entry.task}]  {entry.summary}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        content, seal, appended = check_integrity(args.log)
    except LogIntegrityError as error:
        print(f"FAIL: {error}\n\n{integrity_help()}", file=sys.stderr)
        return 1
    if seal is None:
        print("FAIL: no seal file found. Review the log, then run `python scripts/devlog.py seal`.")
        return 1
    entries = parse_entries(content.decode("utf-8"))
    numbers = [entry.number for entry in entries]
    if numbers != list(range(1, len(numbers) + 1)):
        print(f"FAIL: entry IDs are not consecutive from LOG-0001: {numbers}", file=sys.stderr)
        return 1
    message = (
        f"OK: {len(entries)} entries; sealed content intact (last sealed {seal['last_entry']})."
    )
    if appended:
        message += f" {appended} byte(s) appended since the seal; run `seal` to accept them."
    print(message)
    return 0


def cmd_seal(args: argparse.Namespace) -> int:
    try:
        content, seal, appended = check_integrity(args.log)
    except LogIntegrityError as error:
        print(f"REFUSED: {error}\n\n{integrity_help()}", file=sys.stderr)
        return 1
    if seal is not None and appended == 0:
        print("Nothing new to seal.")
        return 0
    new_seal = write_seal(args.log, content)
    action = "Created" if seal is None else "Updated"
    print(f"{action} seal: {new_seal['length']} bytes, last entry {new_seal['last_entry']}.")
    return 0


# -------------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append-only helper for PROCESS_LOG.md")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="path to the log file")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="append a new entry")
    add.add_argument("--type", required=True, choices=ENTRY_TYPES)
    add.add_argument("--summary", required=True, help="one-line summary")
    add.add_argument("--task", help="task ID such as P2.4 (default '-')")
    add.add_argument("--ref", nargs="+", help="related entry IDs, e.g. LOG-0007")
    add.add_argument("--files", nargs="+", help="files changed")
    add.add_argument("--details", action="append", help="detail line (repeatable)")
    add.add_argument("--findings", action="append", help="finding line (repeatable)")
    add.add_argument("--issues", action="append", help="issue line (repeatable)")
    add.add_argument("--next", action="append", help="next step (repeatable)")
    add.add_argument("--dry-run", action="store_true", help="print the entry without writing it")
    add.set_defaults(func=cmd_add)

    tail = sub.add_parser("tail", help="print the last N entries")
    tail.add_argument("-n", type=int, default=5)
    tail.add_argument("--type", choices=ENTRY_TYPES, help="only entries of this type")
    tail.set_defaults(func=cmd_tail)

    issues = sub.add_parser("issues", help="list open issues")
    issues.set_defaults(func=cmd_issues)

    verify = sub.add_parser("verify", help="check that sealed entries are unchanged")
    verify.set_defaults(func=cmd_verify)

    seal = sub.add_parser("seal", help="accept manually appended entries")
    seal.set_defaults(func=cmd_seal)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except LogIntegrityError as error:
        print(f"REFUSED: {error}\n\n{integrity_help()}", file=sys.stderr)
        return 1
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
