"""Command-line entry point: ``toolproof ...``.

Commands that belong to later phases exist already so the interface is fixed early. Until their
task is done they exit with code 2 and name the task that will implement them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console

from toolproof import __version__

app = typer.Typer(
    name="toolproof",
    help="Benchmark and regression harness for LLM agent tool use.",
    no_args_is_help=True,
    add_completion=False,
)
bench_app = typer.Typer(help="Validate tasks and run oracle checks.", no_args_is_help=True)
trace_app = typer.Typer(help="Inspect per-trial traces.", no_args_is_help=True)
runs_app = typer.Typer(help="List and manage experiment runs.", no_args_is_help=True)
app.add_typer(bench_app, name="bench")
app.add_typer(trace_app, name="trace")
app.add_typer(runs_app, name="runs")

err_console = Console(stderr=True)

NOT_IMPLEMENTED_EXIT_CODE = 2


def not_implemented(command: str, task_id: str) -> NoReturn:
    """Exit with a clear message for commands whose task is not done yet."""
    err_console.print(f"[yellow]`toolproof {command}` is not implemented yet ({task_id}).[/yellow]")
    raise typer.Exit(code=NOT_IMPLEMENTED_EXIT_CODE)


def version_callback(show: bool) -> None:
    if show:
        typer.echo(f"toolproof {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Benchmark and regression harness for LLM agent tool use."""


# ------------------------------------------------------------------ top-level commands


@app.command()
def run(
    config: Annotated[
        Path | None, typer.Argument(help="Experiment config (configs/experiments/*.yaml).")
    ] = None,
    resume: Annotated[str | None, typer.Option(help="Resume an interrupted run by ID.")] = None,
    confirm_test_run: Annotated[
        bool, typer.Option("--confirm-test-run", help="Required for test-split runs.")
    ] = False,
) -> None:
    """Run an experiment config, or resume an interrupted run."""
    not_implemented("run", "P3/P6")


@app.command()
def report(run_id: Annotated[str, typer.Argument(help="Run ID to report on.")]) -> None:
    """Write Markdown tables and charts for a finished run."""
    not_implemented("report", "P5.6")


@app.command()
def compare(
    run_a: Annotated[str, typer.Argument(help="Baseline run ID.")],
    run_b: Annotated[str, typer.Argument(help="Comparison run ID.")],
) -> None:
    """Paired comparison of two runs on the same tasks."""
    not_implemented("compare", "P5.7")


# ------------------------------------------------------------------ bench


@bench_app.command("validate")
def bench_validate() -> None:
    """Check every task file against the schema."""
    not_implemented("bench validate", "P4.1")


@bench_app.command("oracle")
def bench_oracle(
    task: Annotated[str | None, typer.Option(help="Only this task ID.")] = None,
) -> None:
    """Run each task's reference solution through its checkers."""
    not_implemented("bench oracle", "P4.3")


# ------------------------------------------------------------------ trace


@trace_app.command("show")
def trace_show(
    run_id: Annotated[str, typer.Argument(help="Run ID.")],
    task_id: Annotated[str, typer.Argument(help="Task ID.")],
    trial: Annotated[int, typer.Argument(help="Trial index.")],
) -> None:
    """Pretty-print one trial's trace."""
    not_implemented("trace show", "P3.6")


# ------------------------------------------------------------------ runs


@runs_app.command("list")
def runs_list(
    status: Annotated[
        str | None, typer.Option(help="Filter by status: running, completed or aborted.")
    ] = None,
) -> None:
    """List runs, optionally filtered by status."""
    not_implemented("runs list", "P3/P6")


if __name__ == "__main__":  # pragma: no cover
    app()
