---
title: 'Save a Run without starting it'
type: 'feature'
created: '2026-09-18'
status: 'in-review'
baseline_revision: 'bbae2fdb511ab952b41b49aa1e10b95180ff375f'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred: []
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

## Review Triage Log

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy (domain + application), import-linter, prettier, tsc, env-contract, test-pairs all pass
- `make test` -- expected: 100% branch coverage on `domain/` and `application/`; 90% line coverage on `web-client/src/lib/**`; all new and existing tests green
- `make openapi` -- expected: no drift after backend schema changes committed
