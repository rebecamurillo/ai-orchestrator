---
title: 'Pre-flight checks and the harness table'
type: 'feature'
created: '2026-09-06'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/briefs/4-3-preflight.md'
  - 'backend-api/AGENTS.md'
warnings: ['oversized']
deferred: []
baseline_revision: '4abef7abf8e906f96b8b4eecc1b67ba9115833f3'
---

<intent-contract>

## Intent

**Problem:** Before a Run can be created (4.4), the Operator needs every reason it could fail at start
reported as one line with a fix, plus *What will run* — nothing computes this yet, and the `harness`
table (SPEC CAP-3, AD-10) that pre-flight's harness line reads does not exist.

**Approach:** `application/use_cases/preflight.py::run_preflight` composes independent line-builders
(one per FR-8 check) over `git`, `templates`, `runs`, `harnesses`, `repositories`, `projects`; it calls
`plan_run` (4.2) for *What will run* rather than reimplementing it. `harness` is a new small table,
port, adapter, fake, migration `0006_harness`, seeded disabled at start-up (idempotent upsert of
`name`/`version_pin`, never `enabled`) from the existing `CLAUDE_CODE_VERSION`/`CODEX_VERSION`/
`OPENCODE_VERSION` settings — no new `.env.example` entry needed.

## Boundaries & Constraints

**Always:**
- `POST /api/v1/runs/preflight` is a path of its own; `test_bearer_auth.py` indexes `paths[path]["get"]`
  for every published path, so `GET /runs/preflight` (no body) ships beside it, answering the same
  computation over an empty request — every line `skip`, matching the missing-repository_id AC.
- Preflight writes nothing; `ls_remote`/`read_file`/`list_files` only. It never re-reads Template YAML
  itself — `plan_run`/`resolve_tree` (4.2) own that.
- `domain/`, `application/` keep 100% branch coverage; every new module <= 400 lines, every function
  <= 50 lines / <= 5 args; `mypy --strict`; no `pragma: no cover`; every module paired with a unit test
  (`scripts/check_test_pairs.py`).
- TDD: each test module written and watched to fail before the module it covers exists.
- Migration `0006_harness`, `down_revision = "0005_run"`.

**Block If:** landing this would require editing `SPEC.md`, `stories.yaml`, any `AGENTS.md`, or an
existing test file.

**Never:** no readiness runs/evaluation (Epic 5 writes `enabled`/`last_readiness_at`/`failing_check`);
no `POST /runs` (4.4); no UI.

## Boundaries & Constraints — response-shape decisions (brief under-specifies these; not intent gaps,
each is resolved to one reading below because the given ACs are consistent with exactly one)

- **`lines` is a fixed set of single-line categories (1,2,6,8,9,10,11,12) plus three variable-count
  categories (3: one per branch the plan checks out; 4: one line, initiative only; 5/7: one per
  `stories.yaml` / spec folder the plan touches)** — present whenever structurally applicable, not only
  when the request is complete for them. AC1's "lines 1–3, 9 (skip), 11, 12 are present" names the facts
  under test, not an exhaustive list (AC2 does the same, naming only line 5 for its scenario) — lines
  4/5/7 are absent for `repo-init` because their structural count is zero (no epics/story loop), not
  because they were suppressed.
- **`check` is the fixed category name** (`"origin reachable"`, `"base branch"`, `"branch"`,
  `"epics.yaml"`, `"stories.yaml"`, `"checkpoints"`, `"SPEC.md"`, `"harness"`, `"method version"`,
  `"existing story files"`, `"clone check"`, `"what will run"`); **`text` carries every substitution**
  (e.g. line 3's `text` is `"chore/bmad-init · will create from main"`, matching AC1's "line 3 reads …").
- **When `project_id`/`repository_id`/`template_name`/`template_version`/`base_branch` is missing or
  does not resolve to a stored entity**, every line is `skip` (AC5) — each depends, directly or through
  `plan_run`, on the Repository and the resolved Template.
- **When `plan_run` raises `PlanError`** for a reason about a list file (`LIST_FILE_NOT_FOUND`,
  `LIST_FILE_NOT_A_LIST`, `ENTRY_MISSING_FIELDS`, `DUPLICATE_ENTRY_ID`, `ID_NOT_PREFIX_FREE`,
  `AMBIGUOUS_STORY_FILE`), it is attributed to line 5 (non-initiative template) or line 4 (initiative —
  the outer loop, since a bare `PlanError` does not name which list file failed); every other
  plan-dependent line (3, 6, 7, 9, 10) is `skip`; line 12 carries the `plan_error`. Any other reason
  (`CALLEE_NOT_RESOLVED`, `BASE_BRANCH_NOT_FOUND`, …) only affects line 12 the same way; 3/6/7/9/10 skip.
- **Line 8 (harness) is `skip` when the resolved Template tree has no `agent`-kind step anywhere**
  (structural — matches "skip for repo-init" without naming the template) **or when `harness` is absent
  from the request.**
- **`queue_note`'s `{label}`** is `f"{run.template_name} · {branch}"` where `branch` is the held/matching
  branch for the line-3 case, and the first `worktrees[].branch` (else `inputs["branch"]` else
  `inputs["base_branch"]`) for the run holding the Repository.
- **"active Runs" (`MAX_ACTIVE_RUNS`)** = Runs with status `running` or `needs_you` (AD-12: the slot is
  held from start through `needs_you`; a merely `queued` Run has not acquired one).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| repo-init, all fields resolve, branch absent | AC1 | lines 1,2,3,9(skip),11,12 as specified; `start_allowed` true; `rows` 6 entries; `queue_note` "starts immediately…" | — |
| epic, `stories.yaml` ids not prefix-free | AC2 | line 5 `fail` naming the ids; `start_allowed` false; `rows` null, `plan_error` set | — |
| epic, `harness: claude`, `harness.enabled=false` | AC3 | line 8 `fail · disabled: no readiness run` with fix | — |
| non-terminal Run holds `feat/x`, preflight for `feat/x` | AC4 | line 3 `fail · held by run epic · feat/x`; `queue_note` names it | — |
| manifest `6.10.0` vs `BMAD_VERSION=6.11.0` | AC5(spec) | line 9 `fail · outdated: 6.10.0`, fix given | — |
| `repository_id` missing | AC5 | 200, every line `skip`, `start_allowed` false | — |
| `GET /runs/preflight`, no body | new | 200, every line `skip` (same code path as an empty `POST`) | — |
| harness table seeded fresh | new | three rows `claude/codex/local`, `enabled=false`, `version_pin` = the matching setting | — |
| `GET /harnesses` | new | `{items: [...]}`, three seeded rows | — |
| repo-init plan has a `bmad.install` row | AC1 | line 9 is `skip` | — |
| clone_check `pending` / `failed` | brief §11 | line 11 `fail · pending · save the project` / `fail · failed`, fix `re-run the clone check on the project` | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/templates/plan_model.py::PlanError` -- reasons to switch on
  (`LIST_FILE_NOT_FOUND` etc.), `Plan{plan_ref, plan_refs, rows}`.
- `backend-api/src/orchestrator/application/use_cases/plan_run.py::PlanPorts, resolve_tree, plan_for` --
  call, don't reimplement.
- `backend-api/src/orchestrator/application/use_cases/clone_check.py::installed_version, MANIFEST_PATH,
  MANIFEST_SECTION, MANIFEST_KEY` -- reuse verbatim for line 9.
- `backend-api/src/orchestrator/application/templates/lines.py::load_sequence` -- reuse to parse
  `epics.yaml`/`stories.yaml` text read directly via `git.read_file` at `plan.plan_refs[path]` (do not
  reuse `application/templates/lists.py` — it is coupled to the walker's `Frame`).
  `application/templates/lines.py::load_with_lines` -- reuse for a story file's frontmatter `status`.
- `backend-api/src/orchestrator/application/steps/__init__.py::KIND_META, WORKTREE_KIND, AGENT_KIND` --
  the one enumeration of kinds; scan `tree.root`/callees' steps for `AGENT_KIND` (line 8), scan
  `plan.rows` for `WORKTREE_KIND` (line 3 branches).
- `backend-api/src/orchestrator/domain/ports/repositories.py::RunRepository` -- `list_by_repository_non_terminal`,
  `list_by_status`, both already there; no change needed.
- `backend-api/src/orchestrator/domain/entities/run.py::Run.worktrees, Run.inputs` -- label source.
- `backend-api/src/orchestrator/domain/entities/repository.py::Repository, CloneCheck` -- `clone_check.status`.
- `backend-api/src/orchestrator/infrastructure/db/models/template.py` +
  `.../repositories/templates.py` + `alembic/versions/0005_run.py` -- the model/adapter/migration triple
  to mirror for `harness` (single small table, no FK, primary key `name`).
- `backend-api/src/orchestrator/application/use_cases/templates.py::seed_shipped, TemplatePorts` -- the
  idempotent-seed shape to mirror in `application/use_cases/harnesses.py::seed_harnesses`.
- `backend-api/src/orchestrator/main.py::seed_shipped_templates, run_migrations` -- harness seeding is
  called from inside `run_migrations`, the same way, with its own engine/session/dispose.
- `backend-api/src/orchestrator/api/routers/{templates,graph_text}.py`, `main.py`'s router-mount-order
  comment -- the GET-sibling-on-a-POST-only-path pattern and why mount order matters.
- `backend-api/src/orchestrator/api/schemas/common.py::Page, MoneyStr` -- envelope + money shape reuse
  for `budget_usd`.
- `backend-api/tests/unit/fakes/{git,runs,projects,templates}.py` -- reuse as-is; `FakeGit`'s `refs`/
  `files`/`listings` mapping keywords are what scripted preflight tests should use.
- `backend-api/tests/unit/fakes/harnesses.py` -- new fake for the new `HarnessRepository` port (no
  existing fake for this port).

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/domain/entities/harness.py` -- new: frozen `Harness{name, enabled,
  last_readiness_at, failing_check, version_pin}`.
- `backend-api/src/orchestrator/domain/ports/harnesses.py` -- new: `HarnessRepository` protocol —
  `get(name)`, `add(harness)`, `update(harness)`, `list()`.
- `backend-api/src/orchestrator/infrastructure/db/models/harness.py` -- new: `HarnessRow`, PK `name`.
- `backend-api/src/orchestrator/infrastructure/db/repositories/harnesses.py` -- new:
  `SQLAlchemyHarnessRepository`.
- `backend-api/alembic/versions/0006_harness.py` -- new: create/drop `harness`.
- `backend-api/tests/unit/fakes/harnesses.py` -- new: `FakeHarnessRepository`.
- `backend-api/src/orchestrator/application/use_cases/harnesses.py` -- new: `HarnessPorts`,
  `seed_harnesses(ports, pins: dict[str, str])` (idempotent, `enabled` untouched on an existing row),
  `list_harnesses(ports)`.
- `backend-api/src/orchestrator/api/schemas/harnesses.py` -- new: `HarnessOut`.
- `backend-api/src/orchestrator/api/routers/harnesses.py` -- new: `GET /harnesses`.
- `backend-api/src/orchestrator/application/preflight/model.py` -- new: `Line`, `LineStatus`,
  `PreflightRequest`, `PreflightResult`, the fixed `check` name constants.
- `backend-api/src/orchestrator/application/preflight/checks.py` -- new: the twelve line-builders, each
  a small pure function; a `_run_label(run) -> str` helper; a `_queue_note(...)` helper.
- `backend-api/src/orchestrator/application/use_cases/preflight.py` -- new: `PreflightPorts`,
  `run_preflight(ports, req) -> PreflightResult`, composing `checks.py` in FR-8 order.
- `backend-api/src/orchestrator/api/schemas/preflight.py` -- new: `PreflightIn`, `LineOut`,
  `PlannedRowOut`, `PlanErrorOut`, `PreflightOut`.
- `backend-api/src/orchestrator/api/routers/runs.py` -- new: `POST /runs/preflight`,
  `GET /runs/preflight` (empty-request sibling, per the bearer-auth `get`-indexing constraint).
- `backend-api/src/orchestrator/api/providers.py` -- add `preflight_ports`, `harness_ports`.
- `backend-api/src/orchestrator/main.py` -- mount `runs.router`, `harnesses.router`; add
  `seed_harness_table(settings)` called from `run_migrations`, mirroring `seed_shipped_templates`.
- `backend-api/src/orchestrator/infrastructure/db/{__init__,models/__init__,repositories/__init__}.py`
  -- export the new row/adapter.
- New test modules (written to fail first): `tests/unit/test_harness_{entity,port,repository_adapter}.py`,
  `tests/unit/application/test_harnesses_use_case.py`, `tests/unit/api/test_harnesses_router.py`,
  `tests/unit/application/preflight/test_{model,checks}.py`,
  `tests/unit/application/test_preflight_use_case.py`, `tests/unit/api/test_runs_router.py`,
  `tests/e2e/test_harness_persistence.py` (extends `test_migrations.py`'s companion pattern without
  touching the frozen file itself).

**Acceptance Criteria:** the five Given/When/Then blocks in the brief (`briefs/4-3-preflight.md`),
verbatim, plus the matrix rows above.

## Spec Change Log

### 2026-09-06 — Operator-authorised anchor edit: `test_main_templates_seed.py`

**Triggering finding.** Landing this story's brief-mandated wiring (harness-table seeding
called from inside `main.run_migrations`, third statement beside `seed_shipped_templates`)
broke the frozen `backend-api/tests/unit/test_main_templates_seed.py::
test_run_migrations_migrates_then_seeds_and_returns_the_head` (lines 57-73 as originally
written): it monkeypatched exactly two collaborators and asserted
`recorder.order == ["migrate", "seed"]`, so the new third, unmocked collaborator
(`seed_harness_table`) ran for real against the test's placeholder `DATABASE_URL` and raised
`OperationalError: failed to resolve host 'postgres'`. Three alternative implementation
placements were tried first (`migrating_lifespan`, folding into `seed_shipped_templates`'s
own body, moving into `infrastructure/db/migrations.py::run_migrations`) and each broke a
*different* frozen test instead of avoiding the conflict — reported as `blocked`.

**What was amended.** The operator authorised, on 2026-09-06, editing exactly this one test
function to also monkeypatch `main_module.seed_harness_table` and assert the three-step
order, on the binding condition that the revised assertion strictly exceeds what it covered
before: it must still prove all three steps run, in that exact order, as one ordered-equality
list (never weakened to membership or a subset check), and it must remain impossible for the
test to pass if a fourth unmocked collaborator is later added and quietly reaches a real
database. The edit: `fake_harness_seed` records `"harness"` and is installed via
`monkeypatch.setattr(main_module, "seed_harness_table", fake_harness_seed)`; the assertion is
now `assert recorder.order == ["migrate", "seed", "harness"]`. Nothing else in that file
changed — `test_run_migrations_never_seeds_when_the_migration_fails` was left alone because
the harness seed is unreachable on its path (the mocked migration raises before either seed
call). No other anchor file changed.

**Known-bad state avoided.** Weakening the assertion to `set(recorder.order) == {...}` or
`"harness" in recorder.order` would have let a caller reorder the three steps, or let a
fourth real collaborator hide behind a passing test as long as it eventually ran — silently
defeating the property this test exists to pin. The exact ordered-equality list, over a
`Settings()` that still carries a real, unreachable `DATABASE_URL`, is what keeps a future
unmocked collaborator a hard failure rather than a quiet pass.

**KEEP.** This is a one-off, narrowly-scoped authorisation for this exact test and this exact
change — not a standing rule that later stories may extend this file further without their
own authorisation. The next story that adds a fourth `run_migrations` collaborator must not
treat this precedent as blanket permission; it must again justify the edit and, if granted,
keep the assertion an exact ordered list.

## Design Notes

**Why line 8's request line is skipped instead of only structurally.** Missing `harness` in the request
already skips every line (foundational field), so the structural (no-agent-step) skip only matters once
`repository_id`/`template_name`/etc. all resolve — exactly the `repo-init` case.

**Why the harness table needs no new `.env.example` entry.** `CLAUDE_CODE_VERSION`, `CODEX_VERSION`,
`OPENCODE_VERSION` already exist (Settings, `.env.example`) for the harness image; `version_pin` reads
them directly. `claude -> claude_code_version`, `codex -> codex_version`, `local -> opencode_version`
(the `.env.example` comment: "LOCAL_MODELS … exposed to the `local` harness (OpenCode)").

**Why `epics.yaml`/`stories.yaml` are re-read directly rather than through `lists.py`.** `lists.read_list`
takes a walker `Frame`, which preflight has no reason to construct. Re-reading the same path at the same
`plan_refs[path]` commit via `git.read_file` + `lines.load_sequence` costs one extra call per file and
avoids a second coupling to walker internals; entries are already known-valid once `plan_run` succeeded.

## Verification

**Commands:**
- `make lint` -- expected: exit 0.
- `make test` -- expected: exit 0, 100% branch on `domain/` + `application/`.
- `make openapi` -- expected: exit 0, no contract drift.
- `PATH="$HOME/.docker/bin:$PATH" make e2e` -- expected: exit 0 (docker off default PATH on this
  machine).
- `make e2e-ui` -- skip: no web-client file changes, and port 4321 is held by the operator's dev stack.

## Auto Run Result

Status: done

**Unblocked 2026-09-06.** The operator authorised editing exactly one frozen test
(`tests/unit/test_main_templates_seed.py::test_run_migrations_migrates_then_seeds_and_returns_the_head`)
to also monkeypatch `seed_harness_table` and assert the three-step order — see the Spec
Change Log entry above for the exact edit and the strictly-exceeds condition it was granted
under. No other anchor file changed.

**Final verification, as run on this machine:**
- `make lint` — exit 0 (ruff, `mypy --strict` on `domain/`+`application/`, `lint-imports`
  3/3 kept, env contract, test pairs 92/92, web-client astro/tsc/eslint/prettier/gen-api all
  clean).
- `make test` — exit 0; backend 3095 passed / 23 skipped, `domain/` + `application/`
  **100% branch, 0 missing**; web-client 722 passed.
- `make openapi` — exit 0; `contracts/openapi.json` and `web-client/src/api/schema.d.ts`
  regenerated with the two new routers (`runs`, `harnesses`).
- `PATH="$HOME/.docker/bin:$PATH" make e2e` — exit 0; 110 passed, 24 subtests, against a
  fresh `aio-e2e` stack torn down cleanly — including the harness table seeded for real at
  startup and schemathesis finding no server error on either new endpoint.
- `make e2e-ui` — not run: this story changes no web-client file, and port 4321 was held by
  the operator's own dev stack.

**Residual risks.** The response-shape decisions recorded above (which category owns which
substitution, the held-branch/queue-note label formula, "active Runs" = running+needs_you)
are each a single defensible reading where the brief under-specifies the exact rendering;
none is contradicted by an acceptance criterion, but a later story reading the brief
differently should check the Design Notes above before assuming a different rendering is a
bug. `budget_usd` is accepted and validated on the request but not yet read by any check —
Epic 5 or 4.4 is its first consumer.

**What was built, complete and verified working end to end:** `domain/entities/harness.py`,
`domain/ports/harnesses.py`, the `harness` table (`infrastructure/db/models/harness.py`,
`.../repositories/harnesses.py`, `alembic/versions/0006_harness.py`),
`tests/unit/fakes/harnesses.py`, `application/use_cases/harnesses.py` (`seed_harnesses`,
`list_harnesses`), `api/schemas/harnesses.py`, `api/routers/harnesses.py` (`GET /harnesses`);
`application/preflight/{model,checks,lists}.py`, `application/use_cases/preflight.py`
(`run_preflight`), `api/schemas/preflight.py`, `api/routers/runs.py` (`POST` + `GET
/runs/preflight`, the GET-sibling solving the frozen `test_bearer_auth.py`
`paths[path]["get"]` sweep the same way Epic 3 did); `api/providers.py::harness_ports,
preflight_ports`; `contracts/openapi.json` + `web-client/src/api/schema.d.ts` regenerated
(`make openapi`). 100% branch coverage on every new `domain/`/`application/` module; the
brief's five ACs and the matrix above are each a passing test in
`tests/unit/application/test_preflight_use_case.py`.
`PATH="$HOME/.docker/bin:$PATH" make e2e` -- **exit 0**, 110 passed / 24 subtests (up from
4-2's 107/21), including a real Postgres seeding the three harness rows at startup and
schemathesis finding no server error on either new endpoint.

**The blocking conflict.** The brief's Implementation notes require harness-table seeding
"in main.py startup", and the inherited context (correctly) places that inside
`main.run_migrations` — mirroring `seed_shipped_templates`, which is exactly what
`tests/unit/test_migrations.py` needs, since that frozen file replaces `main.run_migrations`
wholesale.

But a **second**, narrower frozen file exists that the inherited context did not name:
`backend-api/tests/unit/test_main_templates_seed.py:57-73`,
`test_run_migrations_migrates_then_seeds_and_returns_the_head`. It monkeypatches exactly two
collaborators — `main_module.db_migrations.run_migrations` and
`main_module.seed_shipped_templates` — and asserts:

```python
assert recorder.order == ["migrate", "seed"]
```

Adding the harness seed as a third statement in `run_migrations` (`head =
db_migrations.run_migrations(settings); seed_shipped_templates(settings);
seed_harness_table(settings); return head`) is not accounted for by either mock:
`seed_harness_table` runs for real and raises `sqlalchemy.exc.OperationalError: failed to
resolve host 'postgres'` (this test's `env` fixture sets the real `.env.example`
`DATABASE_URL`, unreachable outside the compose network), so `make test` fails this one test
— the only failure in the whole suite (3094 pass, 1 fails).

**Why this is not worked around.** Three alternative placements were tried and each one
breaks a *different* frozen test instead of fixing this one:
- Calling the harness seed from `migrating_lifespan` (a sibling statement beside
  `run_migrations(settings)`) breaks
  `tests/unit/test_migrations.py::test_main_migrates_before_the_socket_is_bound`, which
  wholesale-mocks `main_module.run_migrations` and asserts
  `recorder.order == ["migrate", "bind"]` over the *whole* `main()` call graph — any new
  real step anywhere in that graph is equally unmocked there.
- Folding it into `seed_shipped_templates`'s own body (so the *same* mock that already
  covers "seed" would also cover it) breaks six further tests in
  `test_main_templates_seed.py` that call the real `seed_shipped_templates` directly with
  granular mocks (`create_engine_from`, `SQLAlchemyUnitOfWork` → `FakeUow`,
  `SQLAlchemyTemplateVersionRepository` → a fake) that do not cover a
  `SQLAlchemyHarnessRepository` call against `FakeUow`'s bare `FakeSession` (no `.get`
  method) — `AttributeError`, not `OperationalError`, but still a break, on more tests.
- Moving the seed into `infrastructure/db/migrations.py::run_migrations` (the innermost,
  real-Alembic function) breaks two of *its own* frozen tests in `test_migrations.py` that
  mock only `command.upgrade`, and additionally contradicts that module's own documented
  scope ("the one statement of when the schema migrates").

Every placement that satisfies the brief's "seed at startup" requirement collides with a
frozen test somewhere in this pair of files; none of the three declared exceptions to hard
rule 1 apply (this test names no later story, is not a pending-gate registry, and asserts
nothing nondeterministic). The code is left in the architecturally correct state (the third
statement in `main.run_migrations`, matching `seed_shipped_templates`'s own wiring and the
brief's implementation note); nothing was reverted to force the gate green, and the tree is
**not committed**.

**Decision the operator needs to make:** either (a) authorize extending
`test_run_migrations_migrates_then_seeds_and_returns_the_head` to also monkeypatch
`main_module.seed_harness_table` and assert the three-step order (a two-line, low-risk
change to that one test), or (b) direct a different startup-wiring location this analysis
has not considered. Everything else in this story is complete, tested (100% branch on
`domain/`/`application/`), and passes `make lint`, `make openapi`, and
`PATH="$HOME/.docker/bin:$PATH" make e2e` (110 passed, 24 subtests) against the real stack.
