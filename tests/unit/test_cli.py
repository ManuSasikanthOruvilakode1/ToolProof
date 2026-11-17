from __future__ import annotations

import pytest
from typer.testing import CliRunner

from toolproof import __version__
from toolproof.cli import NOT_IMPLEMENTED_EXIT_CODE, app

runner = CliRunner()

EXPECTED_COMMANDS = ("run", "report", "compare", "bench", "trace", "runs")


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in EXPECTED_COMMANDS:
        assert command in result.output


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


@pytest.mark.parametrize(
    ("args", "task_id"),
    [
        (["run"], "P3/P6"),
        (["report", "some-run"], "P5.6"),
        (["compare", "a", "b"], "P5.7"),
        (["bench", "validate"], "P4.1"),
        (["bench", "oracle"], "P4.3"),
        (["trace", "show", "run", "task", "1"], "P3.6"),
        (["runs", "list"], "P3/P6"),
    ],
)
def test_stub_commands_name_their_task(args: list[str], task_id: str) -> None:
    result = runner.invoke(app, args)
    assert result.exit_code == NOT_IMPLEMENTED_EXIT_CODE
    assert task_id in result.output
