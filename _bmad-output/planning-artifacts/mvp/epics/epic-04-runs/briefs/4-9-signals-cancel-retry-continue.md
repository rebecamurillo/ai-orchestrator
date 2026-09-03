---
story: "4-9"
epic: 4
title: Signals endpoint with cancel, retry, and continue
requirements: [FR-8 (plan stale continue), FR-11 (push retry), FR-19 (done checkpoint continue), FR-20 (retry, cancel), AR-18]
binds: [AD-8, AD-13, AD-14]
---

# Story 4.9 — Signals endpoint with cancel, retry, and continue

As the Operator,
I want one endpoint for every action on a Run, refusing what the Run's state does not admit and applying the rest exactly once,
So that cancelling, retrying, and continuing are as safe as reading.

## Scope

**In:** `POST /api/v1/runs/{id}/signals {kind, payload}` for every kind (validation for all, effects for `cancel`, `retry`, `continue` on `checkpoint` rows and `plan_stale`), the cancel effects (`kill_group`, `engine.cancel`, worktree removal, branch deletion), `admitted_signals` in the Run read model, tests.
**Out:** `answer`, `skip_*`, `budget_raise`, `continue` on `protected_path`, `terminal_*` effects (Epics 5, 6) — they return 409 `not available yet` after validation.

## Binding rules (inlined)

- **Endpoint.** Body `{kind: SignalKind, payload: {}}`; `signal_run` (4.5) validates and writes; 409 problem `signal {kind} invalid for status {status} / park {kind}`; 200 with the updated `RunSummary` and `admitted_signals: [kind]` computed by `application/rules/signals.admitted_signals(run)`.
- **Cancel (AD-13).** Requires `payload.confirm: true` (the UI's confirm modal) `[ASSUMPTION]`. After `signal_run` returns `CancelPlan{pgids, worktrees}`: for every recorded live `pgid` → `ProcessRunner.kill_group`; `engine.cancel(run_id)`; for each `run.worktrees[]` entry → `Git.remove_worktree(path)` (force), then `Git.delete_branch(branch)` on origin and locally only when `created_branch and not pushed`; append gate record `cancelled` (actor `operator`, text listing removed worktrees and deleted branches). These are the only worktree writes outside an engine step besides file edits (Epic 6). Idempotent: a missing worktree or branch is logged, not an error.
- **Retry.** Valid on `park_kind ∈ {timeout, push_rejected, misconfigured, internal, verify_failed}`; the row goes `error → queued` and the walker re-executes it as a new Attempt; the executor sees `resume_signal.kind == retry` (4.8's push syncs first).
- **Continue.** On a `checkpoint` row: the writer marks it `done` and queues the successor; on `plan_stale`: the `plan` row goes `done`, successor queued; both resume the engine. (Agent-row continue and protected-path accept arrive with Epics 5–6.)
- **`admitted_signals(run)`** returns, for `needs_you`, the kinds admitted by the AD-13 table for `park_kind` and the park row's kind, minus `terminal_*`; for `queued | running` → `[cancel]`; for terminal statuses → `[]`. This list drives the UI's buttons.

## Acceptance criteria

**Given** a Run parked `plan_stale`
**When** `POST /runs/{id}/signals {kind: continue}` is called
**Then** 200, the `plan` row is `done`, the next row `queued`, the Run `running`, the record has `continue`, and the engine received the signal.

**Given** a Run parked on a `checkpoint` row
**When** `continue` is signalled
**Then** the row is `done`, the successor `queued`, and the walker proceeds (e2e).

**Given** a Run parked `push_rejected`
**When** `retry` is signalled
**Then** the row is `queued`, a new Attempt runs, and the record has `retry`.

**Given** a `running` Run with a live process and a worktree on a branch it created and never pushed
**When** `cancel {confirm: true}` is signalled
**Then** the process group is killed, the workflow is cancelled, the worktree directory is gone, the branch is deleted, planned rows are `skipped`, the Run is `cancelled`, and the record text names the worktree and branch; **and** with `pushed: true` the branch survives.

**Given** a `done` Run
**When** any signal is posted
**Then** 409 problem+json.

**Given** `answer` posted on a `blocked` Run in this epic
**When** validated
**Then** 409 with `detail: answer not available yet` (validation passed, effect absent).

**Given** `GET /runs/{id}` for a Run parked `push_rejected`
**When** read
**Then** `admitted_signals` is `[retry, skip_epic, cancel]`.

## Implementation notes

- `api/routers/runs.py::post_signal` → `application/use_cases/signals.py::handle_signal` (orchestrates `signal_run` + effects through ports); keep the router thin.
- `CancelPlan` from 4.5; `Git.remove_worktree`, `delete_branch` from 4.8.
- e2e: `tests/e2e/test_signals.py` on the local remote.

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

Spine AD-13 (table, cancel effects), AD-8. PRD FR-20 (retry, cancel), FR-19 (done checkpoint), FR-8 (plan stale), §4.6 table.
