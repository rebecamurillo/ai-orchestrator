---
status: done
story: "4-11"
epic: 4
title: Queue read model and scheduled jobs
warnings: []
baseline_revision: '033d3c84e9ca901e08563352f6ae690bcffbf0c3'
---

# Story 4.11 — Queue read model and scheduled jobs

As the Operator,
I want to see the queue as the engine sees it, with the reason each Run waits, and to have
stale worktrees and clone checks handled without me,
So that "why is nothing happening" has an answer on screen and the disk does not fill up.

## Code Map

- `backend-api/src/orchestrator/domain/ports/engine.py::WorkflowEngine.list_queue,
  .schedule` (4.6) — already declared, unused until now; this story is their first caller.
- `backend-api/src/orchestrator/infrastructure/dbos/adapter.py::DbosWorkflowEngine.list_queue,
  .schedule` and `infrastructure/dbos/facade.py::DurableEngine.schedule,
  RealEngine.schedule` (4.6) — already implemented and unit-tested; reused whole.
- `backend-api/src/orchestrator/application/preflight/checks.py::run_label, queue_note`
  (4.3) — `run_label`'s exact label format (`"{template} · {branch}"`) is reused by
  `application/use_cases/queue.py`; `queue_note`'s two-way holder/global-concurrency
  decision is the same shape this story's `_reason` makes, in the endpoint's own fixed
  words rather than that one's prose.
- `backend-api/src/orchestrator/application/use_cases/project_runs.py::_current_step_label`
  (4.10) — the same "parked, then running, then queued, then last touched" question this
  story's `_next_step_label` answers; duplicated on purpose (module docstring explains why,
  the same way `_reason` is duplicated between `preflight/checks.py` and
  `use_cases/clone_check.py`).
- `backend-api/src/orchestrator/application/use_cases/clone_check.py::run_clone_check,
  run_clone_checks_for_project` (Epic 2) — reused whole by the `clone_check` job; this story
  writes no second implementation of the four lines.
- `backend-api/src/orchestrator/application/use_cases/signals.py::SignalEffectPorts,
  _apply_cancel` (4.9) — the precedent for `worktree_gc`'s own `Git.remove_worktree` call
  and for reading one Run's environment via `read_run_environment` outside the walker.
- `backend-api/src/orchestrator/infrastructure/db/environment.py::read_run_environment`
  (4.8) — reused, unmodified, by both `worktree_gc`'s wiring and (already) `signals.py`.
- `backend-api/src/orchestrator/api/schemas/runs.py::RunSummaryOut` (4.4/4.9) — the
  `RunSummary` the brief names; `api/schemas/queue.py::QueueItemOut` embeds it as-is.
- `backend-api/src/orchestrator/api/schemas/common.py::Page` — `QueueOut` extends it with
  `max_active_runs` rather than inventing a second envelope shape.
- `backend-api/src/orchestrator/main.py::run_migrations` (frozen collaborator-order test,
  4.3) — gains one more guarded collaborator, `schedule_jobs`, after `launch_engine`.
- `backend-api/tests/unit/test_run_repository_adapter.py::
  test_only_the_columns_a_later_story_fills_may_be_null` — an existing, frozen test this
  story's original design collided with; see Design Notes D1.

## Design Notes

**D1 — a real, spine-first finding: the brief's `worktrees_removed_at` collides with a
frozen test (corrected).** The brief's Implementation Notes ask for a migration adding
`run.worktrees_removed_at` (a nullable timestamp) so `worktree_gc` can tell a swept Run from
one it has not reached yet. `tests/unit/test_run_repository_adapter.py::
test_only_the_columns_a_later_story_fills_may_be_null[run]` is an existing test file
(hard rule 1) asserting a closed, hardcoded set of the `run` table's nullable columns; it
names no later story as its replacement, so none of the three narrow anchor exceptions
applies, and it cannot be edited to add a tenth entry. Resolved spine-first, the way 4.10
corrected its own brief's AC2: the Run gained `worktrees_removed: bool = False` instead — a
`NOT NULL` column (`server_default false`) reaches the same idempotency without joining
that frozen set, and it is *more* accurate than the suggested timestamp would have been,
because `run.worktrees` itself is left untouched as history rather than needing a parallel
field: a swept Run's own record still says which branch it worked on after the files are
gone. `test_the_run_table_carries_exactly_the_columns_the_entity_needs` (same file, a
*dynamic* comparison against `Run.model_fields`) still passes unmodified, because the new
field and the new column were added to both sides together.

**D2 — `list_queue`'s reason is a pure join, not a second copy of pre-flight's queue
logic.** `_reason` reuses exactly `queue_note`'s two facts —
`RunRepository.list_by_repository_non_terminal` for the repository-lock holder,
`list_by_status("running") + list_by_status("needs_you")` for the global-concurrency
label list — but states them in the endpoint's own four fixed sentences (SPEC CAP-11)
rather than `queue_note`'s prose (`"queues behind ..."`), because those are two different
readers: pre-flight answers "what would a *new* Run wait behind", `GET /queue` answers "why
is *this stored* Run waiting right now."

**D3 — ordering resolves a tension between the brief's prose and its own AC1.** The
binding rule says "Ordered: active first, then queued by position." AC1's own three rows,
read as a strict sequence, would put a `needs_you` Run *before* an enqueued one — but
`needs_you` is not literally "active" in the sense that matters for a section head like
*What's running*: it holds its slot but is not advancing. `_order_key` reads "active first"
as `running` only, then queued rows by position ascending, then `waiting for your answer`
last — matching the concurrency story the rule states in prose (a parked Run is not what
the ordering wants foregrounded ahead of a Run that will actually start next) and pinned by
this story's own unit tests rather than left ambiguous.

**D4 — `worktree_gc`'s scope is exactly the brief's, not `cancel`'s.** `Git.remove_worktree`
only; no `delete_branch`. 4.9's `cancel` decides branch fate (kept if pushed, deleted if
not) at the moment the Operator acts; a Run that already reached `done`/`failed`/`cancelled`
on its own has already had that decision made for it (by `cancel` itself, or by never
needing one), so this job does not re-open it. Idempotent by construction: `worktrees_removed`
gates every effect, so a second fire of the same day's cron after a crash mid-sweep is a
no-op for every Run the first pass already reached.

**D5 — job wiring stays inside `infrastructure/`, and `schedule_jobs` is guarded the way
`launch_engine` already is.** `serving(engine)` gains two optional parameters
(`session_factory`, `git`), defaulting to `None` so every existing call in
`tests/unit/test_dbos_startup.py` (frozen) keeps compiling and behaving unchanged — that
module's own tests never reach `schedule_jobs`. `main.run_migrations` gains exactly one new
line, `schedule_jobs(settings)`, after `launch_engine()`; `test_main_templates_seed.py`'s
frozen `recorder.order == ["migrate", "seed", "harness"]` still passes because the new step
runs for real in that test too and is a no-op (`_SERVING` is empty outside a `serving`
block), the same property `launch_engine` already had.

**D6 — `crypto=None` for the `clone_check` job's `ProjectPorts`.** `ProjectPorts.crypto` is
not optional in the dataclass, but `run_clone_check`/`run_clone_checks_for_project` never
read it. Building a real `FernetCrypto` here would validate `ORCHESTRATOR_SECRET_KEY` at
job-registration time — exactly the start-up crash `main.py::crypto_factory` exists to
defer. `tests/unit/test_clone_check_use_cases.py::Harness` already builds `ProjectPorts`
the same way (`crypto=None,  # type: ignore[arg-type]`); `infrastructure/jobs.py` is
outside `mypy`'s scoped files (`domain/` + `application/` only), so no type-ignore comment
is needed there.

## Tasks & Acceptance

### Backend

- [x] `domain/entities/run.py` — `Run.worktrees_removed: bool = False` (D1).
- [x] `domain/ports/workspace.py` — `Workspace.remove(path)`, idempotent (AD-14).
- [x] `infrastructure/workspace/fs.py`, `tests/unit/fakes/workspace.py` — `remove`
  implementations (additive fake, precedented).
- [x] `infrastructure/db/models/run.py`, `infrastructure/db/repositories/runs.py` —
  `worktrees_removed` column and mapping.
- [x] `alembic/versions/0007_run_gc.py` — new: `run.worktrees_removed`, `NOT NULL`,
  `server_default false`.
- [x] `application/use_cases/queue.py` — new: `QueueRow`, `QueueView`, `QueuePorts`,
  `list_queue`, the four fixed reasons, ordering (D2, D3).
- [x] `application/jobs/clone_check.py` — new: `run_clone_check_job`.
- [x] `application/jobs/worktree_gc.py` — new: `WorktreeGcPorts`, `run_worktree_gc` (D4).
- [x] `infrastructure/jobs.py` — new: `scheduled_jobs`, the two jobs' own port wiring (D6).
- [x] `infrastructure/dbos/startup.py` — `serving` gains `session_factory`/`git` (optional);
  new `schedule_jobs` (D5).
- [x] `infrastructure/dbos/__init__.py`, `main.py` — export and call `schedule_jobs`;
  mount `queue.router`.
- [x] `infrastructure/settings.py`, `.env.example` — `worktree_retention_days`,
  `clone_check_cron`, `worktree_gc_cron` (AD-20).
- [x] `api/schemas/queue.py` — new: `QueueItemOut`, `QueueOut` (extends `Page`).
- [x] `api/routers/queue.py` — new: `GET /queue`, its own module (frozen route-count
  precedent on every sibling router).
- [x] `api/providers.py` — new: `queue_ports`.
- [x] New unit tests: `tests/unit/application/test_queue.py`,
  `tests/unit/application/test_jobs_clone_check.py`,
  `tests/unit/application/test_jobs_worktree_gc.py`, `tests/unit/test_fs_workspace_remove.py`,
  `tests/unit/test_queue_router.py`, `tests/unit/test_queue_schema.py`,
  `tests/unit/test_scheduled_jobs.py` — 100% branch coverage on every new/changed line of
  `domain/` + `application/`.
- [x] New e2e test: `tests/e2e/test_queue.py` — `max_active_runs`, a real parked Run and the
  real one queued behind it (both fixed reasons), and AC5 (both jobs registered with their
  configured crons, read from `dbos.workflow_schedules`).

### Acceptance criteria (brief, verbatim; AC1/AC2 as unit tests, AC3/AC4 as unit tests, AC5
as an e2e test)

1. Two Runs on Repository A (running, enqueued) and one parked on Repository B → three
   rows, fixed reasons and positions. —
   `test_queue.py::test_running_queued_and_parked_runs_read_the_fixed_reasons`.
2. `MAX_ACTIVE_RUNS=2`, two active Runs on two Repositories, a third enqueued on a third →
   `global concurrency, held by {label1}, {label2}`. —
   `test_queue.py::test_an_enqueued_run_with_a_free_repository_reads_global_concurrency`.
3. `worktree_gc` on the fake ports, one Run terminal 8 days ago and one terminal
   yesterday → only the older Run's worktrees and logs are removed, marked swept. —
   `test_jobs_worktree_gc.py::test_only_the_older_run_is_swept`.
4. `clone_check` on a Repository whose origin is now unreachable → `status: failed`, no Run
   status changes. —
   `test_jobs_clone_check.py::test_a_repository_whose_origin_is_unreachable_is_stored_failed_and_blocks_no_run`.
5. The app started in the e2e stack; DBOS lists scheduled workflows → both jobs registered
   with their configured crons. —
   `test_queue.py` (e2e)::`test_both_jobs_are_registered_with_their_configured_crons`.

## Spec Change Log

_None._ No anchor file was edited. D1 above is the one place this story's own behaviour
diverges from the brief's literal implementation note; the brief is not an anchor, and the
divergence is resolved spine-first per this run's own operating rules, recorded there
rather than silently.

## Verification

```bash
make lint && make test && make openapi && PATH="$HOME/.docker/bin:$PATH" make e2e && make e2e-ui
```

## Auto Run Result

Status: done

Gates, as run on this machine:

- `make lint` — exit 0 (ruff, ruff format, `mypy --strict` on `domain/`+`application/`,
  `lint-imports` 4/4 kept, env contract 30/36 (6 allowlisted), backend test pairs 143/143,
  `gen:api --check`, web-client astro/tsc/eslint/prettier, web test pairs 43/43).
- `make test` — exit 0; backend `domain/`+`application/` at 100% branch coverage
  (`--fail-under=100`); web-client 738 unit tests passed (no web-client code changed by
  this story).
- `make openapi` — exit 0; `contracts/openapi.json` and `schema.d.ts` regenerated with
  `GET /queue`, `QueueOut`, `QueueItemOut`.
- `PATH="$HOME/.docker/bin:$PATH" make e2e` — exit 0; 144 passed, 32 subtests passed.
- `make e2e-ui` — exit 0; 75 passed (no web-client surface in this story's scope; the
  operator's dev stack was stopped for this dispatch specifically to free
  `127.0.0.1:4321`, and nothing was left listening on it afterward).

One real defect was found and fixed rather than worked around: the brief's own
`worktrees_removed_at` (nullable timestamp) collides with a frozen, closed-set unit test
(D1). Resolved spine-first with a `NOT NULL` boolean instead, which is both compatible and
arguably a better fit for the data (no timestamp precision to reason about, no loss of
`run.worktrees` history).

A stale, locally-generated `.env.e2e` (predating this story's three new settings) initially
made the e2e stack's `backend-api` container fail its healthcheck; regenerating it (it is
git-ignored, not a repository file) resolved it. Noted here in case another local `.env`/
`.env.e2e` on this machine needs the same regeneration before a future story's `make e2e`.

Deferred / for the next story:

- The Runs screen's own queue section (CAP-16, story 4.16) is this story's only consumer of
  `GET /queue`; nothing in `web-client/` was touched here.
- `terminal_poll` (Epic 6) is explicitly out of scope, per the brief.
- No UI yet reads `run.worktrees_removed`; it exists purely for `worktree_gc`'s own
  idempotency until a later story (if any) wants to surface it.
