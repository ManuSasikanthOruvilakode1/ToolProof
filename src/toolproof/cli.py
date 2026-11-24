"""Command-line entry point: ``toolproof ...``.

Commands that belong to later phases exist already so the interface is fixed early. Until their
task is done they exit with code 2 and name the task that will implement them.
"""

from __future__ import annotations

import functools
from datetime import datetime
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.table import Table

from toolproof import __version__
from toolproof.agent.llm import DEFAULT_OLLAMA_URL, LLMError, OllamaAdapter
from toolproof.agent.loop import AgentLimits
from toolproof.agent.strategies import STRATEGIES
from toolproof.paths import runs_dir
from toolproof.tracing import format_trace, read_trace, trace_path

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

console = Console()
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


@app.command()
def models(
    base_url: Annotated[str, typer.Option(help="Ollama server URL.")] = DEFAULT_OLLAMA_URL,
) -> None:
    """List local Ollama models and whether they support native tool calling."""
    import httpx

    try:
        tags = httpx.get(f"{base_url}/api/tags", timeout=10).json().get("models", [])
    except httpx.HTTPError as error:
        err_console.print(f"[red]Cannot reach Ollama at {base_url}: {error}[/red]")
        err_console.print("Start the Ollama app (or `ollama serve`) and try again.")
        raise typer.Exit(code=1) from None
    table = Table("model", "size", "parameters", "tool calling", "digest")
    for entry in tags:
        try:
            info = OllamaAdapter(entry["name"], base_url=base_url).describe()
        except LLMError as error:
            err_console.print(f"[yellow]{entry['name']}: {error}[/yellow]")
            continue
        table.add_row(
            entry["name"],
            f"{entry.get('size', 0) / 1e9:.1f} GB",
            str(info.get("parameter_size")),
            "yes" if "tools" in info.get("capabilities", []) else "no",
            str(info.get("digest"))[:12],
        )
    console.print(table)


@app.command()
def pilot(
    model: Annotated[list[str], typer.Option(help="Ollama model; repeat for several.")],
    strategy: Annotated[str, typer.Option(help=f"One of {sorted(STRATEGIES)}.")] = "plain",
    trials: Annotated[int, typer.Option(min=1, help="Trials per task.")] = 1,
    temperature: Annotated[float, typer.Option(min=0.0, max=2.0)] = 0.7,
    max_steps: Annotated[int, typer.Option(min=1)] = 15,
    num_ctx: Annotated[
        int | None, typer.Option(help="Context window; default from configs/models.yaml.")
    ] = None,
    record: Annotated[bool, typer.Option(help="Save cassettes for replay tests.")] = False,
    base_url: Annotated[str, typer.Option(help="Ollama server URL.")] = DEFAULT_OLLAMA_URL,
) -> None:
    """P3.7 pilot: run the pilot requests on each model and summarise speed and reliability."""
    from toolproof.models_config import load_models_config
    from toolproof.pilot import load_pilot_tasks, run_pilot

    defaults = load_models_config().defaults
    options = {"num_ctx": num_ctx or defaults.num_ctx}

    if strategy not in STRATEGIES:
        err_console.print(f"[red]Unknown strategy {strategy!r}[/red]")
        raise typer.Exit(code=1)
    out_dir = runs_dir() / f"pilot_{datetime.now():%Y%m%d-%H%M}"
    summary = run_pilot(
        load_pilot_tasks(),
        {
            name: functools.partial(OllamaAdapter, name, base_url=base_url, extra_options=options)
            for name in model
        },
        out_dir=out_dir,
        strategy_name=strategy,
        trials=trials,
        temperature=temperature,
        limits=AgentLimits(
            max_steps=max_steps,
            max_wall_seconds=defaults.max_wall_seconds,
            max_output_tokens=defaults.max_output_tokens,
        ),
        record=record,
        progress=lambda message: console.print(message, markup=False, highlight=False),
    )
    table = Table("model", "s/trial", "tokens/trial", "with tool calls", "malformed", "sanity")
    for name, stats in summary["models"].items():
        if "error" in stats:
            table.add_row(name, "unavailable", "", "", "", "")
            continue
        table.add_row(
            name,
            str(stats["median_seconds_per_trial"]),
            str(stats["mean_tokens_per_trial"]),
            f"{stats['share_trials_with_tool_calls']:.0%}",
            str(stats["malformed_call_rate"]),
            f"{stats['sanity_pass_rate']:.0%}",
        )
    console.print(table)
    console.print(f"Traces and summary: {out_dir}")


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
    path = trace_path(runs_dir(), run_id, task_id, trial)
    if not path.exists():
        err_console.print(f"[red]No trace at {path}[/red]")
        raise typer.Exit(code=1)
    for line in format_trace(read_trace(path)):
        console.print(line, markup=False, highlight=False)


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
