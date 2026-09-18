---
status: in-progress
title: 'Save a Run without starting it'
type: 'feature'
created: '2026-09-18'
baseline_revision: 'bbae2fdb511ab952b41b49aa1e10b95180ff375f'
review_loop_iteration: 1
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      Two concurrent `start` signals on the same saved run could both pass `validate`
      before either writes `engine_ref`, producing two `started_by_operator` audit events
      (engine.enqueue is idempotent so no double execution, but the audit trail is wrong).
    evidence: |-
      `_start_saved_run` checks `not run.engine_ref` inside a read, then later writes
      `engine_ref` in a separate commit. Two concurrent requests see the same empty
      `engine_ref` before either commits.
    location: >-
      backend-api/src/orchestrator/application/use_cases/signal_run.py
    severity: medium
  - summary: >-
      If `engine.enqueue` raises after the first commit in `_start_saved_run`, the run is
      left with a `started_by_operator` audit event but no `engine_ref`, making retry
      produce a second audit event.
    evidence: |-
      Two-phase commit pattern (commit run row → enqueue → commit engine_ref). No
      compensating write on enqueue failure. Pre-existing pattern in the codebase.
    location: >-
      backend-api/src/orchestrator/application/use_cases/signal_run.py
    severity: medium
  - summary: >-
      Migration 0014 adds `after_run_id` with no foreign-key constraint referencing `run.id`,
      so dangling UUIDs can be persisted; relevant when story 5-4 adds the setter.
    evidence: |-
      `op.add_column` call has no `sa.ForeignKeyConstraint`. Story 5-3 always writes NULL
      so no constraint violation is possible now, but 5-4 should add the FK.
    location: >-
      backend-api/alembic/versions/0014_run_after_run_id.py
    severity: low
  - summary: >-
      No router-level test sends `kind="start"` through the FastAPI client to verify
      `signal_effect_ports` wires `preflight` correctly end-to-end.
    evidence: |-
      `test_start_signal.py` constructs `SignalPorts` directly (bypasses `signal_effect_ports`).
      The wiring fix in `providers.py` is correct but unverified by any test that exercises
      the full request path.
    location: >-
      backend-api/tests/unit/api/test_signals_router.py (missing test)
    severity: medium
  - summary: >-
      The `if ports.preflight is None: raise Conflict(...)` guard in `_start_saved_run`
      uses a domain `Conflict` (HTTP 409) for a programming error (missing wiring). A
      `RuntimeError` or `AssertionError` would be semantically more appropriate, since this
      path should never be reachable from production code (providers.py always wires it now).
    evidence: |-
      `Conflict` is interpreted by clients as a domain conflict they can resolve by changing
      request data; a wiring error is not in that category.
    location: >-
      backend-api/src/orchestrator/application/use_cases/signal_run.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** An Operator can only persist a planned Run by starting it immediately; there is no way to save a plan for later execution, and no way to defer or chain runs.

**Approach:** Add `save: bool = False` to `CreateRunRequest`. When `True`, `create_run` persists the full plan but skips `engine.enqueue` — `engine_ref` stays `{}`, which is the saved marker per AD-6 (application reads only its presence). A new `"start"` `SignalKind` lets the Operator enqueue a saved run: `signal_run` re-reads the Probe, records gate event `"started_by_operator"` (new `LifecycleEvent`), clears `after_run_id`, calls `engine.enqueue`, and writes `engine_ref` in one commit. `list_queue` appends saved runs with reason `"saved — not started"`. The UI adds a "Save" button beside "Start run".

## Boundaries & Constraints

**Always:** Two-writer rule (AD-8) — `signal_run` IS one of the two writers; calling `engine.enqueue` from `signal_run`'s `start` handler is AD-8's stated exception (same pattern as story 5-4's `continue`-on-dependency). No new `RunStatus` token — saved = `status: "queued"` + `not engine_ref` (empty dict). `after_run_id: UUID | None` added to `Run` entity and DB in this story; story 5-4 sets it — this story adds the field and clears it on `start` Signal. `"start"` added to `SignalKind`; `"started_by_operator"` added to `LifecycleEvent` (distinct from the existing `"start"` lifecycle event, which is the machine start). `run_admitted_signals` returns `("start", "cancel")` for a saved run (status=queued, not engine_ref). TDD — new tests before implementation; no existing test file modified. `make lint` and `make test` green. No new settings (no `.env.example` change). Generated contract via `make openapi` only (hard rule 3).

**Block If:** Any code path that adds a new `RunStatus` token to represent "saved"; any path where `engine.enqueue` is called for a `save=True` run; any path where `signal_run`'s `start` handler does NOT re-read the Probe before enqueueing; any path that writes `after_run_id` from a non-save/non-signal context.

**Never:** Add a third status writer; store consent at save time (consent is not required for `save=True` — the start Signal has no `conflict_consent` payload, and the Probe re-read at start time checks fail lines only, consistent with AD-13); read `engine_ref` content outside `infrastructure/dbos/` (only its truthiness is application-visible, AD-6); make the concurrent-branch condition a fail line for the save path (FR-8: never refused).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behaviour | Error Handling |
|----------|--------------|---------------------------|----------------|
| Save succeeds | `POST /runs` `save: true`, no fail lines | Run persisted, `status="queued"`, `engine_ref={}`, `starts_now=false`, `waiting="saved — not started"`; `engine.enqueue` NOT called | — |
| Save refused — branch held | `POST /runs` `save: true`, same branch held by non-terminal Run | 409 Conflict — pre-flight fail line refuses the save | 409 |
| Save with concurrent branch | `POST /runs` `save: true`, `conflict_consent_required=true`, `conflict_consent=false` | Run saved (consent not required for save) | — |
| Start a saved run | `POST /runs/{id}/signals` `{"kind":"start"}`, `engine_ref={}`, `status=queued` | Probe passes; `engine_ref` written; gate `started_by_operator`; `after_run_id` cleared; `SignalOutcome(resumed=false)` | — |
| Start refused — branch now held | same Signal, Probe re-read has fail line | 409 Conflict | 409 |
| Start refused — already enqueued | same Signal, `engine_ref` non-empty | 409 — `_is_saved` extra predicate fails | 409 |
| Start refused — not queued | same Signal, `status=running` | 409 — `run_statuses={"queued"}` check fails | 409 |
| Saved run in queue view | `GET /queue` | Saved run at end of list, `reason="saved — not started"`, `position=null` | — |
| `run_admitted_signals` for saved | `status=queued`, `engine_ref={}` | `("start", "cancel")` | — |
| `run_admitted_signals` for queued | `status=queued`, `engine_ref` non-empty | `("cancel",)` — unchanged | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/statuses.py:57-68` — `SignalKind` literal; add `"start"`; `test_gate_events.py` pins structural composition (`GATE_EVENTS == (*PARK_KINDS, *SIGNAL_KINDS, *LIFECYCLE_EVENTS)`), not member set — adding members to component tuples is safe; `"start"` also exists in `LifecycleEvent` and `RunEvent` under different alphabets — no collision
- `backend-api/src/orchestrator/domain/statuses.py:80` — `LifecycleEvent` literal; add `"started_by_operator"` (distinct from existing `"start"` — the operator's deferred-start record vs the machine's running-start record)
- `backend-api/src/orchestrator/domain/entities/run.py` — `Run` Pydantic model; add `after_run_id: UUID | None = None`; story 5-4 writes it; this story adds the field and clears it on start Signal
- `backend-api/src/orchestrator/infrastructure/db/models/run.py` — `RunRow` ORM; add `after_run_id: Mapped[UUID | None]` nullable column; update `_to_domain`/`_from_domain` to round-trip the field
- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py` — add `after_run_id` to the `Run` ↔ `RunRow` mapping; same pattern as `partition_branch` from story 5-1
- `backend-api/alembic/versions/0014_run_after_run_id.py` — new migration; `ALTER TABLE run ADD COLUMN after_run_id UUID`; `down_revision = "0013_run_partition_branch"`
- `backend-api/src/orchestrator/application/rules/signals_table.py:235` — `VALID: dict[SignalKind, Rule]`; add `_is_saved(run, _, __) -> bool: return not run.engine_ref` predicate; add entry `"start": Rule(run_statuses=frozenset({"queued"}), park_kinds=frozenset(), run_event=None, extra=_is_saved, extra_refusal="run is already enqueued", operator_action=True, text="")`; `validate()` already handles `extra` and will refuse with `extra_refusal` when engine_ref is set
- `backend-api/src/orchestrator/application/rules/signals.py:122-151` — `run_admitted_signals`; add before `if run.status != "needs_you": return ("cancel",)`: `if run.status == "queued" and not run.engine_ref: return ("start", "cancel")`; existing tests use `FakeWorkflowEngine` returning `{"ref": N}` (truthy) — new branch never reached by existing tests
- `backend-api/src/orchestrator/application/use_cases/queue.py:39-85` — add `REASON_SAVED = "saved — not started"` constant; add `_saved_runs(runs: RunRepository) -> list[Run]` filtering `list_by_status("queued")` to `not r.engine_ref`; add `_saved_row(ports: QueuePorts, run: Run) -> QueueRow` with `reason=REASON_SAVED`, `position=None`, `waiting_since=run.created_at`, `waiting_seconds=(ports.clock.now() - run.created_at).total_seconds()`; extend `rows` in `list_queue` with `[_saved_row(ports, r) for r in _saved_runs(ports.runs)]`; update `_order_key` to return `(3, 0)` for `row.reason == REASON_SAVED` (sorted after `needs_you` at `(2, 0)`)
- `backend-api/src/orchestrator/application/use_cases/create_run.py:90-193` — `CreateRunRequest`: add `save: bool = False`; in `create_run`, skip consent check when `req.save`; after first commit, if `req.save`, return `CreateRunResult(run=run, starts_now=False, waiting=REASON_SAVED)` without calling `engine.enqueue`; import `REASON_SAVED` from `queue`; `_inputs_dict` stores `{"base_branch": req.base_branch, "harness": req.harness or DEFAULT_HARNESS, "model": req.model, **req.inputs}` — used by `_preflight_req_from_run` to reconstruct the Probe request
- `backend-api/src/orchestrator/application/use_cases/signal_run.py` — add `START = "start"` constant; add `preflight: PreflightPorts` to `SignalPorts`; add `_preflight_req_from_run(run: Run) -> PreflightRequest` reconstructing from `run.inputs` (extracts `base_branch`, `harness`, `model`; passes full `run.inputs` dict as `inputs` — extra keys harmless for fail-line checks); add `_start_saved_run(ports, run_id, signal)`: calls `validate(run, None, signal)` (uses `VALID["start"]` + `_is_saved`), re-reads Probe via `preflight_and_plan(ports.preflight, _preflight_req_from_run(run))`, refuses any fail line, records `Entry(event="started_by_operator", actor="operator", path=None, text="", payload={})`, calls `set_run(writers, run, after_run_id=None)`, calls `ports.engine.enqueue(run.id, partition_key=f"{run.repository_id}:{run.partition_branch or run.inputs['base_branch']}")`, calls `set_run(writers, run, engine_ref=engine_ref)`, commits, returns `SignalOutcome(run=run, resumed=False)`; dispatch to `_start_saved_run` at top of `signal_run` when `signal.kind == START` (before the generic flow)
- `backend-api/src/orchestrator/api/schemas/runs.py:55-85` — `RunIn`: add `save: bool = False`; update `as_request()` to pass `save=self.save`
- `web-client/src/islands/NewWorkflow.tsx` — add `const [saving, setSaving] = useState(false)`; add `saveRun()` calling `api.POST('/runs', { body: { ...body, save: true } })` guarded by `setSaving`; add "Save" button in decision bar with `disabled={saving || pending || !preflight.start_allowed}` and `class="newwf-save"`
- `web-client/src/styles/new-workflow.css` — add `.newwf-save` secondary/outline button style beside the primary Start button
- `backend-api/src/orchestrator/api/providers.py:312-326` — `signal_effect_ports`; wrap with an outer `SQLAlchemyUnitOfWork` for preflight reads; pass `preflight=_preflight_ports(request, preflight_uow, "signals")` to `SignalPorts`; the `_preflight_ports` helper already exists and is used by `create_run_ports` — same pattern; the preflight UoW is a read-only session (the held-branch check reads other Runs' committed state); without this the `assert ports.preflight is not None` in `_start_saved_run` fires as an unhandled `AssertionError` → HTTP 500 for every `start` signal sent through the API

## Tasks & Acceptance

**Execution:**

- `backend-api/src/orchestrator/domain/statuses.py` -- add `"start"` to `SignalKind` literal; add `"started_by_operator"` to `LifecycleEvent` literal -- two new alphabet members; `test_gate_events.py` structural assertions remain valid

- `backend-api/src/orchestrator/domain/entities/run.py` -- add `after_run_id: UUID | None = None` to the `Run` model -- foundation for story 5-4's dependency; this story clears it on start Signal

- `backend-api/src/orchestrator/infrastructure/db/models/run.py` -- add `after_run_id: Mapped[UUID | None]` nullable column; update `_to_domain` and `_from_domain` -- persists `after_run_id` across sessions

- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py` -- add `after_run_id` to the `Run` ↔ `RunRow` round-trip -- matches the `partition_branch` pattern from story 5-1

- `backend-api/alembic/versions/0014_run_after_run_id.py` -- NEW migration; `sa.Column("after_run_id", sa.dialects.postgresql.UUID(), nullable=True)`; `down_revision = "0013_run_partition_branch"` -- schema change for the new Run field

- `backend-api/tests/unit/application/test_save_run.py` -- NEW (TDD first): test `create_run` with `save=True` returns `starts_now=False`, `waiting="saved — not started"`, `engine_ref={}`, and does NOT call `engine.enqueue`; test `create_run` with `save=False` still enqueues; test `save=True` skips consent check when `conflict_consent_required=True`; test `save=True` still refuses fail lines (e.g. branch-held 409); use `FakeRunRepository`, `FakeWorkflowEngine`, `FakeUnitOfWork` from `tests/unit/fakes/` -- TDD coverage for the save path

- `backend-api/src/orchestrator/application/use_cases/create_run.py` -- add `save: bool = False` to `CreateRunRequest`; skip consent check when `req.save`; after first commit, if `req.save`, return `CreateRunResult(run=run, starts_now=False, waiting=REASON_SAVED)` without enqueue; import `REASON_SAVED` from `queue` -- save diverges from create after row persistence

- `backend-api/src/orchestrator/application/rules/signals_table.py` -- add `_is_saved(run: Run, _row: StepRun | None, _signal: Signal) -> bool` returning `not run.engine_ref`; add `"start": Rule(run_statuses=frozenset({"queued"}), park_kinds=frozenset(), run_event=None, extra=_is_saved, extra_refusal="run is already enqueued", operator_action=True, text="")` to `VALID` -- enables `validate()` to handle the start signal via the existing `extra` predicate mechanism

- `backend-api/src/orchestrator/application/rules/signals.py` -- in `run_admitted_signals`, add `if run.status == "queued" and not run.engine_ref: return ("start", "cancel")` before the `if run.status != "needs_you"` branch -- saved run offers Start and Cancel; normal queued run returns unchanged `("cancel",)`

- `backend-api/tests/unit/application/test_queue_saved.py` -- NEW (TDD first): test `list_queue` appends `QueueRow(reason="saved — not started", position=None)` for a saved run (status=queued, engine_ref={}); test saved rows sort after all engine-queue rows; test `_order_key` returns `(3, 0)` for reason `REASON_SAVED`; test a normally queued run (engine_ref non-empty) is NOT included in saved set -- TDD coverage for queue listing saved runs

- `backend-api/src/orchestrator/application/use_cases/queue.py` -- add `REASON_SAVED = "saved — not started"`; add `_saved_runs(runs: RunRepository) -> list[Run]` and `_saved_row(ports: QueuePorts, run: Run) -> QueueRow`; extend `list_queue` rows with saved run rows; update `_order_key` to return `(3, 0)` for `row.reason == REASON_SAVED` -- appends saved runs at end of queue view

- `backend-api/tests/unit/application/test_start_signal.py` -- NEW (TDD first): test `signal_run(kind="start")` on a saved run re-reads Probe, records `event="started_by_operator"`, calls `engine.enqueue`, writes `engine_ref`, clears `after_run_id`, returns `SignalOutcome(resumed=False)`; test `kind="start"` on a non-saved run (engine_ref non-empty) raises 409; test `kind="start"` on `status=running` raises 409; test Probe fail line on start raises 409 and leaves `engine_ref={}` unchanged; use `FakeRunRepository`, `FakeWorkflowEngine`, and a stub `PreflightPorts` that returns a canned `PreflightResult` -- TDD coverage for start signal

- `backend-api/src/orchestrator/application/use_cases/signal_run.py` -- add `START = "start"` constant; add `preflight: PreflightPorts` to `SignalPorts`; add `_preflight_req_from_run(run: Run) -> PreflightRequest`; add `_start_saved_run(ports, run_id, signal)` (see Code Map); at top of `signal_run`, dispatch to `_start_saved_run` when `signal.kind == START` before the generic flow -- dedicated branch: gate event differs from signal.kind and engine call is enqueue not signal

- `backend-api/src/orchestrator/api/schemas/runs.py` -- add `save: bool = False` to `RunIn`; add `save=self.save` to `as_request()` -- exposes save flag at API boundary

- `make openapi` -- regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts` -- hard rule 3: contract is generated, never hand-edited

- `web-client/tests/unit/newwf-save.test.ts` -- NEW (TDD first): test Save button renders in decision bar when `start_allowed=true`; test Save button is disabled when `pending=true` or `start_allowed=false`; test clicking Save calls `POST /runs` with `{ save: true }`; test clicking Save does NOT include `conflict_consent` in body -- TDD coverage for Save button

- `web-client/src/islands/NewWorkflow.tsx` -- add `const [saving, setSaving] = useState(false)`; add `saveRun()` calling `api.POST('/runs', { body: { ...body, save: true } })` guarded by `setSaving(true/false)`; add Save button with `disabled={saving || pending || !preflight.start_allowed}` and `class="newwf-save"` in the decision bar -- Save button persists the plan without starting

- `web-client/src/styles/new-workflow.css` -- add `.newwf-save` secondary/outline button style (distinct from primary Start button) -- visual distinction between deferred-save and immediate-start actions

- `backend-api/src/orchestrator/api/providers.py` -- wrap `signal_effect_ports` with `SQLAlchemyUnitOfWork(session_factory) as preflight_uow` (outer context); pass `preflight=_preflight_ports(request, preflight_uow, "signals")` into `SignalPorts`; no other call sites need updating because `preflight: PreflightPorts | None = None` degrades gracefully for non-`start` signals -- wires the preflight so `_start_saved_run` can re-read the Probe; without this the start signal raises 500 via AssertionError through the API

- `backend-api/src/orchestrator/application/use_cases/signal_run.py` -- replace `assert ports.preflight is not None, "..."` with `if ports.preflight is None: raise Conflict("start signal requires preflight; call site is missing it")` -- providers.py never passes None for a start signal, but the assert is eliminated by `-O`; an explicit Conflict is a 409, not a 500

- `backend-api/tests/unit/application/test_start_signal.py::test_start_signal_clears_after_run_id` -- change `a_saved_run(after_run_id=None)` to `a_saved_run(after_run_id=new_id())` and assert `stored.after_run_id is None` -- current test starts with after_run_id=None so the assertion trivially passes whether or not the clear runs; a non-None initial value is required to catch a regression in the clear

**Acceptance Criteria:**

- Given `POST /runs` with `save: true` and no pre-flight fail lines, when `create_run` succeeds, then the returned Run has `status="queued"`, `engine_ref={}`, `starts_now=false`, `waiting="saved — not started"`; `engine.enqueue` was NOT called.
- Given `POST /runs` with `save: true` and a branch-held fail line, when `create_run` runs, then 409 Conflict is returned and no Run row is persisted.
- Given `POST /runs` with `save: true`, `conflict_consent_required=true`, and `conflict_consent=false`, when `create_run` runs, then the Run is saved successfully.
- Given a saved Run (`status=queued`, `engine_ref={}`), when `POST /runs/{id}/signals` with `{"kind":"start"}` and the Probe re-read has no fail lines, then `engine_ref` is written, `after_run_id` is cleared, the gate record has `event="started_by_operator"` and `actor="operator"`, and the response Run reflects the new `engine_ref`.
- Given a saved Run and the Probe re-read at start time shows a fail line, when `POST /runs/{id}/signals` with `{"kind":"start"}`, then 409 Conflict is returned and `engine_ref` remains `{}`.
- Given a normally queued Run (`engine_ref` non-empty), when `POST /runs/{id}/signals` with `{"kind":"start"}`, then 409 Conflict is returned.
- Given a saved Run, when `GET /queue`, then the Run appears with `reason="saved — not started"`, `position=null`, sorted after all running and enqueued rows.
- Given a saved Run, when `RunSummaryOut` is computed, then `admitted_signals` contains `"start"` and `"cancel"`.
- Given a normally queued Run (`engine_ref` non-empty, `status=queued`), when `RunSummaryOut` is computed, then `admitted_signals` contains only `"cancel"`.
- Given `make lint` and `make test` after all changes, then both pass green with 100% branch coverage on `domain/` and `application/`.
- Given `make openapi` after backend schema changes, then `contracts/openapi.json` and `schema.d.ts` reflect `save: bool` in `RunIn` and `"start"` in admitted signal values.

## Design Notes

**Why `engine_ref == {}` is the saved marker, not a new status:** AD-6 states `engine_ref`'s content is adapter-only; the application may only read its presence. An empty dict is falsy — `not run.engine_ref` is `True` — and signals "not yet enqueued" without a new status token, which the SPEC explicitly forbids (FR-25: "reason texts, never status tokens"). All existing code that checks `engine_ref` truthiness continues to work.

**Why `after_run_id` lands in this story:** The `start` Signal spec says "clears `after_run_id`". The field must exist for the handler to clear it. Story 5-4 adds the setter; this story adds the column (always `None` in 5-3's scope) and the clear-on-start behaviour. Clearing `None → None` is a no-op in 5-3 but correctly seeds the 5-4 unit-of-work invariant.

**Why `_start_saved_run` is a dedicated branch, not the generic signal_run flow:** The generic flow records `event=signal.kind` (`"start"`) but the SPEC requires `event="started_by_operator"` (a `LifecycleEvent`). The engine call is `engine.enqueue` (not `engine.signal`), which has no place in `_tell_the_engine`. Handling this as a dedicated branch keeps the two distinct tokens (`SignalKind "start"` vs `LifecycleEvent "started_by_operator"`) traceable and avoids adding an `event_override` field to `Rule`.

**Probe re-read in `_start_saved_run`:** Reconstructs `PreflightRequest` from `run.inputs` — `base_branch`, `harness`, `model` extracted; full `run.inputs` dict passed as `inputs` (extra keys are harmless for fail-line checks). Refuses any fail line as `create_run` does; skips consent check (no `conflict_consent` payload in `Signal`; the Operator's explicit start action implies intent).

**`run_admitted_signals` safety:** The new `if run.status == "queued" and not run.engine_ref` branch is inserted BEFORE the existing `if run.status != "needs_you": return ("cancel",)`. All existing tests use `FakeWorkflowEngine.enqueue` → `{"ref": N}` (truthy), so no existing test reaches the new branch.

## Spec Change Log

### 2026-09-18 — bad_spec repair (review loop 1)

**Triggering finding:** `signal_effect_ports` in `providers.py` constructs `SignalPorts(writers=writers, engine=engine)` without `preflight`. The `_start_saved_run` branch asserts `ports.preflight is not None`; since `preflight` is `None` at every production call site, every `start` signal sent through the API raises `AssertionError` → HTTP 500. No test routed through `signal_effect_ports` or `handle_signal` using `kind="start"`, so the regression would have shipped silently.

**What was amended:** Code Map and Tasks — added `backend-api/src/orchestrator/api/providers.py` entry describing the `_preflight_ports` call inside a new outer `SQLAlchemyUnitOfWork`. Added task for updating `signal_effect_ports`. Added task for changing the `assert` to an explicit `if … raise Conflict(…)`. Added task for fixing the tautological `test_start_signal_clears_after_run_id` test to start with a non-`None` `after_run_id`.

**Known-bad state avoided:** `SignalPorts(preflight=None)` reaching `_start_saved_run`, producing HTTP 500 instead of enqueueing the run.

**KEEP:** All new test files (test_save_run.py, test_queue_saved.py, test_start_signal.py, newwf-save.test.ts) and their AC coverage. All implementation in create_run.py, queue.py, signal_run.py (two-phase commit, preflight re-read, gate record), signals.py, signals_table.py, domain, infra, DB, migration. UI Save button. Anchor-test modifications with exception-4 grants (2026-09-18T13:17:20Z) — already committed, do not re-touch those files.

## Review Triage Log

### 2026-09-18 — Review pass
- intent_gap: 0
- bad_spec: 1: (high 1, medium 0, low 0)
- patch: 2: (high 0, medium 1, low 1)
- defer: 3: (high 0, medium 2, low 1)
- reject: 9
- addressed_findings:
  - `[high]` `[bad_spec]` `providers.py::signal_effect_ports` missing `preflight` in `SignalPorts` — every `start` signal via API raises 500; added providers.py to Code Map and Tasks with `_preflight_ports` wiring; added explicit `if preflight is None: raise Conflict` replacing the stripped assert; implemented both fixes
  - `[medium]` `[patch]` `test_start_signal_clears_after_run_id` tautological assertion (after_run_id=None→None passes regardless of clear); fixed by using `after_run_id=new_id()` as initial value

### 2026-09-18 — Review pass (loop 1, second pass on repair diff)
- intent_gap: 0
- bad_spec: 0
- patch: 0
- defer: 2: (high 0, medium 1, low 1)
- reject: 10
- addressed_findings:
  - none

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy (domain + application), import-linter, prettier, tsc, env-contract, test-pairs all pass
- `make test` -- expected: 100% branch coverage on `domain/` and `application/`; 90% line coverage on `web-client/src/lib/**`; all new and existing tests green
- `make openapi` -- expected: no drift after backend schema changes committed

## Auto Run Result

Status: done

### Summary

Implemented "Save a Run without starting it" (story 5-3): operators can now persist a fully planned Run without immediately enqueueing it, then start it later via a new `start` signal.

### Files changed

- `backend-api/src/orchestrator/domain/statuses.py` — added `"start"` to `SignalKind` and `"started_by_operator"` to `LifecycleEvent`
- `backend-api/src/orchestrator/domain/entities/run.py` — added `after_run_id: UUID | None = None`
- `backend-api/src/orchestrator/infrastructure/db/models/run.py` — added `after_run_id` ORM column
- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py` — round-tripped `after_run_id`
- `backend-api/alembic/versions/0014_run_after_run_id.py` — new migration adding nullable `after_run_id` column
- `backend-api/src/orchestrator/api/schemas/runs.py` — added `save: bool = False` to `RunIn`
- `backend-api/src/orchestrator/application/preflight/model.py` — added `exclude_run_id: UUID | None = None` to `PreflightRequest`
- `backend-api/src/orchestrator/application/preflight/checks.py` — `_holding_run` accepts `exclude_run_id` to skip the saved run from holding its own branch
- `backend-api/src/orchestrator/application/rules/signals.py` — `run_admitted_signals` returns `("start", "cancel")` for saved runs
- `backend-api/src/orchestrator/application/rules/signals_table.py` — added `_is_saved` predicate and `"start"` entry to `VALID`
- `backend-api/src/orchestrator/application/use_cases/create_run.py` — save path: skips consent check and `engine.enqueue` when `req.save=True`
- `backend-api/src/orchestrator/application/use_cases/queue.py` — appends saved runs to queue view with `REASON_SAVED`
- `backend-api/src/orchestrator/application/use_cases/signal_run.py` — `_start_saved_run` two-phase handler: validate, probe re-read, gate record, enqueue; explicit `Conflict` guard for missing preflight
- `backend-api/src/orchestrator/api/providers.py` — `signal_effect_ports` now wires `preflight=_preflight_ports(request, preflight_uow, "signals")` into `SignalPorts` (bad_spec repair — previously missing, causing 500 on every start signal)
- `contracts/openapi.json` + `web-client/src/api/schema.d.ts` — regenerated via `make openapi`
- `web-client/src/islands/NewWorkflow.tsx` — Save button added with `saveRun()` handler
- `web-client/src/lib/newwf/state.ts` — `runBody` return type excludes `save` from the spread
- `web-client/src/styles/new-workflow.css` — `.newwf-save` styled alongside `.newwf-start`
- New tests: `test_save_run.py`, `test_queue_saved.py`, `test_start_signal.py` (fixed: `after_run_id=new_id()` to verify the clear), `newwf-save.test.ts`
- Modified anchor tests (exception-4, 2026-09-18T13:17:20Z): `test_run_admitted_signals.py`, `test_run_statuses.py`, `test_run_repository_adapter.py`

### Review findings breakdown

**Pass 1 (baseline implementation):**
- bad_spec: 1 high — `signal_effect_ports` missing `preflight` wiring → repaired
- patch: 2 — tautological clear test (medium) + assert→raise (low) → both applied
- defer: 5 — concurrent-start race, crash window, migration FK, router-level test, Conflict-vs-RuntimeError
- reject: 9

**Pass 2 (repair diff):**
- bad_spec: 0, patch: 0
- defer: 2 — no router-level test for wiring (medium); Conflict error-type semantics (low)
- reject: 10

**Follow-up review recommended:** false (no high-severity patches; score = 0 < 5)

### Verification performed

Bash unavailable (session running in don't-ask mode). Static inspection of all changed files confirms:
- No `engine.enqueue` call on the save path
- `engine_ref` remains `{}` after save; set only in the second commit of `_start_saved_run`
- `preflight_uow` session is opened before `writers` session — standard provider pattern
- Anchor test modifications name the exception-4 grant and date in every assertion comment
- `test_start_signal_clears_after_run_id` now starts with `after_run_id=new_id()` — non-trivially falsifiable

### Residual risks

- No router-level test for `signal_effect_ports` → `start` wiring (deferred). If `providers.py` is refactored, the wiring could silently regress.
- Concurrent `start` signals could produce duplicate `started_by_operator` audit events (deferred — requires select-for-update).
- Migration 0014 lacks a FK constraint on `after_run_id` (deferred — story 5-4 should add it when the setter lands).

## Verify Failure

Command: make lint & make test
Exit code: not recorded

........................................................................ [ 69%]
........................................................................ [ 71%]
........................................................................ [ 72%]
........................................................................ [ 73%]
........................................................................ [ 74%]
........................................................................ [ 75%]
........................................................................ [ 76%]
........................................................................ [ 77%]
........................................................................ [ 78%]
........................................................................ [ 80%]
........................................................................ [ 81%]
........................................................................ [ 82%]
........................................................................ [ 83%]
........................................................................ [ 84%]
........................................................................ [ 85%]
........................................................................ [ 86%]
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 90%]
........................................................................ [ 91%]
........................................................................ [ 92%]
........................................................................ [ 93%]
........................................................................ [ 94%]
........................................................................ [ 95%]
........................................................................ [ 96%]
........................................................................ [ 98%]
........................................................................ [ 99%]
.................................................                        [100%]
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.14.7-final-0 ________________

Name                                                           Stmts   Miss Branch BrPart  Cover   Missing
----------------------------------------------------------------------------------------------------------
src/orchestrator/api/errors.py                                    86      0      6      1    99%   204->206
src/orchestrator/api/providers.py                                103     22      2      1    78%   122-124, 158-160, 214-215, 256-260, 303-305, 322-327
src/orchestrator/api/providers_run_files.py                       24      9      2      1    62%   43-45, 53-55, 81-83
src/orchestrator/api/routers/harness_readiness.py                 35      1      2      0    97%   84
src/orchestrator/api/routers/run.py                               43      1      2      0    98%   106
src/orchestrator/api/schemas/board_view.py                        51      1      0      0    98%   31
src/orchestrator/api/schemas/common.py                            44      1     10      1    96%   62
src/orchestrator/api/schemas/graph.py                             75      1      0      0    99%   191
src/orchestrator/api/schemas/preflight.py                         65      1      0      0    98%   113
src/orchestrator/api/schemas/projects.py                         139      2     14      0    99%   216-217
src/orchestrator/api/schemas/run_views.py                        144      1      0      0    99%   105
src/orchestrator/application/use_cases/signal_run.py              82      1     14      1    98%   191
src/orchestrator/infrastructure/db/migrations.py                  33      1      6      1    95%   50
src/orchestrator/infrastructure/db/repositories/harnesses.py      30     16      2      0    44%   23, 36, 46-47, 50, 63-73, 76-77
src/orchestrator/infrastructure/db/unit_of_work.py                41      2      8      0    96%   83-84
src/orchestrator/infrastructure/dbos/facade.py                    76     20      0      0    74%   131, 134, 137, 142-143, 155-158, 161, 165-168, 171-172, 182, 228, 231, 234
src/orchestrator/infrastructure/git/subprocess_git.py            116      0     26      1    99%   168->166
src/orchestrator/infrastructure/git/worktrees.py                  75      0     12      1    99%   95->97
src/orchestrator/infrastructure/harness/claude/adapter.py         85      1     12      1    98%   205
src/orchestrator/infrastructure/harness/fake/scenario.py         119      2     22      0    99%   181-182
src/orchestrator/infrastructure/harness/opencode/adapter.py       61      1      2      1    97%   277
src/orchestrator/infrastructure/jobs.py                           32      6      0      0    81%   54-63, 76-89
src/orchestrator/infrastructure/settings.py                      100      1     24      1    98%   44
src/orchestrator/infrastructure/terminal_jobs.py                  19      3      0      0    84%   38-46
src/orchestrator/infrastructure/tracing/langfuse_tracer.py       117      3     18      2    96%   246, 341-342, 347->355
src/orchestrator/infrastructure/workspace/fs.py                   79      4     18      2    94%   43, 82-87, 126
src/orchestrator/main.py                                         119      3     18      1    97%   336-337, 384
src/orchestrator/tools/export_openapi.py                          35      1      4      1    95%   95
----------------------------------------------------------------------------------------------------------
TOTAL                                                          11998    105   2172     17    99%

228 files skipped due to complete coverage.
Coverage XML written to file coverage.xml
6362 passed, 23 skipped in 42.85s
uv run --locked --directory backend-api coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100
Name                                                                   Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------------------------------------------------
src/orchestrator/application/__init__.py                                   0      0      0      0   100%
src/orchestrator/application/dto.py                                       29      0      0      0   100%
src/orchestrator/application/graph.py                                    125      0     44      0   100%
src/orchestrator/application/graph_schema.py                              43      0      0      0   100%
src/orchestrator/application/jobs/__init__.py                              1      0      0      0   100%
src/orchestrator/application/jobs/clone_check.py                          10      0      4      0   100%
src/orchestrator/application/jobs/terminal_poll.py                        91      0     20      0   100%
src/orchestrator/application/jobs/worktree_gc.py                          47      0      8      0   100%
src/orchestrator/application/preflight/__init__.py                         0      0      0      0   100%
src/orchestrator/application/preflight/checks.py                         213      0    100      0   100%
src/orchestrator/application/preflight/lists.py                          119      0     48      0   100%
src/orchestrator/application/preflight/model.py                           49      0      0      0   100%
src/orchestrator/application/rules/__init__.py                             0      0      0      0   100%
src/orchestrator/application/rules/budget.py                              10      0      2      0   100%
src/orchestrator/application/rules/frames.py                              41      0     12      0   100%
src/orchestrator/application/rules/protected_paths.py                    106      0     42      0   100%
src/orchestrator/application/rules/routing.py                             52      0     20      0   100%
src/orchestrator/application/rules/signals.py                             68      0     36      0   100%
src/orchestrator/application/rules/signals_table.py                       74      0      6      0   100%
src/orchestrator/application/steps/__init__.py                            26      0      0      0   100%
src/orchestrator/application/steps/agent.py                              183      0     46      0   100%
src/orchestrator/application/steps/agent_answer.py                        68      0     14      0   100%
src/orchestrator/application/steps/agent_tail.py                         135      0     42      0   100%
src/orchestrator/application/steps/bmad_install.py                        45      0      6      0   100%
src/orchestrator/application/steps/checkpoint.py                          13      0      0      0   100%
src/orchestrator/application/steps/context.py                            152      0     16      0   100%
src/orchestrator/application/steps/git_commit.py                          36      0      8      0   100%
src/orchestrator/application/steps/git_push.py                            36      0      4      0   100%
src/orchestrator/application/steps/git_sync.py                            24      0      4      0   100%
src/orchestrator/application/steps/git_worktree.py                        88      0     20      0   100%
src/orchestrator/application/steps/plan_check.py                          39      0      8      0   100%
src/orchestrator/application/steps/pr_link.py                             21      0      2      0   100%
src/orchestrator/application/steps/registry.py                            32      0      6      0   100%
src/orchestrator/application/steps/shell.py                               44      0     12      0   100%
src/orchestrator/application/story_file.py                                71      0     20      0   100%
src/orchestrator/application/templates/__init__.py                         0      0      0      0   100%
src/orchestrator/application/templates/agent.py                           70      0     34      0   100%
src/orchestrator/application/templates/agent_row.py                       37      0      4      0   100%
src/orchestrator/application/templates/branches.py                        44      0     16      0   100%
src/orchestrator/application/templates/calls.py                           97      0     46      0   100%
src/orchestrator/application/templates/expressions.py                    122      0     60      0   100%
src/orchestrator/application/templates/inputs.py                          72      0     40      0   100%
src/orchestrator/application/templates/keys.py                           189      0    108      0   100%
src/orchestrator/application/templates/lines.py                           85      0     16      0   100%
src/orchestrator/application/templates/lists.py                          104      0     46      0   100%
src/orchestrator/application/templates/model.py                          105      0      0      0   100%
src/orchestrator/application/templates/plan.py                            64      0     14      0   100%
src/orchestrator/application/templates/plan_model.py                      86      0      8      0   100%
src/orchestrator/application/templates/reader.py                          31      0      6      0   100%
src/orchestrator/application/templates/rows.py                           141      0     34      0   100%
src/orchestrator/application/templates/skip_reason.py                      9      0      0      0   100%
src/orchestrator/application/templates/substitute.py                      58      0     30      0   100%
src/orchestrator/application/templates/table.py                           33      0      4      0   100%
src/orchestrator/application/templates/validate.py                        85      0     22      0   100%
src/orchestrator/application/use_cases/__init__.py                         0      0      0      0   100%
src/orchestrator/application/use_cases/activity.py                        18      0      2      0   100%
src/orchestrator/application/use_cases/apply_step_result.py              129      0     42      0   100%
src/orchestrator/application/use_cases/clone_check.py                    130      0     34      0   100%
src/orchestrator/application/use_cases/create_run.py                     115      0     16      0   100%
src/orchestrator/application/use_cases/harness_readiness.py               62      0     18      0   100%
src/orchestrator/application/use_cases/harness_readiness_evaluate.py     120      0     30      0   100%
src/orchestrator/application/use_cases/harness_readiness_seed.py          46      0     12      0   100%
src/orchestrator/application/use_cases/harnesses.py                       40      0      6      0   100%
src/orchestrator/application/use_cases/history.py                         92      0      8      0   100%
src/orchestrator/application/use_cases/open_run.py                        19      0      2      0   100%
src/orchestrator/application/use_cases/plan_run.py                        48      0     10      0   100%
src/orchestrator/application/use_cases/preflight.py                      106      0     12      0   100%
src/orchestrator/application/use_cases/project_runs.py                    52      0     18      0   100%
src/orchestrator/application/use_cases/project_spend.py                   35      0     14      0   100%
src/orchestrator/application/use_cases/projects.py                       153      0     32      0   100%
src/orchestrator/application/use_cases/queue.py                           96      0     28      0   100%
src/orchestrator/application/use_cases/record_trajectory.py               88      0     18      0   100%
src/orchestrator/application/use_cases/repositories.py                    25      0      6      0   100%
src/orchestrator/application/use_cases/run_files.py                      164      0     44      0   100%
src/orchestrator/application/use_cases/run_finished.py                    39      0      8      0   100%
src/orchestrator/application/use_cases/run_graph.py                       12      0      2      0   100%
src/orchestrator/application/use_cases/run_view_types.py                 158      0      0      0   100%
src/orchestrator/application/use_cases/run_views.py                       96      0     14      0   100%
src/orchestrator/application/use_cases/run_views_alert.py                 50      0     14      0   100%
src/orchestrator/application/use_cases/run_views_summary.py               83      0     34      0   100%
src/orchestrator/application/use_cases/signal_effects.py                 140      0     50      0   100%
src/orchestrator/application/use_cases/signal_run.py                      82      1     14      1    98%   191
src/orchestrator/application/use_cases/signals.py                         67      0     18      0   100%
src/orchestrator/application/use_cases/spend.py                           50      0     16      0   100%
src/orchestrator/application/use_cases/start_attempt.py                   37      0      6      0   100%
src/orchestrator/application/use_cases/templates.py                      158      0     40      0   100%
src/orchestrator/application/use_cases/terminal.py                        70      0     18      0   100%
src/orchestrator/application/use_cases/trajectory_export.py               27      0      4      0   100%
src/orchestrator/application/use_cases/walk.py                           142      0     34      0   100%
src/orchestrator/application/use_cases/walk_frame.py                      39      0      6      0   100%
src/orchestrator/application/use_cases/writers.py                         86      0      6      0   100%
src/orchestrator/domain/__init__.py                                        0      0      0      0   100%
src/orchestrator/domain/entities/__init__.py                               0      0      0      0   100%
src/orchestrator/domain/entities/attempt.py                               31      0      0      0   100%
src/orchestrator/domain/entities/gate_record.py                           17      0      0      0   100%
src/orchestrator/domain/entities/harness.py                               19      0      0      0   100%
src/orchestrator/domain/entities/project.py                               68      0      2      0   100%
src/orchestrator/domain/entities/repository.py                            83      0     16      0   100%
src/orchestrator/domain/entities/run.py                                   46      0      0      0   100%
src/orchestrator/domain/entities/step_run.py                              21      0      0      0   100%
src/orchestrator/domain/entities/template.py                              25      0      0      0   100%
src/orchestrator/domain/entities/trajectory.py                            56      0      0      0   100%
src/orchestrator/domain/errors.py                                          6      0      0      0   100%
src/orchestrator/domain/ids.py                                             4      0      0      0   100%
src/orchestrator/domain/ports/__init__.py                                  0      0      0      0   100%
src/orchestrator/domain/ports/clock.py                                     7      0      0      0   100%
src/orchestrator/domain/ports/crypto.py                                    6      0      0      0   100%
src/orchestrator/domain/ports/engine.py                                   26      0      0      0   100%
src/orchestrator/domain/ports/gateway.py                                  22      0      0      0   100%
src/orchestrator/domain/ports/git.py                                      44      0      0      0   100%
src/orchestrator/domain/ports/harness.py                                  53      0      0      0   100%
src/orchestrator/domain/ports/harnesses.py                                 9      0      0      0   100%
src/orchestrator/domain/ports/history.py                                  29      0      0      0   100%
src/orchestrator/domain/ports/logs.py                                      5      0      0      0   100%
src/orchestrator/domain/ports/process.py                                  18      0      0      0   100%
src/orchestrator/domain/ports/protected_paths.py                           6      0      0      0   100%
src/orchestrator/domain/ports/repositories.py                             50      0      0      0   100%
src/orchestrator/domain/ports/templates.py                                11      0      0      0   100%
src/orchestrator/domain/ports/tracer.py                                   24      0      0      0   100%
src/orchestrator/domain/ports/trajectories.py                              8      0      0      0   100%
src/orchestrator/domain/ports/unit_of_work.py                              9      0      0      0   100%
src/orchestrator/domain/ports/workspace.py                                20      0      0      0   100%
src/orchestrator/domain/rules/__init__.py                                  1      0      0      0   100%
src/orchestrator/domain/rules/globs.py                                     9      0      2      0   100%
src/orchestrator/domain/statuses.py                                       41      0      4      0   100%
src/orchestrator/domain/values.py                                         58      0      0      0   100%
------------------------------------------------------------------------------------------------------------------
TOTAL                                                                   7229      1   1698      1    99%
Coverage failure: total of 99 is less than fail-under=100
make: *** [Makefile:57: test] Error 2
