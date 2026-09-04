---
title: 'Database, migrations, bearer auth, and API conventions'
type: 'feature'
created: '2026-09-03'
status: 'done'
baseline_commit: '5def00f7f242532857cb34766fc495ea994af093'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/briefs/1-2-database-auth-and-api-conventions.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** backend-api is a skeleton with one public route. It has no datasource, no migrations, no authentication, and no error or list shape — so every later endpoint would have to re-decide persistence, who may call it, and what a failure looks like, and `make e2e-api` still refuses.

**Approach:** Add one Postgres datasource behind `infrastructure/db/`, an Alembic baseline applied at start-up before the first request, a constant-time bearer dependency that every `/api/v1/*` route carries, RFC 9457 problem responses with the list envelope, UUIDv7 and time/money helpers, a `postgres`-only compose file, and the `tests/e2e/` harness that turns `make e2e-api` from a refusal into a gate.

## Boundaries & Constraints

**Always:**
- One credential (AD-4): `ORCHESTRATOR_TOKEN` compared with `hmac.compare_digest`. `/healthz` and `/openapi.json` stay public; no cookies, no CORS headers on backend-api.
- Errors are `application/problem+json` `{type, title, status, detail, instance, errors?}`; `errors[]` entries are `{template?, version?, line?, path?, reason}`. Lists are `{items, next_cursor}` and nothing else.
- Ids are UUIDv7 (`uuid.uuid7()`); times ISO 8601 UTC with `Z`; DB `timestamptz`; money `numeric(12,6)` USD serialised as a string.
- Alembic manages schema `public` only; `alembic upgrade head` runs before the process serves, and logs `migrations applied` with the head revision.
- Layering (AD-2): `domain/` and `application/` never import `sqlalchemy`, `fastapi`, `os`, `httpx`. The datasource lives behind `infrastructure/db/`; its contract is a `domain/ports/` Protocol with one fake in `tests/unit/fakes/`.
- Unit tests never need Postgres or the network (AD-18); `tests/e2e/` needs the running stack.
- Stack pins exact: SQLAlchemy 2.0.52, psycopg 3.3.5, Alembic 1.19.1, httpx 0.28.1, schemathesis 4.25.2, PostgreSQL 18. `uv.lock` regenerated and committed.
- Tests first: every test module below is written and fails before the module it covers exists.
- No new environment variable. The contract stays at 25 settings fields / 31 `.env.example` variables / 6 allowlisted.
- Existing files are revised in place, never moved, renamed, or replaced. Anchors (`SPEC.md`, `stories.yaml`, either `AGENTS.md`, any existing test file) are not edited. `GUIDELINES.md` is untouched.
- The story that lands a gate must add a test proving the landed gate now runs (root `AGENTS.md` hard rule 1).
- No real secret and no `.env` is ever committed; a token value never reaches a log line or a problem body.

**Ask First:**
- Any dependency, top-level directory, or environment variable the brief does not name.
- Any change that makes a gate pass by weakening it — loosening ruff/mypy, widening an import-linter contract, adding an ignore, skipping a test.
- Anything that would delete, move, or overwrite an existing file.

**Never:** any domain table or entity (the story that needs it creates it); cookies or session handling (1.5); the web-client, the exported contract, `make openapi`, `make e2e-ui` (1.3); the full compose stack, Dockerfiles, `make up` (1.6); CI (1.7); DBOS imports or `DBOS.launch()` (Epic 4); coverage thresholds (1.7).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Start-up migration | process starts against Postgres | `alembic upgrade head` completes and `migrations applied` is logged with the head revision, before the server binds | a failed upgrade aborts start-up; the process never serves a half-migrated schema |
| Missing bearer | `GET /api/v1/ping`, no `Authorization` | 401 `application/problem+json`, `title: "unauthorized"` | body identical to every other 401 — nothing distinguishes the cases |
| Wrong bearer | correct-length token differing by one byte | 401, byte-identical body to the missing-header case | comparison is `hmac.compare_digest` over bytes |
| Non-ASCII bearer | `Authorization: Bearer ünicode` | 401, same body | encoded to bytes before comparison — never a 500 |
| Wrong scheme | `Authorization: Basic abc` | 401, same body | N/A |
| Correct bearer | `GET /api/v1/ping` with the token | 200 `{"pong": true}` | N/A |
| Public routes | `GET /healthz`, `GET /openapi.json` with no header | 200 | N/A |
| Body validation | a request body failing Pydantic validation | 422 problem+json, `errors[]` of `{path, reason}`, `detail` naming the first error | one handler; FastAPI's default validation shape is replaced |
| Unknown path | `GET /api/v1/nope` | 404 `application/problem+json` | Starlette's HTML/JSON default is replaced |
| Domain error | a use case raises `NotFound` / `Conflict` / `Invalid` | 404 / 409 / 422 problem+json | domain never imports `fastapi`; the api layer maps |
| List envelope | any paged payload | `{items: [...], next_cursor: str \| null}` | N/A |
| Money and time | a `Decimal` amount and a UTC datetime | `"12.500000"` (6 dp string) and `...Z` | a naive datetime is refused, not silently localised |
| Ids | `new_id()` | a `UUID` with `version == 7`, monotonically increasing | N/A |
| Unit-of-work rollback | a block raising inside the unit of work | `rollback()` called, `commit()` not | the exception propagates |
| Landed gate | `make e2e-api` | runs `pytest tests/e2e` under `uv run --locked --directory backend-api` | it no longer prints `not available until story 1.2` |

</frozen-after-approval>

## Code Map

Read-only / must not change:
- `backend-api/tests/unit/test_makefile.py` -- **existing test, frozen.** Its `PENDING_TARGETS` no longer lists `e2e-api` (a pre-authorised operator edit already in the working tree at baseline). Do not touch this file. Reuse its `_make()` and `_uv_invocations()` by importing them from a **new** module; `_uv_invocations` matches on the executable basename because `$(UV)` expands to an absolute path — a `startswith("uv run")` filter makes the assertion vacuous (that bug shipped in 1.1).
- `AGENTS.md`, `backend-api/AGENTS.md`, `SPEC.md`, `stories.yaml`, `GUIDELINES.md` -- anchors.
- `.env.example` (31 vars) and `scripts/check_env_contract.py` -- the contract is frozen at 25/31/6. `BACKEND_API_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` are already declared and allowlisted, so the e2e harness and compose need nothing new.

Existing, edited in place:
- `backend-api/src/orchestrator/main.py:36` `create_app(settings)` -- add `app.state.settings`, the problem handlers, and the `/api/v1` router mounted with the bearer dependency; `main():51` gains `run_migrations(settings)` before `uvicorn.run`.
- `backend-api/pyproject.toml` -- runtime deps gain sqlalchemy/psycopg/alembic; dev deps gain schemathesis. Gate configuration is not relaxed.
- `Makefile:32` -- the `e2e-api` recipe replaces its refusal with `$(PYTHON_RUN) pytest tests/e2e -q`.
- `README.md` -- the gate table marks `e2e-api` as landed and gains the bring-up line. Every existing section survives, including "Setting up the BMAD method on a new machine".

Reuse pointers:
- `backend-api/src/orchestrator/infrastructure/settings.py:56` -- `database_url: SecretStr` and `orchestrator_token: SecretStr` already exist. Read them, never re-read the environment.
- `backend-api/src/orchestrator/infrastructure/logging.py` -- `structlog.get_logger()`; no `print` (asserted by `test_source_limits.py`).
- `backend-api/tests/unit/conftest.py` -- the `env` fixture derives the whole environment from `.env.example`. Every new unit test that builds `Settings()` takes it.
- `backend-api/tests/unit/fakes/clock.py` -- the shape the new `fakes/db.py` follows: one fake per port, no new doubles.
- `backend-api/src/orchestrator/domain/ports/clock.py` -- the Protocol style for `ports/unit_of_work.py`.

Verified during planning (do not re-verify):
- All pins resolve together on CPython 3.14.7 — 62 packages, `uv 0.12.9`. `uuid.uuid7()` exists and returns version 7.
- import-linter **permits** `orchestrator.api` importing `orchestrator.infrastructure` under the committed contract (probed against a copy of the tree; 3 contracts kept). So `api/deps.py` may take `Settings` directly.
- `postgres:18` declares its volume at `/var/lib/postgresql` with `PGDATA=/var/lib/postgresql/18/docker` — **not** the pre-18 `/var/lib/postgresql/data`. Mount `pgdata` at `/var/lib/postgresql`.
- schemathesis 4.25.2 exposes `schemathesis.openapi.from_url(...)`, `schema.parametrize()`, `case.call_and_validate(...)` and `schemathesis.checks.not_a_server_error`.

## Tasks & Acceptance

**Execution:** (tests first — every `test_*` task lands red before the module it names)

- [x] `backend-api/pyproject.toml`, `backend-api/uv.lock` -- add `sqlalchemy==2.0.52`, `psycopg[binary]==3.3.5`, `alembic==1.19.1` (runtime) and `schemathesis==4.25.2` (dev); regenerate the lock -- reproducible gates.
- [x] `backend-api/tests/unit/test_ids.py` + `src/orchestrator/domain/ids.py` -- `new_id() -> UUID` (uuid7) -- one id generator, asserted to be version 7 and increasing.
- [x] `backend-api/tests/unit/test_domain_errors.py` + `src/orchestrator/domain/errors.py` -- `DomainError`/`NotFound`/`Conflict`/`Invalid` -- use cases raise these; only the api layer knows their status codes.
- [x] `backend-api/tests/unit/test_uow_fake.py` + `src/orchestrator/domain/ports/unit_of_work.py` + `tests/unit/fakes/db.py` -- the `UnitOfWork` Protocol and its one in-memory fake -- AD-18: the port and its fake exist before the adapter.
- [x] `backend-api/tests/unit/test_problem_details.py` + `src/orchestrator/api/errors.py` -- `ProblemDetail`, `ProblemError`, `Problem`, `install_error_handlers(app)` for `Problem`, `RequestValidationError`, `HTTPException` and `DomainError` -- one error shape for the whole API.
- [x] `backend-api/tests/unit/test_api_schemas.py` + `src/orchestrator/api/schemas/common.py` -- `Page[T]`, `MoneyStr`, `UtcTimestamp` -- the list envelope and the money/time conventions in one place.
- [x] `backend-api/tests/unit/test_bearer_auth.py` + `src/orchestrator/api/deps.py` + `src/orchestrator/api/routers/ping.py` -- `require_bearer`, `GET /api/v1/ping` -- covers the 401 rows of the matrix plus a structural assertion that every `/api/v1` route carries the dependency and that the token is never compared with `==`.
- [x] `backend-api/tests/unit/test_db_adapters.py` + `src/orchestrator/infrastructure/db/{__init__,base,engine,session,unit_of_work}.py` -- engine from `DATABASE_URL`, session factory, `SQLAlchemyUnitOfWork` -- no Postgres in the unit test: construction and rollback semantics only.
- [x] `backend-api/alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_baseline.py` -- baseline creating nothing, schema `public` only, URL from settings -- never a URL in a committed file.
- [x] `backend-api/tests/unit/test_migrations.py` + `src/orchestrator/infrastructure/db/migrations.py` -- `run_migrations(settings) -> str` logging `migrations applied` with the head revision; a test proves `main()` calls it before `uvicorn.run` -- the schema is current before the first request.
- [x] `backend-api/src/orchestrator/main.py` -- wire handlers, router and migration into the existing composition root -- edited in place.
- [x] `docker-compose.yml` + `backend-api/tests/unit/test_compose.py` -- `postgres` service only: `postgres:18`, `POSTGRES_*` from the env, `pgdata:/var/lib/postgresql`, healthcheck, published on `127.0.0.1` -- 1.6 adds the rest; the test proves it has not been pre-empted.
- [x] `backend-api/tests/e2e/{__init__,conftest,test_smoke,test_schemathesis}.py` -- httpx scenarios (healthz, the 401s, ping) and Schemathesis over every `/openapi.json` operation with the bearer -- the e2e-api gate's content.
- [x] `Makefile` -- `e2e-api` runs `pytest tests/e2e -q` under `--locked --directory backend-api` -- the gate stops refusing.
- [x] `backend-api/tests/unit/test_makefile_e2e_api.py` -- **new file**, importing `_make`/`_uv_invocations` from the frozen module; asserts the matched invocation list is non-empty, that the recipe runs `pytest tests/e2e` with `--locked --directory backend-api`, that it no longer prints `not available until story`, and that `e2e-api` is absent from `PENDING_TARGETS` -- required by hard rule 1: the commit that retires the pending entry adds the test that the landed gate runs.
- [x] `README.md` -- mark `e2e-api` landed and document the local bring-up -- edited in place, every section kept.

**Acceptance Criteria:**

- Given a clean checkout, when `make lint` runs, then it exits 0 and the env-contract line still reports 25 settings fields and 31 `.env.example` variables.
- Given a clean checkout with no database and no network, when `make test` runs, then it exits 0 and the count is strictly greater than the 144 tests at baseline.
- Given `docker compose up -d postgres` and the app started against it, when `make e2e-api` runs, then it exits 0 having executed both the httpx scenario module and the Schemathesis module, and the `alembic_version` table holds the baseline revision.
- Given the Makefile recipe for `e2e-api` is mutated to drop `--locked`, `--directory backend-api`, or `pytest tests/e2e`, when `make test` runs, then the new Makefile test fails — proving it is not vacuous.
- Given the finished story, when `git status` is compared to the pre-story tree, then no file is deleted or renamed, `backend-api/tests/unit/test_makefile.py` carries only the pre-authorised one-line removal, and `GUIDELINES.md` is absent from the diff.
- Given the repository, when it is searched for credentials, then no `.env` file and no real secret value is committed.

## Spec Change Log

**Migrations are wired by `main()` as the application's start-up step, not called inline before `uvicorn.run`.**
The Design Note below specifies `main()` calling `run_migrations(settings)` directly ahead of `uvicorn.run`.
That cannot hold: `backend-api/tests/unit/test_logging.py::test_uvicorn_is_not_allowed_to_replace_the_json_logging_config`
is an existing test file (frozen, root `AGENTS.md` hard rule 1) that calls `main()` with only
`uvicorn.run` stubbed, so an inline call reaches Postgres and contradicts the frozen boundary
"unit tests never need Postgres or the network" and the acceptance criterion "`make test` exits 0 with
no database and no network".

What landed instead keeps every frozen requirement and every stated goal of the Design Note:
`main()` builds `create_app(settings, lifespan=migrating_lifespan(settings))` and hands it to uvicorn.
uvicorn awaits lifespan start-up before it creates the listening socket, so the upgrade still runs
exactly once per process, logs one `migrations applied` line with the head revision, completes before
the server binds, and aborts start-up on failure. `create_app` still performs no I/O, and an
application built by a test carries no start-up step at all — which is the property the Design Note
was protecting. The ordering is asserted in `tests/unit/test_migrations.py` by driving the start-up
step the way uvicorn does and recording what happened when
(`test_main_migrates_before_the_socket_is_bound`, `test_a_failed_migration_stops_the_process_before_it_serves`).

**`Page[T]` uses PEP 695 type-parameter syntax.** `class Page(BaseModel, Generic[T])` is refused by
ruff `UP046` under the committed configuration, which this story may not relax.

**The structural bearer assertion sweeps the OpenAPI document, not FastAPI route objects.**
FastAPI 0.141 keeps an included router as a lazy `_IncludedRouter` with no public `routes`, so
walking `app.routes` for a `dependant` finds nothing and would have made the assertion vacuous.
`tests/unit/test_bearer_auth.py` instead calls every operation the contract publishes under
`/api/v1` without a credential and requires a 401 — a stronger check, and one a future router
cannot slip past.

**Two notes from the review round, both inside the story's scope.**
`Problem.__init__` gained `headers` (a 401 must carry `WWW-Authenticate`, RFC 9110 §15.5.2) and
lost `type` as a keyword, which would have pushed it past ruff `PLR0913`; `type` is an attribute
initialised to `about:blank`, which is what every problem this system raises means today.
The declared 401 lists its schema under `application/problem+json` *and* under
`application/json`: `model` is what registers `ProblemDetail` in `components.schemas`, and
FastAPI writes a model-derived schema under the route's own response media type with no way to
override it per response. Both entries reference the same schema, so 1.3 generates the same type
either way.

## Design Notes

**Why migrations run in `main()`, not in a lifespan.** The spine puts `alembic upgrade head` at container start "before `DBOS.launch()`". Running it in `main()` before `uvicorn.run` gives exactly one upgrade per process and one `migrations applied` line, and keeps `create_app` free of I/O — which is what lets the existing unit tests build the app over `httpx.ASGITransport` with no database. The ordering is asserted by monkeypatching both calls and recording the order.

**Why the bearer compares bytes.** `hmac.compare_digest` raises `TypeError` on non-ASCII `str`, which Schemathesis would surface as a 5xx. Encode both sides to UTF-8 first: still constant-time, and a junk header is a 401 like any other.

```python
presented = credentials.credentials if credentials else ""
expected = settings.orchestrator_token.get_secret_value()
if not hmac.compare_digest(presented.encode(), expected.encode()):
    raise Problem(status=401, title="unauthorized")
```

**Schemathesis check selection.** The acceptance criterion is "reports no 5xx", so the suite runs `not_a_server_error` explicitly rather than the v4 default check set, whose schema- and data-conformance checks would fail on a 401 the contract does not yet enumerate and would make an unattended gate flaky. Later stories that add response models can widen it.

## Verification

**Commands:**
- `make lint` -- expected: exit 0; `env contract: 25 settings fields and 31 .env.example variables agree`.
- `make test` -- expected: exit 0, more than 144 tests, no database or network used.
- `export PATH="$HOME/.docker/bin:$PATH" && docker compose up -d postgres` -- expected: the service reaches healthy.
- `uv run --locked --directory backend-api python -m orchestrator.main` -- expected: a JSON `migrations applied` line carrying the revision, then uvicorn binds.
- `docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'select * from alembic_version'` -- expected: one row, the baseline revision.
- `BACKEND_API_URL=http://localhost:8000 make e2e-api` -- expected: exit 0, both e2e modules executed.
- Mutate the `e2e-api` recipe (drop `--locked`), run `make test` -- expected: `test_makefile_e2e_api.py` fails; restore the recipe.
- `git status --porcelain` and `git diff --stat` -- expected: no `D` or `R` entries; `GUIDELINES.md` absent.
- `git grep -nE '(ghp_|sk-)[A-Za-z0-9]' -- ':!*.env.example'` -- expected: no hits.
