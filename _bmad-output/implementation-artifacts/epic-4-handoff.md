# Epic 4 handoff — what exists, and why it is shaped that way

Written 2026-09-07, after story 4-17. For whoever builds Epic 5 and after.

`epic-1-handoff.md`, `epic-2-handoff.md` and `epic-3-handoff.md` still hold; nothing in any of them
was undone here. Read this once before your first Epic 5 story; you do not need it again.

The commits are `b91d277..4e30cf4` on `feat/epic-4-runs`: seventeen stories in twenty commits,
342 files, +56704/−964. Every story landed; none was abandoned.

---

## 1. What you can rely on

**A Run is planned completely before it starts, and then walked one row at a time.**

```
domain/entities/{run,step_run,attempt,gate_record,harness}.py   the four entities + harness
domain/statuses.py                     both state machines as pure functions; unknown transitions raise
domain/values.py                       Park · Redispatch · StepResult · Signal · PlannedRow
application/plan/                      plan_run() — the only expander
application/use_cases/preflight.py     run_preflight() + PreflightPorts
application/use_cases/create_run.py    create_run() — persists rows and enqueues, one transaction
application/use_cases/{start_attempt,apply_step_result,signal_run}.py   the ONLY status writers
application/steps/                     the executor registry and nine kinds
application/graph.py                   build_template_graph + build_run_graph, one module by design
infrastructure/dbos/                   the WorkflowEngine port's only implementation
```

`/api/v1` gained, on top of Epics 1–3:

```
GET POST  /runs/preflight                    api/routers/runs.py
GET POST  /runs                              api/routers/run.py
GET       /runs/{run_id}                     api/routers/run.py      (minimal — see §2)
GET       /runs/{run_id}/detail              the full read model
GET       /runs/{run_id}/graph               api/routers/graph.py, beside the template graph
GET POST  /runs/{run_id}/signals
GET POST  /repositories/{id}/init
GET       /queue
GET       /harnesses
```

**The screens.** `/workflows/new` (pre-flight and *What will run*), the Board on `/`,
`/workflows/:runId` (Run detail), and the queue section of `/runs`. Logic lives in
`src/lib/{newwf,board,runs}/` so it unit-tests without rendering, following `ProjectForm.tsx`.

**Gates.** All pass from a clean tree: `make lint` (4 import-linter contracts), `make test`
(4072 backend / 973 web-client, `domain/` + `application/` **100 % branch, 0 partial, no pragmas**),
`make openapi` (no drift), `make e2e` (144 + 34 subtests), `make e2e-ui` (118), and a new
`make durability` (11). `make e2e` is twice-runnable against one stack and must stay that way —
verified by running it three times against one held stack with zero leftover `queued`/`needs_you`
rows after each pass.

**`repo-init@1` runs end to end.** `plan → checkout → install → commit → push → link` on the real
engine against a local bare `file://` origin, with `run.worktrees` recording
`created_branch: true, pushed: true` and the compare URL captured. `tests/e2e/test_repo_init.py`
is the proof.

---

## 2. Decisions that are load-bearing — do not undo these by accident

**`GET /runs/{run_id}` is deliberately still minimal, and the full read model is a sibling route.**
Two frozen tests pin the bare route byte-for-byte to the run embedded in `POST /runs`'s response, so
4-12 landed `RunDetailOut` on `GET /runs/{run_id}/detail`. The Run detail screen reads the sibling.
Do not "fix" this by widening the bare route.

**A router module is frozen at its own route count, so new routes go in a new module on the same
prefix.** `runs.py`, `run.py`, the signals module, `repository_init.py`, the queue module and
`graph.py` each carry a route-count assertion. Stories 4-4, 4-9, 4-10, 4-11 and 4-12 all hit this and
all solved it the same way — same prefix, same bearer dependency, invisible from outside. **Mount
order is load-bearing**: `run.router` mounts *after* `runs.router`, or `/runs/{run_id}` swallows
`/runs/preflight`. `main.py` uses a `_mount` helper for every router **except** `graph_text.router`
and `templates.router`, which keep literal `include_router` calls because `test_graph_text_router.py`
reads that literal source via AST. Do not tidy those two.

**Every published path still needs a GET** — `test_bearer_auth.py` indexes `paths[path]["get"]` for
every path in the contract, so a POST-only path fails it. That is why `GET /runs/preflight`,
`GET /runs/{id}/signals` and `GET /repositories/{id}/init` exist at all.

**Executors register by an explicit import in `infrastructure/dbos/startup.py`, never from
`application/steps/__init__.py`.** That package cannot import the executor modules itself: they
import `application/templates/*`, which imports back into `application/steps` for `KIND_META`. It is
a real circular import, reproduced and documented on 4-7. Put `register(...)` inside each
`steps/<kind>.py` and import it from `startup.py`.

**The executor contract.** `execute(ctx: StepContext) -> StepResult`. An executor **must** return a
completion status (`done|blocked|checkpoint|error|skipped`); anything else is refused as
`internal · misreported {status}`. A raise becomes `internal: {ExceptionClass}` — **class name only,
never the message**, which is an AD-5 property, not a style choice. An unregistered kind parks
`misconfigured · no executor for kind {kind}`. Executors never write status and never touch a
repository. `StepPorts.workspace` is a **factory** (`Callable[[str | None], Workspace]`), so a git
executor calls `ctx.ports.workspace(ctx.cwd)`. `StepPorts` grows additively, wired in
`startup.walker_deps`.

**The walker's step sequence is frozen at five steps** by `test_dbos_walker.py`, and that sequence is
what `DBOS_APPLICATION_VERSION` pins (AD-6). Story 4-10 needed a completion hook and wired it as
plain code inside the existing `apply_result` / `close_run` closures rather than declaring a sixth
step. Changing the sequence is a spine-level decision, not a story-level one.

**`dbos` is importable by exactly one module.** `infrastructure/dbos/facade.py`, enforced by a
dedicated import-linter contract with a negative test proving the contract fires. Four contracts
now; all must stay kept.

**Insert order is the adapter's job.** No SQLAlchemy model in this repo declares `relationship()`,
so the unit of work has no dependency edge and orders inserts arbitrarily — an `attempt` reached the
database before its `run` and violated the foreign key. The four Run adapters `flush()` at each
insert, which makes the caller's order the database's order, so **`create_run` calls them
parent-first**: run → step_runs → attempts → gate_records. A use case cannot fix this itself; the
`UnitOfWork` port has `commit`/`rollback` and no `flush`.

**`with_resolved` carries everything the executor needs, because AD-7 forbids re-reading the Template
at execution time.** The resolved `timeout_min`; `on_fail` as `"fail" | "continue" | "escalate"` or
`{"target_seq": int, "max": int}` — those are `Redispatch`'s own field names, so a consumer writes
`Redispatch(**on_fail)` with no other input; and `escalate_when` on agent rows, carried verbatim for
Epic 5 with no consumer in this epic. An absent `on_fail` key means the DSL default, `escalate`. The
redispatch target is resolved to a `seq` **within the row's own frame** at plan time; a target that
names no row in the frame is a plan error.

**Row paths use step ids verbatim.** `stories[0].commit-guard` has a hyphen because
`templates/story.yaml` declares that id. Paths are the join key for the run graph — do not
normalise, translate or prettify one anywhere. The template graph stays index-free with calls
collapsed; the run graph is the expanded rows and carries indices. Expansion belongs to the planner.

**`InvalidTransition` is deliberately not a `DomainError`.** Reaching it means a bug and surfaces as
a 500. `signal_run` validates against the AD-13 table **first** and raises `Conflict` for the 409, so
an invalid operator signal never reaches the transition function.

**`GATE_EVENTS` stays bound to its old value** because a frozen assertion pins it;
`MachineEvent = ("redispatch", "retry_auto")` and `ALL_GATE_EVENTS` sit beside it. Use
`ALL_GATE_EVENTS` when you mean the union. Note the frozen assertion's *name* is now narrower than
the union — `test_gate_events.py` states the split.

**Three brief-vs-spine conflicts were resolved spine-first**, all recorded in their stories' Design
Notes: `continue` on a `plan_stale` park is `error → running`, not `→ done` (`STEP_TRANSITIONS` has
no `error → done`); `retry` admits `protected_path` as a park kind rather than via a disjunct that
would also admit `plan_stale` and `budget`; and `cancel` writes only the gate record AD-13's table
requires, not a second one listing removed worktrees.

**Two briefs were factually wrong and the code follows reality.** 4-10's AC2 assumed the clone check
would report the new method version after init — it does not, because `repo-init@1` pushes `_bmad/`
to `chore/bmad-init` and never to the default branch, so the check keeps answering `missing` until
the Operator merges the compare link. 4-11 asked for a nullable `run.worktrees_removed_at`, which
would have joined a frozen closed-set assertion about which columns may be null; it landed as
`Run.worktrees_removed: bool` NOT NULL instead, same idempotency guarantee.

**Web-client shape.** One polling loop for the whole app: `src/stores/poll.ts`
(`$poll` / `configurePolling` / `forceTick` / `stopPolling`) — call `configurePolling` from your own
fetch rather than opening a second interval. `src/components/FailedFetch.tsx` is generic
(`{method, path, status, onRetry}`). **Rail and footer live counts cannot be a nested `client:load`
island**: `AppRail` / `FooterReadout` / `SurfaceBar` / `Shell` are rendered via
`AstroContainer.create()` with zero framework renderers in two frozen unit tests, so nesting React
there throws. 4-14 solved it by DOM-patching the already-rendered elements (`syncFooter` / `syncRail`,
with `copyScopeAttr` to inherit Astro's scoped CSS) and 4-15 reused it. Do not invent a third way.
A `client:load` island needs a **hydration gate** before a Playwright test interacts with it —
4-13's `openForm` helper is the pattern, and its absence causes an intermittent hang rather than an
immediate failure. The Board caps its `done` and `failed` columns at the 20 newest with an explicit
"N more not shown" line; `queued`, `running` and `needs_you` are never capped.

---

## 3. The rules that will bite you

**Three anchor edits happened in this epic. All three were operator decisions, in the shape of a
conversation, and NONE is a standing rule.** Cite them as precedent for *asking*, never for
*editing*.

1. `test_main_templates_seed.py` (story 4-3) — the one test
   `test_run_migrations_migrates_then_seeds_and_returns_the_head` monkeypatched exactly two start-up
   collaborators and asserted `["migrate", "seed"]`. Harness seeding had to go inside
   `main.run_migrations` (anything beside it is invisible to `test_migrations.py`, which replaces
   that function wholesale), and three other placements each broke a different frozen test. Operator
   authorised adding the third mock, on condition the assertion stay an **exact ordered equality** so
   a fourth unmocked collaborator still reaches the real, unreachable database and fails loudly.
2. `test_engine_walker.py` (story 4-7) — **its precondition depended on an executor being missing.**
   The `walked` fixture claimed "parked on its first row", which was true only because no executor
   existed and the row parked `misconfigured · no executor for kind shell`. Registering `plan.check`
   and `shell` — the whole point of 4-7 — made the Run run to `done` and free the Repository
   partition, so `assert second["starts_now"] is False` failed. Operator authorised giving the module
   its own `CHECKPOINT_TEMPLATE` so the first Run genuinely parks. Coverage strictly increased:
   `!= QUEUED` became `== NEEDS_YOU`, the park fields are now asserted exactly, and the AD-12
   assertion was left untouched.
3. `test_engine_walker.py` again (story 4-17) — `wait_until_walked` returned the instant a Run left
   `queued`, so it could capture `running` on the way to `needs_you`. Harmless under the old
   assertion; an intermittent gate failure under the strengthened one. Operator authorised making the
   helper wait for a **settled** status (`needs_you`/`done`/`failed`/`cancelled`). The deadline now
   distinguishes "never left `queued`" from "left `queued` but never settled" — different bugs. No
   assertion was weakened.

**The lesson under all three: a test whose precondition is "the feature does not exist yet" becomes
a liability the moment the feature lands.** Do not write one. Assert the property you mean.

**`make e2e` is the only gate that catches an entire class of bug.** It builds and runs the real
image. It caught, in this epic alone: `DBOS.register_queue` refusing a thread with a running event
loop; the queue needing to be declared *after* `launch` because it writes to the system database; and
a Dockerfile/packaging gap in Epic 3 that every local gate missed. Run it before you believe you are
done.

**Two latent 500s were found by schemathesis, not by anyone reading the code** — an uncaught
`decimal.InvalidOperation` in `MoneyStr` on an enormous `budget_usd`, and a NUL byte in
`template_name` reaching psycopg. Both were fixed at the source and pinned with unit tests so they no
longer depend on the fuzzer sampling them.

**Port 4321 is still single-tenant.** `make e2e-ui` runs `pnpm preview` on it, and so does the
compose `web-client` container. Stop the container, run the gate, start it again. Stories cannot run
in parallel for this reason among others.

**A story agent that spawns an implementation subagent must wait for it.** Story 4-1 ended its turn
while its subagent was still writing and stalled the run with the diff uncommitted; story 4-13's
`fork`, dispatched for research only, implemented and committed the entire story on its own. Neither
lost work, because both were caught and audited — but finish synchronously or HALT.

---

## 4. Known gaps, honestly

- **`cancel` kills no process group today.** `attempt.pgid` is never written, because AD-8 gives that
  write to the `agent` executor and the field list scopes `pgid` to `agent` rows. `signal_effects._cancel`
  collects `attempt.pgid` and always finds `None`. Costless in Epic 4 — nothing here leaves a process
  running at a stop — but **Epic 5's `agent` kind must land the `mark_started` write with it**, or
  cancel silently fails to kill anything.
- **The orphan clause of FR-12: the reaping half is now proven, the Run-level half is not.**
  `tests/unit/test_process_runner_reaping.py` proves on Linux that `kill_group` collects its own
  child (`waitpid` answers `ECHILD`) and that the group leaves the process table (`killpg` answers
  `ESRCH`), with the process table standing and no namespace teardown involved. What is left for
  Epic 5 is an end-to-end orphan scenario at Run level — a kill that leaves the process table
  standing — and that needs `attempt.pgid` (above) first. Note that `tests/e2e/test_durability.py`
  defers this coverage to "`ProcessRunner.kill_group`'s own unit coverage", and until commit
  `bb69235` that coverage **did not actually prove reaping**: on Darwin it passed for an unreaped
  zombie, and on Linux it failed.

- **No local gate runs on Linux, and that is a structural blind spot.** `make lint`, `make test`,
  `make e2e-ui` and `make durability` all run on the operator's macOS machine; only `make e2e` runs
  anything inside a Linux image, and it runs the *app*, not the unit suite. A syscall whose
  behaviour differs between the two platforms can therefore be green locally and broken in
  production. That is exactly what happened: `_group_alive` probed with `os.killpg(pgid, 0)` and
  treated any `OSError` as "dead", which is true on Darwin — where an unreaped zombie answers
  `EPERM` — and false on Linux, where it answers successfully. So `kill_group` waited out its full
  ten-second grace and then `SIGKILL`ed a corpse on **every** kill in a container, while every local
  gate passed. Measured on Linux before the fix: 20.16 s for two `kill_group` calls, group still
  reading alive; after: 0.10 s, group gone. CI's `unit` job on ubuntu is what caught it. **Treat a
  green local run as evidence about macOS, not about the deployment platform.**
- **`tests/unit/test_dbos_facade.py::CALLED` is stale**: it lists `create_schedule`, which the facade
  no longer calls, and omits `apply_schedules`. It still passes and nothing is unpinned
  (`test_dbos_schedule_registration.py` covers the new call), but correcting it is an anchor edit and
  therefore an operator decision.
- **Project env vars are not wired into `shell`** (`env={}`) — Epic 5's decryption work.
  `StepPorts.protected_paths` is `None` for all of Epic 4; Epic 5 wires
  `application/rules/protected_paths.py` into it without touching `steps/git_commit.py`.
- **N+1 reads** in `run_detail` and the Board, matching an existing codebase pattern. Deferred, not
  introduced here.
- **A concurrent write race still surfaces as a 500, not a 409** — the same unmapped `IntegrityError`
  pattern Epics 2 and 3 recorded.
- **The CI durability step is the one thing that could not be verified locally**, because nothing in
  this repo runs GitHub Actions. A sixth job was impossible (`test_ci_workflow.py` freezes the job
  tuple at five, and AD-18 fixes those five), so `make durability` runs as a **step** of the `e2e-api`
  job after its own stack is stopped, building its own compose stack; the job timeout went 20 → 40
  minutes for the image build. If the runner exceeds it, the fix is a larger timeout or moving the
  step to the `images` job. **The first CI run on this branch is what will say.**
- **`followup_review_recommended: true`** on several stories, and roughly forty deferred items sit
  across the seventeen specs' frontmatter.

---

## 5. What Epic 5 specifically inherits

Epic 5 adds the agent step. Five things are already decided for you:

- **The registry is the seam and it is closed.** Implement `StepExecutor`, register from
  `startup.py`, return a completion status, never write status, never touch a repository. Nine kinds
  already do this; the `agent` kind is the tenth.
- **`escalate_when` is already on the row**, carried verbatim by the planner with no consumer in this
  epic. So is `retry`. AD-7 forbids re-reading the Template, so `with_resolved` is your only source —
  if you need a field that is not there, it goes in the planner, not in the executor.
- **`apply_step_result` already implements redispatch bounds**, including the exhausted case and the
  skipped-target case. The `## Verify Failure` append on a redispatched attempt is yours.
- **The budget seam exists.** `after_route(run, row, result)` is left deliberately empty for AD-8's
  double record. Do not add a second data-collection path; trajectory capture is one append-only row
  per Story reaching `done` (AD-19).
- **`attempt.pgid` is your obligation**, per the first bullet of §4. Cancel does not work without it.
