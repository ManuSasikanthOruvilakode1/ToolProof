# ToolProof: Process Log

The permanent record of the project: edits, completed tasks, decisions, findings, issues,
experiments, checkpoints and recoveries.

## Rules for this file

1. **Append-only.** New entries go at the **bottom**. Nothing that is already written is ever edited, reordered or deleted, including typos.
2. **Corrections** are new `CORRECTION` entries that reference the wrong entry (`Refs: LOG-NNNN`).
3. **Issues** stay open until a `RESOLVED` entry references them. `python scripts/devlog.py issues` lists the open ones.
4. **IDs** are consecutive (`LOG-0001`, `LOG-0002`, …) and never reused.
5. **Integrity** is checked by `python scripts/devlog.py verify` against `.process_log.seal`. It runs in pre-commit, in CI and at the start of every recovery.
6. **No PII** (RULES.md section A).

## How to add an entry

Preferred, using the helper. It assigns the ID and timestamp, appends the entry and re-seals the log:

```bash
python scripts/devlog.py add --type DONE --task P2.4 \
  --summary "Added read-only sql_query tool with row cap and time limit" \
  --files src/toolproof/env/tools/sql_query.py tests/unit/test_sql_query.py \
  --details "PRAGMA query_only=ON; one statement per call; 50-row cap; 2 s limit" \
  --findings "SQLite progress handler is the simplest way to enforce the time limit" \
  --next "P2.5 calculator and date tools"
```

Other commands: `tail -n 5`, `tail --type ISSUE`, `issues`, `verify`, `seal` (after a manual append).

## Entry format (for manual appends)

```markdown
---

### LOG-NNNN | YYYY-MM-DD HH:MM +HH:MM | TYPE | TASK-ID

**Summary:** One line saying what happened.

- **Refs:** LOG-NNNN (related entries; required for RESOLVED and CORRECTION)
- **Files:** `path/one`, `path/two`
- **Details:** what was done and how
- **Findings:** what was learned
- **Issues:** problems found (also log each as its own ISSUE entry)
- **Next:** the next concrete step
```

Only the heading and **Summary** are required. Use `-` as the task ID when no task applies.

**Types:** `DECISION` · `EDIT` · `DONE` · `FINDING` · `ISSUE` · `RESOLVED` · `EXPERIMENT` ·
`CHECKPOINT` · `RECOVERY` · `CORRECTION` · `NOTE`

# Entries (oldest first; append new entries at the bottom)

---

### LOG-0001 | 2026-11-17 16:43 +11:00 | FINDING | P0.1

**Summary:** Reviewed the existing portfolio and identified the gaps a new project should fill.

- **Details:**
  - Six existing projects: RegLens (regulatory NLP fine-tuning), MoodTune (facial-emotion music recommender), Enterprise Default Radar (credit-risk tabular ML), GymWatch (real-time computer vision), Taxiflow (fare prediction under pricing drift, conformal intervals) and CiteSure (RAG with faithfulness evaluation).
  - Shared strengths: held-out evaluation, confidence intervals, honest limitations, reproducible pipelines, small deployed apps.
- **Findings:**
  - Not yet covered: LLM agents and tool use, causal inference and A/B testing, classic time-series forecasting, speech and audio, graph ML and streaming anomaly detection, large-scale recommender systems.
  - CiteSure evaluates retrieval but not actions, so an agent-evaluation project extends existing work instead of repeating it.

---

### LOG-0002 | 2026-11-17 16:43 +11:00 | DECISION | P0.2

**Summary:** Selected the LLM agent tool-use evaluation project from six candidates.

- **Details:**
  - Candidates: causal uplift and A/B toolkit; LLM agent tool-use evaluation; probabilistic energy demand forecasting; speech transcription with diarization; graph-ML fraud detection; production-style recommender.
  - Chosen: LLM agent tool-use evaluation.
- **Findings:** Strong fit with current hiring demand and builds on the evaluation discipline from CiteSure.

---

### LOG-0003 | 2026-11-17 16:43 +11:00 | DECISION | P0.3

**Summary:** Named the project ToolProof and fixed the core scope.

- **Details:**
  - Name: ToolProof. Alternatives considered: AgentAudit, ToolTrace, Callcheck.
  - Research question: how much do model, prompting strategy and tool design each affect agent reliability, and how do agents fail?
  - Local models through Ollama (3–4 sizes), optional single API model as a reference point.
  - Fully offline, deterministic sandbox (a small online store): 8 core tools plus 15 distractor tools.
  - 150 tasks: 50 dev, 100 test (locked); k = 3 trials on dev, k = 5 on test.
  - Agent loop written from scratch; rule-based primary scoring only.
  - Out of scope for v0.1: multi-agent systems, fine-tuning, web browsing, real email or payments.

---

### LOG-0004 | 2026-11-17 16:43 +11:00 | EDIT | P0.4

**Summary:** Created the project documents and the append-only log helper.

- **Files:** `PLAN.md`, `RULES.md`, `CHECKPOINT.md`, `PROCESS_LOG.md`, `scripts/devlog.py`, `.process_log.seal`
- **Details:**
  - PLAN.md: goals, definition of done, architecture, repository layout, phases P0–P9 with task IDs, benchmark specification, metric definitions, statistical methods, experiment matrix and compute budget, run-level resume design, failure taxonomy, risks, timeline.
  - RULES.md: the standard portfolio rules plus evaluation integrity, sandbox safety, benchmark authoring, process log, checkpoint and git rules (47 rules).
  - CHECKPOINT.md: save procedure, light and full recovery mode, conflict table, rollback, and the current save point.
  - devlog.py: `add`, `tail`, `issues`, `verify`, `seal`. Integrity check uses a SHA-256 seal of the normalised log prefix.
- **Next:** P1.1 git init, `.gitignore`, `.gitattributes`.

---

### LOG-0005 | 2026-11-17 16:43 +11:00 | FINDING | P0.4

**Summary:** Checked the local environment before setup.

- **Details:**
  - System Python 3.14.6, uv 0.12.0, git 2.55.0, Ollama client 0.35.1.
  - The Ollama server was not running at the time of the check, and `ollama list` hung without it, so the installed models are unknown.
- **Findings:**
  - Earlier projects pin Python below 3.13 for library compatibility, so ToolProof will pin 3.12 with `.python-version` instead of using the system 3.14.
  - The earlier projects' RULES.md asks for `requirements.txt`, but they actually use uv; ToolProof's rule 7 asks for `uv.lock` plus an exported `requirements.txt`.

---

### LOG-0006 | 2026-11-17 16:43 +11:00 | ISSUE | P1.1

**Summary:** Name availability for "ToolProof" on GitHub and PyPI has not been checked.

- **Next:** Search GitHub and PyPI before the first push; if taken, pick an alternative and log a DECISION.

---

### LOG-0007 | 2026-11-17 16:43 +11:00 | ISSUE | P1.4

**Summary:** Licence not chosen yet (MIT as in most projects, or Apache-2.0 as in RegLens).

- **Next:** Decide in P1.4.

---

### LOG-0008 | 2026-11-17 16:43 +11:00 | ISSUE | P3.7

**Summary:** Final model list and default temperature are not chosen; they depend on which models support native tool calling in the installed Ollama version.

- **Next:** Start the Ollama server, list installed models, and run the P3.7 pilot.

---

### LOG-0009 | 2026-11-17 16:43 +11:00 | ISSUE | P7.3

**Summary:** Unverified whether a GitHub-hosted runner can run a small local model for the live smoke test within memory and time limits.

- **Next:** Test in P7.3; if not feasible, CI relies on replay tests only and the live smoke test runs locally.

---

### LOG-0010 | 2026-11-17 16:43 +11:00 | CHECKPOINT | P0

**Summary:** CP-0001 saved: planning complete, no code yet, next step P1.1.

- **Refs:** LOG-0004, LOG-0006, LOG-0007, LOG-0008, LOG-0009
- **Details:** No git repository yet, so this checkpoint has no commit or tag. CP-0002 (end of P1) will be the first tagged checkpoint.
- **Next:** P1.1 git init, `.gitignore`, `.gitattributes`.

---

### LOG-0011 | 2026-11-17 16:55 +11:00 | FINDING | P1.1

**Summary:** Name check: 'toolproof' is free on PyPI; GitHub has about 11 unrelated repositories with the same name

- **Details:**
  - PyPI JSON API returned 404 for toolproof on 2026-11-17
  - GitHub repository search found 11 repos named like toolproof, the largest with 11 stars (a static-site testing tool); none is an LLM agent benchmark
- **Findings:** Repository names are unique per account, so the name is usable; README should describe the project clearly to avoid confusion with the existing tool

---

### LOG-0012 | 2026-11-17 16:55 +11:00 | RESOLVED | P1.1

**Summary:** Keeping the name ToolProof: free on PyPI, GitHub collisions are unrelated projects

- **Refs:** LOG-0006, LOG-0011

---

### LOG-0013 | 2026-11-17 16:55 +11:00 | DECISION | P1.4

**Summary:** Licence: MIT, matching most of the portfolio

- **Files:** `LICENSE`, `pyproject.toml`
- **Details:** Copyright holder written as 'ToolProof contributors' so no personal name appears in the repository (RULES 1)

---

### LOG-0014 | 2026-11-17 16:55 +11:00 | RESOLVED | P1.4

**Summary:** Licence chosen (MIT) and LICENSE added

- **Refs:** LOG-0007, LOG-0013

---

### LOG-0015 | 2026-11-17 16:55 +11:00 | DONE | P1.1

**Summary:** Initialised git repository on branch main with .gitignore and .gitattributes

- **Files:** `.gitignore`, `.gitattributes`
- **Details:**
  - .gitignore covers .venv, __pycache__, .env, results/runs/, tool caches, the generated world SQLite file and model files
  - .gitattributes forces LF for md, sh, py, yaml, toml, jsonl, lock and the log seal; png, gif and sqlite are binary

---

### LOG-0016 | 2026-11-17 16:55 +11:00 | DONE | P1.2

**Summary:** Package set up with uv, hatchling, src/ layout and Python 3.12

- **Files:** `pyproject.toml`, `.python-version`, `uv.lock`, `requirements.txt`, `src/toolproof/__init__.py`, `src/toolproof/py.typed`, `README.md`
- **Details:**
  - Runtime deps: httpx, pydantic, pyyaml, rich, typer. Dev group: mypy, pre-commit, pytest, pytest-cov, ruff, types-pyyaml
  - requires-python >=3.12,<3.13; uv sync used cpython 3.12.13
  - requirements.txt exported with 'uv export --no-hashes --no-dev --no-emit-project' (runtime deps only; README says to pip install -e . afterwards)

---

### LOG-0017 | 2026-11-17 16:55 +11:00 | DONE | P1.3

**Summary:** Configured ruff, mypy strict and pre-commit hooks

- **Files:** `pyproject.toml`, `.pre-commit-config.yaml`
- **Details:**
  - ruff: line length 100, rules E W F I B UP SIM S RUF; the S (bandit) set flags eval/exec, supporting RULES 20
  - mypy: strict on src/; pytest markers 'replay' and 'live' registered with --strict-markers
  - pre-commit: local hooks for ruff, ruff-format, mypy and devlog.py verify (all run through uv)

---

### LOG-0018 | 2026-11-17 16:55 +11:00 | DONE | P1.5

**Summary:** Added GitHub Actions CI: uv sync --locked, devlog verify, ruff, ruff format check, mypy, pytest

- **Files:** `.github/workflows/ci.yml`
- **Issues:** Not run yet: no remote exists, so 'CI is green' from the P1 done-condition is unverified until the first push

---

### LOG-0019 | 2026-11-17 16:55 +11:00 | DONE | P1.6

**Summary:** CLI skeleton: toolproof --help lists run, report, compare, bench, trace, runs

- **Files:** `src/toolproof/cli.py`, `tests/unit/test_cli.py`, `tests/unit/test_devlog.py`
- **Details:**
  - Unimplemented commands exit with code 2 and name the task that will implement them (e.g. 'bench oracle' -> P4.3)
  - tests/unit/test_devlog.py covers append IDs, edit and deletion detection, manual append + seal, CRLF checkouts, RESOLVED ref checks and open-issue listing
- **Findings:** Local gates: ruff clean, ruff format clean, mypy strict clean (2 files), pytest 16 passed

---

### LOG-0020 | 2026-11-17 16:55 +11:00 | ISSUE | P1.5

**Summary:** CI workflow has not run yet because the repository has no remote; the P1 done-condition 'CI is green' is unverified

- **Refs:** LOG-0018
- **Next:** Create the GitHub repository, push main, and confirm the ci workflow passes

---

### LOG-0021 | 2026-11-17 16:55 +11:00 | DONE | P1.7

**Summary:** First commit c679cc2 on main; checkpoint CP-0002 saved and tagged

- **Files:** `CHECKPOINT.md`, `PLAN.md`

---

### LOG-0022 | 2026-11-17 16:55 +11:00 | CHECKPOINT | P1

**Summary:** CP-0002 saved: P1 project setup complete locally; next P2.1 sandbox data generator

- **Refs:** LOG-0015, LOG-0016, LOG-0017, LOG-0018, LOG-0019, LOG-0020, LOG-0021
- **Details:**
  - Tests: pytest 16 passed; ruff, ruff format, mypy strict and devlog verify clean; pre-commit all hooks passed
  - Open issues: LOG-0008, LOG-0009, LOG-0020
- **Next:** P2.1 write scripts/build_sandbox.py (seed 42) generating data/seed/*.csv
