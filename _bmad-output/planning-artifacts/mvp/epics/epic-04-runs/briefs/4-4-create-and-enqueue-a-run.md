---
story: "4-4"
epic: 4
title: Create and enqueue a Run
requirements: [FR-6 (freeze on pin), FR-8, FR-13, AR-7 (engine port), AR-9 (interface only)]
binds: [AD-6, AD-7, AD-12, AD-15]
---

# Story 4.4 — Create and enqueue a Run

As the Operator,
I want *Start run* to persist the whole plan and put the Run in the queue behind its Repository, telling me whether it starts now or waits,
So that what I saw in *What will run* is exactly what the engine will execute, and two Runs never share a Repository.

## Scope

**In:** `domain/ports/engine.py` (`WorkflowEngine` protocol, `QueueEntry`, `EngineRecord`) + fake, `application/use_cases/create_run.py`, `POST /api/v1/runs`, a minimal `GET /api/v1/runs/{id}` (full read model in 4.12), `pinned_by` on Template versions, tests.
**Out:** the DBOS implementation (4.6), the walker.

## Binding rules (inlined)

- **Engine port (AD-6).** `WorkflowEngine{enqueue(run_id, partition_key) -> engine_ref, signal(run_id, Signal), cancel(run_id), list_queue() -> [QueueEntry{run_id, engine_state: enqueued | pending, position: int | None, enqueued_at}], attempt_record(engine_ref) -> EngineRecord | None, schedule(name, cron, job)}`. Fake in `tests/unit/fakes/engine.py` records calls and holds an in-memory queue.
- **`create_run` (AD-7).** Steps: (1) re-run pre-flight; any `fail` line → 409 problem with the line texts, a `plan_error` → 422; (2) build `Run` (status `queued`, `plan_ref`, `plan_refs`, `pinned_versions` = the root version plus every callee version in the resolved tree, `inputs`, `budget_usd`, `manual_estimate_h`, `re_review_done`); (3) in **one unit of work** add the Run and all `step_run` rows from the plan; (4) after commit call `engine.enqueue(run_id, partition_key=repository_id)` and store the returned `engine_ref` on the Run in a second small unit of work; (5) compute `starts_now` = no other non-terminal Run on the Repository and active non-terminal Runs (`running` + `needs_you`) < `MAX_ACTIVE_RUNS`, and `waiting` text as pre-flight's `queue_note`.
- **Manual estimate.** Stored at creation; `PUT` of the Run does not exist; the read model shows it.
- **Freeze on pin (AD-15).** `TemplateVersion.pinned_by` = count of Runs whose `pinned_versions` contains it (any status). Saving still only creates n+1 (3.3), so nothing else changes; deletion endpoints do not exist. The Templates read model now returns the real count.
- **Request/response.** `POST /runs` body = the pre-flight request plus `budget_usd` (required, > 0) and `manual_estimate_h?`; response 201 `{run: RunSummary, starts_now: bool, waiting: str}`. `GET /runs/{id}` → `RunSummary{id, status, template, version, project, repository, branch, budget_usd, spend_usd, plan_ref, created_at}` (the full read model replaces this in 4.12; keep the schema module shared).
- **Readiness exception (AD-10).** A Run for Project `readiness` skips the harness-enabled fail (Epic 5 creates such Runs); implement the flag `skip_harness_check` on the use case now.

## Acceptance criteria

**Given** a passing pre-flight for `repo-init@1`
**When** `POST /runs` is called
**Then** 201; the Run row exists with six `step_run` rows (`seq` 1–6, `plan` first, all `planned`), `pinned_versions = [{repo-init, 1}]`, `engine.enqueue` was called once with the Repository id, and `starts_now` is true.

**Given** a passing pre-flight for `initiative@1`
**When** created
**Then** `pinned_versions` is `[{initiative,1},{epic,1},{story,1}]` and `GET /templates/story/1` reports `pinned_by: 1`, `GET /templates/epic/1` `pinned_by: 1`.

**Given** a non-terminal Run on the same Repository
**When** a second Run is created
**Then** 201 with `starts_now: false` and `waiting: queues behind {label}`; the Run is `queued`.

**Given** a failing pre-flight line
**When** posted
**Then** 409 problem+json with the line texts in `detail` and no Run row written.

**Given** a plan error
**When** posted
**Then** 422 problem+json with `errors[]` carrying template, version, line, item, reason.

**Given** the unit-of-work fake
**When** the step-row insert raises
**Then** no Run row remains and `enqueue` is not called.

## Implementation notes

- `create_run.py::create_run(req, *, preflight, planner, engine, runs, steps, uow, clock, max_active_runs, skip_harness_check=False) -> CreateRunResult`.
- Router `POST /runs`, `GET /runs/{id}` in `api/routers/runs.py`; `api/schemas/runs.py` with `RunSummary`; run `make openapi`.
- `TemplateVersionRepository.pinned_by(name, version)` implemented with a JSONB containment query.

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

PRD FR-6, FR-8 (Start run), FR-13. Spine AD-6 (port signature), AD-7 (`create_run` persists rows before enqueue), AD-12, AD-15 (pins), AD-10 (readiness exemption).
