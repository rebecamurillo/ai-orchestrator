---
title: 'Create and enqueue a Run'
type: 'feature'
created: '2026-09-06'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/briefs/4-4-create-and-enqueue-a-run.md'
  - 'backend-api/AGENTS.md'
warnings: []
deferred: []
baseline_revision: '6cd8eca2e19bb768de37c991d7fdecf0e048ba3a'
---

<intent-contract>

## Intent

**Problem:** Pre-flight (4.3) can say a Run *would* start; nothing yet persists one. `POST
/runs` has to turn *What will run* into a real `Run` and its `step_run` rows, pin every
Template Version the tree touches (AD-15), and enqueue behind the Repository — the whole
thing in a shape a caller can trust, since the walker (4.6) has not landed yet to prove it
by executing anything.

**Approach:** `create_run` re-runs pre-flight's exact resolution — not a second one — through
a new public `preflight_and_plan` in `application/use_cases/preflight.py` that returns the
`PreflightResult` *and* the `ResolvedTree`/`Plan` in one pass, so the rows persisted and the
rows *What will run* showed can never diverge. `domain/ports/engine.py` is the whole
`WorkflowEngine` protocol (AD-6), even though this story only calls `enqueue`; a
process-local, non-durable `LocalWorkflowEngine` (`infrastructure/engine/local.py`) is wired
in `main.py` until 4.6 replaces it with DBOS, because the schemathesis gate fuzzes every
published operation and a missing adapter would 500 on the first call.

## Boundaries & Constraints

**Always:**
- `POST /runs` and `GET /runs`/`GET /runs/{run_id}` live in a *new* router
  (`api/routers/run.py`), not `api/routers/runs.py`: that module is frozen at exactly its two
  preflight operations by `tests/unit/test_runs_router.py::
  test_the_router_declares_exactly_the_two_operations`. `run.router` is mounted in `main.py`
  *after* `runs.router` — `/runs/{run_id}` and `/runs/preflight` are the same shape to
  Starlette, which matches registration order, so the literal path has to be checked first.
  `tests/unit/test_run_router.py` pins both the shape and a real request proving the order.
- Every published path publishes a `GET` (`test_bearer_auth.py`'s `paths[path]["get"]`
  sweep): `GET /runs` (a plain list) is the sibling `POST /runs` needs, the same way 4.3 gave
  `POST /runs/preflight` one.
- `create_run` adds in FK order — `run` then `step_run` — because neither model declares
  `relationship()` and the adapters flush per insert (4.1); reversing the order would
  reference a `run_id` that is not in the database yet.
- `pinned_versions` is `tree.pinned_versions()`: root first, then every callee in walk order
  (AD-15) — the exact list `TemplateVersionRepository.pinned_by`'s `jsonb` containment query
  counts against.
- `starts_now`/`waiting` are pre-flight's own `queue_note`, read *before* this Run exists.
- `domain/`, `application/` keep 100% branch coverage; no `pragma: no cover`; every module
  paired with a unit test; TDD.

**Block If:** landing this would require editing `SPEC.md`, `stories.yaml`, any `AGENTS.md`,
or an existing test file outside the three narrow declared exceptions.

**Never:** no DBOS (4.6), no walker, no signals (4.5/4.9), no protected paths/budget
enforcement (Epic 5/6) — `budget_usd` is stored, not yet read for a rule of its own.

## Response-shape decisions (brief under-specifies these; each resolved to one reading the
## brief's own ACs are consistent with)

- **`RunSummaryOut.project`/`.repository` are the Project/Repository ids** (`project_id`,
  `repository_id`), read the same way `.template`/`.version` split `template_name`/
  `template_version` rather than merging them.
- **`Run.inputs`** holds exactly `base_branch`, `harness`, `model` and the Template's own
  declared inputs — never the Project/Repository snapshot, which the Run's own foreign keys
  already name.
- **A second, independent resolution pass could in principle disagree with the first** (a
  callee saved between two calls); `create_run` therefore never makes a second pass — it
  takes `preflight_and_plan`'s single `Preflighted` result apart — which is also what keeps
  `plan`/`resolved.tree`'s "impossible" branch an `assert` rather than a code path a second
  pass could actually reach.
- **`FakeTemplateVersionRepository.pinned_by`** needs a live `FakeRunRepository` to count
  against, which the port's fake had no reason to hold before this story; it takes one
  additively (`runs: FakeRunRepository | None = None`, default preserves every pre-4.4
  caller's `pinned_by == 0`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| repo-init@1, clean | AC1 | 201; 6 `step_run` rows, `seq` 1-6, `plan` first, all `planned`; `pinned_versions=[{repo-init,1}]`; `engine.enqueue` called once with the Repository id; `starts_now` true | — |
| initiative@1, clean | AC2 | `pinned_versions=[{initiative,1},{epic,1},{story,1}]`; `GET /templates/story/1` and `.../epic/1` report `pinned_by: 1` | — |
| non-terminal Run already on the Repository | AC3 | 201, `starts_now: false`, `waiting: "queues behind {label}"`, Run still `queued` | — |
| a pre-flight line is `fail` | AC4 | no Run row written, `engine.enqueue` never called | `Conflict` (409), `detail` = the failing lines' own text, joined |
| the tree cannot be planned | AC5 | no Run row written, `engine.enqueue` never called | the `PlanError` itself, rendered 422 with `errors[]` (`template`,`version`,`line`,`item` as `path`,`reason`) |
| the step-row insert raises | AC6 | nothing commits (`uow.committed is False`), `engine.enqueue` never called | the raised exception propagates |
| unknown `project_id`/`repository_id` | new | — | `NotFound` (404) — pre-flight itself reports every line `skip` for this case, not a `fail`, so `create_run` checks the resolved entities itself |
| `budget_usd` a finite but huge magnitude (schemathesis) | new | 422, not 500 | `MoneyStr`'s `_as_money` now catches `decimal.InvalidOperation` from `.quantize()`, not only the non-finite case |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/use_cases/preflight.py::_resolve, _build_plan,
  _Resolved, PreflightPorts` (4.3) -- reused whole, via the new `preflight_and_plan` /
  `Preflighted` this story adds beside them; `run_preflight` is now a one-line projection of
  it.
- `backend-api/src/orchestrator/application/use_cases/plan_run.py::PlanPorts, resolve_tree,
  plan_for` (4.2) -- the shape `preflight_and_plan` composes; not called a second time here.
- `backend-api/src/orchestrator/domain/entities/run.py`, `.../step_run.py` (4.1) -- every
  field `create_run` fills; `Run.pinned_versions`/`inputs`/`plan_ref`/`plan_refs`/
  `budget_usd`/`manual_estimate_h`/`re_review_done` in particular.
- `backend-api/src/orchestrator/domain/ports/repositories.py::RunRepository,
  StepRunRepository` (4.1) -- `add`, `add_many`, `update`, `list`,
  `list_by_repository_non_terminal` (already there; no change needed).
- `backend-api/src/orchestrator/infrastructure/db/repositories/runs.py`,
  `step_runs.py` (4.1) -- the real adapters, already flush-per-insert; wired unchanged.
- `backend-api/src/orchestrator/api/routers/templates.py`, `graph_text.py` -- the
  GET-sibling-on-a-POST-only-path pattern and the router-mount-order lesson, both reused by
  `api/routers/run.py` and its own `main.py` mount comment.
- `backend-api/src/orchestrator/api/schemas/common.py::MoneyStr, _as_money` -- `budget_usd`'s
  first real consumer; the fix this story makes to it (catch `ArithmeticError` from
  `.quantize()`) is the schemathesis gate's own find, not a pre-planned task.
- `backend-api/tests/unit/fakes/{runs,db,git,harnesses,projects,templates}.py` -- reused
  as-is except `templates.py`, extended additively with `pinned_by`.
- `backend-api/tests/unit/application/templates/plan_fixtures.py` -- the shipped-Template
  fixtures `test_create_run_use_case.py` plans from, the same way 4.2/4.3's own tests do.
- `backend-api/tests/e2e/test_clone_check.py::Fixtures, manifest_stating` -- reused directly
  by `tests/e2e/test_run_creation.py` for a real bare repository, rather than a second copy
  of that script.

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/domain/ports/engine.py` -- new: `WorkflowEngine` protocol,
  `QueueEntry`, `EngineRecord`.
- `backend-api/tests/unit/fakes/engine.py` -- new: `FakeWorkflowEngine`.
- `backend-api/src/orchestrator/infrastructure/engine/local.py` (+`__init__.py`) -- new:
  `LocalWorkflowEngine`, the placeholder `main.py` wires until 4.6.
- `backend-api/src/orchestrator/application/use_cases/preflight.py` -- add `Preflighted`,
  `preflight_and_plan`; `run_preflight` becomes a projection of it.
- `backend-api/src/orchestrator/application/use_cases/create_run.py` -- new:
  `CreateRunPorts`, `CreateRunRequest`, `CreateRunResult`, `create_run`, `RunReadPorts`,
  `get_run`.
- `backend-api/src/orchestrator/domain/ports/templates.py` -- add `pinned_by(name, version)`.
- `backend-api/src/orchestrator/infrastructure/db/repositories/templates.py` -- implement
  `pinned_by` as a `jsonb` containment query over `run.pinned_versions`.
- `backend-api/tests/unit/fakes/templates.py` -- add `runs` kwarg + `pinned_by`, additively.
- `backend-api/src/orchestrator/application/use_cases/templates.py` -- `TemplateVersionDetail.
  pinned_by` (default `0`); `get_version` fills it from the port.
- `backend-api/src/orchestrator/api/schemas/templates.py`,
  `api/routers/templates.py` -- read the real `pinned_by` instead of hardcoding `0`.
- `backend-api/src/orchestrator/api/schemas/common.py` -- `_as_money` catches
  `ArithmeticError` from `.quantize()` (schemathesis find).
- `backend-api/src/orchestrator/api/schemas/runs.py` -- new: `RunIn`, `RunSummaryOut`,
  `CreateRunOut`, `plan_error_problems`.
- `backend-api/src/orchestrator/api/routers/run.py` -- new: `POST /runs`, `GET /runs`,
  `GET /runs/{run_id}`.
- `backend-api/src/orchestrator/api/providers.py` -- `create_run_ports`, `run_read_ports`,
  `_preflight_ports`/`_required_git` extracted so pre-flight and `create_run` share one
  `PreflightPorts` construction.
- `backend-api/src/orchestrator/main.py` -- mount `run.router` after `runs.router`; wire
  `LocalWorkflowEngine` as `app.state.engine`.
- New test modules: `tests/unit/application/test_create_run_use_case.py`,
  `tests/unit/test_run_router.py`, `tests/unit/test_runs_schemas.py`,
  `tests/unit/test_local_workflow_engine.py`, `tests/unit/test_template_pinned_by.py`,
  `tests/e2e/test_run_creation.py`.

**Acceptance Criteria:** the six Given/When/Then blocks in the brief
(`briefs/4-4-create-and-enqueue-a-run.md`), verbatim, plus the matrix above.

## Spec Change Log

_None._ No anchor file was edited; the frozen `test_runs_router.py` was read, understood,
and worked around structurally (a second router, correctly ordered) rather than touched.

## Design Notes

**Why `preflight_and_plan` exists instead of two public wrappers around `_resolve`/
`_build_plan`.** An earlier draft added `resolve`/`build_plan` as thin public aliases and
called pre-flight's resolution twice — once inside `run_preflight`, once directly. Both
calls are pure given the same `Git`/repository state, so in the tests they always agreed,
but that made the "the two disagreed" branch (`plan is None` after everything else resolved)
genuinely unreachable — a 100%-branch-coverage violation with no honest test to write for
it. Reusing one `Preflighted` result removes the second pass entirely, so `assert plan is
not None` / `assert tree is not None` are true invariants (mirroring `use_cases/templates.py
::graph_text`'s own `assert parsed is not None`), not defensive dead code.

**Why `LocalWorkflowEngine` exists at all.** The brief's own scope note is "AR-9 (interface
only)" and the DBOS adapter is explicitly 4.6's. But `POST /runs` is now a published
operation the schemathesis gate fuzzes on every `make e2e`, and `api/providers.py`'s
dependency pattern raises `RuntimeError` for any adapter `app.state` does not hold —
unconditionally, before any request-specific logic runs. Without *some* wired adapter, every
fuzzed `POST /runs` call would 500 before ever reaching pre-flight's own checks. A
process-local, admittedly non-durable stand-in (in-memory queue, lost on restart, `signal`/
`schedule` are no-ops) is the minimum that keeps the gate honest without pretending to be
the durable engine 4.6 owns.

**Why the router is a new module, not a growth of `api/routers/runs.py`.** Story 4.3's own
frozen test names the shape exactly: `test_the_router_declares_exactly_the_two_operations`.
Epic 3 hit the identical situation three times (`templates.py`/`graph.py`/`graph_text.py`
share one prefix); `api/routers/run.py` is the same move, with its own frozen route-count
test and a real-request test proving `/runs/preflight` still resolves once `/runs/{run_id}`
is mounted beside it.

**The schemathesis-found `_as_money` gap.** `MoneyStr` (`api/schemas/common.py`) existed
before this story but had never been used by a schema, so its `.quantize()` call had never
been exercised against an out-of-range magnitude. `budget_usd` (`RunIn`) is its first real
consumer; the gate's own fuzzing (`-1.46e284`) found the gap on the first `make e2e` run.
Fixed at the one place the rule already lived, not worked around in `RunIn`.

## Verification

**Commands, as run on this machine:**
- `make lint` -- exit 0 (ruff, ruff format, `mypy --strict` on `domain/`+`application/`,
  `lint-imports` 3/3 kept, env contract, test pairs 97/97 backend + 42/42 web-client,
  `gen:api --check`, web-client astro/tsc/eslint/prettier).
- `make test` -- exit 0; backend 3161 passed / 23 skipped; `domain/`+`application/` **100%
  branch, 0 missing**; web-client 722 passed.
- `make openapi` -- exit 0; `contracts/openapi.json` and `web-client/src/api/schema.d.ts`
  regenerated with the new `run` router's three operations and `pinned_by`'s real
  description.
- `PATH="$HOME/.docker/bin:$PATH" make e2e` -- exit 0; 117 passed, 27 subtests (up from
  4-3's 110/24), against a fresh `aio-e2e` stack torn down cleanly. One real defect was
  found and fixed rather than worked around: schemathesis's fuzzing of `POST /runs` hit an
  uncaught `decimal.InvalidOperation` in `MoneyStr._as_money` on a finite-but-enormous
  `budget_usd` magnitude — see the Design Notes entry above.
- `make e2e-ui` -- not run: this story changes no hand-written web-client file (only the
  generated `schema.d.ts`), and port 4321 was held by the operator's own dev stack, per the
  operator's own instruction for this dispatch.

**What was built, complete and verified working end to end:** `domain/ports/engine.py`
(`WorkflowEngine`, `QueueEntry`, `EngineRecord`) + `tests/unit/fakes/engine.py`;
`infrastructure/engine/local.py::LocalWorkflowEngine`, wired in `main.py`;
`application/use_cases/preflight.py::Preflighted, preflight_and_plan`;
`application/use_cases/create_run.py` (`create_run`, `get_run`); `TemplateVersionRepository.
pinned_by` on the port, the fake, and the adapter (a real `jsonb` containment query),
threaded through `get_version`/`TemplateVersionOut`; `api/schemas/runs.py`;
`api/routers/run.py` (`POST /runs`, `GET /runs`, `GET /runs/{run_id}`), mounted after
`runs.router`; `api/providers.py::create_run_ports, run_read_ports`; the `_as_money`
`ArithmeticError` fix; `contracts/openapi.json` + `schema.d.ts` regenerated. All six of the
brief's acceptance criteria are passing tests in `tests/unit/application/
test_create_run_use_case.py`; the router shape, mount order, and HTTP-level behavior are in
`tests/unit/test_run_router.py`; the full round trip against real Postgres and real `git` is
in `tests/e2e/test_run_creation.py`, using fresh per-test Template names so the shipped
Templates' `pinned_by` — asserted `== 0` by the frozen `tests/e2e/test_templates.py` — is
never touched.

**Deferred / what 4.5 and later need to know:**
- `skip_harness_check` is accepted by `CreateRunPorts` and implemented (it looks past a
  failing `harness` line only) but nothing in this story or the API sets it to `True` —
  Epic 5's `readiness` Runs are its caller.
- `LocalWorkflowEngine` is explicitly not durable: a restart loses its in-memory queue.
  Nothing yet reads that queue to decide what runs (no walker), so this is inert today, but
  4.6 replaces the *adapter* wholesale rather than building on it — `main.py`'s own wiring
  comment says so.
- The known, pre-existing gap from Epics 2/3 (a concurrent-write `IntegrityError` surfaces
  as 500 rather than 409) is untouched and still open.
- `RunSummaryOut` is deliberately minimal (`id, status, template, version, project,
  repository, branch, budget_usd, spend_usd, plan_ref, created_at`); the full read model
  (worktrees, compare links, cost block, gate record) is 4.12's.
