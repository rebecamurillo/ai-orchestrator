---
title: 'Save a Run without starting it'
type: 'feature'
created: '2026-09-18'
status: 'blocked'
baseline_revision: '011604dcef53b89026b38f9db1bdd654ed43ca9b'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** An operator has no way to stage a planned Run for later execution; every Run starts immediately on creation, preventing deliberate sequencing and "queue now, start manually" workflows.

**Approach:** Add `save: bool = False` to `POST /runs`; when true, `create_run` commits the Run and plan rows without calling `engine.enqueue` (leaving `engine_ref = {}`). Add a `start` Signal (admitted only when `engine_ref == {}` and `status == "queued"`) that re-probes pre-flight, records `started_by_operator`, clears `after_run_id`, calls `engine.enqueue`, and writes back `engine_ref` in a second commit (two-commit pattern mirroring `create_run`). `list_queue` appends saved Runs with reason `"saved — not started"`.

## Boundaries & Constraints

**Always:** Two-writer rule (AD-8) — `signal_run` calls `engine.enqueue` for the `start` signal (AD-8's stated exception); `engine_ref == {}` (empty dict) is the sole indicator of saved state (AD-6); the `start` signal is only admitted when `engine_ref == {}` and `status == "queued"`; TDD with shared fakes; existing test files unmodified; `make openapi` regenerates contract after API schema changes; new migration uses `down_revision = "0013_run_partition_branch"`.

**Block If:** Any code path that sets `engine_ref` to non-empty without going through `engine.enqueue`; any attempt to add a `saved` status token; `start` signal calling `engine.signal` rather than `engine.enqueue`.

**Never:** Add a new `RunStatus` or `park_kind` for the saved state; store a separate `saved` flag on the Run entity (emptiness of `engine_ref` IS the state); use the allocated fresh worktree branch as partition key (use `run.partition_branch`, set by story 5-1); add a third status writer (`start_saved_run` is read + delegate only, not a writer).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behaviour | Error Handling |
|----------|--------------|---------------------------|----------------|
| Save a run | `POST /runs` with `save: true` | Run created, `status="queued"`, `engine_ref={}`, 201; no engine entry | — |
| Start a saved run | `POST /runs/{id}/signals` `kind="start"` on saved Run | Status `"running"`, `engine_ref` set, gate event `started_by_operator` recorded, `after_run_id` null | — |
| Start already-enqueued | `start` on Run with non-empty `engine_ref` | 409 Conflict | 409 |
| Start non-queued | `start` on `running`/`needs_you`/terminal Run | 409 Conflict | 409 |
| Pre-flight fails at start | Concurrent Run now holds same `partition_branch` | `start_allowed=False` → 409 Conflict | 409 |
| Saved Run in list_queue | `list_queue` with a saved Run present | Row appended with `reason="saved — not started"`, `position=null` | — |
| `after_run_id` cleared | Saved Run has `after_run_id` non-null, then `start` | Field set to null in same UoW commit as status transition | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/entities/run.py:40–112` — `Run` entity; add `after_run_id: UUID | None = None` after `partition_branch` (~line 95); `engine_ref: dict` at line 64 — empty dict `{}` is the saved state; application code must test `not run.engine_ref`, never compare to `None`
- `backend-api/src/orchestrator/domain/statuses.py:57–68,80,104` — `SignalKind` Literal at lines 57–68: add `"start"`; `WriteEvent = Literal["spec_edit"]` at line 104: add `"started_by_operator"` → `Literal["spec_edit", "started_by_operator"]`; update `WRITE_EVENTS` tuple at line 105
- `backend-api/src/orchestrator/domain/ports/repositories.py:88` — `RunRepository.list_by_status(status)` — used in `list_queue` to find saved Runs
- `backend-api/src/orchestrator/domain/ports/engine.py:59` — `WorkflowEngine.enqueue(run_id, partition_key: str) -> dict` — called by `signal_run` for `start` kind
- `backend-api/src/orchestrator/infrastructure/db/models/run.py:109` — `RunRow`; add `after_run_id: Mapped[UUID | None] = mapped_column(Uuid(), nullable=True)` after `partition_branch` at line 109
- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py:55–145` — `to_entity`/`row_values`; add `after_run_id` round-trip (nullable UUID)
- `backend-api/alembic/versions/0013_run_partition_branch.py` — head; new migration's `down_revision = "0013_run_partition_branch"`
- `backend-api/alembic/versions/0014_run_after_run_id.py` — NEW; `down_revision = "0013_run_partition_branch"`; `op.add_column("run", sa.Column("after_run_id", sa.Uuid(), nullable=True))`
- `backend-api/src/orchestrator/application/use_cases/create_run.py:91–193` — `CreateRunRequest` (line 91): add `save: bool = False`; lines 186–189 are the second commit (enqueue + write engine_ref) — skip entirely when `save=True`
- `backend-api/src/orchestrator/application/use_cases/queue.py:40–44,81–111` — constants block: add `REASON_SAVED = "saved — not started"`; `list_queue` at line 81: after building engine-queue `rows`, query `ports.runs.list_by_status("queued")`, filter `[r for r in queued if not r.engine_ref]`; for each, get `step = ports.steps.first_queued(r.id)` (returns `StepRun | None`), build `QueueRow(position=None, run=r, next_step_label=step.gate if step else "", reason=REASON_SAVED, waiting_since=r.created_at, waiting_seconds=(ports.clock.now() - r.created_at).total_seconds())`; append to `rows` before sorting
- `backend-api/src/orchestrator/application/rules/signals_table.py:235–314` — `VALID` dict; add `"start": Rule(park_kinds=frozenset(), run_statuses=frozenset({"queued"}), extra=lambda run, _row, _sig: not run.engine_ref, extra_refusal="run already enqueued or not in saved state", run_event="start", actor="operator")`; `park_kinds=frozenset()` is correct — `validate` only checks `park_kinds` when `run.status in PARKED` (line 87 of signals.py), so a non-parked queued run bypasses the park check entirely
- `backend-api/src/orchestrator/application/use_cases/signal_effects.py:332–343` — `EFFECTS` dict; add `"start": _start` where `_start(writers, run, rows, park_row, signal) -> Run` returns `run.model_copy(update={"after_run_id": None})`
- `backend-api/src/orchestrator/application/use_cases/signal_run.py:69–136` — `SignalPorts` (lines 69–72): add `preflight: PreflightPorts | None = None`; after the main `writers.uow.commit()`, add `start` special case: `if signal.kind == "start": engine_ref = ports.engine.enqueue(run_id, partition_key=f"{run.repository_id}:{run.partition_branch}"); run = run.model_copy(update={"engine_ref": engine_ref}); writers.runs.update(run); writers.uow.commit()` and skip `_tell_the_engine` for this kind — mirrors create_run's two-commit pattern
- `backend-api/src/orchestrator/application/use_cases/start_run.py` — NEW thin orchestrator; `@dataclass StartRunPorts(writers: WriterPorts, engine: WorkflowEngine, preflight: PreflightPorts)`; `start_saved_run(ports, run_id)` re-probes via `preflight_and_plan(ports.preflight, PreflightRequest(repository_id=run.repository_id, project_id=run.project_id, template_name=run.template_name, template_version=run.template_version, base_branch=run.partition_branch, inputs=dict(run.inputs), budget_usd=run.budget_usd, re_review_done=run.re_review_done))`, refuses on `plan_error` or `not result.start_allowed`, then delegates to `signal_run(SignalPorts(writers=ports.writers, engine=ports.engine), run_id, Signal(kind="start", payload={}))`; `start_saved_run` is read + delegate — the actual status write stays in `signal_run`
- `backend-api/src/orchestrator/api/schemas/runs.py:55–85` — `RunIn`: add `save: bool = False`; update `as_request()` to pass `save=self.save`
- `backend-api/src/orchestrator/api/routes/` — signal route `POST /runs/{run_id}/signals`: for `kind == "start"` dispatch to `start_saved_run` (which carries preflight ports); existing signal route already returns `RunSummaryOut`
- `backend-api/tests/unit/fakes/engine.py:30–78` — `FakeWorkflowEngine` already has `enqueue`; no changes needed
- `web-client/src/lib/newwf/state.ts` — add `export const SAVE_TEXT = "Save"` constant (test-pairs coverage for this export)
- `web-client/src/islands/NewWorkflow.tsx:204–227` — decision bar; add a Save `<button>` beside Start run, `disabled` when `pending || starting`; on click, `api.POST('/runs', { body: { ...body, save: true } })`

## Tasks & Acceptance

**Execution:**

- `backend-api/tests/unit/application/test_create_run_save.py` — NEW (TDD first): test `create_run` with `save=True` does not call `engine.enqueue` (FakeWorkflowEngine.calls empty); returned run has `engine_ref={}` and `status="queued"`; test `save=False` (default) still enqueues with correct partition_key
- `backend-api/tests/unit/application/test_signal_start.py` — NEW (TDD first): test `start` signal on saved Run transitions to `running`, calls `engine.enqueue` not `engine.signal`, gate record has `event="started_by_operator"` and `actor="operator"`, `after_run_id` is None; test refused (Conflict) when `engine_ref` non-empty; test refused when `status="running"`; test pre-probe failure (start_allowed=False) returns Conflict; use FakeRunRepository, FakeWorkflowEngine from `tests/unit/fakes/`
- `backend-api/tests/unit/application/test_queue_saved.py` — NEW (TDD first): test `list_queue` appends saved Run with `reason="saved — not started"` and `position=None`; test `waiting_since == run.created_at`; test engine-queue Runs with non-empty `engine_ref` are not duplicated in saved-run path
- `web-client/tests/unit/newwf-save.test.ts` — NEW (TDD first): assert `SAVE_TEXT === "Save"` imported from `state.ts`
- `backend-api/src/orchestrator/domain/entities/run.py` — add `after_run_id: UUID | None = None` field
- `backend-api/src/orchestrator/domain/statuses.py` — add `"start"` to `SignalKind`; add `"started_by_operator"` to `WriteEvent`; update `WRITE_EVENTS`
- `backend-api/src/orchestrator/infrastructure/db/models/run.py` — add `after_run_id` nullable UUID column after `partition_branch`
- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py` — add `after_run_id` to `to_entity` and `row_values`
- `backend-api/alembic/versions/0014_run_after_run_id.py` — NEW migration; `down_revision = "0013_run_partition_branch"`; add nullable `UUID` column `after_run_id` to `run` table
- `backend-api/src/orchestrator/application/use_cases/create_run.py` — add `save: bool = False` to `CreateRunRequest`; skip second commit (lines 186–189) when `save=True`
- `backend-api/src/orchestrator/application/use_cases/queue.py` — add `REASON_SAVED`; extend `list_queue` to append saved Runs
- `backend-api/src/orchestrator/application/rules/signals_table.py` — add `"start"` Rule to `VALID`
- `backend-api/src/orchestrator/application/use_cases/signal_effects.py` — add `_start` effect clearing `after_run_id`; add to `EFFECTS`
- `backend-api/src/orchestrator/application/use_cases/signal_run.py` — add `preflight: PreflightPorts | None = None` to `SignalPorts`; add `start` two-commit special case after main commit; skip `_tell_the_engine` for `start`
- `backend-api/src/orchestrator/application/use_cases/start_run.py` — NEW: `StartRunPorts`, `start_saved_run` thin orchestrator
- `backend-api/src/orchestrator/api/schemas/runs.py` — add `save: bool = False` to `RunIn`; update `as_request()`
- `backend-api/src/orchestrator/api/routes/` — dispatch `kind="start"` signals to `start_saved_run` (with preflight ports)
- `make openapi` — regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts`
- `web-client/src/lib/newwf/state.ts` — add `export const SAVE_TEXT = "Save"`
- `web-client/src/islands/NewWorkflow.tsx` — add Save button to decision bar; POST `/runs` with `save: true` on click

**Acceptance Criteria:**

- Given `POST /runs` with `save: true`, when 201, then the returned run has `status: "queued"` and empty `engine_ref`, and the engine queue has no entry for that run.
- Given a saved Run (engine_ref empty, status queued), when `POST /runs/{id}/signals` with `kind: "start"`, then: response has `status: "running"` and non-empty `engine_ref`; gate records include `event: "started_by_operator"` with `actor: "operator"`; `after_run_id` is null.
- Given `start` signal on a Run with non-empty `engine_ref`, when posted, then 409 Conflict.
- Given `start` signal when pre-flight `start_allowed: false`, when posted, then 409 Conflict.
- Given a saved Run in the system, when `GET /queue`, then the response includes a row with `reason: "saved — not started"` and `position: null`.
- Given `make lint` and `make test` after all changes, then both pass green.
- Given `make openapi` after schema changes, then `contracts/openapi.json` includes `save: bool` in the run creation schema with no drift.

## Design Notes

**`engine_ref == {}` is the saved state:** `Run.engine_ref` defaults to `{}` (empty dict via `Field(default_factory=dict)`). Code must test `not run.engine_ref` — never compare to `None`.

**`start_saved_run` is a thin orchestrator, not a third writer:** It reads (pre-probe) and then delegates to `signal_run`. All status transitions and writes happen inside `signal_run` (the two writers rule holds). The pre-probe uses `partition_branch` as `base_branch` for `PreflightRequest` — this is the same approximation as story 5-2's `_new_partition_branch`.

**Two-commit pattern for `start`:** First commit transitions status `queued→running` and records the gate event. Second commit writes back `engine_ref` after `engine.enqueue` succeeds. This mirrors `create_run` lines 182–189 and ensures the gate record exists even if the engine call fails.

**`park_kinds=frozenset()` for `start` Rule:** `validate` in signals.py (line 87) checks `park_kinds` only when `run.status in PARKED`. A queued non-parked Run bypasses the park check entirely, so an empty frozenset correctly signals "never valid for a parked run."

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy (domain + application), import-linter, prettier, tsc, env-contract, test-pairs all pass
- `make test` -- expected: 100% branch coverage on `domain/` and `application/`; all new and existing tests green
- `make openapi` -- expected: no drift after running

## Review Triage Log

### 2026-09-18 — Review pass
- intent_gap: 1: (high 1, medium 0, low 0)
- bad_spec: 0
- patch: 3: (high 0, medium 1, low 2)
- defer: 6: (high 1, medium 3, low 2)
- reject: 6
- addressed_findings:
  - none

## Spec Change Log

*(No spec amendments were made in this pass — the blocking condition is inside the intent-contract.)*

## Auto Run Result

Status: blocked
Blocking condition: intent gap

**Unresolved question:** The intent-contract's I/O matrix specifies `POST /runs/{id}/signals kind="start"` as the API surface for starting a saved Run. Implementing this requires adding `"start"` to `SIGNAL_KINDS` in `domain/statuses.py`. However, `tests/unit/test_run_statuses.py:120` is an anchor test that pins `SIGNAL_KINDS` to exactly its current ten values. Additionally, `test_signals_table.py:58` and `test_signal_rules.py:59` pin `tuple(VALID) == SIGNAL_KINDS`. Adding `"start"` to `SIGNAL_KINDS` without modifying these tests is impossible; modifying these tests requires an Operator anchor exception (hard rule 1, exception 4).

The attempted implementation (commit `0e6048e`, reverted) correctly identified this constraint and used a dedicated endpoint `POST /api/v1/runs/{run_id}/start` instead of the signals endpoint. All behavioral requirements are met (two-commit pattern, gate record `started_by_operator`, `after_run_id` cleared, `list_queue` saves-row, `save: bool = False` on `POST /runs`). The only divergence is the API surface.

**Saved patch:** `_bmad-output/implementation-artifacts/5-3-save-run-patch.md` (describes the full implementation and what was correct vs what needs Operator guidance).

**Three resolution paths — Operator must choose:**

A) **Accept the dedicated-endpoint approach** (as implemented): keep `POST /api/v1/runs/{run_id}/start` as the API surface. Update the I/O matrix in the intent-contract (exception 4, Operator decision revision) so the acceptance criteria match the built surface. The patch commit is functionally complete under this reading.

B) **Use a different signal kind name** (e.g., `"save_start"`): change the I/O matrix in the intent-contract to `kind="save_start"` (exception 4). Update `test_run_statuses.py:120` with a new pinned value (anchor exception 4 required). Re-derive through the signals mechanism.

C) **Grant anchor exception to add `"start"` to `SIGNAL_KINDS`**: Exception 4 authorises the revision of `test_run_statuses.py:120`. The test must be updated in the same commit that asserts the new behaviour. Re-derive through the signals mechanism.

## Human Answer

2026-09-18T13:17:20.945908Z · operator

ACCEPT and update to meet new requirements-  AUTHORIZATION to update
