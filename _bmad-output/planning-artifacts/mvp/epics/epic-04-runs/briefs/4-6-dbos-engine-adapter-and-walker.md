---
story: "4-6"
epic: 4
title: DBOS engine adapter and walker
requirements: [FR-12, FR-13, NFR-1, AR-9]
binds: [AD-2, AD-6, AD-8, AD-9, AD-12, AD-14]
---

# Story 4.6 — DBOS engine adapter and walker

As the Operator,
I want a Run to survive a restart or a container replacement and resume at the row it was on, and two Runs never to run on the same Repository,
So that I can walk away from a Run for days and trust that what completed stays completed.

## Scope

**In:** `infrastructure/dbos/{adapter.py, walker.py, config.py}` implementing `WorkflowEngine`; DBOS launch in `main.py`; the queue; human waits; cancel; `list_queue`; `attempt_record`; `schedule`; `DBOS_APPLICATION_VERSION`; the executor registry hook-up; tests (unit with a fake DBOS facade where possible; e2e for the real engine).
**Out:** executors (4.7, 4.8), signals' worktree effects (4.9).

## Binding rules (inlined)

- **Engine is opaque (AD-6).** Only `infrastructure/dbos/` imports `dbos`; `run.engine_ref = {workflow_id}`; `attempt.engine_ref = {workflow_id, step_id}`; the adapter reads and writes them, nothing else does.
- **Queue (AD-12).** One DBOS queue `runs` with `concurrency = MAX_ACTIVE_RUNS` (read at container start) and partition concurrency 1; `enqueue(run_id, partition_key=repository_id)` starts the walker workflow with `workflow_id = run_id` on that partition key. The slot and the partition are held for the workflow's whole life, including while it waits in `recv`.
- **Walker (`walker.py`).** `@DBOS.workflow()` `walk(run_id)`: loop — `row = step(first_queued_row)`; if none → `step(finish)` and return; `attempt = step(start_attempt)`; `result = step(execute_row)` (looks up the executor by `row.kind` in `application/steps/__init__.py`, builds `StepContext{row, with_resolved, cwd, frame_start_sha, previous_attempt, attempt, resume_signal, ports}`, catches every exception into `StepResult(error, reason "internal: {ExceptionClass}", park internal)`); `step(apply_step_result)`; if the Run is now `needs_you` → `msg = DBOS.recv(topic=f"human:{run_id}", timeout_seconds=30 days)`; on timeout → `step(expire)` (Run `failed`, reason `parked 30 days`, record `expired`) and return; on message → continue the loop (the message is the `Signal`; the walker stores it as `resume_signal` for the next executor call and otherwise only reads). If the Run is `failed | cancelled` → return. **Every side effect is inside a `@DBOS.step()` with `retries_allowed=False`**; the loop body itself branches only on data read inside steps; no wall-clock reads outside steps.
- **Signal / cancel.** `signal(run_id, signal)` = `DBOS.send(run_id, signal.model_dump(), topic=f"human:{run_id}")`; `cancel(run_id)` = `DBOS.cancel_workflow(run_id)` — the walker's next step raises and the workflow ends; a step result arriving after cancel is absorbed by `apply_step_result`'s late-result rule.
- **`list_queue()`** reads DBOS's queued/pending workflows for queue `runs` and returns `QueueEntry` rows with `position` = index among `enqueued` entries ordered by enqueue time, `None` for `pending` (active).
- **`attempt_record(engine_ref)`** returns the DBOS step record (`function_id`, status, output) or `None`; used by tests and the Runs history later.
- **`schedule(name, cron, job)`** registers `@DBOS.scheduled(cron)` functions at startup (4.11 registers the jobs).
- **Version pin.** `DBOS` config `application_version = settings.DBOS_APPLICATION_VERSION`; document in `AGENTS.md` (backend) that changing the walker's step sequence requires bumping it after draining running Runs.
- **Startup order (Operations):** migrations → seed templates → seed harnesses → `DBOS.launch()` → uvicorn; DBOS uses the same `DATABASE_URL` (schema `dbos`).
- **Restart recovery (FR-12, NFR-1):** completed steps are replayed from DBOS's `operation_outputs`; an interrupted `execute_row` step re-executes as a **new attempt** (the walker calls `start_attempt` again only when the row is still `running` from an unfinished attempt: on recovery, `execute_row`'s replay sees the row `running` with an attempt lacking `ended_at`, closes it as `error · interrupted`, and starts a new attempt `[the exact recovery sequence is decided at the spec checkpoint of this story]`).
- **Research:** `_bmad-output/planning-artifacts/mvp/architecture/research/dbos.md` holds the verified API notes (queues, partition keys, `recv`, `send`, `list_queued_workflows`, step ids); read it before planning.

## Acceptance criteria

**Given** a Run created with rows `plan, checkout`… whose executors are fakes returning `done`
**When** enqueued on the real engine in the e2e stack
**Then** the walker runs rows in `seq` order, each row has exactly one Attempt, and the Run ends `done` with the `start` and `done` records.

**Given** an executor that returns a `checkpoint` park
**When** the walker reaches it
**Then** the Run is `needs_you`, the workflow is waiting in `recv`, `list_queue()` shows the Run as `pending` with position `None`, and `signal(run_id, continue)` resumes it within 5 s.

**Given** two Runs on the same Repository
**When** both are enqueued
**Then** the second stays `enqueued` (position 1) until the first is terminal; **and** given `MAX_ACTIVE_RUNS=2` and two Runs parked in `needs_you` on two Repositories, a third Run on a third Repository stays `enqueued`.

**Given** the backend killed (`SIGKILL`) while a row's executor is sleeping
**When** the backend restarts
**Then** rows completed before the kill are not re-executed (their Attempt count stays 1), the interrupted row gets Attempt 2, and the Run completes.

**Given** `cancel(run_id)` while the walker waits in `recv`
**When** called
**Then** the workflow ends within 5 s and a later fake result for that Run is ignored.

**Given** a Run parked with a `recv` timeout shortened to 5 s in a test configuration
**When** the timeout elapses
**Then** the Run is `failed` with reason `parked 30 days` and record `expired`.

**Given** `import-linter`
**When** run
**Then** `dbos` is imported only under `infrastructure/dbos/`.

## Implementation notes

- Keep the walker body tiny; every branch reads a value returned by a step.
- `StepContext.ports` is a small container built in `main.py` (git, workspace, process, clock, repositories, settings values) and passed to the walker at registration; executors never import infrastructure.
- Settings: add `HUMAN_WAIT_SECONDS` (default 30 days) so tests can shorten it; add to `.env.example`.
- e2e tests use fake-kind executors registered only under `ORCH_TEST_MODE=1` (`shell` is enough for most: `sleep` and `true`).

## Verification

```bash
make lint && make test && make up && make e2e-api
```

## Sources for detail only

Spine AD-6 (port + replay rules), AD-8 (writers inside the engine step), AD-12 (queue), AD-13 (`recv` on `human:{run_id}`), Operations (startup order). `research/dbos.md`. PRD FR-12, FR-13, NFR-1.
