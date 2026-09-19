# Story 5-3 — Implementation Patch (Attempt 2, Blocked)

**Baseline revision:** `011604dcef53b89026b38f9db1bdd654ed43ca9b`
**WIP commit:** `0e6048e` ("wip: story 5-3 attempt 2 (interrupted)")
**Patch diff:** `git diff 011604dcef53b89026b38f9db1bdd654ed43ca9b 0e6048e`

## Blocking Condition

**Intent gap — API surface conflict with anchor test.**

The intent-contract specifies:
- I/O matrix: `POST /runs/{id}/signals kind="start"` as the API surface for starting a saved Run.
- Boundaries: `signal_run calls engine.enqueue for the start signal`.

Implementing this requires adding `"start"` to `SIGNAL_KINDS` in `domain/statuses.py`.

`tests/unit/test_run_statuses.py:120` is an **anchor test** (hard rule 1) that pins:
```python
assert SIGNAL_KINDS == (
    "answer", "continue", "retry", "skip_story", "skip_epic",
    "budget_raise", "cancel", "terminal_start", "terminal_release", "terminal_resume",
)
```
Adding `"start"` would break this assertion. The test file cannot be modified.

Additionally, `tests/unit/application/test_signals_table.py:58` and `test_signal_rules.py:59` pin
`tuple(signals_table.VALID) == SIGNAL_KINDS`, meaning both must be updated together — but
`test_run_statuses.py:120` still blocks.

## Unresolved Questions for the Operator

Three resolution paths exist; only the Operator can choose:

**A) Accept the dedicated-endpoint approach** (what this implementation did):
- Keep `POST /api/v1/runs/{run_id}/start` as the API surface.
- Requires updating the intent-contract's I/O matrix (exception 4: Operator decision
  revision) so the acceptance criteria match what was built.
- The implementation (`0e6048e`) is functionally correct and complete under this reading.

**B) Use a different signal kind name** (e.g., `"save_start"`):
- Change the I/O matrix in the intent-contract to `kind="save_start"` (exception 4).
- Add `"save_start"` to `SIGNAL_KINDS` (does not conflict with existing constraints).
- Requires `test_run_statuses.py:120` to be updated (anchor exception 4 needed).

**C) Grant an anchor exception to add `"start"` to `SIGNAL_KINDS`**:
- Exception 4: Operator authorises the revision of `test_run_statuses.py:120`.
- The test must be updated in the same commit that asserts the new behaviour.

## What the Implementation Got Right (KEEP for any re-implementation)

All of the following is correct and should be preserved regardless of which resolution is chosen:

- `backend-api/alembic/versions/0014_run_after_run_id.py` — migration adds nullable `after_run_id` UUID column.
- `backend-api/src/orchestrator/domain/entities/run.py` — `after_run_id: UUID | None = None` field.
- `backend-api/src/orchestrator/infrastructure/db/models/run.py` — `after_run_id` SQLAlchemy column.
- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py` — `after_run_id` round-trip in `to_entity` and `row_values`.
- `backend-api/src/orchestrator/domain/statuses.py` — `OperatorInitEvent = Literal["started_by_operator"]` added alongside GateEvent (same pattern as `WriteEvent`/`spec_edit`). This is correct regardless of routing choice — the gate record event for operator-initiated start should be `"started_by_operator"` not `"start"` (to distinguish from LifecycleEvent `"start"`).
- `backend-api/src/orchestrator/api/schemas/runs.py` — `save: bool = False` on `RunIn`, passed through `as_request()`.
- `backend-api/src/orchestrator/application/use_cases/create_run.py` — `save: bool = False` on `CreateRunRequest`; conditional skip of second commit (`if not req.save:`).
- `backend-api/src/orchestrator/application/use_cases/queue.py` — `REASON_SAVED = "saved — not started"`; `list_queue` extension appending saved Runs. **Patch needed**: add `if r.engine_ref: continue` after the `engine_run_ids` check to prevent misclassifying enqueued runs absent from the engine listing.
- `backend-api/tests/unit/application/test_create_run_save.py` — all test scenarios correct.
- `backend-api/tests/unit/application/test_queue_saved.py` — all test scenarios correct.
- `backend-api/tests/unit/test_run_repository_adapter.py` — `"after_run_id"` added to the `NULLABLE` set.
- `web-client/src/lib/newwf/state.ts` — `export const SAVE_TEXT = 'Save'`.
- `web-client/src/islands/NewWorkflow.tsx` — Save button, `saveRun()`, `saving` state.
- `web-client/tests/unit/newwf-save.test.ts` — constant assertion test.
- The **two-commit pattern** for the start action (gate record + status → commit 1; `engine.enqueue` + `engine_ref` write → commit 2) is correct regardless of routing choice.
- The **`after_run_id` clearing** in the start action is correct.

## What the Implementation Changed (routing — needs Operator guidance)

- Created `POST /api/v1/runs/{run_id}/start` (dedicated endpoint) instead of using `POST /runs/{id}/signals kind="start"`.
- `backend-api/src/orchestrator/api/routers/start_run.py` — NEW dedicated router.
- `backend-api/src/orchestrator/application/use_cases/start_run.py` — NEW use case that handles the full transition logic (not a thin delegator to `signal_run`).
- `backend-api/src/orchestrator/api/providers.py` — `start_run_ports` dependency added.
- `backend-api/src/orchestrator/main.py` — mounts the new router.
- `backend-api/tests/unit/application/test_signal_start.py` — tests `start_saved_run` directly.
- Did NOT modify `signals_table.py`, `signal_effects.py`, or `signal_run.py`.
- Did NOT add `"start"` to `SignalKind` / `SIGNAL_KINDS`.
- `admitted_signals` does NOT surface the start action for saved Runs.
