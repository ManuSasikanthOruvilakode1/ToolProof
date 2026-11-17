"""Tests for scripts/devlog.py, the append-only process-log helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "devlog.py"

LOG_HEADER = "# Test log\n\n# Entries\n"


def load_devlog() -> ModuleType:
    spec = importlib.util.spec_from_file_location("devlog", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["devlog"] = module
    spec.loader.exec_module(module)
    return module


devlog = load_devlog()


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    path = tmp_path / "PROCESS_LOG.md"
    path.write_text(LOG_HEADER, encoding="utf-8", newline="\n")
    assert devlog.main(["--log", str(path), "seal"]) == 0
    return path


def add(log_path: Path, *extra: str) -> int:
    return int(devlog.main(["--log", str(log_path), "add", *extra]))


def test_add_assigns_consecutive_ids(log_path: Path) -> None:
    assert add(log_path, "--type", "NOTE", "--summary", "first") == 0
    assert add(log_path, "--type", "NOTE", "--summary", "second", "--task", "P1.1") == 0
    entries = devlog.parse_entries(log_path.read_text(encoding="utf-8"))
    assert [e.log_id for e in entries] == ["LOG-0001", "LOG-0002"]
    assert entries[1].task == "P1.1"
    assert entries[1].summary == "second"
    assert devlog.main(["--log", str(log_path), "verify"]) == 0


def test_verify_detects_edit_of_sealed_content(log_path: Path) -> None:
    add(log_path, "--type", "NOTE", "--summary", "original wording")
    text = log_path.read_text(encoding="utf-8")
    log_path.write_text(text.replace("original", "edited"), encoding="utf-8", newline="\n")
    assert devlog.main(["--log", str(log_path), "verify"]) == 1
    assert devlog.main(["--log", str(log_path), "seal"]) == 1  # seal refuses to accept edits


def test_verify_detects_deletion(log_path: Path) -> None:
    add(log_path, "--type", "NOTE", "--summary", "will be removed")
    log_path.write_text(LOG_HEADER, encoding="utf-8", newline="\n")
    assert devlog.main(["--log", str(log_path), "verify"]) == 1


def test_manual_append_passes_verify_and_can_be_sealed(log_path: Path) -> None:
    with open(log_path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            "\n---\n\n### LOG-0001 | 2026-01-01 00:00 +00:00 | NOTE | -\n\n**Summary:** x\n"
        )
    assert devlog.main(["--log", str(log_path), "verify"]) == 0
    assert devlog.main(["--log", str(log_path), "seal"]) == 0


def test_crlf_checkout_still_verifies(log_path: Path) -> None:
    add(log_path, "--type", "NOTE", "--summary", "line endings")
    raw = log_path.read_bytes()
    log_path.write_bytes(raw.replace(b"\n", b"\r\n"))
    assert devlog.main(["--log", str(log_path), "verify"]) == 0


def test_resolved_needs_existing_ref(log_path: Path) -> None:
    assert add(log_path, "--type", "RESOLVED", "--summary", "no ref") == 2
    assert add(log_path, "--type", "RESOLVED", "--summary", "bad", "--ref", "LOG-0099") == 2


def test_issues_closed_by_resolved(log_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    add(log_path, "--type", "ISSUE", "--summary", "something broke")
    add(log_path, "--type", "RESOLVED", "--summary", "fixed it", "--ref", "LOG-0001")
    capsys.readouterr()
    devlog.main(["--log", str(log_path), "issues"])
    assert "No open issues." in capsys.readouterr().out
