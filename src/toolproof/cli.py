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
def bench_validate(
    strict_counts: Annotated[
        bool, typer.Option(help="Also require the per-category counts from PLAN.md section 8.2.")
    ] = False,
) -> None:
    """Check every task file: schema, unique IDs, tools, tables, docs and difficulty rules."""
    from collections import Counter

    from toolproof.bench.schema import validate_all

    tasks, problems = validate_all(strict_counts=strict_counts)
    for name, items in sorted(problems.items()):
        for item in items:
            err_console.print(f"[red]{name}[/red]: {item}", markup=True, highlight=False)
    table = Table("category", "dev", "test", "easy", "medium", "hard")
    by_category: dict[str, Counter[str]] = {}
    for task in tasks:
        counter = by_category.setdefault(task.category, Counter())
        counter[task.split] += 1
        counter[task.difficulty] += 1
    for category, counter in sorted(by_category.items()):
        table.add_row(
            category, *(str(counter[key]) for key in ("dev", "test", "easy", "medium", "hard"))
        )
    console.print(table)
    console.print(f"{len(tasks)} tasks, {sum(len(v) for v in problems.values())} problem(s)")
    if problems:
        raise typer.Exit(code=1)


@bench_app.command("oracle")
def bench_oracle(
    task: Annotated[str | None, typer.Option(help="Only this task ID.")] = None,
) -> None:
    """Run each task's reference solution through its checkers. Every task must pass."""
    from toolproof.bench.oracle import run_oracle
    from toolproof.bench.schema import load_tasks
    from toolproof.env.docs_index import load_docs_index
    from toolproof.env.world import ensure_base_db

    tasks = [item for item in load_tasks() if task is None or item.id == task]
    if not tasks:
        err_console.print(f"[red]No task {task!r}[/red]" if task else "[red]No tasks found[/red]")
        raise typer.Exit(code=1)
    base_db, docs = ensure_base_db(), load_docs_index()
    failed = 0
    for item in tasks:
        result = run_oracle(item, base_db=base_db, docs=docs)
        if not result.passed:
            failed += 1
            err_console.print(f"[red]FAIL {item.id}[/red]")
            for problem in result.problems():
                err_console.print(f"    {problem}", markup=False, highlight=False)
    console.print(f"oracle: {len(tasks) - failed}/{len(tasks)} tasks pass")
    if failed:
        raise typer.Exit(code=1)


@bench_app.command("calibrate")
def bench_calibrate(
    model: Annotated[
        list[str], typer.Option(help="Model role (small/medium/large) or name; repeat.")
    ],
    trials: Annotated[int, typer.Option(min=1, help="Trials per task.")] = 1,
    strategy: Annotated[str, typer.Option(help=f"One of {sorted(STRATEGIES)}.")] = "plain",
    task: Annotated[list[str] | None, typer.Option(help="Only these dev task IDs.")] = None,
) -> None:
    """P4.8: run dev tasks on the pilot models; list tasks every model or no model solves."""
    from toolproof.bench.calibrate import run_calibration
    from toolproof.bench.schema import load_tasks
    from toolproof.models_config import load_models_config

    config = load_models_config()
    tasks = [t for t in load_tasks(split="dev") if not task or t.id in task]
    out_dir = runs_dir() / f"calibrate_{datetime.now():%Y%m%d-%H%M}"
    summary = run_calibration(
        tasks,
        {config.resolve(m).name: functools.partial(config.adapter, m) for m in model},
        out_dir=out_dir,
        strategy_name=strategy,
        trials=trials,
        temperature=config.defaults.temperature,
        limits=config.defaults.limits(),
        progress=lambda message: console.print(message, markup=False, highlight=False),
    )
    table = Table("model", "success", "safety-violation trials", "context hits")
    for name, stats in summary["by_model"].items():
        table.add_row(
            name,
            f"{stats['success_rate']:.0%}",
            str(stats["safety_violation_trials"]),
            str(stats["context_limit_hits"]),
        )
    console.print(table)
    console.print(f"solved by every model: {summary['solved_by_every_model']}")
    console.print(f"solved by no model: {summary['solved_by_no_model']}")
    console.print(f"Rows, traces and summary: {out_dir}")


@bench_app.command("try")
def bench_try(
    rater: Annotated[
        str, typer.Option(help="Your rater ID: rater_a, rater_b, ... (never a name).")
    ],
    task: Annotated[
        str | None, typer.Argument(help="Task ID; default: your next validation task.")
    ] = None,
) -> None:
    """P4.7: solve a task yourself with the agent's tools, then judge the checker's verdict."""
    from toolproof.bench.human import (
        RATER_RE,
        agreement_report,
        labels_path,
        record_attempt,
        run_attempt,
        validation_set,
    )
    from toolproof.bench.schema import load_tasks

    if not RATER_RE.match(rater):
        err_console.print("[red]Use a rater ID such as rater_a (no names; RULES 1).[/red]")
        raise typer.Exit(code=1)
    tasks = {t.id: t for t in load_tasks()}
    if task is None:
        done = set()
        if labels_path().exists():
            import csv

            with labels_path().open(newline="", encoding="utf-8") as handle:
                done = {r["task_id"] for r in csv.DictReader(handle) if r["rater"] == rater}
        remaining = [tid for tid in validation_set(list(tasks.values())) if tid not in done]
        if not remaining:
            console.print(f"{rater} has finished all validation tasks.")
            console.print(agreement_report())
            return
        task = remaining[0]
        console.print(f"{len(remaining)} validation task(s) left for {rater}.")
    if task not in tasks:
        err_console.print(f"[red]No task {task!r}[/red]")
        raise typer.Exit(code=1)
    attempt = run_attempt(
        tasks[task], input, lambda text: console.print(text, markup=False, highlight=False)
    )
    if attempt is None:
        console.print("Stopped; nothing recorded.")
        return
    record_attempt(
        attempt, rater, input, lambda text: console.print(text, markup=False, highlight=False)
    )
    console.print(f"Recorded in {labels_path()}")


@bench_app.command("agreement")
def bench_agreement() -> None:
    """P4.7: agreement between raters and the checkers, and tasks flagged for fixing."""
    from toolproof.bench.human import agreement_report

    report = agreement_report()
    console.print_json(data=report)


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
