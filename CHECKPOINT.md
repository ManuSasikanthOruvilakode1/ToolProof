# ToolProof: Checkpoint Save and Recovery

This file has two parts:

- **Part 1: Protocol.** How to save a checkpoint and how to recover after an interruption. This part stays the same.
- **Part 2: Current checkpoint.** The latest save point. At each save, **only** the block between the `CHECKPOINT:START` and `CHECKPOINT:END` markers is replaced. Earlier checkpoints are kept as `CHECKPOINT` entries in [PROCESS_LOG.md](PROCESS_LOG.md) and as git tags `checkpoint/CP-NNNN`.

Jump to: [When to save](#11-when-to-save) · [How to save](#12-how-to-save) · [Recovery mode](#13-recovery-mode) · [Conflicts](#14-conflict-resolution) · [Rollback](#15-rollback-to-a-checkpoint) · [Interrupted runs](#16-interrupted-experiment-runs) · [**Current checkpoint**](#part-2-current-checkpoint)

---

# Part 1: Protocol

## 1.1 When to save

Save a checkpoint (RULES 38):

| Trigger | Why |
|---|---|
| End of every work session | The next session starts from a known state |
| After finishing a task ID that changes code or data | Each task becomes a restore point |
| **Before** a risky operation: large refactor, dependency upgrade, deleting files, a test-split run, changing `tasks/test.lock` | So the operation can be undone |
| After about 90 minutes of continuous work | Limits how much can be lost |
| When blocked, before switching to other work | Records exactly where you stopped and why |
| Before a long experiment run starts | Records the run ID and the resume command |

## 1.2 How to save

**S1. Reach a clean point.** Tests pass, or the failing tests are written down in the checkpoint. Don't save halfway through a file edit.

**S2. Run the checks.**

```bash
uv run ruff check . && uv run mypy src && uv run pytest -q     # from P1 onwards
python scripts/devlog.py verify
```

**S3. Log the work done since the last checkpoint.** Add `DONE`, `EDIT`, `FINDING` and `ISSUE` entries for anything not logged yet.

**S4. Replace the current-checkpoint block** in Part 2 below. Fill in **every** field; write `none` instead of leaving a field empty. Increase the ID by one (`CP-0001` → `CP-0002`).

**S5. Append the CHECKPOINT log entry.**

```bash
python scripts/devlog.py add --type CHECKPOINT --task P2.6 \
  --summary "CP-0007 saved: refund tool done, email tool in progress" \
  --ref LOG-0031 LOG-0032 \
  --next "P2.6 finish send_email outbox test"
```

**S6. Commit and tag** (from P1.1 onwards):

```bash
git add -A
git commit -m "chore: checkpoint CP-0007 (P2.6)"          # on a branch, `wip:` prefix is fine (RULES 44)
git tag checkpoint/CP-0007
git push && git push origin checkpoint/CP-0007          # once a remote exists
```

**S7. If an experiment is running**, make sure its `run_id` and resume command are in the checkpoint's *Active runs* field.

> **Quick save** (when you must stop *now*): do S4 with at least *Phase / task*, *In progress* and *Next step*, then S5 with the summary "quick save". Commit with `wip:`. Do the full save next session.

## 1.3 Recovery mode

### When to enter recovery mode

| Situation | Mode |
|---|---|
| Start of any normal work session | **Light** |
| After a crash, power loss, forced restart, or a terminal closed during a task | **Full** |
| After a gap of 7 days or more | **Full** |
| A new assistant or helper session with no memory of earlier sessions | **Full** |
| The repository looks different from what the checkpoint says | **Full** |
| `devlog.py verify` fails | **Full**, starting with R3 |

### Light mode (about 2 minutes): R1, R2, R4, R9

### Full mode (about 10–15 minutes): R1 to R9

**R1. Read the current checkpoint** (Part 2 below). Note the phase, task, *In progress*, *Next step* and *Active runs*.

**R2. Read the recent log and open issues.**

```bash
python scripts/devlog.py tail -n 8
python scripts/devlog.py issues
```

If there are log entries **newer** than the checkpoint's *Last log entry*, they describe work done after the save; the log wins (RULES 41).

**R3. Check log integrity.**

```bash
python scripts/devlog.py verify
```

If it fails: save a copy of any entries added after the last seal → `git checkout HEAD -- PROCESS_LOG.md` (or find the last good version with `git log -p -- PROCESS_LOG.md`) → re-append the new entries → `python scripts/devlog.py seal` → add a `RECOVERY` entry describing the problem. **Never** run `seal` to accept an edit of existing entries.

**R4. Compare the repository with the checkpoint.**

```bash
git status --short
git log --oneline -5
git describe --tags --always
git stash list
```

Compare with the checkpoint's *Git state*. Any difference goes through the conflict table (§1.4).

**R5. Check the environment.**

```bash
uv sync
uv run pytest -q
ollama --version && ollama list          # start the Ollama app/server first
```

Compare the Python version, Ollama version and **model digests** with the checkpoint's *Environment* field. A different digest means any interrupted run must **not** be resumed (§1.6).

**R6. Check for interrupted runs** (from P6 onwards; the runner exists from P3).

```bash
uv run toolproof runs list --status running
uv run toolproof runs list --status aborted
```

Resume according to §1.6.

**R7. Reconcile.** Fix every mismatch found in R2–R6 using §1.4, and update the checkpoint block so it matches reality.

**R8. Log the recovery.**

```bash
python scripts/devlog.py add --type RECOVERY --task P2.6 \
  --summary "Full recovery after crash; restored uncommitted send_email work" \
  --details "git status showed 2 modified files not in CP-0007; kept them (they belong to P2.6)" \
  --details "Tests: 41 passed, 1 failed (test_outbox_written) as expected for in-progress work" \
  --next "Finish send_email, then save CP-0008"
```

Light mode: only log if something was out of sync.

**R9. Continue** with the checkpoint's *Next step*.

## 1.4 Conflict resolution

| What you find | What to do | Log as |
|---|---|---|
| Log entries newer than the checkpoint | Trust the log; update the checkpoint block | `RECOVERY` |
| Uncommitted changes that match *In progress* | Keep them and continue | — |
| Uncommitted changes **not** mentioned anywhere | Inspect with `git diff`. Keep them if they clearly belong to the current task; otherwise `git stash push -m "recovery-YYYY-MM-DD"` | `RECOVERY` |
| Checkpoint says tests pass, but they fail now | Stop new work; find the cause (environment? partial edit?) and fix it first | `ISSUE`, later `RESOLVED` |
| `devlog.py verify` fails | Follow R3 | `RECOVERY` |
| `tasks/test.lock` does not match the test tasks | **Stop.** Find out which file changed and why with `git log -p tasks/test`. Restore it unless a `DECISION` entry approved the change. Never regenerate the lock to make the check pass (RULES 12) | `ISSUE` + `RECOVERY` |
| Model digest or Ollama version changed | Don't resume old runs; start new runs, and note the change | `FINDING` |
| A run's status is `running`, but nothing is running | It was interrupted: resume it (§1.6) | `EXPERIMENT` |
| HEAD is not at the commit or tag in the checkpoint | `git log --oneline checkpoint/CP-NNNN..HEAD` shows the commits made after the save; check they are logged, and log any that are not | `RECOVERY` |
| The checkpoint block is missing or damaged | Rebuild it from the last `CHECKPOINT` log entry and the git state | `RECOVERY` |

## 1.5 Rollback to a checkpoint

Use this when the work after a checkpoint should be abandoned or re-done.

```bash
git tag --list "checkpoint/*"                              # list save points
git log --oneline checkpoint/CP-0007..HEAD                 # what would be undone
git switch -c rollback/cp-0007 checkpoint/CP-0007          # safe: new branch from the save point
```

- Do **not** reset `main` or force-push (RULES 46). Merge the rollback branch through a normal commit, or revert specific commits with `git revert`.
- The process log is **not** rolled back. Keep the current `PROCESS_LOG.md`, and add a `DECISION` entry explaining the rollback and which entries describe abandoned work.
- After a rollback, save a new checkpoint immediately.

## 1.6 Interrupted experiment runs

The runner design is in [PLAN.md §12](PLAN.md#12-run-level-checkpointing-and-resume). Summary:

1. `uv run toolproof runs list --status running` shows runs that were interrupted.
2. `uv run toolproof run --resume <run_id>` continues the run. Finished trials (in `trials.jsonl`) are skipped; unfinished ones restart from a fresh world copy.
3. The runner **refuses** to resume if the config, benchmark version, test lock, model digest or prompts have changed. In that case start a **new** run and log an `EXPERIMENT` entry explaining why the old run was abandoned. The old run stays on disk.
4. For test-split runs, the resume is recorded automatically in `results/test_run_register.jsonl`.
5. Log the resume: `devlog.py add --type EXPERIMENT --summary "Resumed <run_id> at 412/500 trials" ...`.

## 1.7 Checkpoint field guide

| Field | What to write |
|---|---|
| Checkpoint ID | `CP-NNNN`, one higher than the last |
| Saved at | Local time with UTC offset |
| Last log entry | The `LOG-NNNN` of this checkpoint's own `CHECKPOINT` entry |
| Phase / task | Current phase and task ID, e.g. `P2 / P2.6` |
| Phase progress | Tasks done / total in this phase |
| Last completed | The last task ID completed (with its `DONE` entry) |
| In progress | What is half-finished, which files, and what state they are in |
| Next step | One concrete action that can be started without thinking, e.g. "write `tests/unit/test_outbox.py::test_email_written`" |
| Git state | Branch, last commit (short hash + message), tag, clean/dirty, stashes |
| Tests | Command and result, e.g. `pytest: 41 passed, 1 failed (expected)` |
| Environment | Python, uv and Ollama versions; models with digests |
| Active runs | Run IDs, status, progress, resume command |
| Open issues | IDs from `devlog.py issues` |
| Blockers | Anything that stops progress |
| Notes for the next session | Context that is easy to forget |

---

# Part 2: Current checkpoint

<!-- CHECKPOINT:START (replace only the content between these markers when saving) -->

| Field | Value |
|---|---|
| **Checkpoint ID** | CP-0005 |
| **Saved at** | 2026-11-25 05:14 +11:00 |
| **Last log entry** | LOG-0059 |
| **Phase / task** | P3 (Agent loop) / P3.7 pilot, **blocked** on model downloads |
| **Phase progress** | P3: 6/8 done (P3.1, P3.3–P3.6, P3.8); P3.2 deferred (LOG-0049); P3.7 first pilot run done on qwen2.5:7b, decisions pending |
| **Last completed** | P3.8: loop and adapter tests (LOG-0054); pilot run pilot_20261125-0511 (LOG-0055) |
| **In progress** | none (all work committed and merged) |
| **Next step** | With the owner's approval: `ollama pull qwen2.5:3b` and `ollama pull qwen2.5:14b`; then `uv run toolproof pilot --model qwen2.5:3b --model qwen2.5:7b --model qwen2.5:14b --trials 3 --record`; then log DECISIONs for the model list, default temperature and step limit, resolve LOG-0057 and LOG-0008, tick P3.7 |
| **Git state** | Branch `main` pushed to origin; `9b66bf7` (P3) + this checkpoint commit tagged `checkpoint/CP-0005`; clean; no stashes. Merged local branches `p2/...` and `p3/p3.1-p3.8-agent-loop` still exist (safe to delete). Repo-local git email is the GitHub noreply address |
| **Tests** | `uv run pytest -q` → 312 passed; coverage 99%; ruff, ruff format, mypy strict, pre-commit and `devlog.py verify` pass |
| **Environment** | Python 3.12.13 (uv), uv 0.12.0, git 2.55.0, Ollama 0.35.1 (server started this session with `ollama serve`). Tool-calling models: qwen2.5:7b (digest 845dbda0ea48). GPU RTX 4060 Laptop 8 GB, RAM 15 GB, 165 GB free disk |
| **Active runs** | none |
| **Open issues** | LOG-0008 (model list), LOG-0009 (CI runner capacity, P7.3), LOG-0043 (institutional email in pushed commits), LOG-0057 (P3.7 needs more models) |
| **Blockers** | P3.7 needs the owner's approval to download about 11 GB of models. P4 can start without it |
| **Notes for the next session** | Pilot failures were genuine (ignored_error, wrong_tool + premature_answer, hallucinated_fact; LOG-0056); the loop treats a narrated-but-unexecuted next step as the final answer by design. Pilot summaries are committed under reports/pilot/. `toolproof models` lists local models with tool support; `toolproof trace show <run> <task> <trial>` prints a trace (pilot run IDs look like `pilot_20261125-0511/qwen2.5-7b`). P4 late-delivery tasks: 10% of a total can fall on exactly half a cent, so use a 0.01 tolerance (LOG-0041). P9 packaging: data/ is outside the wheel; set `TOOLPROOF_DATA_DIR` (LOG-0044). Sandbox entry point for the agent loop: `toolproof.env.sandbox.Sandbox.open(workdir, user_replies=..., faults=..., n_distractors=..., description_level=...)`; `sandbox.toolbox.schemas()` gives Ollama tool definitions, `sandbox.toolbox.call(name, args)` returns a `ToolCallRecord` (`content_for_model()` is the tool message), and `sandbox.diff()` gives the world changes. Policy rules enforced by tools vs only in docs: see docs/DESIGN_NOTES.md. `data/world.sqlite` is rebuilt automatically from the seed CSVs |

<!-- CHECKPOINT:END -->
