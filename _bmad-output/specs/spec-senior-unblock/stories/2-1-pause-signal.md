---
title: 'Pause signal'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'a976f2d53431e51beaf7718e3c6135555f27709c'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Run that has not stopped itself cannot be stopped. The Operator's only lever on a running Run is `cancel`, which kills the work, and a wait for a natural stop can take hours.

**Approach:** The AD-13 `pause` row (CAP-8). `pause` on a `running` Run records a request on the Run. When the row now executing finishes and the Run would carry on, `apply_step_result` parks it `paused` on the next row instead. Nothing is killed. The stop admits `continue` and `cancel`, and `continue` resumes at the row it parked on. The Run page offers *Pause* beside *Cancel run* while the Run runs, behind a confirm.

## Boundaries & Constraints

**Always:**
- `pause` is valid only when the Run is `running` and no pause is already requested; otherwise 409, nothing written. It writes `run.pause_requested = true` and one gate record (`pause`, actor operator). It calls neither `engine.signal` nor `engine.cancel`.
- `apply_step_result` is the only writer of the park (AD-8). The park happens where it queues a successor: the next row is queued, the Run parks `paused` with `park_path` = that row, and the flag is cleared. `ParkKind` gains `paused`; the park takes a `park_seq` like any other.
- Any write that moves the Run out of `running` clears the flag, so a row that parks by itself keeps its own stop, and a Run that ends, fails or is cancelled carries no pending pause. One rule in `set_run`.
- A row that does not finish (a Template retry, a consult requeue, a redispatch) leaves the flag set; the pause lands at the first row boundary after it.
- `paused` admits `continue` and `cancel` only. `continue` queues nothing itself: the successor was queued at the park, so the walker's `next_row` finds it. The row that runs next is handed no resume signal, because nothing was asked of it: a `continue` that resumed a pause is not the `continue` that approves a spec checkpoint or a stale plan.
- `paused` renders `CHK` everywhere a token is derived, backend and web-client.
- The 30-day `recv` expiry applies to `paused` as to any park.
- `DBOS_APPLICATION_VERSION` stays `1`: the park is written inside the existing `apply_result` step, and no step is added, removed or reordered.

**Never:** No new status token. No signal other than `continue`, `cancel` (and `session_start`, which story 2-3 adds) at a `paused` stop: not `skip_*`, `retry`, `answer`, `terminal_start`. No edit to an existing test file beyond the declared revisions below. `AGENTS.md` is not touched. No container is stopped.

**Decided:** Hard rule 1(b), AD-13 table (`pause` row, 2026-11-01 amendment), 2026-11-02:
- `test_run_statuses.py`: the park kinds tuple gains `paused` and the signal kinds tuple gains `pause`, each last; the counts in the two test names follow.
- `test_terminal_signals.py`: `REFUSED_WHILE_RUNNING` excludes `pause`, which AD-13 admits on a running Run.
- `test_run_admitted_signals.py`, `test_run_events_use_case.py`, `test_signals_router.py`: a running Run with no pause requested admits `["pause", "cancel"]`.
- Whatever else a full `make test` shows pinning the same two lists is revised the same way and named in the hand-back.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Request | `pause`, Run `running`, no request | `pause_requested = true`, one `pause` record, Run still `running`, engine untouched | N/A |
| Repeated | `pause` with a request pending | Nothing written | 409 |
| Not running | `pause` on `needs_you`, `queued`, or terminal | Nothing written | 409 |
| Row finishes, successor exists | flag set; row `done` or `skipped`-through | Successor `queued`, Run `needs_you`, `park_kind = paused`, `park_path` = successor, flag cleared, `park_seq` +1, one `paused` record | N/A |
| Last row | flag set; the finishing row has no successor | Run `done`, flag cleared, no park | N/A |
| Row parks itself | flag set; row blocks, errors to a stop, or goes over budget | The row's own stop stands; flag cleared | N/A |
| Consult requeue (1-4) | flag set; stop sent to a senior | Row requeued, Run `running`, flag still set | N/A |
| Template retry or redispatch | flag set; row re-queued | Flag still set; the park lands after the row passes | N/A |
| `on_fail: continue` | flag set; row `error`, carries on | Treated as finishing: parks `paused` on the successor | N/A |
| Continue | `continue` at `paused` | Run `running`, park fields cleared, the parked row runs next with no resume signal | N/A |
| Other signals | `answer`, `retry`, `skip_*`, `budget_raise`, `terminal_start` at `paused` | Nothing written | 409 |
| Cancel | `cancel` at `paused` | Run `cancelled`; the queued row is `skipped` | N/A |
| Expiry | `paused` for 30 days | Run `failed`, `parked 30 days` | N/A |
| Cancel with a request pending | `cancel` on a `running` Run | Run `cancelled`, flag cleared | N/A |
| Read models | Run `running` | `admitted_signals` = `["pause", "cancel"]`, or `["cancel"]` once requested; `pause_requested` present only when true | N/A |
| Read models | Run `paused` | `admitted_signals` = `["continue", "cancel"]`; token `CHK` | N/A |
| Run page | Run running, pause not requested | *Pause* beside *Cancel run*; clicking asks for confirmation, confirming posts `{kind: pause}` with no `stop` | Server's 409 detail shows in the existing error readout |
| Run page | pause requested | A line stating the Run parks when the current step ends; no *Pause* | N/A |
| Run page | `paused` stop | `CHK`; reason; *Continue* and *Cancel run* | N/A |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `domain/statuses.py` -- `ParkKind` gains `paused`; `SignalKind` gains `pause`, last; `CHK_PARK_KINDS` names the two stops that render `CHK`. `domain/entities/run.py` -- `pause_requested: bool = False`, `NOT NULL` with a default, outside the frozen nullable set.
- `application/rules/signals_table.py` -- `VALID["pause"]` (`run_statuses = {running}`, extra: no request pending, `operator_action`); `paused` joins `continue`'s park kinds and is subtracted from `skip_story`, `skip_epic` and `terminal_start`. `application/rules/signals.py::run_admitted_signals` -- `("pause", "cancel")` for a running Run with no request; `("continue", "cancel")` at `paused`.
- `application/use_cases/pause_stop.py` (new) -- `park_paused`, the reason text, and `resumed_a_pause`.
- `application/use_cases/apply_step_result.py::_advance` -- parks through `park_paused` when the flag is set. `writers.py::set_run` -- the clearing rule. `signal_effects.py` -- the `pause` effect, and `continue` at `paused` writes no row.
- `application/use_cases/walk_context.py::_resume_signal` -- a record that resumed a pause is not handed to the row.
- Token readers: `run_views_alert.py`, `project_runs.py`, `graph.py`.
- `api/schemas/common.py`, `runs.py` -- `pause_requested`, omitted while false, as `park_seq` is.
- `infrastructure/db/models/run.py`, `repositories/runs.py`, `alembic/versions/0025_run_pause_requested.py` -- column and both mapping directions.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- `make openapi` only.
- `web-client/src/lib/run/detail.ts::runToken`, `src/lib/run/pause.ts` (new), `src/components/run/PauseControl.tsx` (new), `StopBody.tsx`, `signals.ts::signalLabel`.
- `deploy/kit/skills/orchestrator/references/api.md` -- the signal and the park kind.

## Tasks & Acceptance

**Execution:**
- [ ] `backend-api/tests/unit/application/test_pause_signal.py`, `test_pause_stop.py`, `test_pause_rules.py`, `tests/unit/test_pause_schemas.py`, `tests/unit/test_run_pause_column.py`; `web-client/tests/unit/run-pause.test.ts`, `run-pause-control.test.tsx` -- new; every matrix row through the shared fakes, each seen failing first -- TDD.
- [ ] The declared revisions under Decided.
- [ ] Code Map in order: domain and migration, rules, writers and effects, read models, then `make openapi`, then web-client.

**Acceptance Criteria:**
- Given a running Run with a pause requested whose current row finishes, when the next row exists, then the Run is `needs_you` parked `paused` on that row and the row is `queued`.
- Given that stop, when the Operator sends `continue`, then the Run is `running` and that row runs as its first dispatch (no resume signal, so a spec checkpoint still halts).
- Given a pause requested during the Run's last row, then the Run ends `done` and the flag is false.

## Implementation Notes

Implemented in one session, tests first: the four new backend test files were seen failing on import before any source existed; the web-client files were written before the wiring and run after it.

**`DBOS_APPLICATION_VERSION` stays `1`.** Nothing under `infrastructure/dbos/` changed, the walker still declares its five steps, and the park is written by `apply_step_result` inside the existing `apply_result` step. A Run in flight across the upgrade replays the same step sequence.

**The resume signal.** `walker.py` carries the kind of the waking signal into the next row as `resume_signal`, found as the latest gate record of that kind. A `continue` that lifted a pause would have reached the next row as the `continue` that approves a stop: a spec-checkpoint row would not halt, and `plan.check` would finish without re-reading. `walk_context._resume_signal` therefore drops a record whose latest preceding stop is `paused`.

**Revised tests (rule 1(b), AD-13 table, 2026-11-02):** `test_run_statuses.py` (both tuples, names now `thirteen`), `test_terminal_signals.py` (`REFUSED_WHILE_RUNNING`), `test_run_admitted_signals.py`, `test_run_events_use_case.py`, `test_run_events_router.py`, `test_signals_router.py` (a running Run admits `["pause", "cancel"]`), `test_signal_rules.py` (the every-park-kind loop for `skip_step` skips `paused`). Each revision names this story.

**The row lock, and story 2-3.** Review found that `signal_run` and `apply_step_result` read the Run without a lock while the adapter writes only the columns an entity changed. A `pause` committed between `apply_step_result`'s read and its park survived a Run that had since parked, finished or failed, and the Run then paused unasked one row after the Operator answered. `RunRepository.get_for_update` (`SELECT … FOR UPDATE` with `populate_existing`; the shared fake records the call and returns the Run) is added here, used by `require_run(..., lock=True)` in `signal_run`'s three units of work and in `apply_step_result`. **Story 2-3 plans the same method under the same name: it reuses this one and adds no second.** Migration `0025` will need renumbering against 2-3's. `session_start` is not in `paused`'s admitted list: its signal kind does not exist at this baseline.

Not run here: `make e2e`, `make e2e-ui` (the new `run-detail-pause.spec.ts` is unrun) and `make durability`. `make lint` and `make test` pass: 8863 backend and 1729 web-client tests, 100% branch coverage on `domain` and `application`.

## Spec Change Log

## Review Triage Log

| Finding | Layer | Verdict | Route | Evidence and action |
| --- | --- | --- | --- | --- |
| A `pause` committed after `apply_step_result` reads the Run leaves `pause_requested = true` on a Run that parked itself, finished or failed; `signal_run` validating a stale `running` read does the same | edge, verification | high | patch | Reproduced in `test_pause_race.py` with a repository that writes only changed columns. Both writers read under `get_for_update`; the port, adapter (FOR UPDATE, `populate_existing`, `test_run_lock_adapter.py`) and fake added. Story 2-3 reuses the method. |
| A pause landing after a redispatch parks on a `done` row between the target and the failed verify row, naming a row that will not run | edge | medium | patch | Reproduced in `test_pause_redispatch.py`. `park_before_next` names the queued row, or queues and names the verify row `_sent_back` would run. |
| "Nothing killed" test never checked the process runner or the cancel plan | verification | low | patch | `test_pause_kills_nothing.py` asserts no `kill_group`, `remove_worktree` or `delete_branch` call and no cancel plan. |

## Verification

**Commands:**
- `make lint` -- expected: passes, including import-linter and test pairs.
- `make test` -- expected: passes, with domain and application at 100% branch coverage.
- `make openapi` -- expected: no drift after generation.
