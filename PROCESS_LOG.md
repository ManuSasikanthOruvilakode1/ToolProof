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

---

### LOG-0023 | 2026-11-17 18:46 +11:00 | RESOLVED | P1.5

**Summary:** CI is green: first GitHub Actions run (44040740869) on commit 2b1238c passed

- **Refs:** LOG-0020
- **Details:**
  - Remote origin added; main and tag checkpoint/CP-0002 pushed
  - P1 done-condition now fully met: CI green, toolproof --help works, devlog verify passes in CI

---

### LOG-0024 | 2026-11-17 18:57 +11:00 | DONE | P2.1

**Summary:** Seed data generator (seed 42) writes data/seed/*.csv: 300 customers, 80 products, 1,200 orders, 2,000 items, 60 refunds, 23 approvals

- **Files:** `scripts/build_sandbox.py`, `data/seed`, `src/toolproof/paths.py`, `src/toolproof/env/clock.py`, `docs/DESIGN_NOTES.md`
- **Details:** Edge cases: exactly 3 Johns and 2 Priyas (unique full names), 13 delivered orders at exactly 200.00, 4 zero-item orders, 80 cancelled, ~10% late deliveries, non-refundable gift cards
- **Findings:** First price ranges put 951/1,200 orders over the 200 approval threshold; lowered ranges and basket sizes to 490/1,200 (median 169.99) so the approval rule is selective

---

### LOG-0025 | 2026-11-17 18:57 +11:00 | DONE | P2.2

**Summary:** World: builds SQLite from CSVs with fingerprint-based rebuild, fresh copy per trial, snapshot/diff, frozen clock 2026-03-16

- **Files:** `src/toolproof/env/world.py`, `src/toolproof/env/sandbox.py`

---

### LOG-0026 | 2026-11-17 18:57 +11:00 | DONE | P2.3

**Summary:** Tool base class with 3 description levels, pydantic args (extra=forbid) -> JSON schema, typed errors, ToolBox dispatcher recording every call

- **Files:** `src/toolproof/env/tools/base.py`, `src/toolproof/env/toolbox.py`

---

### LOG-0027 | 2026-11-17 18:57 +11:00 | DONE | P2.4

**Summary:** Read tools: sql_query (read-only + authorizer, approvals hidden, 1 statement, 50-row cap, 2 s limit), get_order, search_docs (BM25 over doc sections)

- **Files:** `src/toolproof/env/tools/read.py`, `src/toolproof/env/docs_index.py`
- **Details:** approvals table is unreadable through sql_query so agents cannot look up approval codes
- **Findings:** Short sections outranked the right document; counting titles twice (field boost) fixed most queries. 'damaged item refund policy' still ranks refund-policy first but damaged-items is in the default top 3

---

### LOG-0028 | 2026-11-17 18:57 +11:00 | DONE | P2.5

**Summary:** Pure tools: whitelisted AST calculator (no eval/exec), get_date, add_days

- **Files:** `src/toolproof/env/tools/pure.py`

---

### LOG-0029 | 2026-11-17 18:57 +11:00 | DONE | P2.6

**Summary:** Write tools: issue_refund enforcing amount, one-per-order, cancelled and >200 approval rules; send_email writes to outbox only

- **Files:** `src/toolproof/env/tools/write.py`
- **Details:** Refund of exactly 200.00 needs no approval; a used approval code is marked used

---

### LOG-0030 | 2026-11-17 18:57 +11:00 | DONE | P2.7

**Summary:** ask_user returns scripted replies in order, then 'No further information is available.', and records questions asked

- **Files:** `src/toolproof/env/tools/interact.py`

---

### LOG-0031 | 2026-11-17 18:57 +11:00 | DONE | P2.8

**Summary:** Fault injection: per-tool call schedules and a seeded random rate (ToolTimeout/RateLimited); injected errors marked injected=true and block side effects

- **Files:** `src/toolproof/env/faults.py`

---

### LOG-0032 | 2026-11-17 18:57 +11:00 | DONE | P2.9

**Summary:** 15 deterministic, stateless distractor tools (outputs seeded from a hash of name + args)

- **Files:** `src/toolproof/env/tools/distractors.py`, `src/toolproof/env/tools/__init__.py`

---

### LOG-0033 | 2026-11-17 18:57 +11:00 | DONE | P2.10

**Summary:** 30 policy and FAQ documents in data/docs/ for the fictional store Larkspur Home & Office

- **Files:** `data/docs`
- **Details:** Some rules are enforced by tools, others exist only in docs (delivered-only refunds, gift cards, late delivery 10% capped at 50, privacy, no bulk email); split documented in DESIGN_NOTES.md

---

### LOG-0034 | 2026-11-17 18:57 +11:00 | DONE | P2.11

**Summary:** Tool tests: 243 passed; env/ coverage 99%; determinism test passes (identical hashes over a 12-call sequence with faults)

- **Files:** `tests/conftest.py`, `tests/unit/test_build_sandbox.py`, `tests/unit/test_world.py`, `tests/unit/test_tools_read.py`, `tests/unit/test_tools_pure.py`, `tests/unit/test_tools_write.py`, `tests/unit/test_toolbox_and_faults.py`, `tests/unit/test_distractors_and_safety.py`
- **Details:** Safety tests: no network imports, no eval/exec/compile, no real-clock calls anywhere in env/
- **Findings:** Tests caught a real bug: schema title-stripping also deleted a property named 'title' (create_calendar_event), hiding a required argument from the model; fixed in base._strip_titles

---

### LOG-0035 | 2026-11-17 18:58 +11:00 | NOTE | P2

**Summary:** P2 used one branch (p2/p2.1-p2.11-sandbox-world) for all eleven tasks instead of one branch per task (RULES 43), because the tasks share modules and tests; merged fast-forward into main as 30ef347

---

### LOG-0036 | 2026-11-17 18:58 +11:00 | CHECKPOINT | P2

**Summary:** CP-0003 saved: P2 sandbox world complete and merged; end of session; next P3.1 LLM adapter

- **Refs:** LOG-0024, LOG-0034, LOG-0035
- **Details:**
  - Tests: 243 passed; env/ coverage 99%; ruff, mypy strict, pre-commit and devlog verify clean
  - Open issues: LOG-0008 (model list), LOG-0009 (CI runner capacity)
- **Next:** P3.1 LLMAdapter protocol and OllamaAdapter; start the Ollama server and run 'ollama list' first

---

### LOG-0037 | 2026-11-17 19:04 +11:00 | NOTE | P9.2

**Summary:** Publish to GitHub Packages at release time: Docker image to ghcr.io via a tag-triggered workflow (linked to the repo with the org.opencontainers.image.source label), plus the wheel attached to a GitHub Release

- **Details:**
  - GitHub Packages does not host PyPI packages, so a container image is how ToolProof appears under the repo's Packages section
  - Image auth uses the built-in GITHUB_TOKEN (no secrets); new packages start private and must be made public once in package settings
- **Next:** In P9.2 add .github/workflows/publish.yml alongside the Dockerfile; in P9.6 tag v0.1.0 to trigger it
