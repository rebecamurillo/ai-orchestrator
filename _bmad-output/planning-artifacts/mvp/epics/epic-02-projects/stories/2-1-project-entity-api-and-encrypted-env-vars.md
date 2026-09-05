---
title: 'Project entity, API, and encrypted environment variables'
type: 'feature'
created: '2026-09-04'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      Port conformance is asserted with isinstance against runtime_checkable Protocols, which
      checks only that attribute names exist.
    evidence: |-
      test_the_adapter_satisfies_the_port appears in test_fernet_crypto.py, test_clock_adapter.py,
      test_project_ports.py and test_project_repository_adapter.py, and the same idiom predates this
      story in test_clock_fake.py, test_uow_fake.py and test_db_adapters.py. A stub with the right
      method names and wrong signatures or return types passes every one of them.
    location: >-
      backend-api/tests/unit/
    severity: low
  - summary: >-
      Every e2e and Schemathesis run leaves Project rows behind for good, because the API has no
      DELETE, and the unpaginated list decrypts every variable of every Project.
    evidence: |-
      Deletion is a non-goal of the epic ("No deletion of Projects or Repositories in the MVP UI;
      API DELETE is out of scope"), and this story ships no cursor paging, so next_cursor is always
      null. tests/e2e/test_projects.py makes names unique per run so the suite stays green, but the
      dev database and the cost of GET /api/v1/projects both grow with every gate run.
    location: >-
      backend-api/src/orchestrator/api/routers/projects.py
    severity: low
baseline_revision: '8b72c17443a8d2ffdc457b6c84f9da2a60778212'
---

<intent-contract>

## Intent

**Problem:** The orchestrator has no Project: nothing holds the context every agent reads, the agent environment variables a Run exports, or the per-Project content-logging switch — and no secret the Operator types has anywhere to live except in clear.

**Approach:** Add the `project` table and its migration, the frozen domain entity with its `Crypto` and `ProjectRepository` ports, `application/use_cases/projects.py` (create, update, get, list, `decrypt_env_vars`), a Fernet adapter, and `/api/v1/projects` (`GET` list, `POST`, `GET {id}`, `PUT {id}`) whose reads mask every variable value.

## Boundaries & Constraints

**Always:**
- AD-2 layering: entity + ports in `domain/`, use cases in `application/` (no `fastapi`, `sqlalchemy`, `os`, `subprocess`), SQLAlchemy model + repository in `infrastructure/db/`, Fernet in `infrastructure/crypto/`, router in `api/routers/`, schemas in `api/schemas/`.
- AD-5: values are encrypted with `cryptography.fernet.Fernet(ORCHESTRATOR_SECRET_KEY)`; names stay in clear; no endpoint ever returns plaintext.
- AD-18: tests first; reuse `tests/unit/fakes/clock.py` and `tests/unit/fakes/db.py`; add `tests/unit/fakes/projects.py` and `tests/unit/fakes/crypto.py` as the only fakes for their ports. `domain/` + `application/` stay at 100% branch coverage (`make test` second line).
- AD-3: `make openapi` regenerates `contracts/openapi.json` and `web-client/src/api/schema.d.ts`; both are committed, neither is hand-edited.
- Every new `src/orchestrator/**` module is imported by some `tests/unit/` module (`scripts/check_test_pairs.py` runs in `make lint`).
- `create_app` must keep performing no I/O and must not dereference a `Settings` field: `tools/export_openapi.py` builds it from `Settings.model_construct()`.
- `main()` must stay callable with the `.env.example` placeholders — `tests/unit/test_logging.py` and `tests/unit/test_migrations.py` call it — so nothing it does may validate `ORCHESTRATOR_SECRET_KEY`.
- Ids UUIDv7 (`domain/ids.new_id`), timestamps from the `Clock` port, errors RFC 9457, lists `{items, next_cursor}`.

**Block If:**
- A frozen anchor (`SPEC.md`, `stories.yaml`, any `AGENTS.md`, any existing test file) would have to change for a gate to pass.
- The architecture spine and this spec disagree on a field, a route, or a port signature.

**Never:**
- No `repository` table, no clone check, no UI, no `DELETE`, no per-Project credential field (`GITHUB_TOKEN`/Gateway keys are instance settings, AD-5).
- Never derive, pad, or hash `ORCHESTRATOR_SECRET_KEY` into a Fernet key — it *is* the key.
- Never add a `repositories` relation or field to the project read model (2.2 does that).
- Never log, echo, or serialise a plaintext variable value.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Create with two env vars | `POST` `{name, env_vars:[{name:"API_URL",value:"https://x"},{name:"TOKEN_A",value:"abcdefgh"}]}` | 201; stored `env_vars_enc[].value_enc` are Fernet tokens (`gAAAAA…`, ≠ plaintext); response `env_vars:[{name,masked}]`, `masked` = `••••efgh` | No error expected |
| Value shorter than four | value `"ab"` | `masked` == `••••` exactly | No error expected |
| Reserved variable name | name `GITHUB_TOKEN`, `LITELLM_API_KEY`, `LITELLM_SPEND_KEY`, `LANGFUSE_*`, `ORCHESTRATOR_*` | 422 problem+json, `errors[]` entry whose `path` names `env_vars`, the index, and `name` | reason `instance setting, not a project variable` |
| Malformed variable name | `api_url`, `1ABC`, `A-B`, `""` | 422 problem+json naming the same path | reason names the `^[A-Z][A-Z0-9_]*$` rule |
| Duplicate variable name in one payload | two entries named `A` | 422 problem+json | reason `duplicate variable name` |
| Update keeps / replaces / deletes | stored `A`,`B`; `PUT env_vars:[{name:"A"},{name:"C",value:"x"}]` | `A` keeps its exact stored ciphertext, `B` gone, `C` added; `updated_at` > previous | No error expected |
| Update keeps an unknown name | stored `A`; `PUT env_vars:[{name:"Z"}]` | 422 problem+json | reason `no stored value to keep` |
| Duplicate project name | second `POST` with a stored name | 409 problem+json | `Conflict` from the use case |
| Rename to another project's name | `PUT` name equal to a different project's | 409 problem+json | `Conflict`; renaming to its own name is allowed |
| `log_prompt_content` omitted | `LOG_PROMPT_CONTENT_DEFAULT=false` / `=true` | stored `false` / `true` respectively | No error expected |
| Slug | name `"My Website 2!"` → `my-website-2`; a name with no slug characters → `project`; collision → `-2`, `-3`… ; slug never changes on `PUT` | ≤ 40 chars, `[a-z0-9-]`, no leading/trailing/repeated `-` | No error expected |
| Unknown id | `GET`/`PUT` `/projects/{uuid}` not stored | 404 problem+json | `NotFound` |
| Non-UUID id | `GET /projects/not-a-uuid` | 422 problem+json | FastAPI path validation |
| List | three projects | `{items, next_cursor:null}` sorted by `name`; every item masked | No error expected |
| Hostile text | name/context containing a NUL character or an unpaired surrogate | 422 problem+json, never a 5xx | rejected in the API schema before the database sees it |
| Unauthenticated | any `/api/v1/projects` call without the bearer | 401 problem+json with `WWW-Authenticate` | inherited router dependency |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/main.py` -- composition root; `create_app(settings, *, lifespan=None)` at L69. Adds `session_factory` and `crypto` keyword ports stored on `app.state`, and a second `include_router(projects.router, prefix=API_PREFIX, dependencies=[Depends(require_bearer)], responses={HTTP_UNAUTHORIZED: UNAUTHORIZED_RESPONSE})` — `tests/unit/test_bearer_auth.py::test_the_versioned_router_is_mounted_with_the_dependency` parses this call and requires exactly those keywords.
- `backend-api/src/orchestrator/api/deps.py` -- `get_settings(request)` reads `app.state.settings`; **read-only for this story** — `tests/unit/test_bearer_auth.py` ast-scans this module and fails on any `ast.Compare` mentioning `token`/`credentials`. Put the new providers in a new module instead.
- `backend-api/src/orchestrator/api/errors.py` -- `Problem`, `ProblemError`, `ProblemDetail`, `DOMAIN_STATUS` maps `NotFound→404`, `Conflict→409`, `Invalid→422`; `_handle_validation_error` renders pydantic `loc` as `errors[].path` joined with dots (`body.env_vars.0.name`). Reuse; do not extend.
- `backend-api/src/orchestrator/domain/errors.py` -- `NotFound`, `Conflict`, `Invalid`; `domain/ids.py` -- `new_id()` UUIDv7.
- `backend-api/src/orchestrator/domain/ports/{clock,unit_of_work}.py` -- the `Protocol` + `runtime_checkable` shape to copy for `crypto.py` and `repositories.py`.
- `backend-api/src/orchestrator/api/schemas/common.py` -- `Page[T]`, `UtcTimestamp`, `MoneyStr`; the place a shared "text Postgres can store" validator belongs.
- `backend-api/src/orchestrator/infrastructure/db/{base,engine,session,unit_of_work}.py` -- `Base` (naming convention, schema `public`), `create_engine_from`, `create_session_factory`, `SQLAlchemyUnitOfWork` (exposes `.session` once entered). `db/__init__.py` re-exports them and is the place to import the new model so `Base.metadata` sees the table.
- `backend-api/src/orchestrator/infrastructure/settings.py` -- `orchestrator_secret_key: SecretStr`, `log_prompt_content_default: bool` already exist; **no new setting is needed**.
- `backend-api/alembic/versions/0001_baseline.py` -- the revision file shape; `down_revision` of the new file is `0001_baseline`. `tests/unit/test_migration_chain.py` walks the chain from source and already accepts a second revision.
- `backend-api/tests/unit/conftest.py` -- the `env` fixture injects `.env.example` placeholders; `ORCHESTRATOR_SECRET_KEY=change-me-fernet-key` is **not** a valid Fernet key, so unit tests must build the adapter with `Fernet.generate_key()`.
- `backend-api/tests/unit/test_bearer_auth.py` -- frozen sweep: every published `/api/v1` operation must 401 unauthenticated, and `document["paths"][path]["get"]` must exist for every published path (so every new path needs a `GET`).
- `backend-api/tests/unit/test_source_limits.py` -- ≤400 lines/module, no `print`, no `datetime.now()` outside `infrastructure/`.
- `backend-api/tests/unit/test_db_adapters.py` -- `RecordingSessionFactory` pattern for driving SQLAlchemy code without a database; also asserts every declared table sits in schema `public`.
- `backend-api/tests/e2e/{conftest.py,test_smoke.py}` -- `authenticated` httpx fixture; `tests/e2e/test_schemathesis.py` runs `not_a_server_error` over every published operation.
- `backend-api/pyproject.toml` -- dependencies (no `cryptography` yet), ruff `PL` (max 5 arguments, 50 statements), mypy strict over `domain` + `application`, import-linter contracts.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- generated; `web-client/tests/unit/generated-types.test.ts` requires every contract path to appear in the schema file.
- `.env.example` L7 / L16 -- `ORCHESTRATOR_SECRET_KEY`, `LOG_PROMPT_CONTENT_DEFAULT`; unchanged.

## Tasks & Acceptance

**Execution:**

1. `backend-api/pyproject.toml` -- add `cryptography` (pinned, current release) to `[project].dependencies`; run `uv lock` -- Fernet is the only new third-party need.
2. `backend-api/tests/unit/fakes/crypto.py`, `backend-api/tests/unit/fakes/projects.py` -- new fakes: a reversible non-identity `FakeCrypto` (records calls, refuses to decrypt a token it never issued) and an in-memory `FakeProjectRepository` (`add`, `get`, `get_by_slug`, `list`, `update`) -- the only doubles for the two new ports (AD-18).
3. `backend-api/tests/unit/test_project_entity.py` -- failing tests for the entity, the name pattern, the reserved-name set, masking, and slug derivation -- TDD; drives task 4.
4. `backend-api/src/orchestrator/domain/entities/project.py` (+ `entities/__init__.py`) -- frozen pydantic `Project{id, slug, name, context_text, context_paths, env_vars_enc:[{name,value_enc}], log_prompt_content, created_at, updated_at}`, the masked read model `ProjectView`/`MaskedEnvVar`, `ENV_NAME_PATTERN`, the reserved-name rule, `mask(value)`, `slugify(name)` -- one place names the rules every layer restates.
5. `backend-api/src/orchestrator/domain/ports/crypto.py`, `.../ports/repositories.py` -- `Crypto{encrypt,decrypt}` and `ProjectRepository{add,get,get_by_slug,list,update}` as `runtime_checkable` Protocols -- ports before adapters.
6. `backend-api/tests/unit/test_project_ports.py` -- assert both fakes satisfy their Protocol and honour the in-memory contract -- pairs the two port modules with a test (`check_test_pairs`).
7. `backend-api/tests/unit/test_projects_use_cases.py` -- failing tests for every I/O-matrix row that is a use-case rule -- TDD; drives task 8 to 100 % branch coverage.
8. `backend-api/src/orchestrator/application/use_cases/projects.py` (+ `application/use_cases/__init__.py`) -- `ProjectPorts{uow, projects, crypto, clock}` and module functions `create_project`, `update_project`, `get_project`, `list_projects`, `decrypt_env_vars`; encryption, masking, slug collision, name conflict (`Conflict`), unknown id (`NotFound`), keep/replace/delete update semantics, unknown keep (`Invalid`) -- the business rules, on ports only.
9. `backend-api/tests/unit/test_fernet_crypto.py` -- round-trip, non-determinism of two encryptions of one value, tamper rejection, invalid-key message -- TDD; drives task 10.
10. `backend-api/src/orchestrator/infrastructure/crypto/fernet.py` (+ `crypto/__init__.py`) -- `FernetCrypto(key: str)` implementing `Crypto`; an unusable key raises with a message naming `ORCHESTRATOR_SECRET_KEY` and the generator command -- AD-5.
11. `backend-api/tests/unit/test_clock_adapter.py` -- the wall-clock adapter returns tz-aware UTC -- pairs task 12.
12. `backend-api/src/orchestrator/infrastructure/clock.py` -- `SystemClock` implementing `Clock` -- the only reader of `datetime.now` (`test_source_limits.py` forbids it elsewhere).
13. `backend-api/tests/unit/test_project_repository_adapter.py` -- table name, columns, JSONB, unique indexes on `name` and `slug`, schema `public`, and the entity-to-row mapping driven through a recording session -- TDD; drives task 14.
14. `backend-api/src/orchestrator/infrastructure/db/models/project.py`, `.../db/repositories/projects.py`, and the `__init__.py` of both packages; import the model from `infrastructure/db/__init__.py` -- `ProjectRow` + `SQLAlchemyProjectRepository`, so `Base.metadata` and Alembic see one table.
15. `backend-api/alembic/versions/0002_project.py` -- `down_revision = "0001_baseline"`; create `project` with `uuid` pk, `text` columns, `jsonb` `context_paths`/`env_vars_enc`, `timestamptz` `created_at`/`updated_at`, unique indexes on `name` and `slug`; `downgrade()` drops the table -- every model change ships a revision.
16. `backend-api/tests/unit/test_project_schemas.py` -- payload validation rows of the I/O matrix, including the hostile-text rejection -- TDD; drives tasks 17 and 18.
17. `backend-api/src/orchestrator/api/schemas/common.py` -- add a `StorableText` annotated `str` that refuses NUL characters and unencodable surrogates -- keeps generated input out of the database as a 422, not a 500 (Schemathesis gate).
18. `backend-api/src/orchestrator/api/schemas/projects.py` -- `ProjectCreate` (value required), `ProjectUpdate` (value optional), `EnvVarIn`, `MaskedEnvVarOut`, `ProjectRead` (`UtcTimestamp`), reusing `Page[ProjectRead]`; env-var name/duplicate rules validated here so they surface as `errors[]` -- the HTTP shape, and nothing else.
19. `backend-api/tests/unit/test_api_providers.py`, `backend-api/tests/unit/test_projects_router.py` -- provider wiring (a missing port answers 500 as a problem document, never an `assert`) and the router over httpx ASGI with fakes injected through `dependency_overrides` -- TDD; drives tasks 20 to 22.
20. `backend-api/src/orchestrator/api/providers.py` -- request-scoped `project_ports` dependency: open a `SQLAlchemyUnitOfWork`, build the repository on its session, read the crypto factory and the settings off `app.state` -- a new module so `deps.py`'s ast guards stay untouched.
21. `backend-api/src/orchestrator/api/routers/projects.py` -- four thin operations under `/projects`, each with a summary and a response model; `POST` returns 201 -- routers parse, call one use case, and map.
22. `backend-api/src/orchestrator/main.py` -- build the engine, the session factory and a deferred crypto factory in `main()`, accept them as `create_app` keywords, store them on `app.state`, and mount the projects router -- `main.py` stays the only place an adapter is named, and `create_app` still dereferences no setting.
23. `backend-api/tests/e2e/test_projects.py` -- create → get → list → update round-trip against the stack, asserting the masked read, the 409, and that no response body contains a plaintext value -- the claim only a database settles.
24. `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- regenerate with `make openapi` and commit -- AD-3; `make lint` fails on drift.

**Acceptance Criteria:**
- Given a valid create payload with two env vars, when `POST /api/v1/projects` is called with the bearer, then it returns 201, the persisted `env_vars_enc` values are Fernet tokens that differ from the plaintext, and each response `masked` ends with that value's last four characters.
- Given a stored Project with `A` and `B`, when `PUT` sends `[{name:"A"},{name:"C",value:"x"}]`, then `A`'s ciphertext is byte-identical to what was stored, `B` is gone, `C` decrypts to `x`, `slug` is unchanged, and `updated_at` is later than before.
- Given `LOG_PROMPT_CONTENT_DEFAULT` is `false` and then `true`, when a Project is created without `log_prompt_content`, then the stored value is `false` and then `true`.
- Given the whole suite, when `make lint && make test` run, then `import-linter`, `check_test_pairs`, the contract-drift check and the 100 % branch-coverage report over `domain/` + `application/` all pass.
- Given the running stack, when `make e2e-api` runs, then the create → get → list → update round-trip passes and Schemathesis reports no 5xx on any `/api/v1/projects` operation.

## Spec Change Log

## Review Triage Log

### 2026-09-04 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 11: (high 0, medium 5, low 6)
- defer: 2: (high 0, medium 0, low 2)
- reject: 14: (high 0, medium 2, low 12)
- addressed_findings:
  - `[medium]` `[patch]` `name` carried only `min_length=1` although the brief states 1–80 chars — added `max_length=80` and the tests for 80 and 81 characters, which also keeps a generated name out of PostgreSQL's btree index-entry limit.
  - `[medium]` `[patch]` a `PUT` omitting `log_prompt_content` reset the stored switch to `LOG_PROMPT_CONTENT_DEFAULT`; the brief scopes that default to creation. `ProjectDraft.log_prompt_content` is now `bool | None`, `create_project` resolves it against the instance default and `update_project` against the stored value.
  - `[medium]` `[patch]` `context_paths` were unconstrained free text although the brief calls them repo-relative — absolute paths, `..` segments and empty entries are now refused with the offending index in `errors[].path`.
  - `[medium]` `[patch]` `test_no_route_reaches_decrypt_env_vars` collected only `ImportFrom` aliases, so `use_cases.decrypt_env_vars(...)` — the call form the router's import style would actually use — passed it. The guard now collects attribute and name nodes too, and two tests prove it fires on both leak shapes.
  - `[medium]` `[patch]` nothing asserted that the migration created the two unique indexes it calls the guarantee; deleting both `create_index` calls left every test green. Added e2e assertions that read `pg_index` on the migrated database for `ix_project_name` and `ix_project_slug`, existence and uniqueness separately.
  - `[low]` `[patch]` only 422 was declared in `responses`, so the generated client had no type for the 404 and 409 the brief specifies — both are now declared per operation and the contract regenerated.
  - `[low]` `[patch]` two tests asserted the opposite of their names and could not fail for the reason they gave (`test_the_row_holds_no_plaintext_value`, `test_the_stored_entity_never_serialises_a_plaintext_value`); both were rewritten around a plaintext the assertion can actually find.
  - `[low]` `[patch]` timestamps were compared as strings although `_iso_z` drops a zero fraction, so `…12:00:00Z` sorts after `…12:00:00.5Z`; both comparisons now parse first, and the e2e helpers assert the create status before reading `["id"]`.
  - `[low]` `[patch]` `main.py` and `api/providers.py` claimed a bad `ORCHESTRATOR_SECRET_KEY` fails "on the first project write" — the factory is called per request, so reads fail identically and the body is a bare `internal server error`. The docstrings now say what happens, and the model and migration no longer call the unique index a guarantee that produces a 409.
  - `[low]` `[patch]` `cryptography` was absent from both AD-2 forbidden contracts although two docstrings claimed `domain/` and `application/` import no crypto library — added, so the claim is a gate.
  - `[low]` `[patch]` router hygiene: `HTTP_UNPROCESSABLE_CONTENT` is imported from `api/errors.py` instead of redefined, `get_project` has a description, and the providers test asserts its `missing` parameter and builds its session factory inside the test rather than at collection time.

## Design Notes

**Why a deferred crypto factory.** `tests/unit/test_logging.py` and `tests/unit/test_migrations.py` call `main()` with the `.env.example` placeholders, where `ORCHESTRATOR_SECRET_KEY=change-me-fernet-key` is not a Fernet key. `main()` therefore passes `create_app` a *callable* that builds `FernetCrypto` on first use; the adapter still validates its key strictly, and a misconfigured instance fails on the first project write with a message naming the variable — not at import, and not silently.

```python
# main.py
def crypto_factory(settings: Settings) -> Callable[[], Crypto]:
    @cache
    def build() -> Crypto:
        return FernetCrypto(settings.orchestrator_secret_key.get_secret_value())
    return build
```

**Where each rule lives.** The regex, the reserved names and `mask()` are constants and pure functions in `domain/entities/project.py`; `api/schemas/projects.py` calls them from a pydantic validator so a violation becomes a `RequestValidationError` and therefore an `errors[]` entry with a `path` — the shape 2.5 renders beside the field. The reserved-name refusal keeps the exact reason string `instance setting, not a project variable`.

**Update semantics.** `PUT` replaces the whole variable set: an entry with `value` is encrypted afresh, an entry without `value` copies the stored `value_enc` verbatim (so a keep never re-encrypts and never decrypts), and any stored name absent from the payload is dropped. An entry without `value` naming a variable that is not stored has nothing to keep and is refused as `Invalid` — the brief does not name this case, and both alternatives (storing an empty value, or silently dropping it) would lose the Operator's intent without saying so.

**`decrypt_env_vars`** returns `{name: plaintext}` for the Run machinery of Epic 4 and is reachable from no route; the router never imports it.

## Verification

**Commands:**
- `cd backend-api && uv run --locked pytest tests/unit -q` -- expected: green, including every new module
- `make lint` -- expected: ruff, mypy strict, import-linter, env contract, test pairs, contract drift, eslint/tsc all pass
- `make test` -- expected: green, and `coverage report --include='src/orchestrator/domain/*,src/orchestrator/application/*' --fail-under=100` passes
- `make openapi` -- expected: `contracts/openapi.json` and `web-client/src/api/schema.d.ts` change only by the four new operations and their schemas
- `make up` then `BACKEND_API_URL=http://127.0.0.1:8000 ORCHESTRATOR_TOKEN=... make e2e-api` -- expected: the projects round-trip passes and Schemathesis reports no 5xx. The local `.env` still carries the `change-me-fernet-key` placeholder; a real key (`python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`) must be in `.env` before the stack can encrypt anything.

## Auto Run Result

Status: done

**Implemented change.** `/api/v1/projects` with four operations, the `project` table behind
them, and Fernet encryption of agent environment variables that no read ever returns in
clear. Rules sit where AD-2 puts them: the name pattern, the reserved-name set, `mask()`
and `slugify()` in `domain/entities/project.py`; encryption, the keep/replace/delete `PUT`
semantics, slug collision numbering and the name conflict in
`application/use_cases/projects.py`; the payload shape and its `errors[]` in
`api/schemas/projects.py`; four thin operations in `api/routers/projects.py`.

**Files changed**

- `backend-api/src/orchestrator/domain/entities/project.py` — `Project`, `ProjectView`, `EncryptedEnvVar`, `MaskedEnvVar`, and the four rules every layer restates.
- `backend-api/src/orchestrator/domain/ports/crypto.py`, `.../ports/repositories.py` — the `Crypto` and `ProjectRepository` Protocols.
- `backend-api/src/orchestrator/application/use_cases/projects.py` — `ProjectPorts`, `ProjectDraft`, and create/update/get/list/`decrypt_env_vars`.
- `backend-api/src/orchestrator/infrastructure/crypto/fernet.py` — `FernetCrypto`, refusing an unusable key by name.
- `backend-api/src/orchestrator/infrastructure/clock.py` — `SystemClock`, the only reader of the wall clock.
- `backend-api/src/orchestrator/infrastructure/db/models/project.py`, `.../db/repositories/projects.py`, `.../db/__init__.py` — the row, the adapter, and the import that puts the table in `Base.metadata`.
- `backend-api/alembic/versions/0002_project.py` — the `project` table, JSONB columns, two unique indexes.
- `backend-api/src/orchestrator/api/{providers.py,routers/projects.py,schemas/projects.py,schemas/common.py}` — request-scoped ports, the four operations, the payloads, and the shared `StorableText`.
- `backend-api/src/orchestrator/main.py` — engine, session factory and a deferred crypto factory on `app.state`; the projects router mounted behind the one bearer dependency.
- `backend-api/pyproject.toml`, `backend-api/uv.lock` — `cryptography==50.0.1`, and `cryptography` added to both AD-2 forbidden contracts.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` — regenerated (two new paths, seven new schemas; nothing removed).
- Tests: `tests/unit/fakes/{crypto,projects}.py` and nine new unit modules, plus `tests/e2e/test_projects.py`. No pre-existing test file, `AGENTS.md`, `SPEC.md` or `stories.yaml` was modified.

**Review findings.** 11 patches applied (5 medium, 6 low), 2 items deferred (both low), 14
rejected. Follow-up review recommended: `true` — 0 high, 5 medium, 6 low patched, score
`3 × 5 + 1 × 6 = 21`, which is at or above the threshold of 5.

**Verification.**

- `make lint` — ruff, mypy strict, `lint-imports` (3 contracts kept), env contract, test pairs (27 backend modules paired), contract-drift check, and the whole web-client lane: pass.
- `make test` — 1023 backend unit tests passed, 1 skipped; `domain/` + `application/` at 100 % branch coverage with `--fail-under=100`; 488 vitest tests passed.
- `make openapi` — regenerated and committed; re-running the drift check reports the generated types match.
- `make e2e-api` — 28 passed, 6 Schemathesis subtests, no 5xx on any of the six published operations. Run with `DATABASE_URL` pointed at `127.0.0.1:5432`: `tests/e2e/test_migrations.py` reads the database directly, and the compose hostname `postgres` does not resolve from the host.
- `make coverage` — changed lines at 100 %.
- Every row of the I/O & Edge-Case Matrix is covered by a test that ran and passed.

**Residual risks.**

- The local `.env` carried the `change-me-fernet-key` placeholder, which cannot encrypt; a real Fernet key was generated into it (`.env` is git-ignored, so nothing about it is committed). Any other machine running this stack must do the same before the Projects API works, and an unusable key surfaces as a bare 500 with the variable named only in the log.
- A lost race between two concurrent creates is refused by the unique index as a 500, not as the 409 the sequential check produces. One operator, so it is not reachable in practice, and nothing translates `IntegrityError` yet.
- A stored value that the configured key cannot decrypt — a rotated `ORCHESTRATOR_SECRET_KEY`, a restored dump — makes `GET /api/v1/projects` answer 500 for the whole list rather than degrading one Project. Key rotation is not in this story.
- The two deferred items above.
