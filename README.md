# ToolProof

A reproducible benchmark and regression harness that measures how reliably LLM agents choose
tools, fill arguments, recover from errors and respect policies.

[![ci](https://github.com/ManuSasikanthOruvilakode1/ToolProof/actions/workflows/ci.yml/badge.svg)](https://github.com/ManuSasikanthOruvilakode1/ToolProof/actions/workflows/ci.yml)

> **Status:** in development. Project setup (P1) and the sandbox world (P2) are complete; the
> agent loop (P3) is next. No benchmark results yet. See [PLAN.md](PLAN.md) for the design and
> roadmap, and [docs/DESIGN_NOTES.md](docs/DESIGN_NOTES.md) for the sandbox store and its tools.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv installs it if missing).

```bash
git clone <repository-url> ToolProof
cd ToolProof
uv sync
uv run toolproof --help
```

Without uv:

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
python scripts/devlog.py verify     # process-log integrity
uv run pre-commit install           # run the same checks before every commit
```

## Project documents

| File | Purpose |
|---|---|
| [PLAN.md](PLAN.md) | Scope, design, phases and specifications |
| [RULES.md](RULES.md) | Project rules |
| [CHECKPOINT.md](CHECKPOINT.md) | Save and recovery protocol, current save point |
| [PROCESS_LOG.md](PROCESS_LOG.md) | Append-only project history |

## Licence

MIT. See [LICENSE](LICENSE).
