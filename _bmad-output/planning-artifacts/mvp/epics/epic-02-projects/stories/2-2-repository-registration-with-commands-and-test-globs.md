---
title: 'Repository registration with commands and test globs'
type: 'feature'
created: '2026-09-04'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      A lost race between two concurrent creates for the same URL, or the same slug,
      is refused by the unique indexes as a 500, not the 409/renumbered-slug the
      sequential application check produces.
    evidence: |-
      `_refuse_duplicate_url` and `_free_repo_slug` are both read-then-write; nothing
      translates the resulting `IntegrityError` from `ix_repository_project_id_url` or
      the new `ix_repository_project_id_slug`. This mirrors 2.1's own accepted residual
      risk for `Project.name`/`Project.slug` — one Operator at a keyboard does not reach
      the race in practice.
    location: backend-api/src/orchestrator/application/use_cases/projects.py
    severity: low
  - summary: >-
      Reading a Repository row whose `clone_check` JSON is missing a key raises
      `KeyError` instead of a handled error.
    evidence: |-
      `clone_check_from_entity` in infrastructure/db/repositories/repository.py indexes
      `data[STATUS_KEY]` etc. directly; every row this story ever writes has the full
      shape via `CloneCheck.pending()`, so this is only reachable from manual database
      surgery or a future migration that changes the shape without a data migration.
    location: backend-api/src/orchestrator/infrastructure/db/repositories/repository.py
    severity: low
  - summary: >-
      A stored `package_manager` outside the current `Literal` (e.g. from a future
      migration widening the enum before this code is updated) makes a read of that
      Repository fail pydantic validation rather than degrading.
    evidence: |-
      `Repository.package_manager: PackageManager` is a `Literal`; `to_entity` passes
      the stored string straight through with no fallback. Not reachable today — nothing
      writes an out-of-range value — but the same class of gap as the `clone_check` one
      above.
    location: backend-api/src/orchestrator/domain/entities/repository.py
    severity: low
  - summary: >-
      Neither `test_globs` nor the number of Repositories a Project can register has an
      upper bound.
    evidence: |-
      Mirrors 2.1's identical, already-accepted gap for `Project.env_vars` — an MVP,
      single-Operator instance with no untrusted multi-tenant input.
    location: backend-api/src/orchestrator/api/schemas/projects.py
    severity: low
  - summary: >-
      Nothing asserts that `RepositoryRow`'s implicit foreign-key constraint name
      (from the naming convention) agrees with `0003_repository.py`'s explicit
      `op.f(f"fk_{TABLE}_project_id_{PARENT_TABLE}")`.
    evidence: |-
      A future naming-convention change in `infrastructure/db/base.py` would make
      `alembic --autogenerate` propose a rename that nothing in `make test` would have
      predicted. Cosmetic today; the table works either way.
    location: backend-api/src/orchestrator/infrastructure/db/models/repository.py
    severity: low
baseline_revision: '3f3297af1e0cceecf72aba2aad687e26910ead39'
---

<intent-contract>

## Intent

**Problem:** A Project has nowhere to register the git repositories a Run works in: no URL, branch, install/quality-gate/unit-test commands, or the globs that protect tests an agent must not touch.

**Approach:** Add a `repository` table nested under `project`, its domain entity + `CloneCheck` value object + a pure glob-validation rule, a `RepositoryRepository` port + SQLAlchemy adapter + fake, use-case functions appended to the existing `application/use_cases/projects.py` module, and `/api/v1` endpoints to add/get/update/list Repositories, embedding them into `GET /projects/{id}`.

## Boundaries & Constraints

**Always:**
- AD-2 layering as in 2.1: `Repository` entity + `CloneCheck` value object in `domain/entities/repository.py`; the glob rule in `domain/rules/globs.py`; `RepositoryRepository` Protocol added to `domain/ports/repositories.py` (same file as `ProjectRepository`); use cases appended to `application/use_cases/projects.py`, repository section; SQLAlchemy model + adapter in `infrastructure/db/`; schemas added to `api/schemas/projects.py`; router in the new `api/routers/repositories.py`, mounted from `main.py` beside `projects.router`.
- Ids UUIDv7 (`domain.ids.new_id`); timestamps from the `Clock` port; no plaintext or credential field anywhere on `Repository` (AD-5) — `GITHUB_TOKEN` is instance-only and never a payload field.
- `clone_check` is initialised by `POST` to `{status: "pending", at: null, output: "", bmad_version: null}` and is never touched by `PUT`; only `run_clone_check` (2.3) writes it later.
- `test_globs` always contains the three defaults (`tests/**`, `**/*.test.*`, `**/*.spec.*`); Operator-supplied globs are appended, order-preserving, without duplicates. The merge rule applies on both `POST` and `PUT`.
- `verify_skipped` is a derived property (`not quality_gate_command`), never a stored column.
- `slug` is derived once, from the URL's last path segment with a trailing `.git` stripped, run through the same character rule as `Project.slugify` (lowercase, `[a-z0-9-]`), and numbered on collision *within the Project* (reuse `slugify`/`numbered_slug` from `domain/entities/project.py`); it never changes on `PUT`.
- `tests/unit/test_bearer_auth.py::test_the_contract_declares_the_401_and_its_media_type` is frozen and requires a `GET` operation on every published path. `list repositories of a project` is already in scope (see brief use-case list), so expose it as `GET /api/v1/projects/{id}/repositories` (envelope `Page[RepositoryOut]`) — this is what keeps the `POST` on that same path from leaving it without a `GET`.
- Every new module gets a *new* test module; AGENTS.md hard rule 1 forbids editing an existing test file, so the appended functions in `application/use_cases/projects.py` are covered by a new `tests/unit/test_repositories_use_cases.py`, never by edits to `test_projects_use_cases.py`. Same for `test_repository_entity.py`, `test_repository_globs.py`, `test_repository_ports.py`, `test_repository_repository_adapter.py`, `test_repository_schemas.py`, `test_repositories_router.py`, `tests/e2e/test_repositories.py`.
- `ProjectPorts` (application/use_cases/projects.py) gains one new field, `repositories: RepositoryRepository | None = None` (default so the existing frozen constructions in `test_projects_use_cases.py`, `test_projects_router.py`, `test_api_providers.py` keep compiling unchanged); `api/providers.py`'s `project_ports()` always supplies a real adapter, so only the router path ever sees `None`.
- Run `make openapi` and commit the regenerated `contracts/openapi.json` and `web-client/src/api/schema.d.ts`.

**Block If:**
- The architecture spine and this brief disagree on a field, route, or port signature.
- A frozen anchor (`SPEC.md`, `stories.yaml`, any `AGENTS.md`, any existing test file) would have to change for a gate to pass.

**Never:**
- No Clone check execution — `clone_check` is written only by 2.3's `run_clone_check`.
- No UI (2.4, 2.5).
- No `DELETE`.
- No `repositories` field added to `ProjectRead` (used by `POST`/`PUT`/`GET`-list `/projects`) — only the new `GET /projects/{id}` detail shape carries it.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Minimal create | `POST /projects/{id}/repositories {url, default_branch}` | 201; `test_globs` == the three defaults; `verify_skipped: true`; `clone_check.status: "pending"`; `package_manager: "other"` | No error expected |
| `test_globs` merge | `POST … {url, default_branch, test_globs:["e2e/**"]}` | stored globs == the three defaults + `"e2e/**"`, in that order, no duplicates | No error expected |
| Quality gate set | `POST … {quality_gate_command:"make lint test"}` then `GET` | `verify_skipped: false` | No error expected |
| Duplicate URL, same Project | second `POST` under the same Project with a stored `url` | 409 problem+json | `Conflict`; the same `url` under another Project is accepted |
| `PUT` changes `default_branch` | `PUT /repositories/{id} {default_branch: "develop", …}` | the field updates; `clone_check` unchanged (`pending` or its last result) | No error expected |
| `GET /projects/{id}`, two repositories | Project has two stored Repositories | both embedded, every field plus `verify_skipped`, in URL order of creation | No error expected |
| Missing required field | `POST` omitting `url` or `default_branch` | 422 problem+json, `errors[]` names the field's `path` | reason: the field is required |
| Invalid glob | `test_globs:["/abs/**"]` or `test_globs:["../x"]` | 422 problem+json naming the glob's index | reason: no leading `/`, no `..` segment |
| Unknown Project id | `POST` or `GET` `/projects/{uuid}/repositories`, id not stored | 404 problem+json | `NotFound` |
| Unknown Repository id | `GET`/`PUT /repositories/{uuid}`, id not stored | 404 problem+json | `NotFound` |
| Unauthenticated | any `/repositories` call without the bearer | 401 problem+json with `WWW-Authenticate` | inherited router dependency |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/entities/project.py` -- reuse `slugify`, `numbered_slug` for the Repository slug; the frozen-pydantic-entity + pure-rule-functions pattern to copy.
- `backend-api/src/orchestrator/domain/entities/repository.py` (NEW) -- `Repository` (frozen pydantic), `CloneCheck` value object, `PackageManager` (`Literal`, precedent: `infrastructure/settings.py:23 LogLevel`), `DEFAULT_TEST_GLOBS`, `verify_skipped` property, `repo_slug(url)`.
- `backend-api/src/orchestrator/domain/rules/globs.py` (NEW package) -- `is_valid_glob(glob: str) -> bool` (no leading `/`, no `..` segment); reused by the protected-path rule later (brief note).
- `backend-api/src/orchestrator/domain/ports/repositories.py` -- add `RepositoryRepository` Protocol (`add`, `get`, `list_by_project`, `update`) beside the existing `ProjectRepository`; mirror its `runtime_checkable` shape.
- `backend-api/src/orchestrator/domain/errors.py`, `domain/ids.py`, `domain/ports/clock.py` -- reuse `NotFound`/`Conflict`/`Invalid`, `new_id()`, `Clock` unchanged.
- `backend-api/src/orchestrator/application/use_cases/projects.py` -- append: `ProjectPorts.repositories: RepositoryRepository | None = None`; `RepositoryDraft`; `add_repository`, `get_repository`, `list_repositories_by_project`, `update_repository` -- mirrors `_refuse_duplicate_name`/`_require` patterns already in this module (`Conflict` on duplicate URL scanned via `list_by_project`, `NotFound` via `_require`-style helper). `get_project`'s router caller composes its `ProjectView` with `list_repositories_by_project` for the detail response; no new use case needed for that composition.
- `backend-api/tests/unit/fakes/projects.py` -- add `FakeRepositoryRepository` (mirrors `FakeProjectRepository`: dict keyed by id, `list_by_project` ordered by `created_at`).
- `backend-api/src/orchestrator/infrastructure/db/models/project.py`, `infrastructure/db/models/repository.py` (NEW), `infrastructure/db/models/__init__.py` -- `RepositoryRow`: `Text` columns, `JSONB` `test_globs`/`clone_check`, `Uuid` FK-shaped `project_id` (no `ForeignKey` needed beyond the column per 2.1's `project` table precedent, but add one since the row is meaningless without its Project), unique index on `(project_id, url)`.
- `backend-api/src/orchestrator/infrastructure/db/repositories/projects.py`, `infrastructure/db/repositories/repository.py` (NEW), `infrastructure/db/repositories/__init__.py` -- `SQLAlchemyRepositoryRepository`, mirroring `SQLAlchemyProjectRepository`'s `to_entity`/mutable-fields pattern.
- `backend-api/src/orchestrator/infrastructure/db/__init__.py` -- import the new model/repository so `Base.metadata` and `alembic --autogenerate` see them, same as `ProjectRow`.
- `backend-api/alembic/versions/0002_project.py` -- the revision shape to copy; `tests/unit/test_migration_chain.py` walks the chain from source automatically, so `0003_repository.py` with `down_revision = "0002_project"` needs no other test change.
- `backend-api/src/orchestrator/api/schemas/common.py` -- reuse `StorableText`, `UtcTimestamp`, `Page[T]`.
- `backend-api/src/orchestrator/api/schemas/projects.py` -- add `RepositoryCreate`, `RepositoryUpdate` (both validate globs via `is_valid_glob` through an `AfterValidator`, same wiring as `_valid_env_name`/`_repo_relative`), `RepositoryOut`, and `ProjectDetail(ProjectRead)` adding `repositories: list[RepositoryOut]` -- `ProjectRead` itself is unchanged (still used by `POST`/`PUT`/list).
- `backend-api/src/orchestrator/api/providers.py` -- `project_ports()` also builds `SQLAlchemyRepositoryRepository(uow.session)` and passes it as `ProjectPorts(..., repositories=...)`; no new `app.state` attribute, so `test_api_providers.py`'s missing-port assertions are unaffected.
- `backend-api/src/orchestrator/api/routers/projects.py` -- `get_project` changes its `response_model` to `ProjectDetail` and composes `use_cases.get_project(...)` with `use_cases.list_repositories_by_project(...)`; `create_project`/`update_project`/`list_projects` keep `ProjectRead`.
- `backend-api/src/orchestrator/api/routers/repositories.py` (NEW) -- `POST /projects/{project_id}/repositories`, `GET /projects/{project_id}/repositories`, `GET /repositories/{repository_id}`, `PUT /repositories/{repository_id}`; same refusal-declaration pattern as `routers/projects.py` (`_refusal`, `VALIDATION`/`READ_REFUSALS`/etc).
- `backend-api/src/orchestrator/main.py` -- add `repositories` to the `from orchestrator.api.routers import ping, projects` line and a third `include_router(repositories.router, prefix=API_PREFIX, dependencies=[Depends(require_bearer)], responses={HTTP_UNAUTHORIZED: UNAUTHORIZED_RESPONSE})`; `test_bearer_auth.py::test_the_versioned_router_is_mounted_with_the_dependency` ast-parses this and requires exactly those keywords on every `include_router` call.
- `backend-api/tests/unit/test_bearer_auth.py` -- frozen; drives the "every published path needs a `GET`" and "every mount carries `require_bearer`" constraints noted above.
- `backend-api/tests/unit/test_source_limits.py`, `test_check_test_pairs.py` -- frozen gates the new modules must satisfy (≤400 lines, no `print`, no wall-clock read outside `infrastructure/`, every `src` module imported by some new unit test).
- `backend-api/tests/e2e/test_projects.py` -- pattern for `authenticated` httpx fixture and `unique_name`-style isolation to copy in the new `tests/e2e/test_repositories.py` (a Project must exist first; there is no `DELETE`, so names/URLs must be unique per run).

## Tasks & Acceptance

**Execution:**
1. `backend-api/tests/unit/fakes/projects.py` -- add `FakeRepositoryRepository` -- the only fake for the new port (AD-18).
2. `backend-api/tests/unit/test_repository_globs.py` -- failing tests for `is_valid_glob` (leading `/`, `..` segment, ordinary glob) -- TDD; drives task 3.
3. `backend-api/src/orchestrator/domain/rules/__init__.py`, `.../rules/globs.py` -- `is_valid_glob`.
4. `backend-api/tests/unit/test_repository_entity.py` -- failing tests for `Repository`, `CloneCheck`, `repo_slug`, `DEFAULT_TEST_GLOBS`, `verify_skipped` -- TDD; drives task 5.
5. `backend-api/src/orchestrator/domain/entities/repository.py` -- the entity, value object, and pure functions.
6. `backend-api/src/orchestrator/domain/ports/repositories.py` -- add `RepositoryRepository` Protocol.
7. `backend-api/tests/unit/test_repository_ports.py` -- assert the fake satisfies the Protocol; pairs the port module with `check_test_pairs`.
8. `backend-api/tests/unit/test_repositories_use_cases.py` -- failing tests for every I/O-matrix row that is a use-case rule (merge, duplicate URL, keep-`clone_check`-on-`PUT`, unknown project/repository) -- TDD; drives task 9.
9. `backend-api/src/orchestrator/application/use_cases/projects.py` -- append `ProjectPorts.repositories`, `RepositoryDraft`, `add_repository`, `get_repository`, `list_repositories_by_project`, `update_repository`.
10. `backend-api/tests/unit/test_repository_repository_adapter.py` -- table name, columns, JSONB, unique index `(project_id, url)`, schema `public`, entity-to-row mapping over a recording session -- TDD; drives task 11.
11. `backend-api/src/orchestrator/infrastructure/db/models/repository.py`, `.../db/repositories/repository.py`, and both packages' `__init__.py`; import from `infrastructure/db/__init__.py`.
12. `backend-api/alembic/versions/0003_repository.py` -- `down_revision = "0002_project"`; create `repository` with `uuid` pk + `project_id`, `text` columns, `jsonb` `test_globs`/`clone_check`, `timestamptz` timestamps, unique index on `(project_id, url)`; `downgrade()` drops it.
13. `backend-api/tests/unit/test_repository_schemas.py` -- payload validation rows of the I/O matrix (required fields, invalid glob, `verify_skipped` derivation) -- TDD; drives task 14.
14. `backend-api/src/orchestrator/api/schemas/projects.py` -- add `RepositoryCreate`, `RepositoryUpdate`, `RepositoryOut`, `ProjectDetail`.
15. `backend-api/tests/unit/test_repositories_router.py` -- router tests over httpx ASGI with fakes injected through `dependency_overrides`, covering every declared refusal -- TDD; drives tasks 16-18.
16. `backend-api/src/orchestrator/api/providers.py` -- extend `project_ports()` to also build `SQLAlchemyRepositoryRepository`.
17. `backend-api/src/orchestrator/api/routers/repositories.py` -- the four operations.
18. `backend-api/src/orchestrator/api/routers/projects.py`, `main.py` -- `get_project` returns `ProjectDetail`; mount `repositories.router`.
19. `backend-api/tests/e2e/test_repositories.py` -- create Project → add Repository → get → list-by-project → update → duplicate-URL 409 → unknown-id 404, against the running stack, plus a `GET /projects/{id}` assertion that `repositories` embeds correctly.
20. `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- regenerate with `make openapi` and commit.

**Acceptance Criteria:**
- Given the whole suite, when `make lint && make test` run, then `import-linter`, `check_test_pairs`, the contract-drift check, and the 100% branch-coverage report over `domain/` + `application/` all pass.
- Given the running stack, when `make e2e-api` runs, then the Repository round-trip passes and Schemathesis reports no 5xx on any `/api/v1/projects*` or `/api/v1/repositories*` operation.
- Given no existing test file was edited, when the diff is inspected, then every new assertion lives in a new `tests/unit/*.py` or `tests/e2e/*.py` module.
- Given `GET /api/v1/openapi.json`, when every published path is checked, then each one declares a `get` operation with a `401` response (the frozen `test_bearer_auth.py` sweep).

## Design Notes

**Why one `ProjectPorts`, not a second ports dataclass.** `POST /projects/{id}/repositories` has to confirm the parent Project exists and scan its siblings for a duplicate URL in the same transaction that inserts the new row — that is exactly what `ProjectPorts` already opens (`uow`, and now `projects` and `repositories` on the same session). A second `RepositoryPorts` would either duplicate the transaction wiring in `api/providers.py` or force two open sessions for the one `GET /projects/{id}` call that needs both. Giving `repositories` a default of `None` is what keeps this backward compatible: the three frozen test files that construct `ProjectPorts(uow=..., projects=..., crypto=..., clock=...)` never pass it, and never call a repository use case, so they keep working unmodified.

**Where `GET /projects/{id}` gets its list.** No new use case composes the two calls — the router does it, the same way `create_project` in `routers/projects.py` already composes a use case with a settings read:
```python
view = use_cases.get_project(ports, project_id)
repos = use_cases.list_repositories_by_project(ports, project_id)
return ProjectDetail.of(view, repos)
```

## Verification

**Commands:**
- `cd backend-api && uv run --locked pytest tests/unit -q` -- expected: green, including every new module
- `make lint` -- expected: ruff, mypy strict, import-linter, env contract, test pairs, contract drift, eslint/tsc all pass
- `make test` -- expected: green, and `coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100` passes
- `make openapi` -- expected: `contracts/openapi.json` and `web-client/src/api/schema.d.ts` change only by the new repository operations and schemas, plus `GET /projects/{id}`'s response shape
- `make up` then `BACKEND_API_URL=http://127.0.0.1:8000 ORCHESTRATOR_TOKEN=... make e2e-api` -- expected: the repository round-trip passes and Schemathesis reports no 5xx

## Spec Change Log

### 2026-09-04 — Operator-directed resolution of the blocked frozen-anchor conflict

- **Triggering finding.** Step-03 implementation verification found this story's `Never`
  clause ("No `repositories` field added to `ProjectRead` (used by `POST`/`PUT`/`GET`-list
  `/projects`) — only the new `GET /projects/{id}` detail shape carries it") and its Design
  Notes' `ProjectDetail` shape irreconcilable with the frozen
  `tests/unit/test_projects_router.py::test_reading_one_project_answers_the_masked_project`
  and its e2e counterpart in `tests/e2e/test_projects.py`, both of which assert
  `GET /projects/{id}` returns a body byte-identical to `POST /projects`'s body. Any shape
  satisfying the brief's "`GET /projects/{id}` embeds repositories" acceptance criterion via
  a separate `ProjectDetail` type gives `GET` a key `POST` lacks, which the frozen assertion
  forbids. The run halted `blocked`, in the `## Auto Run Result` this entry's resolution
  supersedes.
- **Amendment.** The coordinator directed this resolution, which this spec's
  Boundaries & Constraints and Code Map are understood to be superseded by on this one
  point — `<intent-contract>` itself is left unedited per the read-only rule, and this entry
  is the record of the deviation: `ProjectRead` (not a separate `ProjectDetail`) gains
  `repositories: list[RepositoryOut]`, populated truthfully by every route that renders
  it — `POST /projects`, `PUT /projects/{id}`, `GET /projects/{id}`, and each item of
  `GET /projects` (list) — via a new `embedded_repositories(ports, project_id)` use case
  that queries the real Repository store per Project. No separate `ProjectDetail` type
  exists in the shipped code.
- **Known-bad state avoided.** Editing an anchor test file (forbidden by AGENTS.md hard
  rule 1) to make the two frozen assertions above accept a `repositories` key on `GET` but
  not `POST`; or narrowing the story to silently drop its own "`GET /projects/{id}` embeds
  repositories" acceptance criterion instead of resolving the conflict; or an unbounded
  blocked/review loop with no path to `done`.
- **KEEP.** `ProjectRead.of`'s `repositories` parameter stays optional
  (`list[Repository] | None = None`, defaulting to `[]`) so the frozen
  `tests/unit/test_project_schemas.py` calls that build a `ProjectRead` from only a view
  keep compiling. `ProjectPorts.repositories` stays `RepositoryRepository | None = None` so
  the frozen `test_projects_router.py` `Harness` (which never wires a repository port)
  keeps working: `embedded_repositories` degrades to `[]` on `None` rather than raising.
  Only the dedicated repository use cases (`add_repository`, `get_repository`,
  `list_repositories_by_project`, `update_repository`) still raise loudly via `_repos()`
  when reached without a real port — those are only ever exercised through a route that
  always supplies one, so a `None` there is a wiring bug, not a legitimate legacy caller.

## Review Triage Log

### 2026-09-05 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 4, low 4)
- defer: 5: (high 0, medium 0, low 5)
- reject: 6: (high 0, medium 0, low 6)
- addressed_findings:
  - `[medium]` `[patch]` `PackageManager` (`domain/entities/repository.py`) held
    `Literal["npm", "pnpm", "yarn", "poetry", "uv", "other"]` — dropping the brief's
    `pip`/`cargo`/`go` and inventing `poetry`. Corrected to the brief's exact eight values;
    `tests/unit/test_repository_schemas.py`'s `test_an_unknown_package_manager_is_refused`
    (which had asserted `"cargo"` was refused) now refuses `"poetry"` instead, and a new
    parametrized test asserts all eight brief values are accepted.
  - `[medium]` `[patch]` `CloneCheckStatus` held `Literal["pending", "passed", "failed"]`;
    the brief specifies `"pending" | "ok" | "failed"`. Corrected, including the module
    docstring that named `"passed"`.
  - `[medium]` `[patch]` only `(project_id, url)` was uniquely indexed; nothing stopped two
    Repositories in one Project from landing with the same `slug` under a concurrent
    create, the same race class the `url` index already guards. Added
    `ix_repository_project_id_slug` to both `infrastructure/db/models/repository.py` and
    `alembic/versions/0003_repository.py` (edited in place; the revision had not landed),
    plus coverage in `test_repository_repository_adapter.py` and `tests/e2e/test_repositories.py`.
  - `[medium]` `[patch]` `tests/unit/test_repositories_router.py` asserted the
    Repository-embedding behaviour only for `GET /projects/{id}`; reverting `list_projects`
    or `update_project` to render `repositories: []` unconditionally would have passed
    every existing test. Added `test_the_project_list_also_embeds_each_projects_repositories`
    and `test_updating_a_project_still_carries_its_stored_repository`.
  - `[low]` `[patch]` `Repository.verify_skipped` returned `not self.quality_gate_command`,
    so a whitespace-only command read as "declared". Now strips before the check, with a
    test for the whitespace-only case.
  - `[low]` `[patch]` `list_by_project`'s `.order_by(RepositoryRow.created_at)` had no
    tiebreaker, leaving two same-timestamp creates in undefined order although the brief
    requires reliable "URL order of creation". Added `RepositoryRow.id` as the secondary
    sort key.
  - `[low]` `[patch]` `add_repository` queried `list_by_project` twice (once for the
    duplicate-url check, again for slug numbering). Both helpers now take the
    already-fetched list instead of re-querying.
  - `[low]` `[patch]` this spec's own `## Auto Run Result` and the frontmatter it carried
    still narrated the pre-resolution `blocked` state (a stale `Residual risk` paragraph
    claiming a code path — `_repos()` raising — that the shipped `embedded_repositories`
    never takes). Rewritten below to match the code actually shipped.

## Auto Run Result

Status: done

**Resolution of the earlier block.** This run halted `blocked` after step-03 because the
brief's "`GET /projects/{id}` embeds repositories" acceptance criterion, delivered via a
separate `ProjectDetail` shape (as this spec originally specified), is irreconcilable with
the frozen `tests/unit/test_projects_router.py::test_reading_one_project_answers_the_masked_project`
and its e2e counterpart, both of which assert `GET /projects/{id}` returns a body
byte-identical to `POST /projects`'s. The coordinator directed the resolution recorded in
`## Spec Change Log` above: `ProjectRead` itself gains `repositories`, populated truthfully
by every route that renders it. Because no Project in either frozen test ever has a stored
Repository, every one of that test's bodies now carries `repositories: []` on both sides of
its equality checks, and both files pass untouched.

**What was built.** All 20 tasks from the original plan, TDD throughout, every new module
paired with a *new* unit test module (`tests/unit/fakes/projects.py` is the only edit under
`tests/`, and it is purely additive — the `FakeRepositoryRepository` task 1 directs), plus
the read-model widening and the eight patches above.

- `domain/entities/repository.py` — `Repository`, `CloneCheck`, `PackageManager`
  (`uv | pnpm | npm | yarn | pip | cargo | go | other`), `CloneCheckStatus`
  (`pending | ok | failed`), `DEFAULT_TEST_GLOBS`, `verify_skipped` (whitespace-safe),
  `repo_slug()`, `merge_test_globs()`.
- `domain/rules/globs.py` (new package) — `is_valid_glob()`.
- `domain/ports/repositories.py` — `RepositoryRepository` Protocol (additive).
- `application/use_cases/projects.py` — `ProjectPorts.repositories` (defaults `None` for
  the frozen Project-only tests), `RepositoryDraft`, `add_repository`, `get_repository`,
  `list_repositories_by_project`, `update_repository`, and the tolerant
  `embedded_repositories()` every Project route calls to render `ProjectRead.repositories`.
- `infrastructure/db/models/repository.py` + `db/repositories/repository.py`, wired into
  `db/__init__.py`; two unique indexes, `(project_id, url)` and `(project_id, slug)`.
- `alembic/versions/0003_repository.py` — `down_revision = "0002_project"`.
- `api/schemas/projects.py` — `RepositoryCreate`, `RepositoryUpdate`, `RepositoryOut`,
  `CloneCheckOut`; `ProjectRead` widened with `repositories: list[RepositoryOut]` and an
  `.of(view, repositories=None)` that defaults to `[]` for the frozen `test_project_schemas.py`
  calls that pass only a view.
- `api/routers/repositories.py` (new, four operations) mounted in `main.py`;
  `api/routers/projects.py`'s four operations all route through one `_read()` helper so
  every response — create, read, update, list — carries the Project's current Repositories,
  freshly queried, never a stale snapshot.
- `api/providers.py` builds `SQLAlchemyRepositoryRepository` alongside the Project
  repository, same session, same transaction.
- Eight new unit test modules plus `tests/e2e/test_repositories.py`; `contracts/openapi.json`
  and `web-client/src/api/schema.d.ts` regenerated via `make openapi`.

**Review.** Four layers (blind hunter, edge-case hunter, verification-gap, intent-alignment)
ran over the full diff. 8 patches applied (4 medium, 4 low; listed above), 5 items deferred
(all low; see frontmatter `deferred`), 6 rejected — including, notably, the two findings
that flagged the `ProjectRead` widening as contradicting this spec's original `Never`
clause: correct as a description, but already the coordinator's authorized resolution,
recorded in `## Spec Change Log` rather than re-litigated here. Follow-up review
recommended: `true` — 0 high, 4 medium, 4 low patched, score `3 × 4 + 1 × 4 = 16`, at or
above the threshold of 5.

**Verification.**

- `cd backend-api && uv run --locked pytest tests/unit -q` — 1210 passed, 1 skipped.
- `make lint` — ruff, mypy strict, `lint-imports` (3 contracts kept), env contract, test
  pairs (32 backend modules paired), contract-drift check, and the whole web-client lane:
  pass.
- `make test` — 1210 backend unit tests passed, 1 skipped; `domain/` + `application/` at
  100% branch coverage (318 statements, 40 branches) with `--fail-under=100`; 488 vitest
  tests passed.
- `make coverage` — 100% over the 502 diffed lines `diff-cover` can see (tracked files);
  several new files are still untracked at review time, so `diff-cover` cannot include
  them — `make test`'s own 100% branch figure over `domain/` + `application/` is what
  actually covers those modules, and every new module has its own dedicated unit test file.
- `make openapi` — regenerated and committed; the drift check reports the generated types
  match.
- `make e2e-api` — run twice against a freshly rebuilt stack (`make up --build`, then
  `docker compose down -v` once to force the edited-in-place `0003_repository` migration to
  re-run after the slug-index patch, then `make up` again), `DATABASE_URL` pointed at
  `127.0.0.1:5432`: 44 passed, 10 Schemathesis subtests, no 5xx on any published operation.
  `tests/e2e/test_projects.py`'s 15 tests — including the three 2.1 assertions the block was
  about — pass unedited. A manual `curl` round-trip additionally confirmed `repositories` is
  populated truthfully (not faked empty) on `POST`, `GET /projects/{id}`, `PUT`, and the
  matching item of `GET /projects` (list), for a Project with one real stored Repository.
  Stack brought down (`make down`) after.
- Every row of the I/O & Edge-Case Matrix is covered by a test that ran and passed.

**Files changed.** See "What was built" above, plus
`_bmad-output/implementation-artifacts/sprint-status.yaml` (2-1 corrected to `done`,
matching its landed commit `3f3297a`; 2-2 to `review`, corrected to `done` in this same
change alongside this file's own `status`). No anchor (`SPEC.md`, `stories.yaml`,
`epics.yaml`, any `AGENTS.md`, or any pre-existing test file) was edited or deleted;
`tests/unit/fakes/projects.py` — a fake, not a test file, and the one this spec's task 1
directs — is the only change under `tests/` to a file that existed before this story.

**Residual risks.** The 5 items in frontmatter `deferred` (all low: the two unique indexes'
races surfacing as 500 rather than 409/renumbered-slug, a malformed `clone_check` or
out-of-range `package_manager` row raising on read instead of degrading, no upper bound on
`test_globs`/Repository counts, and an untested FK-naming-convention agreement between the
model and the migration).
