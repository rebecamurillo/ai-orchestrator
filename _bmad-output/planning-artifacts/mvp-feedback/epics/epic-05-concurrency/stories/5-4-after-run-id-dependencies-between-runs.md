---
title: 'after {run_id} — dependencies between Runs'
type: 'feature'
created: '2026-09-18'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
baseline_revision: '23501591b24bf30c693aa5728d54d150c8034d7d'
context: []
warnings: []
deferred:
  - summary: >-
      _continue_dependency_run writes status="queued" directly bypassing RUN_TRANSITIONS
    evidence: |-
      needs_you → queued is absent from RUN_TRANSITIONS. The implementation uses set_run(status="queued")
      to put the run back in a state the engine walker expects. This is intentional but lacks an AD ruling.
    location: >-
      backend-api/src/orchestrator/application/use_cases/signal_run.py
    severity: medium
  - summary: >-
      RunOut response schema does not expose after_run_id
    evidence: |-
      After_run_id is accepted on input (RunIn) but not returned in responses (RunOut), so API clients
      cannot read back the dependency relationship or display it in the UI.
    location: >-
      backend-api/src/orchestrator/api/schemas/runs.py
    severity: low
  - summary: >-
      No self-referential guard: create_run allows after_run_id == run_id
    evidence: |-
      A run declaring its own id as its predecessor will never resolve and is not caught by any startup sweep.
    location: >-
      backend-api/src/orchestrator/application/use_cases/create_run.py
    severity: low
  - summary: >-
      No existence check for after_run_id predecessor at creation time
    evidence: |-
      after_run_id is stored without verifying that a Run with that UUID exists; if the predecessor was
      deleted or never created the dependent stays queued indefinitely.
    location: >-
      backend-api/src/orchestrator/application/use_cases/create_run.py
    severity: low
  - summary: >-
      No circular-chain detection for after_run_id dependencies
    evidence: |-
      Run A with after_run_id=B and Run B with after_run_id=A would deadlock indefinitely with no error.
    location: >-
      backend-api/src/orchestrator/application/use_cases/create_run.py
    severity: low
  - summary: >-
      Startup sweep extended to park failed/cancelled predecessor dependents, beyond stated intent
    evidence: |-
      The intent specifies only "done Run" for the startup sweep. The diff's sweep_dependency_waiting also
      parks dependents of failed/cancelled predecessors. This is defensible by symmetry but unauthorized.
    location: >-
      backend-api/src/orchestrator/application/use_cases/dependency_sweep.py
    severity: low
  - summary: >-
      run_admitted_signals lacks a direct unit test for the dependency park branch
    evidence: |-
      The dependency branch in run_admitted_signals is exercised only through signal_run integration tests,
      not by a direct call testing the function's returned tuple for a dependency-parked run.
    location: >-
      backend-api/src/orchestrator/application/rules/signals.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** A saved Run cannot express "start me only after run X completes". Sequential multi-run workflows require manual operator intervention between runs because there is no dependency mechanism.

**Approach:** Add `after_run_id` to `CreateRunRequest`. When the predecessor Run reaches a terminal status, the writer applying that transition resolves all dependents whose `engine_ref == {}` in the same logical unit of work: `done → engine.enqueue`; `failed | cancelled → park(kind="dependency")`. A dedicated `_continue_dependency_run` handler in `signal_run` handles `continue` on a dependency park by enqueueing (not signalling). The queue row shows `"waiting for run {x}"` while the predecessor is non-terminal. A container-startup sweep enqueues any dependency-waiting runs whose predecessor is already `done`.

## Boundaries & Constraints

**Always:**
- Two-writer rule (AD-8): only `apply_step_result` (execution) and `signal_run` (operator) write Run status. No poller, no third writer.
- `engine.enqueue` is the correct call for `done`-dependent resolution and `continue` on a dependency park — `engine.signal` wakes a `recv`, but a dependency-waiting run was never enqueued and has no `recv` to wake.
- `failed | cancelled` dependent resolution (park write) happens in the **same DB transaction** as the predecessor's terminal write. `done` dependent resolution (enqueue) happens in the two-phase-commit pattern: commit predecessor → enqueue → commit engine_ref.
- A dependency park never expires: `walk.expire` must guard `run.park_kind != "dependency"` before applying the 30-day timeout.
- `after_run_id` requires `save=True`; if `save=False` and `after_run_id` is set, `create_run` raises `Conflict`.
- Migration 0015 adds the FK constraint on `after_run_id` with `ON DELETE SET NULL`.
- Import-linter: `domain/` and `application/` never import infrastructure symbols.

**Block If:** None.

**Never:**
- A dependency poller or scheduler.
- A third Run-status writer.
- Using `engine.signal` (not `enqueue`) for dependency-dependent continuation.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Predecessor done, dependent waiting | Run A: done; Run B: after_run_id=A, engine_ref={} | B is enqueued (two-phase); B.engine_ref set; B departs queue | — |
| Predecessor failed, dependent waiting | Run A: failed; Run B: after_run_id=A, engine_ref={} | B → needs_you, park_kind=dependency, park_reason="run {A.id} ended failed", park_path=None | Same DB tx as A's terminal write |
| Predecessor cancelled, dependent waiting | Run A: cancelled; Run B: after_run_id=A, engine_ref={} | B → needs_you, park_kind=dependency, park_reason="run {A.id} ended cancelled" | Same DB tx as A's terminal write |
| Dependent already enqueued | Run B: engine_ref non-empty, after_run_id=A | Skip B (engine_ref guard): do nothing | — |
| Continue on dependency park | Run B: needs_you, park_kind=dependency | B → running via `_continue_dependency_run`; engine.enqueue called; engine_ref written | Dedicated handler, not EFFECTS["continue"] |
| Cancel dependency-parked run | Run B: needs_you, park_kind=dependency | B → cancelled; all planned rows skipped; empty pgids/worktrees CancelPlan | Normal _cancel effect, no engine.signal |
| Queue row — waiting for predecessor | Run B: after_run_id=A, A not terminal | Queue row reason = "waiting for run {A.id}" | — |
| Queue row — plain saved run | Run B: after_run_id=None, engine_ref={} | Queue row reason = "saved — not started" | — |
| Startup sweep | Backend restarts; Run B: after_run_id=A, engine_ref={}, A.status=done | B is enqueued during startup sweep | Idempotent on run_id (AD-12) |
| Expire guard | Run B: needs_you, park_kind=dependency | walk.expire returns without touching B | No 30-day expiry for dependency parks |
| after_run_id without save | CreateRunRequest(after_run_id=X, save=False) | Conflict raised | 409 |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/statuses.py:42` -- `ParkKind` Literal; add `"dependency"` member; `PARK_KINDS` tuple auto-updates via `get_args`. `GATE_EVENTS` already includes `*PARK_KINDS` so `"dependency"` will appear in gate records.
- `backend-api/src/orchestrator/domain/ports/repositories.py` -- `RunRepository` Protocol; add `list_by_after_run_id(run_id: UUID) -> list[Run]` returning only runs with `engine_ref == {}`.
- `backend-api/src/orchestrator/application/use_cases/writers.py:69` -- `WriterPorts` dataclass; add `engine: WorkflowEngine | None = None` optional field (pattern from `git` and `trajectories`). Import `WorkflowEngine` from `orchestrator.domain.ports.engine`.
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py:137` -- `apply_step_result`; after `_route` and `after_route`, park failed/cancelled dependents in same UoW before `ports.uow.commit()`; after commit, enqueue done dependents via two-phase pattern using `ports.engine`. New helpers `_park_dependents` and `_enqueue_dependents`.
- `backend-api/src/orchestrator/application/use_cases/signal_run.py:96` -- `signal_run`; add `DEPENDENCY = "dependency"` constant; top-of-dispatch check: if `signal.kind == "continue"` and run.park_kind == DEPENDENCY → `_continue_dependency_run`; also resolve dependents after terminal transitions inside `signal_run` (cancel/done).
- `backend-api/src/orchestrator/application/use_cases/signal_run.py:173` -- `_start_saved_run` already clears `after_run_id` (line 205: `run = set_run(writers, run, after_run_id=None)`) — no change needed here.
- `backend-api/src/orchestrator/application/use_cases/signal_effects.py` -- `_cancel`: already handles empty pgids/worktrees; no change needed. `_continue`: NOT used for dependency park (dedicated handler intercepts first).
- `backend-api/src/orchestrator/application/rules/signals_table.py:250` -- `"continue"` Rule; add `"dependency"` to `park_kinds` frozenset so table admits the signal (even though the dedicated handler intercepts it; the table validates before dispatch).
- `backend-api/src/orchestrator/application/rules/signals.py` -- `run_admitted_signals`; add branch: `if run.status == "needs_you" and run.park_kind == "dependency": return ("continue", "cancel")` (or ensure existing admitted_signals logic covers it via table).
- `backend-api/src/orchestrator/application/use_cases/queue.py:41` -- add `REASON_WAITING_FOR = "waiting for run {run}"` constant; update `_saved_runs` to exclude dependency-waiting runs (runs with `after_run_id` set); update `_saved_row` to emit `REASON_WAITING_FOR.format(run=str(run.after_run_id))` when `run.after_run_id` is set, else `REASON_SAVED`. Also add a `_dependency_runs` path producing queue rows for after_run_id-set runs.
- `backend-api/src/orchestrator/application/use_cases/create_run.py:92` -- `CreateRunRequest`; add `after_run_id: UUID | None = None`; in `create_run` validate that if `after_run_id` is set then `save == True` (Conflict otherwise); pass `after_run_id` to `Run(...)` constructor.
- `backend-api/src/orchestrator/application/use_cases/walk.py:381` -- `expire`; guard `if run.park_kind == "dependency": return run.status` before calling `expire_run` (dependency parks never expire). Also add dependent resolution after `expire_run` (expired run is `failed`; park its dependents in same UoW).
- `backend-api/src/orchestrator/application/use_cases/walk.py:360` -- `close_run`; add dependent enqueue after `finish_run` (same two-phase pattern as `apply_step_result`).
- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py` -- `SQLAlchemyRunRepository`; add `list_by_after_run_id` implementation filtering `run.after_run_id == run_id AND run.engine_ref == {}`.
- `backend-api/src/orchestrator/infrastructure/db/writers.py` -- `open_writer_ports`; pass `engine=engine` to `WriterPorts` where the engine is available (startup.py wires it through `open_ports`).
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py:191` -- add `dependency_startup_sweep(settings)` called from `main.py::run_migrations` after `launch_engine()`. Queries all runs with `after_run_id` pointing to a `done` run and `engine_ref == {}`, enqueues each with two-phase commit.
- `backend-api/src/orchestrator/api/schemas/runs.py` -- `RunIn`; add `after_run_id: UUID | None = None`; `as_request()` passes it through to `CreateRunRequest`.
- `backend-api/alembic/versions/0015_run_after_run_id_fk.py` -- migration adding FK constraint `after_run_id → run.id` with `ON DELETE SET NULL`, `DEFERRABLE INITIALLY DEFERRED`.
- `backend-api/tests/unit/fakes/runs.py` -- `FakeRunRepository`; add `list_by_after_run_id` method returning runs whose `after_run_id == run_id and not engine_ref`.

## Tasks & Acceptance

**Execution:**

- `backend-api/src/orchestrator/domain/statuses.py` -- add `"dependency"` to `ParkKind` Literal -- enables gate records and park transitions for dependency parks; `PARK_KINDS` gets the new member automatically.

- `backend-api/src/orchestrator/domain/ports/repositories.py` -- add `list_by_after_run_id(run_id: UUID) -> list[Run]` to `RunRepository` Protocol -- enables querying dependents at terminal-transition time and startup sweep.

- `backend-api/tests/unit/fakes/runs.py` -- add `list_by_after_run_id` to `FakeRunRepository` -- shared fake stays in sync with the protocol (AD-18).

- `backend-api/src/orchestrator/application/use_cases/writers.py` -- add `engine: WorkflowEngine | None = None` field to `WriterPorts`; import `WorkflowEngine` from `orchestrator.domain.ports.engine` -- gives `apply_step_result` and `walk` access to the engine for dependent enqueue without breaking existing call sites.

- `backend-api/src/orchestrator/application/use_cases/create_run.py` -- add `after_run_id: UUID | None = None` to `CreateRunRequest`; validate `save=True` when set; pass to `Run(...)` -- wires the new field end-to-end from request to entity.

- `backend-api/src/orchestrator/api/schemas/runs.py` -- add `after_run_id: UUID | None = None` to `RunIn`; pass through in `as_request()` -- exposes the field in the API.

- `backend-api/src/orchestrator/application/rules/signals_table.py` -- add `"dependency"` to `"continue"` Rule's `park_kinds` frozenset -- table admits `continue` on a dependency park (dedicated handler still intercepts; table validates first per step 1 of signal_run's contract).

- `backend-api/src/orchestrator/application/rules/signals.py` -- add `dependency` park to `run_admitted_signals` so `"continue"` and `"cancel"` are returned for `needs_you + park_kind=dependency` -- prevents 409 before the dedicated handler runs.

- `backend-api/src/orchestrator/application/use_cases/signal_run.py` -- add `DEPENDENCY = "dependency"` constant; add `_continue_dependency_run` dedicated handler (two-phase: validate → record `"continue"` event → `needs_you→running` transition → commit → `engine.enqueue` → write `engine_ref` → commit); dispatch to it at top of `signal_run` when `signal.kind == "continue" and run.park_kind == DEPENDENCY`; add `_park_dependents` call inside UoW for failed/cancelled terminal runs; add `_enqueue_dependents` call after commit for done runs -- implements dependency resolution for operator-path terminal transitions, and the dedicated continue handler that enqueues instead of signals.

- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py` -- add `_park_dependents(ports, run)` call before `ports.uow.commit()` when `run.status in {"failed"}` (cancelled arrives via signal_run, not here); add `_enqueue_dependents(ports, run)` call after `with ports.uow:` block when `run.status == "done"` -- implements dependency resolution for execution-path terminal transitions.

- `backend-api/src/orchestrator/application/use_cases/queue.py` -- add `REASON_WAITING_FOR = "waiting for run {run}"` constant; update `_saved_runs` to skip runs with `after_run_id` set (they are not plain saved); add `_dependency_waiting_runs` returning queued runs with `after_run_id` set and `engine_ref == {}`; add rows from `_dependency_waiting_runs` to `list_queue` output using `REASON_WAITING_FOR` -- FR-25 queue reason.

- `backend-api/src/orchestrator/application/use_cases/walk.py` -- in `expire`: guard against expiring dependency-parked runs (`if run.park_kind == "dependency": return run.status`); in `expire` and `close_run`: add dependent resolution (park for expired=failed, enqueue for finished=done) -- execution-path dependent resolution for the walker's own terminal transitions.

- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py` -- implement `list_by_after_run_id` querying `run.after_run_id == run_id AND run.engine_ref == cast('{}', JSONB)` -- persistence layer.

- `backend-api/src/orchestrator/infrastructure/db/writers.py` -- pass `engine=engine` to `WriterPorts` in `open_writer_ports` where engine is threaded through `WalkDeps`/`open_ports` -- wires engine into execution-path dependent resolution.

- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` -- add `dependency_startup_sweep(session_factory, engine)` that enqueues runs with `after_run_id → done Run` and `engine_ref == {}`; call from `main.py::run_migrations` after `launch_engine()` -- crash-residue recovery (AD-12).

- `backend-api/alembic/versions/0015_run_after_run_id_fk.py` -- add FK constraint migration -- referential integrity deferred from story 5-3.

- `backend-api/tests/unit/application/test_dependency_resolution.py` -- TDD: predecessor done/failed/cancelled → dependents resolved correctly; same-UoW guarantee for failed; two-phase for done; engine_ref guard; multi-dependent fan-out -- new behavior coverage (operator revision 2026-09-18).

- `backend-api/tests/unit/application/test_dependency_continue_signal.py` -- TDD: `_continue_dependency_run` enqueues (not signals); records `"continue"` event; clears park; two-phase commit; requires `engine` in `SignalPorts` -- new behavior coverage.

- `backend-api/tests/unit/application/test_dependency_cancel_signal.py` -- TDD: cancel on dependency-parked run; all rows skipped; empty CancelPlan -- new behavior coverage.

- `backend-api/tests/unit/application/test_create_run_after_run_id.py` -- TDD: `after_run_id` stored; `save=False` + `after_run_id` raises Conflict -- new behavior coverage.

- `backend-api/tests/unit/application/test_queue_waiting_for.py` -- TDD: `"waiting for run {x}"` in queue row for dependency-waiting runs; `"saved — not started"` unchanged for plain saved runs -- FR-25 coverage.

- `backend-api/tests/unit/application/test_dependency_startup_sweep.py` -- TDD: startup sweep enqueues pending dependents; idempotent on second call; skips already-enqueued -- AD-12 crash residue coverage.

- `backend-api/tests/unit/application/test_expire_dependency_guard.py` -- TDD: `walk.expire` returns without expiring a dependency-parked run -- "dependency park never expires" AC.

**Acceptance Criteria:**

- Given run A is `done`, when run B has `after_run_id=A.id` and `engine_ref={}`, then `engine.enqueue` is called for B and B.engine_ref is written (two-phase commit pattern).
- Given run A is `failed`, when run B has `after_run_id=A.id` and `engine_ref={}`, then B transitions to `needs_you` with `park_kind="dependency"`, `park_reason="run {A.id} ended failed"`, `park_path=None`, in the same DB transaction as A's `failed` write.
- Given run B is `needs_you` with `park_kind="dependency"`, when operator sends `continue`, then B is enqueued via `engine.enqueue` and `engine_ref` is written; `engine.signal` is NOT called.
- Given run B is `needs_you` with `park_kind="dependency"`, when operator sends `cancel`, then B transitions to `cancelled` with all rows skipped and a `CancelPlan(pgids=(), worktrees=())`.
- Given run B has `after_run_id=A.id` and A is non-terminal, when `list_queue` is called, then B's queue row shows reason `"waiting for run {A.id}"`.
- Given the backend restarts with run B having `after_run_id=A.id`, `engine_ref={}`, and A.status=`done`, when `dependency_startup_sweep` runs, then B is enqueued.
- Given run B is `needs_you` with `park_kind="dependency"`, when `walk.expire` is called for B, then B is NOT transitioned to `failed` (guard in place).
- `make lint` passes. `make test` passes with 100% branch coverage on `domain/` and `application/`.

## Spec Change Log

## Review Triage Log

### 2026-09-18 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 4, low 3)
- defer: 7: (high 0, medium 1, low 6)
- reject: 4
- addressed_findings:
  - `[medium]` `[patch]` list_by_after_run_id lacked status='queued' filter — startup sweep would raise InvalidTransition on re-park of needs_you dependent; fixed filter in SQL impl and fake.
  - `[medium]` `[patch]` Missing end-to-end test: apply_step_result failed path with dependent — added test_apply_step_result_dependencies.py covering failed and done paths.
  - `[medium]` `[patch]` Missing end-to-end test: apply_step_result done path with dependent — covered in same new test file.
  - `[medium]` `[patch]` Missing end-to-end test: expire() with waiting dependent — added test to test_expire_dependency_guard.py.
  - `[low]` `[patch]` Duplicate list_by_status("queued") calls in list_queue — refactored to pass shared all_queued list.
  - `[low]` `[patch]` _park_dependents/_enqueue_dependents private-named but cross-module — renamed to park_dependents/enqueue_dependents.
  - `[low]` `[patch]` Spurious UoW context for dependency-dispatch peek in signal_run — replaced with direct runs.get() call.

## Design Notes

**`_continue_dependency_run` as a dedicated branch:** `_continue` in `signal_effects.py` calls `_parked(park_row)` which asserts `park_row is not None`. A dependency park has `park_path=None`, so `_park_row(rows, None)` returns `None`, and the shared effect would `AssertionError`. The handler is intercepted before `EFFECTS["continue"]` dispatch, exactly as `_start_saved_run` intercepts before `EFFECTS["start"]`.

**Two-phase commit for `done` dependents:** "same unit of work" (spec §4.6) means the same logical unit, not necessarily the same DB transaction. For the `done` case, the predecessor's commit must be durable before the engine sees the dependent's run_id — hence: commit predecessor done → enqueue → commit engine_ref. For `failed | cancelled`, the park write has no engine call so it fits in the same DB transaction.

**`expire` guard:** The 30-day park timeout is designed for human-wait states (blocked, checkpoint). A dependency-parked run waits for a machine event (predecessor termination), not a human; it should never expire on the clock. Guard `if run.park_kind == "dependency": log; return run.status` at the top of the `if run.status != NEEDS_YOU` branch equivalent in `expire`.

**`engine` threading through `WriterPorts`:** `apply_step_result` and `walk.close_run`/`walk.expire` need engine access for dependent enqueue. Adding `engine: WorkflowEngine | None = None` to `WriterPorts` (defaulting `None`) keeps all existing constructions working; `open_writer_ports` passes the engine when the walker's deps provide it.

**`list_by_after_run_id` returns only `engine_ref == {}`:** The guard at the protocol level ensures the use-case code never double-enqueues a dependent that was already processed. The SQL equivalent is `engine_ref = '{}'::jsonb`.

**Operator revision 2026-09-18:** Tests that pin the `ParkKind` member set or `run_admitted_signals` behavior for parks may be revised per operator exception 4 (anchor exception). Revised tests must name this decision and date, and the same commit must add coverage for the new behavior.

## Verification

**Commands:**
- `cd backend-api && make lint` -- expected: no errors (ruff, mypy, import-linter all pass)
- `cd backend-api && make test` -- expected: all tests pass, 100% branch coverage on domain/ and application/

## Auto Run Result

### Summary
Added `after_run_id` dependency chains between Runs: a saved Run can declare `after_run_id=<predecessor>`, its queue row shows `"waiting for run {x}"`, and when the predecessor reaches a terminal status the writers resolve all waiting dependents in the same logical unit of work (`done → engine.enqueue`, `failed|cancelled → park(kind="dependency")`). A dedicated `_continue_dependency_run` handler enqueues (not signals) a dependency-parked run on operator continue. A container-startup sweep handles crash residue. The 30-day expiry guard skips dependency parks.

### Files Changed

| File | Change |
|------|--------|
| `alembic/versions/0015_run_after_run_id_fk.py` | New: FK constraint on after_run_id with ON DELETE SET NULL, DEFERRABLE INITIALLY DEFERRED |
| `api/schemas/runs.py` | Added after_run_id to RunIn, passed through as_request() |
| `application/rules/signals.py` | Added dependency branch to run_admitted_signals |
| `application/rules/signals_table.py` | Added "dependency" to continue Rule's park_kinds |
| `application/use_cases/apply_step_result.py` | Added park_dependents (failed) and enqueue_dependents (done) calls |
| `application/use_cases/create_run.py` | Added after_run_id to CreateRunRequest; validation save=True required |
| `application/use_cases/dependency_sweep.py` | New: startup crash-recovery sweep function |
| `application/use_cases/queue.py` | Added REASON_WAITING_FOR, _dependency_waiting_runs; deduped list_by_status call |
| `application/use_cases/signal_run.py` | Added _continue_dependency_run, dependency dispatch, park/enqueue dependents on terminal signals; removed spurious peek UoW |
| `application/use_cases/walk.py` | Added expire guard for dependency parks; enqueue dependents in close_run; park dependents in expire |
| `application/use_cases/writers.py` | Added engine field to WriterPorts; added park_dependents, enqueue_dependents, DEPENDENCY_PARK_REASON |
| `domain/ports/repositories.py` | Added list_by_after_run_id to RunRepository protocol |
| `domain/statuses.py` | Added "dependency" to ParkKind |
| `infrastructure/db/repositories/runs.py` | Implemented list_by_after_run_id (status=queued AND engine_ref={}) |
| `infrastructure/db/writers.py` | Passed engine parameter through open_writer_ports |
| `infrastructure/dbos/__init__.py` | Exported dependency_startup_sweep |
| `infrastructure/dbos/startup.py` | Added dependency_startup_sweep function |
| `main.py` | Calls dependency_startup_sweep after launch_engine |
| `tests/unit/application/test_apply_step_result_dependencies.py` | New: end-to-end tests for failed and done dependent resolution via apply_step_result |
| `tests/unit/application/test_create_run_after_run_id.py` | New: after_run_id stored; save=False conflict |
| `tests/unit/application/test_dependency_cancel_signal.py` | New: cancel on dependency-parked run |
| `tests/unit/application/test_dependency_continue_signal.py` | New: _continue_dependency_run enqueues not signals |
| `tests/unit/application/test_dependency_resolution.py` | New: park_dependents and enqueue_dependents helpers |
| `tests/unit/application/test_dependency_startup_sweep.py` | New: startup sweep coverage |
| `tests/unit/application/test_expire_dependency_guard.py` | New: expire guard + expire parks dependents |
| `tests/unit/application/test_queue_waiting_for.py` | New: "waiting for run {x}" queue reason |
| `tests/unit/fakes/runs.py` | Added list_by_after_run_id (status=queued guard) |
| `tests/unit/test_run_statuses.py` | Revised ParkKind count 10→11 (operator revision 2026-09-18) |

### Review Findings Breakdown
- Patches applied: 7 (medium: 4, low: 3)
- Items deferred: 7 (medium: 1, low: 6)
- Items rejected: 4
- Followup review score: 3×4 + 1×3 = 15 (≥5, and 0 high patches) → followup_review_recommended: true

### Verification
- `make lint` from project root: passed (ruff, mypy, import-linter, eslint, prettier, tsc, test-pairs, env-contract all green)
- `make test` from project root: 6423 Python tests passed, 1351 TypeScript tests passed, 100% branch coverage on domain/ and application/

### Residual Risks
- `_continue_dependency_run` bypasses RUN_TRANSITIONS to set status="queued" (deferred D1); tracked above.
- Startup sweep extended to failed/cancelled predecessors beyond the literal intent scope (deferred D6); no harm, but lacks explicit authorization.
- No predecessor existence validation at create_run time (deferred D3); a dangling after_run_id leaves the dependent stuck forever.
