---
title: 'after {run_id} — dependencies between Runs'
type: 'feature'
created: '2026-09-18'
status: 'in-review'
baseline_revision: '0c6de7a5425c821c1fe5a0406ec898f25614b1a1'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** A saved Run (story 5-3) cannot express "start only after Run X finishes"; every dependency must be managed manually, and a predecessor's failure leaves orphan saved Runs in the queue with no indication of why they are stuck.

**Approach:** Add `after_run_id` to `RunIn`; the terminal transition writers (`apply_step_result` for done/failed, `signal_run` for cancel) resolve saved dependents in the same unit of work — enqueueing on `done`, parking `needs_you + park_kind=dependency` on `failed|cancelled`. A startup sweep re-enqueues any dependency run whose predecessor landed `done` before the container crashed. Continue on a dependency park re-enqueues the saved run (start anyway); Cancel cancels it; engine.cancel is a no-op for runs never enqueued. `list_queue` renders the "waiting for run {x}" reason.

## Boundaries & Constraints

**Always:** Two-writer rule (AD-8) — `apply_step_result` and `signal_run` are the sole status writers; engine.enqueue from within them is the AD-8 stated exception (same as story 5-3's `start` signal); `after_run_id` may only be set when `save=True` (saved Runs only, never running or queued-engine Runs); `make lint` and `make test` green; `make openapi` regenerated; TDD — tests exist and fail before implementation; no existing test file modified; new settings land in `.env.example` + typed settings together (none needed); domain and application never import fastapi, sqlalchemy, or dbos.

**Block If:** Any code path that polls for dependency resolution (AD-8: no poller, no third writer); any path that calls `engine.signal` instead of `engine.enqueue` for dependency Continue or for done-dependent activation; any new `RunStatus` token; `after_run_id` set on a non-saved (engine_ref non-empty) Run.

**Never:** A dependency park with `park_path` set (it is always null — the run has no running step); expire a dependency-parked Run (the 30-day recv expiry must be skipped for `park_kind="dependency"`); write `engine_ref` before it is received from `engine.enqueue`; call `engine.cancel` when `engine_ref` is empty (no workflow exists to cancel).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behaviour | Error Handling |
|----------|--------------|---------------------------|----------------|
| Set dependency at save time | `POST /runs` `save:true, after_run_id:<X>` | Run created, `after_run_id=X`, `engine_ref={}`, `status=queued`, `waiting="waiting for run X"` | — |
| after_run_id without save | `POST /runs` `save:false, after_run_id:<X>` | 409 Conflict: after_run_id requires save=true | 409 |
| Predecessor done → dependent enqueued | Run X reaches done; Run Y has `after_run_id=X`, `engine_ref={}` | engine.enqueue(Y) called; `engine_ref` and `after_run_id=null` written in one UoW | — |
| Predecessor failed → dependent parked | Run X reaches failed; Run Y has `after_run_id=X`, `engine_ref={}` | Run Y parked: `needs_you`, `park_kind=dependency`, `park_reason="run X ended failed"`, `park_path=null` | — |
| Predecessor cancelled → dependent parked | Run X cancelled; Run Y has `after_run_id=X`, `engine_ref={}` | Same as failed case with `status=cancelled` in reason | — |
| Continue on dependency park | `POST /runs/{id}/signals {"kind":"continue"}`, `park_kind=dependency` | engine.enqueue called; `engine_ref` and cleared park written; `SignalOutcome(resumed=False)` | — |
| Cancel on dependency park | `POST /runs/{id}/signals {"kind":"cancel"}`, `park_kind=dependency` | Run cancelled; `engine.cancel` NOT called (engine_ref empty); rows marked skipped | — |
| Startup sweep | Container restarts; Run Y has `after_run_id=X`, `engine_ref={}`, Run X is done | engine.enqueue(Y) called; `engine_ref` written | — |
| Dependency never expires | Run Y dependency-parked for >30 days | Run Y stays `needs_you`; expire_run skipped for `park_kind=dependency` | — |
| Queue view — waiting | Run Y saved with `after_run_id=X`, `engine_ref={}` | `GET /queue` row reason = `"waiting for run X"` | — |
| Queue view — saved (no dependency) | Run Y saved, `after_run_id=null`, `engine_ref={}` | `GET /queue` row reason = `"saved — not started"` | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/statuses.py:42-54` — `ParkKind` literal; add `"dependency"` token; `PARK_KINDS` tuple; `test_gate_events.py` pins structural composition, adding to `ParkKind` is safe
- `backend-api/src/orchestrator/application/use_cases/writers.py:69-86` — `WriterPorts`; add `engine: WorkflowEngine | None = None` (default preserves every existing constructor call); import `WorkflowEngine` from `domain/ports/engine.py`
- `backend-api/src/orchestrator/application/use_cases/resolve_dependents.py` — NEW: `REASON_DEPENDENCY_ENDED = "run {x} ended {status}"`; `_find_saved_dependents(runs, predecessor_id) -> list[Run]` filters `runs.list_by_status("queued")` for `r.after_run_id == predecessor_id and not r.engine_ref`; `resolve_for_done(ports: WriterPorts, predecessor: Run) -> list[Run]` returns found dependents without changing their DB state (engine.enqueue happens post-commit); `resolve_for_failed_or_cancelled(ports: WriterPorts, predecessor: Run) -> None` calls `park_run(ports, dep, Park(kind="dependency", reason=REASON_DEPENDENCY_ENDED.format(x=str(predecessor.id), status=predecessor.status), path=None))` for each
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py:137-165` — `apply_step_result`; after `_route()` inside the UoW, call `resolve_for_failed_or_cancelled(ports, run)` when `run.status == "failed"`, or capture `done_deps = resolve_for_done(ports, run)` when `run.status == "done"`; after `ports.uow.commit()`, for each dep in `done_deps`: call `ports.engine.enqueue(dep.id, partition_key=f"{dep.repository_id}:{dep.partition_branch or dep.inputs.get('base_branch', '')}")`, then in a second `with ports.uow:` commit call `set_run(ports, dep, engine_ref=engine_ref, after_run_id=None)` — exact pattern from `_start_saved_run` in signal_run.py; skip engine.enqueue when `ports.engine is None`
- `backend-api/src/orchestrator/application/use_cases/signal_run.py:96-122` — `signal_run`; add constant `CONTINUE_DEPENDENCY = "continue"`; add dedicated branch before generic flow: `if signal.kind == "continue" and run.park_kind == "dependency": return _continue_dependency_park(ports, run_id, signal)`; in `_tell_the_engine`, guard `engine.cancel`: only call when `run.engine_ref` is truthy — if `not run.engine_ref`, the run was never enqueued and the cancel is a no-op
- `backend-api/src/orchestrator/application/use_cases/signal_run.py` — `_continue_dependency_park(ports, run_id, signal) -> SignalOutcome`: calls `validate(run, None, signal)`, records `Entry(event="continue", actor="operator", text="continued by the operator")`, calls `set_run(writers, run, status="queued", park_kind=None, park_path=None, park_reason=None, after_run_id=None)` directly (same direct-set pattern as `_start_saved_run`, no `run_transition` needed since the state machine has no `needs_you → queued` pair), commits, calls `engine.enqueue`, writes `engine_ref` in second UoW, returns `SignalOutcome(run=..., resumed=False)`
- `backend-api/src/orchestrator/application/use_cases/signal_run.py` — `signal_run` cancel path: inside the existing `with writers.uow:` block, after `effect = EFFECTS[signal.kind](...)` and before `ports.uow.commit()`, call `resolve_for_failed_or_cancelled(writers, run)` when `signal.kind == CANCEL` and the run will reach `cancelled` — only for saved (not-yet-enqueued) dependents
- `backend-api/src/orchestrator/application/use_cases/queue.py:41-102` — add `REASON_WAITING_DEPENDENCY = "waiting for run {x}"`; update `_saved_row`: if `run.after_run_id is not None`, use `REASON_WAITING_DEPENDENCY.format(x=str(run.after_run_id))`; update `_order_key` to return `(3, 0)` for both `REASON_SAVED` and `REASON_WAITING_DEPENDENCY`
- `backend-api/src/orchestrator/application/rules/signals_table.py:250-255` — `VALID["continue"]`; add `"dependency"` to its `park_kinds` frozenset — enables validation to pass for Continue on a dependency-parked run; the dedicated handler in `signal_run` intercepts it before the generic `_continue` effect fires
- `backend-api/src/orchestrator/application/rules/signals.py` — `run_admitted_signals`; ensure dependency-parked run returns `("continue", "cancel")` — "cancel" is already admitted via `ANY_PARK`; "continue" is admitted once `"dependency"` is in its `park_kinds` list; verify the function routes correctly for `park_kind="dependency"` 
- `backend-api/src/orchestrator/application/use_cases/create_run.py:90-130` — `CreateRunRequest`: add `after_run_id: UUID | None = None`; in `create_run`, after `_refuse_failing_lines`: if `req.after_run_id is not None and not req.save`, raise `Conflict("after_run_id requires save=true")`; write `after_run_id=req.after_run_id` on `Run(...)` constructor call
- `backend-api/src/orchestrator/api/schemas/runs.py:55-89` — `RunIn`: add `after_run_id: UUID | None = None`; update `as_request()` to pass `after_run_id=self.after_run_id`
- `backend-api/alembic/versions/0015_run_after_run_id_fk.py` — NEW migration; `op.create_foreign_key("fk_run_after_run_id", "run", "run", ["after_run_id"], ["id"])` (nullable self-reference); `down_revision = "0014_run_after_run_id"`; deferred from story 5-3
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` — add `sweep_dependency_residue(settings: Settings) -> None`; uses `_SERVING` guard (no-op outside serving context); opens a session, queries saved Runs with non-null `after_run_id` whose named predecessor has `status=done`, calls `engine.enqueue` for each, writes `engine_ref + after_run_id=None` in a UoW
- `backend-api/src/orchestrator/main.py:182-204` — `run_migrations`; call `sweep_dependency_residue(settings)` after `launch_engine()` — crash residue is enqueued before the server binds
- `backend-api/src/orchestrator/infrastructure/dbos/walker.py` — find the `recv` expiry path; add guard: if `run.park_kind == "dependency"`, skip `expire_run` (a dependency park never expires per SPEC); check how the walker's recv timeout calls expire_run and add the `park_kind` check there
- `backend-api/tests/unit/fakes/runs.py` — read only; `FakeRunRepository` already has `list_by_status` which filters; `_find_saved_dependents` uses it — no fake changes needed

## Tasks & Acceptance

**Execution:**

- `backend-api/tests/unit/application/test_dependency_resolution.py` — NEW (TDD first): test `resolve_for_done` finds saved dependents (queued, engine_ref={}, after_run_id=predecessor.id) and returns them without writing; test finds only engine_ref-empty runs; test `resolve_for_failed_or_cancelled` parks each as `needs_you + park_kind=dependency + park_path=None + reason="run X ended failed"`; use `FakeRunRepository`, `FakeGateRecordRepository`, `FakeUnitOfWork`

- `backend-api/tests/unit/application/test_apply_step_result_dependents.py` — NEW (TDD first): test done run with one saved dependent calls `ports.engine.enqueue`, writes `engine_ref` and `after_run_id=None` on the dependent; test failed run parks dependent as dependency; test no-op when no saved dependents exist; use `FakeRunRepository`, `FakeWorkflowEngine` from `tests/unit/fakes/`

- `backend-api/tests/unit/application/test_signal_run_dependency.py` — NEW (TDD first): test `continue` on dependency-parked run calls `engine.enqueue`, writes engine_ref, clears park, returns `resumed=False`; test `cancel` on dependency-parked run does NOT call `engine.cancel` (engine_ref was empty); test cancel on dependency-parked run parks each saved dependent as dependency; test `cancel` on an enqueued run DOES call `engine.cancel` (engine_ref non-empty)

- `backend-api/tests/unit/application/test_queue_dependency.py` — NEW (TDD first): test `list_queue` saved row with `after_run_id` set has reason `"waiting for run X"`; test saved row without `after_run_id` still has reason `"saved — not started"`; both sort at `(3, 0)`

- `backend-api/tests/unit/application/test_create_run_after.py` — NEW (TDD first): test `create_run` with `save=True, after_run_id=X` sets `run.after_run_id=X`; test `create_run` with `save=False, after_run_id=X` raises `Conflict`; test `save=True, after_run_id=None` leaves `after_run_id` null

- `backend-api/src/orchestrator/domain/statuses.py` — add `"dependency"` to `ParkKind` literal and `PARK_KINDS` tuple

- `backend-api/src/orchestrator/application/use_cases/writers.py` — add `engine: WorkflowEngine | None = None` to `WriterPorts`; add import `from orchestrator.domain.ports.engine import WorkflowEngine`

- `backend-api/src/orchestrator/application/use_cases/resolve_dependents.py` — NEW: `REASON_DEPENDENCY_ENDED`, `_find_saved_dependents`, `resolve_for_done`, `resolve_for_failed_or_cancelled` as described in Code Map

- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py` — call `resolve_for_failed_or_cancelled` for failed runs inside UoW; call `resolve_for_done` for done runs inside UoW and post-commit engine.enqueue + engine_ref write (skipped if `ports.engine is None`)

- `backend-api/src/orchestrator/application/rules/signals_table.py` — add `"dependency"` to `VALID["continue"].park_kinds`

- `backend-api/src/orchestrator/application/use_cases/signal_run.py` — add `_continue_dependency_park` dedicated handler; add Continue-on-dependency dispatch before generic flow; guard `engine.cancel` in `_tell_the_engine` on `not run.engine_ref`; resolve cancelled dependents inside cancel UoW via `resolve_for_failed_or_cancelled`

- `backend-api/src/orchestrator/application/use_cases/queue.py` — add `REASON_WAITING_DEPENDENCY`; update `_saved_row` for `after_run_id`; update `_order_key`

- `backend-api/src/orchestrator/application/use_cases/create_run.py` — add `after_run_id: UUID | None = None` to `CreateRunRequest`; validate `after_run_id` requires `save=True`; write to Run entity

- `backend-api/src/orchestrator/api/schemas/runs.py` — add `after_run_id: UUID | None = None` to `RunIn`; update `as_request()`

- `make openapi` — regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts`; `after_run_id` appears in `RunIn`

- `backend-api/alembic/versions/0015_run_after_run_id_fk.py` — NEW migration; FK constraint `after_run_id → run.id`; `down_revision = "0014_run_after_run_id"`

- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` — add `sweep_dependency_residue(settings: Settings) -> None` using `_SERVING` guard; import required repos; query saved Runs with non-null `after_run_id` whose predecessors are done; enqueue each and write `engine_ref + after_run_id=None`

- `backend-api/src/orchestrator/infrastructure/dbos/walker.py` — find recv-expiry handler; add `park_kind == "dependency"` guard to skip `expire_run`

- `backend-api/src/orchestrator/main.py` — call `sweep_dependency_residue(settings)` after `launch_engine()` in `run_migrations`

**Acceptance Criteria:**

- Given `POST /runs` with `save: true, after_run_id: <X>`, when `create_run` succeeds, then the returned Run has `after_run_id=X`, `engine_ref={}`, `status=queued`, and `waiting="waiting for run X"`.
- Given `POST /runs` with `save: false, after_run_id: <X>`, when `create_run` runs, then 409 Conflict is returned.
- Given Run X reaches `done` and Run Y has `after_run_id=X, engine_ref={}`, when `apply_step_result` commits X's terminal status, then `engine.enqueue(Y.id, ...)` is called and Y's `engine_ref` and `after_run_id=None` are written atomically.
- Given Run X reaches `failed` (or `cancelled`) and Run Y has `after_run_id=X, engine_ref={}`, when the terminal transition commits, then Y is parked `needs_you, park_kind=dependency, park_path=null, park_reason="run X ended failed"` in the same unit of work.
- Given `POST /runs/{id}/signals {"kind":"continue"}` on a dependency-parked run, then `engine.enqueue` is called, `engine_ref` and cleared park fields are written, and the response has `resumed=false`.
- Given `POST /runs/{id}/signals {"kind":"cancel"}` on a run with `engine_ref={}`, then `engine.cancel` is NOT called.
- Given a saved Run with `after_run_id=X` in `GET /queue`, then its `reason` is `"waiting for run X"` and `position` is null.
- Given a container restart where Run Y has `after_run_id=X, engine_ref={}` and Run X has `status=done`, when the app starts, then `engine.enqueue(Y.id, ...)` is called before the server binds.
- Given a dependency-parked Run that has been waiting >30 days, when the walker's recv expiry fires, then `expire_run` is NOT called for that run.
- Given `make lint` and `make test` after all changes, then both pass green with 100% branch coverage on `domain/` and `application/`.

## Design Notes

**Why `_continue_dependency_park` bypasses `run_transition`:** The state machine has no `(needs_you, X) → queued` pair — the only resuming event from `needs_you` is `continue → running`. A dependency-parked run was saved (never enqueued), so transitioning to `running` and then calling `engine.enqueue` would create a status mismatch: the walker's `start_attempt` expects `queued`, not `running`. Using `set_run` directly to set `status="queued"` is an established precedent from `_start_saved_run` (which also uses `set_run` without `run_transition` for engine-related status management). The test for `_continue_dependency_park` covers this path explicitly.

**Why `after_run_id` is not cleared in the predecessor's done UoW (for the crash-residue guarantee):** If we cleared `after_run_id` atomically with the predecessor going done, a crash after that commit but before `engine.enqueue` would leave the dependent with `after_run_id=None, engine_ref={}` — indistinguishable from any regular saved run. Keeping `after_run_id` set until `engine_ref` is written (atomically in the second UoW) means the startup sweep can always find crash-residue by `after_run_id IS NOT NULL AND engine_ref={} AND predecessor.status=done`.

**Why `engine: WorkflowEngine | None = None` on `WriterPorts`:** `apply_step_result` has no engine reference; adding it as an optional field follows the `git` and `trajectories` precedent in `WriterPorts` (both default `None`) and keeps the engine.enqueue calls within the writer that owns the terminal transition, preserving the two-writer semantics.

**`continue` signal park_kinds extension:** Adding `"dependency"` to `VALID["continue"].park_kinds` enables the signals table to admit Continue on a dependency park for validation purposes. The dedicated handler in `signal_run` intercepts it before the generic `_continue` effect fires, so `_parked(park_row)` (which asserts park_row is not None) is never reached — dependency parks have `park_path=None` and no park row.

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy (domain + application), import-linter, prettier, tsc, env-contract, test-pairs all pass
- `make test` -- expected: 100% branch coverage on `domain/` and `application/`; all new and existing tests green
- `make openapi` -- expected: no drift after schema changes committed

## Spec Change Log

## Review Triage Log
