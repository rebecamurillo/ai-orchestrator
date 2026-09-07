---
title: 'Run domain model and status machines'
type: 'feature'
created: '2026-09-06'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/briefs/4-1-run-domain-model-and-status-machines.md'
  - 'backend-api/AGENTS.md'
warnings: ['oversized']
deferred: []
baseline_revision: '67c9e56a4a916d94fdb8e542ee2b39a9b30efcd0'
---

<intent-contract>

## Intent

**Problem:** Epic 4 executes Runs, but `Run`, `StepRun`, `Attempt` and `GateRecord` do not exist yet: there is no
model, no checked transition, no store. Every later story (4.2 planner, 4.4 create_run, 4.5 writers, 4.6 walker)
would otherwise invent its own status handling, which is exactly what AD-8 forbids.

**Approach:** Land the model bottom-up and behaviour-free — four frozen entities, the two transition tables from
AD-8's diagrams as pure functions that raise on anything unlisted, the value objects executors and signals speak in,
four repository ports with in-memory fakes and SQLAlchemy adapters, and migration `0005_run`.

## Boundaries & Constraints

**Always:**
- `domain/` imports no framework and no I/O (AD-2); entities and value objects are frozen pydantic models.
- The two transition tables are the only encoding of AD-8's two state diagrams. `run_transition` /
  `step_transition` return the listed target and raise `InvalidTransition`, naming status *and* event, for every
  pair not listed.
- `domain/` and `application/` keep 100% branch coverage (`make test` re-reports with `--fail-under=100`), every
  `src` module is imported by a unit-test module (`scripts/check_test_pairs.py`), a module is <= 400 lines and a
  function <= 50 lines / <= 5 arguments (ruff `PLR0913`), `mypy --strict` passes on domain and application.
- Every new SQLAlchemy model ships in the same change as its Alembic revision; revisions are append-only.
- Ids are UUIDv7 (`domain/ids.py`); times are tz-aware UTC; money is `Decimal` over `numeric(12,6)`.
- TDD (AD-18): write each test module and watch it fail before the module it covers exists. The **Execution**
  list below is grouped by layer for readability, not as a writing order.

**Block If:**
- Landing the story would require editing `SPEC.md`, `stories.yaml`, any `AGENTS.md`, or an existing test file.

**Never:**
- No use case, no router, no schema, no engine, no executor — 4.2 onward own those. Nothing here writes a status;
  the functions are pure and the repositories only store.
- Do not touch `application/steps/__init__.py`: its `Gate` is the *template-declarable* subset (three tokens) and
  stays that. The domain `Gate` has four, `unvalidated` included, because the planner records that token for a step
  whose Template declared no gate (NFR-2).
- No `pragma: no cover` in `domain/` or `application/`; no new doubles for a port that gets a fake here.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Listed run transition | `run_transition("queued", "start")` | `"running"` | No error expected |
| Listed step transition | `step_transition("checkpoint", "continue_checkpoint")` | `"done"` | No error expected |
| Terminal run | `run_transition("done", <any event>)` | — | `InvalidTransition` naming `done` and the event |
| Unlisted pair | any `(status, event)` outside the two tables | — | `InvalidTransition` naming both |
| Fake round trip | `FakeRunRepository.add` then `update` with a new `spend_usd`/`manual_estimate_h` | `get` returns the changed Run; the call is recorded on `calls` | `update` of an unstored id raises `ValueError` |
| Fake refuses duplicates | second `add` of the same run id / `(run_id, seq)` / `(run_id, path)` / `(step_run_id, n)` | — | `ValueError`, mirroring the unique index |
| Row ordering | `list_for_run`, `list_for_row`, `list_for_run` (gate records) | ordered by `seq`, by `n`, by `(at, id)` | No error expected |
| DB round trip | migrated database; a Run, two `step_run` rows, one `attempt`, one `gate_record` written through the adapters | reads return entities equal to what was written | No error expected |

</intent-contract>

## Code Map

Read these before writing; they are the shape every new file copies.

- `backend-api/src/orchestrator/domain/entities/repository.py` -- the entity voice: module docstring states the
  rules that live here and why; `model_config = ConfigDict(frozen=True)`; `Literal` aliases with `#:` comments.
- `backend-api/src/orchestrator/domain/entities/template.py` -- `TemplateRef{name, version}`, **reuse it** for
  `Run.pinned_versions`; do not invent a second pair type.
- `backend-api/src/orchestrator/domain/ports/repositories.py` (64 lines) -- `@runtime_checkable class X(Protocol)`,
  reads return `None`. The four new ports are appended here.
- `backend-api/src/orchestrator/domain/errors.py` -- `DomainError/NotFound/Conflict/Invalid`, each mapped to a
  status in `api/errors.py::DOMAIN_STATUS`. `InvalidTransition` is **not** one of these: an unlisted transition is
  a bug, not a described HTTP outcome (409 for a refused signal is 4.5's job). It lives in `domain/statuses.py`.
- `backend-api/src/orchestrator/application/steps/__init__.py` -- `KIND_META` is the only enumeration of kinds, so
  `StepRun.kind` is a plain `str` (domain may not import application).
- `backend-api/src/orchestrator/infrastructure/db/models/template.py` + `.../repositories/templates.py` +
  `alembic/versions/0004_template.py` -- the model/adapter/revision triple to mirror, including `TABLE_NAME`
  constants, JSONB for lists and maps, and `to_entity`/`*_json` module-level converters.
- `backend-api/src/orchestrator/infrastructure/db/base.py` -- `NAMING_CONVENTION`; migrations wrap every
  constraint name in `op.f(...)`.
- `backend-api/src/orchestrator/infrastructure/db/{__init__,models/__init__,repositories/__init__}.py` -- three
  re-export lists that must gain the new names, or Alembic never sees the tables.
- `backend-api/tests/unit/fakes/{projects,templates}.py` -- the fake voice: entities not rows, refuse what the
  index refuses. `tests/unit/fakes/runs.py` is new and, per the brief, also records every call on `calls`.
- `backend-api/tests/unit/test_template_repository_adapter.py` -- adapter tests run over a recording session
  double, never a database. Copy that harness.
- `backend-api/tests/e2e/test_migrations.py` + `tests/e2e/test_repositories.py` (from `# ── the schema the
  migration was written to create`) -- how an e2e test reaches the migrated database: `create_engine_from(
  Settings())`, module-scoped fixtures depending on `stack`, `pg_index` queries for index assertions.
- Read-only anchors touched by nothing here: `tests/unit/test_migration_chain.py` walks `alembic/versions/*.py`
  and requires exactly one unbroken chain — `0005_run` must set `down_revision = "0004_template"`.
  `tests/unit/test_source_limits.py`, `test_coverage_gates.py`, `test_check_test_pairs.py`, `test_layering.py`
  enforce the limits listed under **Always**.

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/domain/statuses.py` -- new: `RunStatus`, `StepStatus`, `ParkKind`, `SignalKind`,
  `Gate`, `Actor`, `GateEvent` (`ParkKind | SignalKind | Literal["start","done","failed","cancelled"]`) and the
  event aliases `RunEvent`, `StepEvent` as `Literal` types with `get_args` tuples beside them; `TERMINAL_RUN`;
  `RUN_TRANSITIONS` and `STEP_TRANSITIONS` dicts keyed `(status, event)`; `run_transition`, `step_transition`;
  `InvalidTransition(Exception)`. Transcribe the brief's two tables exactly -- they are AD-8's diagrams.
- `backend-api/src/orchestrator/domain/values.py` -- new: frozen `Park{kind, reason, path=None}`,
  `Redispatch{target_seq, max}`, `StepResult{status, gate, output_ref=None, park=None, redispatch=None,
  reason=None}`, `Signal{kind, payload={}}`, `PlannedRow{seq, path, label, kind, gate, status, reason,
  with_resolved, frame, story_id}`, `Worktree{branch, path, created_branch, pushed}`.
- `backend-api/src/orchestrator/domain/entities/{run,step_run,attempt,gate_record}.py` -- new: one frozen entity
  each, every field of the brief's four field lists, in that order. `Run.worktrees: tuple[Worktree, ...]`,
  `Run.pinned_versions: tuple[TemplateRef, ...]`. Fields a later story fills default to empty/`None`; `spend_usd`
  defaults to `Decimal("0")`, `re_review_done`/`terminal_session` to `False`, `active_seconds` to `0`.
- `backend-api/src/orchestrator/domain/ports/repositories.py` -- append the four `Protocol`s with the brief's
  method sets. `RunRepository.list(*, project_id: UUID | None = None)`; `AttemptRepository.mark_started(attempt)`
  and `mark_finished(attempt)` take the whole entity (AD-8 splits them so a restart finds the start half).
- `backend-api/src/orchestrator/infrastructure/db/models/run.py` -- new: `RunRow`, `StepRunRow`, `AttemptRow`,
  `GateRecordRow`; JSONB for every list and map, `Numeric(12, 6)` for money, `Numeric(10, 2)` for
  `manual_estimate_h`; FKs `run.project_id`, `run.repository_id`, `step_run.run_id`, `attempt.run_id`,
  `attempt.step_run_id`, `gate_record.run_id`; unique `(run_id, seq)`, `(run_id, path)`, `(step_run_id, n)`;
  non-unique `ix_run_project_id`, `ix_run_status`, `ix_run_repository_id_status`, `ix_gate_record_run_id_at`.
- `backend-api/src/orchestrator/infrastructure/db/repositories/{runs,step_runs,attempts,gate_records}.py` -- new:
  one adapter per port, each with module-level `to_entity` / row-payload converters, over the injected `Session`.
- `backend-api/src/orchestrator/infrastructure/db/{models/__init__,repositories/__init__,__init__}.py` -- export
  the four rows and the four adapters.
- `backend-api/alembic/versions/0005_run.py` -- new: `revision = "0005_run"`,
  `down_revision = "0004_template"`; create the four tables and their indexes, drop them in reverse.
- `backend-api/tests/unit/fakes/runs.py` -- new: `FakeRunRepository`, `FakeStepRunRepository`,
  `FakeAttemptRepository`, `FakeGateRecordRepository`; entities in dictionaries, index constraints mirrored as
  `ValueError`, every call appended to `self.calls`.
- `backend-api/tests/unit/test_run_statuses.py` -- new: parametrise over the **full product** of statuses x events
  for each machine; a listed pair returns its target, every other pair raises `InvalidTransition` whose message
  contains both tokens. Assert `TERMINAL_RUN` and the token spellings (`needs_you` is stored as written).
- `backend-api/tests/unit/test_run_values.py`, `backend-api/tests/unit/test_run_entities.py` -- new: the value
  objects and entities are frozen (mutation raises), defaults are what the brief states, and a `model_copy` of a
  Run with a new `spend_usd` is a new object.
- `backend-api/tests/unit/test_run_ports.py` -- new: each fake `isinstance(...)`-satisfies its `Protocol`, plus
  every I/O-matrix row about ordering, duplicates, `None`, and `calls`.
- `backend-api/tests/unit/test_run_repository_adapter.py` -- new: the four tables read off `Base.metadata`
  (columns, types, nullability, unique indexes, FKs) and the four adapters driven over a recording session double.
- `backend-api/tests/e2e/test_run_persistence.py` -- new: against the migrated gate database, insert a Project and
  a Repository through their adapters, then a Run + two `step_run` rows + one `attempt` + one `gate_record`
  through the new ones, commit, and read them back in a fresh session, asserting entity equality; assert the
  unique indexes exist on `run`, `step_run` and `attempt` via `pg_index`, the way `test_repositories.py` does.

**Acceptance Criteria:**
- Given the transition tables, when the test module enumerates statuses x events, then every listed pair returns
  the brief's target and every unlisted pair raises `InvalidTransition` naming both tokens.
- Given `make lint`, when it runs, then ruff, `mypy --strict`, `lint-imports`, the env contract and the test-pair
  gate all pass -- no new module leaks `sqlalchemy`, `os` or `subprocess` into `domain/`.
- Given `make test`, when it runs, then the unit suite is green and `coverage report --include=domain,application
  --fail-under=100` still passes.
- Given `alembic/versions`, when `tests/unit/test_migration_chain.py` walks it, then `0005_run` is the single head
  and hangs off `0004_template`.
- Given a migrated database, when the e2e persistence scenario writes and re-reads the aggregate, then the
  entities compare equal, including `Decimal` money and tz-aware timestamps.

## Spec Change Log

## Review Triage Log

## Design Notes

**Why `InvalidTransition` is not a `DomainError`.** `api/errors.py::DOMAIN_STATUS` maps each `DomainError` kind to
a status; an unlisted transition has no operator-facing meaning, because 4.5's `signal_run` validates the signal
against AD-13 *first* and raises `Conflict` (409). Reaching `InvalidTransition` means a caller skipped that check,
which is a 500 and a bug. Keeping it out of `domain/errors.py` also leaves that frozen-test-covered module alone.

**Why `list(*, project_id=None)`.** The brief writes `list(filter)`. The only filter this epic names is the Board's
project filter (SPEC CAP-14 / FR-22); a keyword-only optional `project_id` is that filter and nothing more. Newest
first (`created_at` descending, `id` descending as the tiebreak, since UUIDv7 sorts by creation).

**Why `mark_started(attempt)` / `mark_finished(attempt)` take an entity.** AD-8 requires the two halves of an
attempt to land in separate units of work so a restart finds the start half. Passing every written column as a
keyword would exceed ruff's `PLR0913`; passing the updated frozen entity keeps the repository entity-in/entity-out
like every other adapter here, and each method's docstring names the columns it writes.

**`Attempt.status` is a `StepStatus`.** An attempt carries the status the row reached through it -- `running` while
in flight, then `done | blocked | checkpoint | error | skipped`. The spine lists the field without enumerating it;
reusing the row's vocabulary avoids a second status alphabet for 4.5 to reconcile.

## Verification

**Commands:**
- `make lint` -- expected: exit 0.
- `make test` -- expected: exit 0, including the 100% branch re-report over `domain/` and `application/`.
- `make e2e-api` -- expected: exit 0. Needs a docker daemon (`make e2e` builds the `aio-e2e` stack). If none is
  available, report that verbatim rather than skipping it silently.

## Auto Run Result

Status: done

Gates, as run on this machine:

- `make lint` — exit 0 (ruff, `mypy --strict`, `lint-imports` 3/3 kept, env contract, test pairs 70/70, web-client).
- `make test` — exit 0; backend 2606 passed / 23 skipped, `domain/` + `application/` 100% branch, web-client 722 passed.
- `make e2e` (which runs `make e2e-api` inside the disposable `aio-e2e` stack) — exit 0; 107 passed, 21 subtests
  passed. Docker is installed at `~/.docker/bin/docker` on this machine but is not on the default PATH, so the
  gate needs `PATH="$HOME/.docker/bin:$PATH" make e2e`.
- `make e2e-ui` — could not run: `127.0.0.1:4321`, the port Playwright's `webServer` binds, is already held by
  the operator's own `aio-dev` compose stack (Docker Desktop's proxy). Not a failure of this story, which changes
  no web-client file; it needs the dev stack stopped, or a free 4321.

One defect was found by the e2e gate and fixed rather than worked around: none of the SQLAlchemy models declare
`relationship()`, so the unit of work had no edge between `run` and `attempt` / `step_run` / `gate_record` and the
insert order inside a single flush was arbitrary — `attempt` reached the database before `run` and violated
`fk_attempt_run_id_run`. The four new adapters now flush at each insert, which makes the caller's order the
database's order; a use case could not do this itself, since the `UnitOfWork` port exposes only `commit` and
`rollback`.
