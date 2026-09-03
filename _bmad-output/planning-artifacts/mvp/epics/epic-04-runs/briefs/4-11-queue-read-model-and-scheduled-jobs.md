---
story: "4-11"
epic: 4
title: Queue read model and scheduled jobs
requirements: [FR-4 (daily re-check), FR-9 (7-day retention), FR-13, FR-25 (queue), AR-19 (jobs)]
binds: [AD-6, AD-12, AD-14]
---

# Story 4.11 — Queue read model and scheduled jobs

As the Operator,
I want to see the queue as the engine sees it, with the reason each Run waits, and to have stale worktrees and clone checks handled without me,
So that "why is nothing happening" has an answer on screen and the disk does not fill up.

## Scope

**In:** `application/use_cases/queue.py::list_queue`, `GET /api/v1/queue`, jobs `clone_check` (daily) and `worktree_gc` (7 days) registered through `engine.schedule`, tests.
**Out:** `terminal_poll` (Epic 6), the Runs screen (4.16).

## Binding rules (inlined)

- **Queue rows (AD-12).** Join `engine.list_queue()` with `run` and `step_run`: `{position: int | null, run: RunSummary, next_step_label, reason, waiting_since, waiting_seconds}`; `reason` ∈ `repository lock held by {label}` (another non-terminal Run on the same Repository), `global concurrency, held by {labels}` (active Runs ≥ `MAX_ACTIVE_RUNS`), `running` (the Run is active and executing), `waiting for your answer` (the Run is `needs_you`; `position: null`). Ordered: active first, then queued by position. No queue table exists; this is a read.
- **`GET /queue`** → `{items, next_cursor: null, max_active_runs}`; the section head text uses `max_active_runs`.
- **`clone_check` job (FR-4).** Cron `0 3 * * *`; for every Repository run `run_clone_check`; a failure sets `status: failed` and blocks new Runs only (queued and running Runs are untouched). Log one line per Repository.
- **`worktree_gc` job (FR-9, AD-14).** Cron `30 3 * * *`; for every Run terminal for more than 7 days iterate `run.worktrees[]`: `Git.remove_worktree(path)`; remove `/work/logs/{run_id}/`; base clones are kept; record on the Run `worktrees_removed_at`. Idempotent.
- **Job registration.** `main.py` calls `engine.schedule("clone_check", cron, job)` and `engine.schedule("worktree_gc", cron, job)`; jobs are application functions taking ports; DBOS's `@DBOS.scheduled` is used only inside the adapter.
- **Settings:** `WORKTREE_RETENTION_DAYS` (default 7), `CLONE_CHECK_CRON`, `WORKTREE_GC_CRON` in settings and `.env.example`.

## Acceptance criteria

**Given** two Runs on Repository A (one running, one enqueued) and one Run parked on Repository B
**When** `GET /queue` is read
**Then** three rows: A's first with `reason: running` and `position: null`; A's second with `position: 1`, `reason: repository lock held by {label}`; B's with `position: null`, `reason: waiting for your answer`.

**Given** `MAX_ACTIVE_RUNS=2`, two active Runs on two Repositories, and a third enqueued on a third Repository
**When** read
**Then** the third's reason is `global concurrency, held by {label1}, {label2}`.

**Given** the `worktree_gc` job on the fake ports with a Run terminal 8 days ago and one terminal yesterday
**When** run
**Then** only the older Run's worktrees and logs are removed and `worktrees_removed_at` is set on it.

**Given** the `clone_check` job
**When** run with one Repository whose origin is now unreachable
**Then** its `clone_check.status` becomes `failed` and no Run status changes.

**Given** the app started in the e2e stack
**When** DBOS lists scheduled workflows
**Then** both jobs are registered with the configured crons.

## Implementation notes

- `queue.py` label helper shared with pre-flight (`run_label(run) = "{template} · {branch}"`).
- Jobs in `application/jobs/{clone_check,worktree_gc}.py`; adapter method `schedule` wraps each job in a DBOS scheduled workflow with a step per Repository / Run.
- Migration `0008_run_gc.py` for `worktrees_removed_at`.

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

PRD FR-13, FR-25 (queue), FR-4 (daily), FR-9 (7-day). Spine AD-12 (reasons, no queue table), AD-14 (jobs), AD-6 (`schedule`).
