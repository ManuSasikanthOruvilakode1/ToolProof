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

---

### LOG-0038 | 2026-11-17 19:09 +11:00 | DECISION | P8.6

**Summary:** Add a hosted read-only FastAPI service on Render (new tasks P8.6 and P9.7, goal G10); plan version 1.0 -> 1.1

- **Files:** `PLAN.md`
- **Details:**
  - Requested by the project owner, following the set-up of an earlier portfolio API (FastAPI on Render with Swagger at /docs)
  - Endpoints: /, /health, /tools, /sandbox/call, /tasks (dev split only), /leaderboard, /runs/{id} and example traces; read-only, no model calls on the server
  - Naming: service and URL use 'toolproof' only; no student field, course code or assignment details (RULES 1-2)
- **Findings:** Render's free tier is enough because the server only serves the deterministic sandbox and committed results
- **Next:** Build in P8.6 after results exist; deploy in P9.7. An early version with /tools and /sandbox/call is possible any time after P2

---

### LOG-0039 | 2026-11-17 19:10 +11:00 | DECISION | P8.6

**Summary:** Hosted API (G10, P8.6, P9.7) made optional: not required for v0.1.0; plan version 1.1 -> 1.2

- **Refs:** LOG-0038
- **Files:** `PLAN.md`
- **Details:**
  - The project owner confirmed the hosted API is not needed; it stays in the plan as an optional extra so it cannot block the definition of done
  - No early API version will be built before P3

---

### LOG-0040 | 2026-11-17 19:18 +11:00 | FINDING | -

**Summary:** Full project and process audit after P2: gates, CI and log integrity clean; 7 problems found

- **Details:**
  - Clean: ruff, ruff format, mypy strict, pytest 243 passed (99% coverage), devlog verify (39 entries), uv.lock in sync, requirements.txt in sync, CI green on all 5 pushed commits, no CRLF in the index
  - Clean: PII, AI-watermark and university scans of tracked files (only false positives such as 'manual' and the rule text itself)
  - Data claims checked against the database: 3 Johns, 13 delivered orders at exactly 200.00, order IDs 9001-10200, city-to-zone mapping matches shipping-zones.md
- **Issues:**
  - 1) data/world.sqlite.sha256 (generated) was committed
  - 2) 3 historical refunds were on orders containing gift cards, and refund reasons/amounts were random, contradicting the policy docs
  - 3) DESIGN_NOTES said about 10% late deliveries; actual 136/1,100 = 12.4%
  - 4) pre-commit hook was never installed in this clone
  - 5) README status and PLAN section 16 were stale
  - 6) CP-0003 was behind the log (LOG-0037 to LOG-0039 were added after it)
  - 7) commit author email in the pushed history is an institutional address (logged separately as an ISSUE)

---

### LOG-0041 | 2026-11-17 19:18 +11:00 | EDIT | P2.1

**Summary:** Historical refunds now follow the policy docs; refunds.csv and approvals.csv regenerated

- **Refs:** LOG-0040
- **Files:** `scripts/build_sandbox.py`, `data/seed/refunds.csv`, `data/seed/approvals.csv`, `tests/unit/test_build_sandbox.py`, `docs/DESIGN_NOTES.md`
- **Details:**
  - No refunds on orders containing gift cards; late_delivery refunds only on late orders, amount min(10% of total, 50.00); other refunds are the full total or one line total; reasons from the policy reason codes
  - Only refunds and approvals changed (random draws for them come after orders); approvals now 36 (12 active, 24 used)
  - New test test_historical_refunds_follow_policy_docs; tests 244 passed
- **Findings:** 10% of a 2-decimal total can land on exactly half a cent (e.g. 123.45 -> 12.345); P4 late-delivery tasks must use a 0.01 tolerance or avoid such totals

---

### LOG-0042 | 2026-11-17 19:18 +11:00 | EDIT | -

**Summary:** Audit fixes: untracked generated fingerprint, installed pre-commit hook, refreshed README, PLAN section 16 and DESIGN_NOTES

- **Refs:** LOG-0040
- **Files:** `.gitignore`, `README.md`, `PLAN.md`, `docs/DESIGN_NOTES.md`
- **Details:**
  - .gitignore now covers data/world.sqlite.*; data/world.sqlite.sha256 removed from the index (kept on disk)
  - README: CI badge and current status (P1-P2 done, P3 next); PLAN section 16 marks name and licence as decided (LOG-0012, LOG-0014); DESIGN_NOTES late-delivery and approval counts corrected
  - Repository-local git identity switched to the GitHub noreply address for all future commits

---

### LOG-0043 | 2026-11-17 19:18 +11:00 | ISSUE | -

**Summary:** The 7 commits already pushed carry an institutional author email that identifies a university (RULES 1-2)

- **Refs:** LOG-0040
- **Details:** Future commits use the GitHub noreply address. Removing the address from existing commits needs a history rewrite and a force-push of main and tags, which RULES 46 forbids without a DECISION
- **Next:** Project owner decides: rewrite history now while the repository is new, or accept and close

---

### LOG-0044 | 2026-11-17 19:18 +11:00 | NOTE | P9.2

**Summary:** Packaging caveat for P9: data/ is not inside the wheel and paths.PROJECT_ROOT assumes a source checkout

- **Details:** A pip-installed or Docker build must set TOOLPROOF_DATA_DIR or ship data/ (seed CSVs and docs) alongside the package

---

### LOG-0045 | 2026-11-17 19:18 +11:00 | CHECKPOINT | P2

**Summary:** CP-0004 saved: post-P2 audit fixes applied; P3 not started

- **Refs:** LOG-0040, LOG-0041, LOG-0042, LOG-0043, LOG-0044
- **Details:**
  - Reconciles CP-0003, which was behind the log (LOG-0037 to LOG-0039)
  - Tests: 244 passed; ruff, mypy strict, pre-commit (now installed) and devlog verify clean
  - Open issues: LOG-0008, LOG-0009, LOG-0043
- **Next:** Owner decision on LOG-0043; then P3.1 when the owner says to start P3

---

### LOG-0046 | 2026-11-25 05:02 +11:00 | RECOVERY | P3

**Summary:** Full recovery after an 8-day gap (2026-11-17 to 2026-11-25): state matches CP-0004

- **Details:**
  - R2-R4: last entry LOG-0045 matches the checkpoint; devlog verify OK (45 entries); tree clean; HEAD f2e01fa = checkpoint/CP-0004; in sync with origin/main; no stashes
  - R5: uv sync OK; pytest 244 passed; Ollama client 0.35.1 but the server is not running, so installed models are still unknown
  - R6: no runs exist yet (runner arrives in P6)
- **Findings:** P3.1-P3.6 and P3.8 can proceed with a scripted fake LLM; only the P3.7 pilot needs the Ollama server
- **Next:** P3.1 LLM adapter on branch p3/p3.1-p3.8-agent-loop

---

### LOG-0047 | 2026-11-25 05:13 +11:00 | EDIT | P3.4

**Summary:** ToolCallRecord.malformed separates schema violations (counted as malformed) from policy errors (not counted), as P3.4 requires

- **Files:** `src/toolproof/env/tools/base.py`, `src/toolproof/env/toolbox.py`, `tests/unit/test_toolbox_and_faults.py`
- **Details:** ToolError gained schema_error; pydantic validation failures and non-object arguments set it; unknown tools are malformed via error_type UnknownTool

---

### LOG-0048 | 2026-11-25 05:13 +11:00 | DONE | P3.1

**Summary:** LLMAdapter protocol, LLMResponse/ToolCall/TokenUsage and OllamaAdapter (/api/chat native tool calling; digest from /api/tags, capabilities from /api/show, server version from /api/version)

- **Files:** `src/toolproof/agent/llm.py`, `tests/unit/test_llm.py`
- **Details:** Provider-neutral message format; adapters never repair output: arguments that are not a JSON object come back with parse_error set

---

### LOG-0049 | 2026-11-25 05:13 +11:00 | DECISION | P3.2

**Summary:** P3.2 (optional API adapter) deferred: built only if the P3.7 decision includes an API reference model

- **Files:** `PLAN.md`
- **Details:** Follows the owner's instruction to skip optional extras unless asked; nothing else in P3 depends on it

---

### LOG-0050 | 2026-11-25 05:13 +11:00 | DONE | P3.3

**Summary:** RecordingAdapter and ReplayAdapter: cassettes are JSONL keyed by SHA-256 of model, messages, tools, temperature, seed and max_tokens

- **Files:** `src/toolproof/agent/llm.py`
- **Details:** Repeated identical requests are served in recorded order; a missing request raises CassetteMiss

---

### LOG-0051 | 2026-11-25 05:13 +11:00 | DONE | P3.4

**Summary:** Agent loop: max_steps 15, max_wall_seconds 180, max_output_tokens 1024; terminations final_answer/step_limit/time_limit/llm_error; malformed calls returned to the model and counted

- **Files:** `src/toolproof/agent/loop.py`, `src/toolproof/trial.py`, `src/toolproof/agent/scripted.py`

---

### LOG-0052 | 2026-11-25 05:13 +11:00 | DONE | P3.5

**Summary:** Strategies plain, react, plan_execute, reflect; prompts in configs/prompts/*.md with version lines; every strategy = base prompt + its own section

- **Files:** `src/toolproof/agent/strategies.py`, `configs/prompts/base.md`, `configs/prompts/plain.md`, `configs/prompts/react.md`, `configs/prompts/plan_execute.md`, `configs/prompts/reflect.md`
- **Details:**
  - plan_execute: first call without tools produces a plan, one re-plan after a tool error; reflect: one self-check, first answer kept if the second is empty; react: text after 'Final answer:'
  - Test guards that prompts name no tools and contain no digits (no task-specific hints)

---

### LOG-0053 | 2026-11-25 05:13 +11:00 | DONE | P3.6

**Summary:** Tracing: JSONL per trial (run, task, trial, step, ts, event, payload, tokens, latency); toolproof trace show prints a timeline

- **Files:** `src/toolproof/tracing.py`, `src/toolproof/cli.py`

---

### LOG-0054 | 2026-11-25 05:13 +11:00 | DONE | P3.8

**Summary:** Loop and adapter tests with a scripted LLM: normal path, malformed JSON, unknown tool, missing fields, repeated calls -> step limit, time limit, LLM error; recorded trace replays exactly for all 4 strategies

- **Files:** `tests/unit/test_agent_loop.py`, `tests/unit/test_strategies.py`, `tests/unit/test_tracing_and_pilot.py`, `tests/unit/test_llm.py`
- **Findings:** 312 tests pass; total coverage 99% (agent/ 97-100%, cli 95%)

---

### LOG-0055 | 2026-11-25 05:13 +11:00 | EXPERIMENT | P3.7

**Summary:** Pilot run pilot_20261125-0511: qwen2.5:7b (digest 845dbda0ea48), plain, temperature 0.7, 5 pilot requests x 1 trial

- **Files:** `configs/pilot_tasks.yaml`, `src/toolproof/pilot.py`, `reports/pilot/pilot_20261125-0511_summary.json`, `reports/pilot/pilot_20261125-0511_rows.jsonl`
- **Details:**
  - Ollama server 0.35.1 started for this session; installed tool-calling models: qwen2.5:7b only (minicpm-v has no tool calling)
  - Median 3.66 s per trial (first trial 48.5 s including model load); mean 3,248 tokens per trial; median 2 steps, max 5; 100% of trials made native tool calls; malformed-call rate 0.0; all 5 ended with final_answer; sanity checks 2/5
  - Hardware: RTX 4060 Laptop GPU 8 GB (model fully in VRAM, 4.4 GB), 15 GB RAM

---

### LOG-0056 | 2026-11-25 05:13 +11:00 | FINDING | P3.7

**Summary:** Pilot failures are genuine agent failures that map onto the taxonomy; the harness behaved correctly

- **Details:**
  - pilot-002: after an injected ToolTimeout the model asked whether to retry instead of retrying (ignored_error)
  - pilot-004: passed SQL to the calculator twice, then fixed the query, then announced 'Now, I will calculate the average' and stopped without a tool call (wrong_tool, premature_answer)
  - pilot-005: never searched the policy docs and stated an invented rule ('0 if more than 7 days late'); no refund issued (hallucinated_fact)
- **Findings:**
  - Narrated-but-not-executed next steps end the trial under the plan's rule (first message without a tool call is final). Keep the rule; it is what premature_answer measures
  - Step limit 15 is ample (max 5 used); speed is well under the 15 s/trial budget assumption for a 7B model on this GPU

---

### LOG-0057 | 2026-11-25 05:13 +11:00 | ISSUE | P3.7

**Summary:** P3.7 decisions blocked: only one tool-calling model (qwen2.5:7b) is installed; the plan needs small (~3-4B) and large (~14B) models too

- **Refs:** LOG-0008
- **Details:** 8 GB VRAM: a 14B model (~9 GB at q4) will partly run on CPU; its speed must be measured before fixing the E1 budget
- **Next:** Owner approves model downloads (suggested qwen2.5:3b ~1.9 GB and qwen2.5:14b ~9 GB, optionally llama3.1:8b as a second family); rerun the pilot with 3 trials per request; then log the model list, temperature and step-limit DECISIONs

---

### LOG-0058 | 2026-11-25 05:14 +11:00 | NOTE | P3

**Summary:** P3 used one branch (p3/p3.1-p3.8-agent-loop) for all tasks, as in P2 (LOG-0035); merged fast-forward into main as 9b66bf7

---

### LOG-0059 | 2026-11-25 05:14 +11:00 | CHECKPOINT | P3

**Summary:** CP-0005 saved: P3 6/8 done and merged; P3.7 blocked on model downloads; P3.2 deferred

- **Refs:** LOG-0046, LOG-0054, LOG-0055, LOG-0056, LOG-0057, LOG-0058
- **Details:**
  - Tests: 312 passed; coverage 99%; ruff, mypy strict, pre-commit and devlog verify clean
  - Open issues: LOG-0008, LOG-0009, LOG-0043, LOG-0057
- **Next:** Owner approves model downloads; then 'ollama pull qwen2.5:3b' and 'ollama pull qwen2.5:14b', rerun 'toolproof pilot' with 3 trials, and log the P3.7 decisions

---

### LOG-0060 | 2026-11-25 05:34 +11:00 | EXPERIMENT | P3.7

**Summary:** Pilot run pilot_20261125-0521: qwen2.5 3b/7b/14b, plain, temperature 0.7, 5 requests x 3 trials (45 trials)

- **Files:** `reports/pilot/pilot_20261125-0521_summary.json`, `reports/pilot/pilot_20261125-0521_rows.jsonl`
- **Details:**
  - Models pulled with the owner's approval: qwen2.5:3b (357c53fb659c), qwen2.5:14b (7cdf5a0187d5); all three report native tool calling
  - Median s/trial: 3b 0.94, 7b 2.31, 14b 13.95 (14b mean 21.8, max 89.4 s); mean tokens/trial ~2.4k-3.0k; malformed-call rate 0.0 for all; 45/45 ended with final_answer; max 5 steps
  - Trials with tool calls: 3b 87%, 7b 100%, 14b 87%. Sanity checks (pilot only, not a benchmark metric): 3b 20%, 7b 40%, 14b 53%

---

### LOG-0061 | 2026-11-25 05:34 +11:00 | FINDING | P3.7

**Summary:** Ollama's default context window is 4096 tokens and it drops the start of longer prompts without an error; the harness must set num_ctx and flag full windows

- **Refs:** LOG-0060
- **Details:** Seen via /api/ps context_length=4096 for the loaded model. Pilot peak was 1,971 input tokens per request, but benchmark tasks with 50-row SQL results, doc snippets and up to 15 steps can exceed 4,096; the system prompt would be lost first

---

### LOG-0062 | 2026-11-25 05:34 +11:00 | EDIT | P3.7

**Summary:** num_ctx is now set explicitly and every LLM call is checked for a full context window

- **Refs:** LOG-0061
- **Files:** `configs/models.yaml`, `src/toolproof/models_config.py`, `src/toolproof/agent/llm.py`, `src/toolproof/agent/loop.py`, `src/toolproof/trial.py`, `src/toolproof/pilot.py`, `src/toolproof/cli.py`, `tests/unit/test_models_config.py`
- **Details:**
  - LLMResponse.context_limit_hit = input_tokens + max_tokens >= num_ctx; counted as AgentResult.context_limit_hits and written to traces, trial summaries and pilot summaries
  - configs/models.yaml holds the model list with full digests and the defaults; toolproof pilot takes num_ctx and limits from it; tests 320 passed

---

### LOG-0063 | 2026-11-25 05:34 +11:00 | EXPERIMENT | P3.7

**Summary:** Confirmation pilot pilot_20261125-0530 with final settings (num_ctx 8192, wall limit 600 s): 3 models x 5 requests x 1 trial

- **Files:** `reports/pilot/pilot_20261125-0530_summary.json`, `reports/pilot/pilot_20261125-0530_rows.jsonl`
- **Details:**
  - Median s/trial: 3b 1.03, 7b 2.91, 14b 21.45 (up from 13.95 at num_ctx 4096: 14b now holds 5.9 of 10.0 GB in VRAM, the rest on CPU); context_limit_hits 0 for all; /api/ps confirms context_length 8192
  - One malformed call: qwen2.5:7b added a junk argument key ('toolbench_rapidf...') to a calculator call; rejected as a schema error and counted, as intended

---

### LOG-0064 | 2026-11-25 05:34 +11:00 | FINDING | P3.7

**Summary:** Compute budget estimate from the pilot: about 43 h for all dev and test runs, within the plan's 46 h estimate; the 14B model dominates

- **Details:**
  - Assumes benchmark trials take 2x the pilot medians (2 s, 6 s, 43 s for small/medium/large) and 650 trials per config (500 test + 150 dev)
  - Configs per model: small 2 (E1, E6), medium 10 (base, E2 x3, E3 x2, E4 x2, E5, E6), large 4 (E1, E4 x2, E6): about 0.7 h + 10.8 h + 31 h
- **Findings:**
  - If the budget is too large, the plan's existing option (run E4 on one model) saves about 15 h
  - First trial per model includes model loading (3b 6.6 s, 14b 20 s); the P6 runner should warm each model up before timing trials

---

### LOG-0065 | 2026-11-25 05:34 +11:00 | DECISION | P3.7

**Summary:** Model list: qwen2.5:3b (small), qwen2.5:7b (medium, base config), qwen2.5:14b (large); no API reference model

- **Refs:** LOG-0008
- **Files:** `configs/models.yaml`, `PLAN.md`
- **Details:**
  - One family at three sizes, so E1 varies size only; all three have native tool calling in Ollama 0.35.1 with 0 malformed calls in 45 pilot trials
  - No API model: keeps the project free and offline, and follows the owner's instruction to skip optional extras; P3.2 therefore stays unbuilt

---

### LOG-0066 | 2026-11-25 05:34 +11:00 | DECISION | P3.7

**Summary:** Default temperature stays 0.7 with seed = trial index; E5 compares it with 0.0

- **Refs:** LOG-0008
- **Details:** At 0.7 the same request gave different outcomes across trials (e.g. 7b pilot-004 passed 1/3, 14b pilot-003 2/3), which pass^k needs

---

### LOG-0067 | 2026-11-25 05:34 +11:00 | DECISION | P3.7

**Summary:** Limits: max_steps 15 (unchanged), max_output_tokens 1024, num_ctx 8192, max_wall_seconds raised from 180 to 600

- **Files:** `configs/models.yaml`, `src/toolproof/agent/loop.py`, `PLAN.md`
- **Details:**
  - Pilot used at most 5 steps. A 14B request took up to 89 s at num_ctx 4096 and 14B trials got slower at 8192; with 180 s the large model would fail on speed on this 8 GB GPU, confounding E1. The wall limit is now a safety net; the step limit is the real cap
  - Same num_ctx for every model so context size never differs between conditions

---

### LOG-0068 | 2026-11-25 05:34 +11:00 | RESOLVED | P3.7

**Summary:** Model list and default temperature decided (LOG-0065, LOG-0066)

- **Refs:** LOG-0008, LOG-0065, LOG-0066

---

### LOG-0069 | 2026-11-25 05:34 +11:00 | RESOLVED | P3.7

**Summary:** Small and large models downloaded and piloted; P3.7 decisions logged

- **Refs:** LOG-0057, LOG-0060

---

### LOG-0070 | 2026-11-25 05:34 +11:00 | DONE | P3.7

**Summary:** Pilot complete: 3 models piloted (60 trials over three runs); model list, temperature, step/wall limits and num_ctx decided; reports in reports/pilot/

- **Files:** `configs/models.yaml`, `reports/pilot`
