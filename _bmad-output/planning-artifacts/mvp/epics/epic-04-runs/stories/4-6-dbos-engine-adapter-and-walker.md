---
title: 'DBOS engine adapter and walker'
type: 'feature'
created: '2026-09-06'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/briefs/4-6-dbos-engine-adapter-and-walker.md'
  - '_bmad-output/planning-artifacts/mvp/architecture/research/dbos.md'
  - 'backend-api/AGENTS.md'
warnings: []
deferred:
  - summary: >-
      The e2e suite can no longer pass twice against one stack: every Run it creates parks, and
      a parked Run holds its global slot and its Repository partition with nothing able to
      release it.
    evidence: |-
      No executor exists until 4.7, so every walked Run stops `needs_you`; AD-12 holds the slot
      for the whole life of the walk; `POST /runs/{id}/signals` (the only way to cancel) lands in
      4.9. With `MAX_ACTIVE_RUNS=2` a second pass against the same stack would find the queue
      full. `make e2e` and CI both build a throwaway stack, so the gate is green; a reused dev
      stack is what this fills up.
    location: >-
      backend-api/tests/e2e/test_engine_walker.py
    severity: medium
  - summary: >-
      The brief's `ORCH_TEST_MODE=1` fake-kind executors were not built, so acceptance criteria
      1-6 are proven over the fake durable engine rather than against the real one.
    evidence: |-
      Every one of those criteria needs a row that can actually execute; the three basic kinds are
      4.7's and the git kinds 4.8's, and a second set of executors written here would be replaced
      by them a story later. The restart-and-orphan proof is story 4.17's whole scope.
    severity: medium
  - summary: >-
      A durable step other than the executor's raising leaves the Run `running` with no park and
      no reason: only the engine's own workflow record and the log say what happened.
    evidence: |-
      `application/steps/registry.execute` catches every executor exception, but `next_row`,
      `apply_result`, `close_run` and `expire` can still raise (`NotFound`, `InvalidTransition`, a
      database error). The workflow ends ERROR and the Run keeps the status it had. Parking from
      the workflow body means catching the library's own cancellation exception separately, which
      is a seam this story did not open.
    location: >-
      backend-api/src/orchestrator/infrastructure/dbos/walker.py
    severity: medium
  - summary: >-
      An Attempt closed because a restart interrupted it carries no operator-visible reason: it is
      `error` with an empty reason, like a genuine failure.
    evidence: |-
      `start_attempt._open_the_row` logs `attempt interrupted` and writes `status`/`ended_at`. The
      `attempt` table has no reason column, and AD-8 appends a gate record for Run transitions, of
      which this is not one. FR-12 wants the interruption visible; the Run detail (4.15) is where
      it would be read.
    location: >-
      backend-api/src/orchestrator/application/use_cases/start_attempt.py
    severity: medium
  - summary: >-
      `on_fail: escalate` — the action the DSL gives a row that declared none — is not routed by
      `apply_step_result`; the Run reaches `close_run` and parks `internal` instead.
    evidence: |-
      AD-9 admits `escalate | fail | continue | {redispatch, max}`. `fail` (4.5) and `continue`
      (this story) are routed. An executor that escalates returns its own `Park`, so the gap is
      only reachable for a row that ends `error` with no park at all — which is what the stall
      park now reports, with the row named, rather than silently.
    location: >-
      backend-api/src/orchestrator/application/use_cases/apply_step_result.py:_on_fail
    severity: low
  - summary: >-
      `RUN_EXPIRED` states "parked 30 days" while `HUMAN_WAIT_SECONDS` makes the deadline
      configurable, so a shortened wait writes a sentence that is not true.
    evidence: |-
      AD-13 fixes the wording, and product copy states facts (PRD NFR-8). Deriving the sentence
      from the setting would diverge from the spine's own text; the two cannot both be honoured
      while the setting is anything but the default.
    location: >-
      backend-api/src/orchestrator/application/use_cases/writers.py:RUN_EXPIRED
    severity: low
  - summary: >-
      `walk._frame_start_sha` and `walk._resume_signal` read every row of a frame and the Run's
      whole gate record on every single row execution.
    evidence: |-
      Both are inside the durable step that runs a row, and both discard almost everything they
      read. A `first_attempt_in_frame` / `latest_record_of_event` repository method would keep the
      cost flat as a Run grows; the repository ports are 4.1's and adding to them was not this
      story's scope.
    severity: low
  - summary: >-
      Only `enqueue` refuses when the engine has not been launched; `signal`, `cancel`,
      `list_queue`, `attempt_record` and `schedule` reach the library and fail opaquely.
    evidence: |-
      `_walker()` raises `NOT_LAUNCHED` because it needs the declared workflow. The others need
      only the instance, so a composition-root bug surfaces as a library exception instead of the
      sentence naming what went wrong.
    location: >-
      backend-api/src/orchestrator/infrastructure/dbos/adapter.py
    severity: low
  - summary: >-
      `RealEngine.schedule` has no caller and its scheduled-workflow signature is an unverified
      guess about the library's contract.
    evidence: |-
      `WorkflowEngine.schedule` is declared by the port and implemented here; the two jobs that
      use it (`clone_check` daily, `worktree_gc` at 7 days) are SPEC CAP-11, story 4.11. The
      facade's test pins `create_schedule`'s existence but not the `(scheduled_at, actual_at)`
      shape it passes.
    location: >-
      backend-api/src/orchestrator/infrastructure/dbos/facade.py:RealEngine.schedule
    severity: low
baseline_revision: '19738cb047e5e61904fc92695d725b5d65f7ca7f'
---

<intent-contract>

## Intent

**Problem:** `POST /runs` stores a plan and hands it to `infrastructure/engine/local.py`, which is a dictionary
in one process: nothing executes a row, nothing survives a restart, and two Runs on one Repository do not
serialise. The three status writers (4.5) have no caller, the plan's first row is never queued, and AD-6's
`WorkflowEngine` has no durable implementation.

**Approach:** DBOS behind the port, in `infrastructure/dbos/` only. One queue `runs`, `global_concurrency =
MAX_ACTIVE_RUNS`, `partition_concurrency = 1` on `repository_id`; a walker workflow whose every side effect is a
`@DBOS.step(retries_allowed=False)`; a single `recv` on `human:{run_id}` for the Operator's answer; the executor
registry in `application/steps/` as the seam the walker dispatches through. The rules the walker needs live in
`application/use_cases/walk.py` and go through 4.5's writers; the walker itself writes no status.

## Boundaries & Constraints

**Always:**
- `dbos` is imported by exactly one module, `infrastructure/dbos/facade.py`, and `make lint` proves it (AD-6).
- The walker calls `start_attempt`, `apply_step_result` and the `writers.py` helpers; it derives no status (AD-8).
- Every side effect is inside a durable step; the workflow branches only on values steps returned; no wall clock
  outside a step (AD-6).
- The slot and the Repository partition are held for the whole walk, `recv` included (AD-12).
- `run.engine_ref = {workflow_id}`, `attempt.engine_ref = {workflow_id, step_id}`, opaque outside the adapter.
- A new setting is added to `infrastructure/settings.py` and `.env.example` in the same change (AD-20).
- 100 % branch coverage over `domain/` and `application/`; modules ≤ 400 lines; every `src` module imported by a
  unit-test module; the shared fakes are reused and extended additively only.

**Block If:**
- Landing the story would require editing `SPEC.md`, `stories.yaml`, `epics.yaml`, any `AGENTS.md`, or an existing
  test file. In particular `tests/unit/test_local_workflow_engine.py` pins `LocalWorkflowEngine`, and
  `tests/unit/test_migrations.py` / `tests/unit/test_main_templates_seed.py` pin the start-up step.

**Never:**
- No executor for any kind (4.7, 4.8): the registry ships empty and an unregistered kind is a described park.
- No `POST /runs/{id}/signals` router (4.9), no queue read model or scheduled jobs (4.11), no OpenAPI change.
- No second `WorkflowEngine`; no status written outside AD-8's writers; no `dbos` symbol outside the facade.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| A created Run is walked | every row `planned`, Run `queued` | first row `planned → queued`, Attempt 1, Run `running` | — |
| Nothing queued, every row finished | rows `done`/`skipped` | `close_run` finishes the Run `done` with the `done` record | — |
| Nothing queued, a row left | a row `error`/`blocked` | `internal` park naming the row and its status | Run `needs_you`, never `done` |
| A row's kind has no executor | registry empty | `error` + `misconfigured · no executor for kind {kind}` | Run parks; no row after it is touched |
| An executor raises | any exception | `error` + `internal: {ExceptionClass}`; traceback logged | no message text in the park reason (AD-5) |
| A row parks the Run | result carries a `Park` | Run `needs_you`; walker waits in one `recv` on `human:{run_id}` | slot and partition held |
| A signal arrives | `signal_run` applied and committed first | walk resumes at the queued row with `resume_signal` set | the record, not the message, is passed on |
| The wait expires | `recv` returns `None` | Run `failed`, record `failed · parked 30 days`, park cleared | — |
| A signal beat the expiry | Run no longer `needs_you` | nothing written, one log line | — |
| The backend is killed mid-row | row `running`, Attempt open | re-executed step closes Attempt 1 `error`, opens Attempt 2 | completed steps are not re-run |
| `cancel(run_id)` | any non-terminal Run | the workflow's next step raises and the walk ends | a late result is absorbed (4.5) |
| `list_queue()` | workflows `ENQUEUED`/`PENDING` | oldest first; positions among the waiting only | an unknown state reads `pending` |
| `attempt_record(ref)` | `{workflow_id, step_id}` | the recorded step, `succeeded` or `failed` | `None` for a ref this adapter did not write |
| `enqueue` before launch | engine not started | `RuntimeError` naming it | never a silent no-op |
| An `error` row with `on_fail: continue` | row declared it | the successor is queued; the row keeps `error` and its reason | last row: Run ends `done` |
| Two Runs, one Repository | both enqueued | the second does not run while the first holds the partition | — |

</intent-contract>

## Code Map

**New — the engine, behind one package (AD-6)**

- [backend-api/src/orchestrator/infrastructure/dbos/facade.py](../../../../../../backend-api/src/orchestrator/infrastructure/dbos/facade.py)
  — `DurableEngine` protocol + `RealEngine`. The only module that writes `import dbos`.
- [.../dbos/config.py](../../../../../../backend-api/src/orchestrator/infrastructure/dbos/config.py) — `EngineConfig`,
  `engine_config(settings)`, `dbos_config`, `QUEUE_NAME`, `HUMAN_TOPIC`, `WORKFLOW_ID`, `STEP_ID`.
- [.../dbos/walker.py](../../../../../../backend-api/src/orchestrator/infrastructure/dbos/walker.py) — `WalkerDeps`,
  `build_walk`: five steps (`next_row`, `attempt_row`, `apply_result`, `close_run`, `expire`) and `run_walk`.
- [.../dbos/adapter.py](../../../../../../backend-api/src/orchestrator/infrastructure/dbos/adapter.py) —
  `DbosWorkflowEngine`: the port's six methods plus `launch`.
- [.../dbos/startup.py](../../../../../../backend-api/src/orchestrator/infrastructure/dbos/startup.py) —
  `walker_deps`, `build_engine`, `serving`, `launch_engine`.

**New — the rules and the seam (application)**

- [.../application/steps/context.py](../../../../../../backend-api/src/orchestrator/application/steps/context.py) —
  `StepPorts`, `StepContext`, `StepExecutor` (AD-9's field list).
- [.../application/steps/registry.py](../../../../../../backend-api/src/orchestrator/application/steps/registry.py) —
  `EXECUTORS`, `register`, `executor_for`, `execute`.
- [.../application/use_cases/walk.py](../../../../../../backend-api/src/orchestrator/application/use_cases/walk.py) —
  `WalkPorts`, `next_row`, `attempt_row`, `run_row`, `apply_result`, `close_run`, `expire`.
- [.../infrastructure/db/writers.py](../../../../../../backend-api/src/orchestrator/infrastructure/db/writers.py) —
  `SessionUnitOfWork`, `open_writer_ports`: one session per durable step.

**Changed**

- `application/use_cases/writers.py` — `park_run`, `expire_run`, `RUN_EXPIRED`.
- `application/use_cases/start_attempt.py` — `_open_the_row`: a row already `running` is the interrupted one.
- `application/use_cases/apply_step_result.py` — `_on_fail`: `continue` routes to the successor; `_park` delegates.
- `application/steps/__init__.py` — re-exports the registry beside `KIND_META`.
- `main.py` — builds the durable engine, `serving(...)` around `uvicorn.run`, `launch_engine()` inside
  `run_migrations`, and the start-up step moved off the event loop with `asyncio.to_thread`.
- `infrastructure/settings.py` + `.env.example` — `HUMAN_WAIT_SECONDS`.
- `pyproject.toml` — `dbos==2.31.0`, and the AD-6 forbidden contract.

**Read-only anchors that shaped the design**

- `tests/unit/test_migrations.py` — replaces `main.run_migrations` wholesale; start-up work must live inside it.
- `tests/unit/test_main_templates_seed.py:85` — `["migrate", "seed", "harness"]`; a fourth collaborator must be
  inert when nothing is serving.
- `tests/unit/test_local_workflow_engine.py` — pins `LocalWorkflowEngine`; the class stays, wired nowhere.
- `tests/unit/test_run_statuses.py` — freezes both transition tables; `expire` is `needs_you → failed`.
- `tests/unit/test_gate_events.py` — freezes `GATE_EVENTS`; the expiry is recorded as `failed`.

## Tasks & Acceptance

- [x] `dbos==2.31.0` in `pyproject.toml` and `uv.lock`; the AD-6 forbidden contract in `[tool.importlinter]`.
- [x] `HUMAN_WAIT_SECONDS` in the typed settings and `.env.example` (AD-20).
- [x] `application/steps/{context,registry}.py` and their re-export; an unregistered kind parks `misconfigured`.
- [x] `application/use_cases/walk.py`; `writers.park_run` / `writers.expire_run`; `start_attempt` recovery branch.
- [x] `apply_step_result` routes `on_fail: continue`.
- [x] `infrastructure/db/writers.py`: one `WriterPorts` scope per durable step.
- [x] `infrastructure/dbos/{facade,config,walker,adapter,startup}.py`.
- [x] `main.py` builds and launches the engine inside the start-up step, off the event loop.
- [x] Unit tests for every module above, including the walk over a fake durable engine.
- [x] `tests/e2e/test_engine_walker.py`: the real engine walks a real Run in the built image.
- [x] `make lint`, `make test`, `make openapi`, `make e2e` green.

## Design Notes

**The brief's `AGENTS.md` edit was refused.** It asks for a line in `backend-api/AGENTS.md` about bumping
`DBOS_APPLICATION_VERSION`; hard rule 1 makes every `AGENTS.md` read-only. The rule is stated instead where it is
read: `.env.example`'s own comment on the variable, and `infrastructure/dbos/config.py`'s docstring.

**`expired` is not a gate event.** The brief says the expiry records `expired`; `domain/statuses.py` says in as
many words that `expired` is not in the alphabet and that AD-13's expiry is applied as Run `failed`. The spine
binds: the record is `failed`, and `parked 30 days` is its text.

**The Attempt is opened inside the executing step, not before it.** The brief's loop has `step(start_attempt)`
and `step(execute_row)` as two steps and leaves "the exact recovery sequence" to this story's spec checkpoint
(waived). Two steps make the start a *recorded* step: after a kill, replay hands back Attempt 1 and the
interrupted row silently continues as the same attempt, contradicting the brief's own acceptance criterion that
the interrupted row gets Attempt 2. One step re-executes both, so `start_attempt` finds the row `running` with an
Attempt that never ended, closes it `error` and opens the next.

**The launch lives inside `main.run_migrations`.** `tests/unit/test_migrations.py` replaces that function
wholesale to prove "migrate before bind", so start-up work outside it is invisible to the gate and reaches a real
database in the unit suite. `serving(engine)` is what keeps the fourth collaborator inert for
`tests/unit/test_main_templates_seed.py`, which calls `run_migrations` directly: an engine is launched only while
a composition root is serving with one.

**The start-up step runs off the event loop.** `DBOS.register_queue` refuses to run on a thread with a running
loop, because it writes to the system database; the lifespan is async. `await asyncio.to_thread(run_migrations,
settings)` is the fix, and it is the right one for the migrations and the seeds too — all of it is blocking I/O
that uvicorn still waits for before it binds.

**The queue is declared after `start`, not before.** Declaring it writes its concurrency to the system database,
which does not exist until the engine is started; the queue manager picks a new queue up on its next poll.

**`LocalWorkflowEngine` stays, wired nowhere.** `tests/unit/test_local_workflow_engine.py` is an anchor, so the
class cannot be deleted. Both its docstrings now say it is dead and why.

**A parked Run waits, whichever half of the loop parked it.** `close_run`'s status goes to the same `recv` the
executor's park goes to. A walk that returned there instead would leave a Run `needs_you` on screen with no
workflow to deliver the Operator's signal to — and, once 4.9 lands, `engine.signal` would write a notification
nobody reads.

**`cancel` sends as well as cancels.** `DBOS.cancel_workflow` makes the *next step* raise, and a walk waiting in
`recv` has no next step: without a message the workflow would hold its slot and its Repository partition until the
thirty-day deadline. The adapter cancels first, then sends on the same topic, so the walk wakes into a step that
raises.

**`close_run` reports a stall rather than a `done`.** A Run with no queued row and an unfinished row parks
`internal · no runnable step: {path} is {status}`. That is what an `on_fail: escalate` row reaches today, and it
is the honest reading of "the walker executes existing rows": there is nothing to execute and the Run is not
finished.

## Verification

```bash
make lint && make test && make openapi
PATH="$HOME/.docker/bin:$PATH" make e2e
```

## Review Triage Log

### 2026-09-06 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 3, medium 5, low 4)
- defer: 9: (high 0, medium 4, low 5)
- reject: 6: (high 0, medium 1, low 5)
- addressed_findings:
  - `[high]` `[patch]` The walker discarded `expire`'s answer, so a Run a signal resumed as the deadline passed
    was abandoned `running` with a queued row and no workflow. The walk now carries on when `expire` reports
    the Run is running again.
  - `[high]` `[patch]` A Run parked by `close_run` ended its walk, so it sat `needs_you` with nothing to deliver
    an Operator signal to. `close_run`'s status now goes to the same `recv` wait an executor's park goes to.
  - `[high]` `[patch]` `cancel` did not end a parked Run's `recv`: `DBOS.recv` has no cancellation check, so the
    workflow — and its slot and its Repository partition — would be held for up to thirty days. The adapter now
    cancels and then sends on the Run's topic.
  - `[medium]` `[patch]` `close_run` on a Run `cancel` had already moved raised `InvalidTransition` inside a
    durable step. It now reports the Run as it stands, the way `apply_step_result` reports a late result.
  - `[medium]` `[patch]` An executor reporting `planned`, `queued` or `running` would raise in
    `apply_step_result` inside a durable step. `registry.execute` refuses it as `internal · misreported {status}`.
  - `[medium]` `[patch]` `HUMAN_WAIT_SECONDS` reached the walker only through `startup`, while a test on the
    unread `EngineConfig.human_wait_seconds` looked like it pinned that wiring. The dead field is gone and
    `walker_deps` is its own asserted function.
  - `[medium]` `[patch]` Two new assertions would have had to be edited by 4.7 — `EXECUTORS == {}` and the e2e
    module's `misconfigured · no executor for kind plan.check`. Both are now written as invariants of having been
    walked, which hard rule 1 asks for.
  - `[medium]` `[patch]` A `recv` message carrying no `kind` raised `KeyError` in the workflow body, where there
    is no step to record it. It now resumes the row with no `resume_signal` and logs one line.
  - `[low]` `[patch]` `serving` cleared the whole registry instead of removing the engine it added.
  - `[low]` `[patch]` The adapter re-spelled `PENDING` as a literal instead of importing the facade's constant.
  - `[low]` `[patch]` `attempt_record`'s payload dropped the step id and the error the engine recorded.
  - `[low]` `[patch]` Three docstrings miscounted the walker's steps, the walk's calls and the facade's methods.

## Auto Run Result

Status: done

**What was implemented.** The `WorkflowEngine` port on DBOS, and the walker that executes a Run's rows through
4.5's writers. DBOS is named in exactly one module; the rules the walk needs are in `application/`, and the
walker is a loop over five durable steps.

**Files changed**

- `backend-api/src/orchestrator/infrastructure/dbos/facade.py` — new: `DurableEngine` + `RealEngine`, the only
  module that imports `dbos`.
- `.../dbos/config.py` — new: `EngineConfig`, `engine_config`, `dbos_config`, the queue and topic names.
- `.../dbos/walker.py` — new: `WalkerDeps`, `build_walk`, the five steps and the workflow.
- `.../dbos/adapter.py` — new: `DbosWorkflowEngine`, the port's six methods plus `launch`.
- `.../dbos/startup.py` — new: `walker_deps`, `build_engine`, `serving`, `launch_engine`.
- `.../application/steps/context.py` — new: `StepPorts`, `StepContext`, `StepExecutor` (AD-9).
- `.../application/steps/registry.py` — new: the executor registry and `execute`, which never raises.
- `.../application/use_cases/walk.py` — new: `next_row`, `attempt_row`, `run_row`, `apply_result`, `close_run`,
  `expire`.
- `.../infrastructure/db/writers.py` — new: `SessionUnitOfWork`, `open_writer_ports` — one session per step.
- `.../application/use_cases/writers.py` — `park_run`, `expire_run`, `RUN_EXPIRED`.
- `.../application/use_cases/start_attempt.py` — the interrupted-row recovery branch.
- `.../application/use_cases/apply_step_result.py` — `on_fail: continue`; `_park` delegates to `park_run`.
- `.../application/steps/__init__.py` — the registry re-exported beside `KIND_META`.
- `.../infrastructure/engine/{__init__,local.py}` — docstrings: the placeholder is wired nowhere now.
- `main.py` — builds the engine, `serving(...)` around `uvicorn.run`, `launch_engine()` inside `run_migrations`,
  and the whole start-up step moved off the event loop.
- `infrastructure/settings.py`, `.env.example` — `HUMAN_WAIT_SECONDS`.
- `pyproject.toml`, `uv.lock` — `dbos==2.31.0`, and the AD-6 forbidden contract.
- Nine new unit modules, one new shared fake (`tests/unit/fakes/dbos.py`) and one new e2e module.

**Review findings.** 12 patched (3 high, 5 medium, 4 low), 9 deferred, 6 rejected. Follow-up review
recommended: **true** — three patched findings were `high` severity.

**Verification, as run on this machine (all after the patches):**

- `make lint` — exit 0. ruff, `ruff format --check` (327 files), `mypy --strict` over `domain/` + `application/`
  (69 files), `lint-imports` **4 contracts kept / 0 broken** (the new AD-6 contract with one ignored import),
  env contract 27 ↔ 33, test pairs 113/113 backend and 42/42 web-client, astro check 0 errors, eslint, prettier.
- `make test` — exit 0. Backend 3543 passed / 23 skipped; the re-report over `domain/` + `application/` is
  **100 % branch** (`--fail-under=100`, 0 missed). Web-client 722 passed.
- `make openapi` — exit 0, no drift: this story publishes no route.
- `PATH="$HOME/.docker/bin:$PATH" make e2e` — exit 0; 124 passed, 27 subtests passed, against a stack built from
  the image. Two failures were diagnosed and fixed on the way there, and both were real packaging/runtime facts
  no local gate could have shown: `DBOS.register_queue` refuses to run on a thread with a running event loop
  (the start-up step now runs in a worker thread), and it writes to the system database, so the queue is declared
  *after* `launch` rather than before it.
- `make e2e-ui` — not run: no hand-written web-client file changed in this story, and `127.0.0.1:4321`, the port
  Playwright's `webServer` binds, is held by the operator's own dev stack. Recorded rather than skipped silently.

**Residual risks**

- The e2e suite is no longer twice-runnable against one stack (deferred item 1): parked Runs hold their slots and
  nothing can release them until 4.9. `make e2e` builds a throwaway stack, so the gate is unaffected.
- `tests/e2e/test_run_creation.py::test_get_reads_back_the_created_run` compares a `POST /runs` body with a later
  `GET`, and the only field that can differ is `status`. It passes today because the walker's Runs occupy both
  `MAX_ACTIVE_RUNS` slots before that test runs, so its Run is never dequeued — a property of the suite's order
  and of `MAX_ACTIVE_RUNS=2`, not of the assertion. When 4.7 lets Runs reach a terminal status the slots free up
  and that assertion becomes a race with the walker. It is an anchor, so this story neither edited it nor relied
  on editing it; the operator should decide before 4.7 lands.
- The engine's own guarantees — replay after a `SIGKILL`, cancel within 5 s, the queue's serialisation — are
  asserted over the fake here and against the library's documented API surface, not yet against the real engine
  under a kill. Story 4.17 is that proof.
