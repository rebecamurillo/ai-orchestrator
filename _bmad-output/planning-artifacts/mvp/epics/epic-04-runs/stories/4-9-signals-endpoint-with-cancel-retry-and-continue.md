---
status: done
story: "4-9"
epic: 4
title: Signals endpoint with cancel, retry, and continue
warnings: []
---

# Story 4.9 — Signals endpoint with cancel, retry, and continue

As the Operator,
I want one endpoint for every action on a Run, refusing what the Run's state does not admit
and applying the rest exactly once,
So that cancelling, retrying, and continuing are as safe as reading.

## Code Map

- `backend-api/src/orchestrator/application/use_cases/signal_run.py` (4.5) — `signal_run`,
  `SignalPorts`, `SignalOutcome`. Already the one writer of every Operator transition; this
  story's endpoint calls it and does not duplicate any of its writes (AD-8).
- `backend-api/src/orchestrator/application/use_cases/signal_effects.py` (4.5) — `CancelPlan`,
  `EFFECTS`. **All ten AD-13 kinds already have real effects**, not placeholders — 4.5 built
  the whole state machine at once. `_cancel` already returns `CancelPlan{pgids, worktrees}`
  for this story to act on.
- `backend-api/src/orchestrator/application/rules/signals.py` (4.5) — `VALID`, `validate`,
  `admitted_signals(park_kind, row_kind)`. Extended additively (`row_at`,
  `run_admitted_signals`); the existing two-argument `admitted_signals` and its own frozen
  test (`test_signal_rules.py`) are untouched.
- `backend-api/src/orchestrator/domain/ports/git.py` / `.../process.py` (4.7, 4.8) —
  `Git.remove_worktree`, `Git.delete_branch`, `ProcessRunner.kill_group`: this story is their
  first real caller outside a unit test.
- `backend-api/src/orchestrator/application/steps/context.py` — `RunEnvironment.base_dir`,
  reused for `cancel`'s worktree path the same way a git executor resolves it.
- `backend-api/src/orchestrator/infrastructure/db/environment.py::read_run_environment` and
  `.../db/writers.py::open_writer_ports` — both reused as-is for the new provider, mirroring
  `infrastructure/dbos/startup.py`'s own `walker_deps` wiring.
- `backend-api/src/orchestrator/api/routers/run.py`, `.../runs.py` — both carry a frozen
  route-count test, so the new operations land in a new module (`api/routers/signals.py`),
  the same move 4.4 made for `run.py` beside `runs.py`.
- `backend-api/tests/unit/application/writer_fixtures.py` — reused whole (`a_world`,
  `an_attempt`, `EPIC_PLAN`) for every new application-layer test.
- `backend-api/tests/e2e/test_run_creation.py`, `test_clone_check.py::Fixtures` — reused for
  the new e2e module, the same way `test_engine_walker.py` and `test_repo_init.py` do.

## Tasks & Acceptance

**Execution:**
- `application/rules/signals.py` — `row_at(rows, path)`; `run_admitted_signals(run,
  park_row_kind)` (terminal → `()`, queued/running → `(cancel,)`, parked → delegates to
  `admitted_signals`).
- `application/use_cases/signals.py` — new: `SignalEffectPorts`, `handle_signal`. Validates
  via `signal_run`'s own `validate`, refuses every kind this epic does not apply yet with
  `"{kind} not available yet"`, applies `cancel`/`retry`/`continue` (on `checkpoint` or
  `plan_stale`) for real, and runs `cancel`'s kill/remove/delete after `signal_run` commits.
- `application/use_cases/create_run.py` — `RunReadPorts.steps` (optional, additive);
  `park_row_kind_of(ports, run)`.
- `api/schemas/signals.py` — new: `SignalIn`.
- `api/schemas/runs.py` — `RunSummaryOut.admitted_signals`, `.of(run, park_row_kind=None)`.
- `api/routers/signals.py` — new: `POST /runs/{run_id}/signals`, `GET` sibling.
- `api/routers/run.py` — `get()` now also resolves `park_row_kind_of` for `admitted_signals`.
- `api/providers.py` — `signal_effect_ports`; `run_read_ports` now also wires `steps`.
- `main.py` — mounts `signals.router` after `run.router`.
- `infrastructure/dbos/facade.py` — `RealEngine.send`/`.cancel` swallow
  `DBOSNonExistentWorkflowError` (see Spec Change Log — a real gap the e2e gate found).
- New unit tests: `test_handle_signal.py`, `test_run_admitted_signals.py`,
  `test_park_row_kind_of.py`, `test_signals_router.py`, `test_signals_schema.py` — 100 %
  branch coverage on every new/changed line of `domain/` + `application/`.
- New e2e test: `tests/e2e/test_signals.py` — the brief's own e2e AC (`continue` on a real
  `checkpoint` row, walker proceeds to `done`), a real `cancel` (worktree removed, branch
  deleted, verified against the base clone in either topology), a cancelled Run refusing a
  second signal, and the twice-runnable sweep (see Design Notes).

**Acceptance Criteria:** the brief's seven Given/When/Then blocks, verbatim
(`briefs/4-9-signals-cancel-retry-continue.md`) — all covered, either at the unit layer
(`test_handle_signal.py`, `test_signals_router.py`) or, for the one the brief itself marks
`(e2e)`, at `tests/e2e/test_signals.py`.

## Spec Change Log

_None._ No anchor file was edited. Two things worth recording as if they were, because a
later story could otherwise mistake either for an oversight:

**`infrastructure/dbos/facade.py` — a real gap the e2e gate found, fixed at its source.**
Schemathesis's own fuzzing of the new `POST /runs/{id}/signals` path, plus a persistence
fixture elsewhere in the suite that writes a Run row with a synthetic `engine_ref` by hand
(never through `engine.enqueue`), reached a Run whose id names no workflow in DBOS's own
system tables. `RealEngine.send`/`.cancel` called the library directly and let
`DBOSNonExistentWorkflowError` reach the router as an unhandled 500 — reproduced identically
under `make e2e` and confirmed via the container's own traceback (`dbos._sys_db.py`'s
`notifications` insert, foreign-keyed to `workflow_status`). Fixed at the one place `dbos` is
named (AD-6): both methods now catch that one exception and no-op, the same idempotence
AD-13 already asks of every other cancel effect ("a process group, a worktree, a branch
already gone are none of them a failure"). No test file changed; `test_dbos_facade.py` pins
symbols, not behaviour, and is untouched.

**`existing test files` were read, not edited, for the cancel gate record's text.** The
brief's own prose asks for "gate record cancelled (actor operator, text listing removed
worktrees and deleted branches)". AD-13's own table — binding over the brief per this run's
operating rules — lists `cancel`'s record as `gate_record; ProcessRunner.kill_group(...);
engine.cancel; for each run.worktrees[]: ...`, with no requirement on the record's *text*,
and 4.5's landed `signal_run`/`rules/signals.py` already write one fixed-text record
(`"cancelled by the operator"`) *before* the cancel plan is even computed, inside the one
transaction `signal_run` owns. Adding a second, later gate-record write from this story's own
`handle_signal` — after the git/process effects run — would be a fourth caller of
`GateRecordRepository.add`, next to the three status writers AD-8 names exactly two/three of.
The spine's own table needed no such write, so none was added; this is recorded here rather
than silently diverging from the brief's prose.

## Design Notes

**Ten kinds already had real effects; this story's job was the boundary, not the machine.**
`signal_effects.py` (4.5) implements `answer`, `skip_story`, `skip_epic`, `budget_raise`, and
the three `terminal_*` kinds fully and correctly — not as placeholders — because AD-13 is one
state machine and 4.5 built it whole under one 100 %-branch bar. This epic ships no surface
for any of them (no `agent` step, no protected-path rule, no terminal session screen), so
`handle_signal` is the one seam that refuses them with `"{kind} not available yet"` after
`validate` has already proven they would otherwise apply — a later epic's whole job on this
axis is deleting one line from `_in_scope`, never wiring a new effect.

**Why `continue` is in scope for `checkpoint` and `plan_stale` but not `protected_path`.**
AD-13 admits all three; only the first two have a row this epic can actually reach (no
`agent` executor yet, and `protected_paths` is a port with nothing wired behind it — 4.8's
own Design Notes D2). `_in_scope` checks `run.park_kind`, not the row's own kind, which is
enough: AD-13's `continue` rule keys on park kind alone.

**`SignalEffectPorts` mirrors the walker's own environment-reading seam, not a new one.**
`cancel`'s worktree cleanup needs the same `RunEnvironment.base_dir` a git executor resolves,
but `handle_signal` runs *outside* a `StepContext` — there is no row, no attempt. Rather than
inventing a second way to reach a Repository's facts, `SignalEffectPorts.read_environment` is
the exact `Callable[[UUID], RunEnvironment | None]` shape `infrastructure/dbos/walker.py`
already builds via `read_run_environment`, reused by `api/providers.py::signal_effect_ports`
the same way `walker_deps` builds it — one function, two call sites, no new abstraction.

**`GET /runs/{id}` (4.4) changed, not just gained a sibling.** The brief's own AC needs
`admitted_signals` on `GET /runs/{id}` itself, not only on the new `/signals` path, so
`RunReadPorts` gained an optional `steps` field (default `None`, so `test_run_router.py`'s
frozen `RunReadPorts(runs=...)` call keeps compiling) and `run.py::get()` now resolves the
parked row's kind through it. `RunSummaryOut.of()` keeps working with no `park_row_kind` at
all for every caller that does not bother — `list_runs` among them, deliberately: a *list* of
Runs computing one extra row lookup per item is 4.12's own "one request per screen" to solve,
not this story's.

**The twice-runnable sweep converges instead of sweeping once.** `test_engine_walker.py`
leaves two Runs behind one Repository partition on purpose (AD-12's own proof): the one it
walks to `needs_you`, and a second it deliberately leaves `queued` behind it. Cancelling only
the first — a single sweep pass — frees the partition and lets the durable engine dequeue the
second, which then walks to a `needs_you` of its own a few seconds later, *after* a one-pass
sweep had already finished. Verified directly: a single-pass version of this test left the
gate genuinely broken on a second `pytest tests/e2e` (reproduced against a real stack, twice,
before this fix). `tests/e2e/test_signals.py`'s sweep instead loops — cancel every `needs_you`
Run found, wait for the queue to react, recheck — until a round finds none left, bounded at
five rounds. Confirmed by running the full e2e suite three times in a row against one
manually-held stack (`docker compose up`, no `down` between runs): 134 tests passed every
time, and `select status, count(*) from run group by status` showed zero `needs_you` and zero
`queued` rows after every run.

## Verification

```bash
make lint && make test && make openapi && PATH="$HOME/.docker/bin:$PATH" make e2e
```

All four green. `make e2e` also run three times in a row against one manually-kept-up stack
(bypassing its own `down -v` trap) to prove twice-runnability; all three passed with 134
tests each and no leftover `needs_you`/`queued` Run afterward.

## Auto Run Result

Status: **done**

**What was implemented.** See Tasks & Acceptance and Design Notes above. Every landed gate
(`make lint`, `make test`, `make openapi`, `make e2e`) is green; `domain/` + `application/`
report 100 % branch coverage including every new module and every changed line of existing
ones (`create_run.py`, `rules/signals.py`, `api/schemas/runs.py`).

**Files changed**

- New: `backend-api/src/orchestrator/application/use_cases/signals.py`,
  `.../api/schemas/signals.py`, `.../api/routers/signals.py`
- New tests: `backend-api/tests/unit/application/test_handle_signal.py`,
  `test_run_admitted_signals.py`, `test_park_row_kind_of.py`,
  `backend-api/tests/unit/test_signals_router.py`, `test_signals_schema.py`,
  `backend-api/tests/e2e/test_signals.py`
- Changed: `.../application/rules/signals.py`, `.../application/use_cases/create_run.py`,
  `.../api/schemas/runs.py`, `.../api/routers/run.py`, `.../api/providers.py`, `.../main.py`,
  `.../infrastructure/dbos/facade.py`
- Regenerated: `contracts/openapi.json`, `web-client/src/api/schema.d.ts` (`make openapi`;
  no hand-written web-client file touched, so `make e2e-ui` was not run — the operator's own
  dev stack holds the port it needs)

**Deferred / for the next story.** `resume_signal.kind == retry` sync-first behaviour on a
`push_rejected` push row is 4.8's own executor concern and was not touched; this story only
proves `retry` re-queues the row (`test_handle_signal.py`). A resuming `continue` leaving
`terminal_session` set (one of 4.5's four deferred items) is Epic 6's own surface — no kind
this epic applies (`cancel`, `retry`, `continue` on `checkpoint`/`plan_stale`) ever touches
`terminal_session`, so nothing here closes or reopens that gap.
