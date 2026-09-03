---
story: "4-5"
epic: 4
title: Status writers start_attempt, apply_step_result, signal_run
requirements: [FR-10 (attempt counters), FR-12, FR-16..FR-20 (transitions), NFR-1, NFR-2, AR-11]
binds: [AD-8, AD-9, AD-13, AD-18]
---

# Story 4.5 — Status writers `start_attempt`, `apply_step_result`, `signal_run`

As the Operator,
I want every change of a Run's or a Step's status to go through three small, fully tested use cases and to leave a line in the gate record,
So that no action is ever applied twice or half-way, and the record on screen is the record of what happened.

## Scope

**In:** `application/use_cases/start_attempt.py`, `apply_step_result.py`, `signal_run.py`, the AD-13 validity table as data, the gate-record writes, unit tests with 100 % branch coverage.
**Out:** the effects of signals in worktrees (executors read `resume_signal`; 4.8, 4.9, Epics 5–6); the engine call implementation (4.6).

## Binding rules (inlined)

- **`start_attempt(run_id, seq) -> Attempt`.** Row `queued → running` (`step_transition`); new `Attempt{n = previous n + 1 or 1, started_at, engine_ref}`; on the Run's first row start: `run.status queued → running`, `started_at`, gate record `start` (actor `machine`, text `run started`). One unit of work, committed before the executor runs.
- **`apply_step_result(run_id, seq, result: StepResult)`.** In one unit of work: (a) close the latest Attempt (`ended_at`, `status`, `output_ref`, `exit_code` if provided); (b) row status ← `result.status` through `step_transition`; `reason` ← `result.reason`; (c) if `result.redispatch` and the target row's `redispatch_count < max`: target row `done → queued` (`redispatch` event), `redispatch_count += 1`, gate record `redispatch` (text `verify failed, story re-dispatched {n}/{max}`); the rows between target and current stay as they are (the walker re-walks from the target); if exhausted: convert to `Park{verify_failed, "verify failed {max+1}/{max+1}"}`; a redispatch whose target row is `skipped` → `Park{verify_failed, "re-baseline failed after skip"}`; (d) if `result.park`: `run.status → needs_you`, `park_kind`, `park_path = row.path`, `park_reason`, gate record `event = park.kind`, `text = reason`, `actor machine`; (e) else if row ended `done | skipped`: successor row (next `seq`) `planned → queued`; when there is no successor: `run.status → done`, `ended_at`, gate record `done`; (f) `on_fail: fail` result (`result.status error` with `reason` and `park None` and `with_resolved.on_fail == fail`) → `run.status → failed`, gate record `failed`, text = reason; (g) if `run.status ≠ running` at entry (cancelled meanwhile): log `late result ignored` and write nothing. Budget's double record (AD-8) is added by Epic 5 through a hook `after_route(run, row, result)`; leave the seam.
- **`signal_run(run_id, signal: Signal) -> SignalOutcome`.** Validate against the table below (else `Conflict` → 409 with `signal {kind} invalid for status {status} / park {kind}`); append the gate record (`event = kind`, `actor operator`, `text` = payload text or the fixed phrase); apply the transition; clear `park_*` (except where noted); call `engine.signal(run_id, signal)` (except `budget_raise` on a `blocked | checkpoint` row and the `terminal_*` kinds, which do not resume); return the outcome.

| Kind | Valid when | Writes (besides the record) | Row transition |
| --- | --- | --- | --- |
| `answer {text}` | `needs_you`, `park_kind ∈ {blocked, checkpoint}`, park row kind `agent` | `run → running` | `blocked → queued` / `checkpoint → queued` |
| `continue` | `needs_you`, `park_kind ∈ {checkpoint, protected_path, plan_stale}` | `run → running`; `protected_path`: `accepted_paths += payload.files`, record payload | `checkpoint` row `→ done` and successor `→ queued`; agent row at checkpoint `→ queued`; `protected_path`: `error → running`; `plan_stale`: row `→ done`, successor `→ queued` |
| `retry` | `needs_you`, `park_kind ∈ {timeout, push_rejected, misconfigured, internal, verify_failed}` or park row `error` | `run → running` | `error → queued` |
| `skip_story` | `needs_you`, `park_kind ∉ {budget, plan_stale, push_rejected}`, `park_path` inside a story frame | `run → running`; every non-terminal `agent`/`checkpoint` row of the frame `→ skipped` (`reason: skipped by operator`); the frame's `git.commit` `with_resolved.message` ← `story {id}: skipped by operator`; the frame's `verify` row `→ queued` (if `skipped · no quality_gate_command`, the `git.commit` row `→ queued`) | as stated |
| `skip_epic` | `needs_you`, `park_kind ∉ {budget, plan_stale}`, `park_path` inside an `epics[i]` frame (or an `epic` Run) | as `skip_story` for the current frame, plus every non-terminal row of the remaining story frames of that epic `→ skipped`; the epic's `push`, `link`, `after` stay `planned` unless `park_kind = push_rejected`, in which case `push` and `link` `→ skipped` and the next epic's first row `→ queued` | as stated |
| `budget_raise {budget_usd}` | `needs_you`, `park_kind = budget`, `budget_usd > spend_usd` | `run.budget_usd`; if the park row is `blocked | checkpoint`: `park_kind ← that status`, Run stays `needs_you`, no `engine.signal`; else `run → running` | none |
| `cancel` | any non-terminal | `run → cancelled`, `ended_at`; every `planned | queued` row `→ skipped`; returns `CancelPlan{pgids, worktrees}` for the caller's effects (4.9) | as stated |
| `terminal_start` | `needs_you`, not `terminal_session` | `terminal_session = true` | none |
| `terminal_release` | `terminal_session` | `terminal_session = false` | none |
| `terminal_resume` | sent by the poll job; `needs_you`, `terminal_session`, park row `blocked` | agent row `→ done` (actor `terminal`), `terminal_session = false`, successor `→ queued`, `run → running` | `blocked → done` |

- **Gate record events** are exactly: park kinds, signal kinds, `redispatch`, `retry_auto` (Epic 5), `start`, `done`, `failed`, `cancelled`, `expired`.
- **Coverage (AD-18):** 100 % branch on the three modules and `domain/statuses.py`.

## Acceptance criteria

**Given** a Run with rows `plan, checkout` and row 1 `queued`
**When** `start_attempt(run, 1)` runs
**Then** row 1 is `running` with Attempt `n=1`, the Run is `running`, and the gate record has `start`.

**Given** row 1 `running`
**When** `apply_step_result` receives `done`
**Then** row 1 is `done`, row 2 is `queued`, and no Run status change occurs; **and** when row 2 is the last and ends `done`, the Run is `done` with the `done` record.

**Given** a result with `park {plan_stale, "plan stale: stories.yaml"}`
**When** applied
**Then** the row is `error`, the Run `needs_you` with `park_kind plan_stale`, `park_path` the row path, and the record event `plan_stale`.

**Given** a `verify` result with `redispatch {target=build, max 1}` and `redispatch_count 0`
**When** applied
**Then** the `build` row is `queued`, its `redispatch_count` is 1, the record says `verify failed, story re-dispatched 1/1`; applied again with count 1 → park `verify_failed`, reason `verify failed 2/2`.

**Given** each row of the signal table, valid and invalid cases
**When** `signal_run` is called
**Then** valid cases write exactly the listed changes and call `engine.signal` when stated; invalid cases raise `Conflict` and write nothing (parametrised tests covering every row and every listed exclusion).

**Given** a cancelled Run
**When** a late `apply_step_result` arrives
**Then** nothing changes and a log line `late result ignored` is emitted.

**Given** `make test` with coverage
**When** run
**Then** the three use cases and `statuses.py` report 100 % branch coverage.

## Implementation notes

- The validity table lives as data in `application/rules/signals.py` (`VALID: dict[SignalKind, Rule]`) so the UI can later fetch admitted signals per park kind (`admitted_signals(park_kind, row_kind)` helper).
- Frame helpers: `rows_in_frame(rows, frame)`, `story_frames_after(rows, frame)` in `application/rules/frames.py`.
- `SignalOutcome{run, resumed: bool, cancel_plan: CancelPlan | None}`.

## Verification

```bash
make lint && make test
```

## Sources for detail only

Spine AD-8 (writer rules, two diagrams), AD-13 (signal table, verbatim), AD-9 (redispatch bounds). PRD FR-10, FR-16..FR-20, §4.6 Stop table.
