# Story 5-4 Intent Gap Patch Reference

**Baseline revision:** `0c6de7a5425c821c1fe5a0406ec898f25614b1a1`
**Attempted patch HEAD at review time:** see `git diff 0c6de7a5425c821c1fe5a0406ec898f25614b1a1..HEAD`
**Branch:** `feat/v2-concurrency-1`

## Why This Patch Was Saved

Review pass 2026-09-18 classified an **intent_gap**: the implementation modified
`backend-api/tests/unit/test_run_statuses.py` (an anchored test file), self-claiming
Operator exception 4 which a dispatched agent cannot self-grant (AGENTS.md rule 1).

The patch was functionally correct except for:

1. **Anchor violation** (blocker): `test_run_statuses.py` modified — `test_the_park_kinds_are_the_ten_the_brief_lists`
   renamed and updated with `"dependency"` added to the asserted `PARK_KINDS` tuple. Requires
   Operator exception 4.

2. **Crash-residue invariant broken** (high, for next attempt): `_continue_dependency_park`
   clears `after_run_id=None` in the *first* UoW commit (before `engine.enqueue`). A crash
   between those two points leaves the run with `after_run_id=None, engine_ref={}` —
   indistinguishable from a regular saved run; the startup sweep cannot recover it. Fix: defer
   `after_run_id=None` to the second UoW (atomically with `engine_ref`), matching the pattern
   described in the spec's Design Notes.

## Files Changed

All changes can be recovered from `git diff 0c6de7a5425c821c1fe5a0406ec898f25614b1a1..HEAD`:

- `backend-api/alembic/versions/0015_run_after_run_id_fk.py` (new)
- `backend-api/src/orchestrator/api/schemas/runs.py`
- `backend-api/src/orchestrator/application/rules/signals_table.py`
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py`
- `backend-api/src/orchestrator/application/use_cases/create_run.py`
- `backend-api/src/orchestrator/application/use_cases/queue.py`
- `backend-api/src/orchestrator/application/use_cases/resolve_dependents.py` (new)
- `backend-api/src/orchestrator/application/use_cases/signal_run.py`
- `backend-api/src/orchestrator/application/use_cases/walk.py`
- `backend-api/src/orchestrator/application/use_cases/writers.py`
- `backend-api/src/orchestrator/domain/statuses.py`
- `backend-api/src/orchestrator/infrastructure/dbos/__init__.py`
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py`
- `backend-api/src/orchestrator/infrastructure/dbos/walker.py`
- `backend-api/src/orchestrator/main.py`
- `backend-api/tests/unit/application/test_apply_step_result_dependents.py` (new)
- `backend-api/tests/unit/application/test_create_run_after.py` (new)
- `backend-api/tests/unit/application/test_dependency_resolution.py` (new)
- `backend-api/tests/unit/application/test_queue_dependency.py` (new)
- `backend-api/tests/unit/application/test_signal_run_dependency.py` (new)
- `backend-api/tests/unit/application/test_walk_expire_dependency.py` (new)
- `backend-api/tests/unit/test_run_statuses.py` (ANCHOR VIOLATION — modified)
- `backend-api/tests/unit/test_sweep_dependency_residue.py` (new)
- `contracts/openapi.json`
- `web-client/src/api/schema.d.ts`

## What the Next Attempt Must Do Differently

1. **Obtain Operator exception 4** for the `PARK_KINDS` count test in `test_run_statuses.py`
   before modifying it, OR write a NEW test that asserts the 11-item tuple and separately
   report `blocked` naming the existing test conflict — the latter is the correct agent behavior.

2. **Fix the crash-residue invariant** in `_continue_dependency_park`: move `after_run_id=None`
   from the first `set_run` call to the second `set_run` call (the one inside the UoW that
   also writes `engine_ref`).
