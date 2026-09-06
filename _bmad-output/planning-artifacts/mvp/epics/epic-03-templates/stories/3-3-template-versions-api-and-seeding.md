---
title: 'Template versions API and seeding'
type: 'feature'
created: '2026-09-05'
status: 'done'
baseline_revision: 'd47e58a6498213b5629cb3b76d5c4b6ab5b6789a'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-03-templates/briefs/3-3-template-versions-api-and-seeding.md'
warnings: ['oversized']
deferred:
  - summary: >-
      A concurrent double-save (two `POST /templates/{name}/versions` calls for the same
      name, or two instances seeding at once) can hit the `(name, version)` unique index
      and surface as an unhandled 500 instead of a clean `Conflict`.
    evidence: |-
      Neither `save_version` nor `seed_shipped` catches `sqlalchemy.exc.IntegrityError`;
      `api/errors.py`'s `DOMAIN_STATUS` has no entry for it. This is the same class of gap
      `domain/entities/project.py`'s own docstring names and defers: "translating it
      belongs with the story that makes this API concurrent" — not unique to Templates.
    location: >-
      backend-api/src/orchestrator/application/use_cases/templates.py,
      backend-api/src/orchestrator/infrastructure/db/repositories/templates.py
    severity: medium
  - summary: >-
      Three `assert`s in `use_cases/templates.py` narrow a type after an invariant
      `validate()` itself guarantees; converting them to an explicit `if/raise` would need
      a `# pragma: no cover` this repository's `application/` package forbids outright,
      since the guarded branch is unreachable in every real call path.
    evidence: |-
      `save_version`'s `assert parsed is not None`, `validate_latest`'s `assert stored is
      not None`, and `_seed_one_round`'s `assert outcome.template is not None` all follow
      a check that already proves the condition; empirically, `make test` reaches 100%
      coverage with the `assert` form and would not with an explicit raise instead.
    location: >-
      backend-api/src/orchestrator/application/use_cases/templates.py:139,149,193
    severity: low
  - summary: >-
      `POST /templates/{name}/validate` now caps posted YAML at 200,000 characters, which
      only partially closes the loader-hardening gap 3.1 deferred here: `yaml.SafeLoader`
      alias/anchor expansion can still blow up memory from a short input.
    evidence: |-
      3.1's own deferred note: "The loader has no input-size, alias-expansion or
      duplicate-key guard on operator YAML... Story 3.3 exposes POST
      /templates/{name}/validate, which is where the guard belongs." A text-length cap
      (`api/schemas/templates.py::MAX_TEMPLATE_YAML_LENGTH`) stops an over-long payload but
      not a small one that expands in `lines.py`'s loader.
    location: >-
      backend-api/src/orchestrator/application/templates/lines.py
    severity: medium
  - summary: >-
      If a future story tightens `validate()`'s rules, a Template Version saved under the
      old rules could start failing re-validation, and `get_version` would then silently
      answer `inputs: []` instead of surfacing that the stored version no longer validates.
    evidence: |-
      `get_version` re-runs `validate(stored.yaml, ...)` for `inputs` and defaults to `()`
      whenever `result.template is None`, with no signal in the response that this
      happened. Not reachable today (nothing changes the validator's rules), so it is
      speculative rather than an active bug.
    location: >-
      backend-api/src/orchestrator/application/use_cases/templates.py:117-125
    severity: low
---

<intent-contract>

## Intent

**Problem:** `application/templates/validate.py` (3.1) and the four shipped YAML files
(3.2) exist, but nothing stores a Template, versions it, or seeds the shipped files at
start-up — the versions API and CAP-3 have no implementation yet.

**Approach:** Tables `template` + `template_version` and their migration; extend
`TemplateVersionRepository` (port, fake, and a new SQLAlchemy adapter) with
`add_version`, `list`, `list_versions`, `callers_of`; `use_cases/templates.py`
(`list_templates`, `list_versions`, `get_version`, `validate_text`, `validate_latest`,
`save_version`, `seed_shipped`); a router at `/api/v1/templates`; and
`seed_shipped_templates` wired into `main.py`'s start-up step, reading `TEMPLATES_DIR`.

## Boundaries & Constraints

**Always:** `calls` is derived from the validator's own parsed tree, never re-parsed by
hand. A saved version's `name`/`version` must match the path and the next number
(`max(existing)+1`); a validation failure returns the validator's own errors, never a
generic message. Seeding tolerates any file order (retry-until-no-progress) and is
idempotent by hash. Every published path carries a `GET` (AD-4 test convention). An
`int` path/body value that could overflow a Postgres column must be rejected before it
reaches the database.

**Block If:** none identified — the brief and spine fully determine behavior.

**Never:** No endpoint updates or deletes a `template_version` (AD-15). No second YAML
parser. Graph (3.4) and UI (3.5/3.6) are out of scope. `pinned_by` is hardcoded `0`
this story.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh DB, first start | `TEMPLATES_DIR` has the 4 shipped files | `GET /templates` lists all 4, `versions: [1]` | none |
| Second start, files unchanged | same DB, same files | nothing new inserted | none |
| Shipped file edited to a new hash | restart | inserted as next version; old version's YAML unchanged | none |
| Callee listed after caller in seed order | e.g. `story` sorts after a caller of it | both seeded correctly via retry rounds | none |
| `POST /versions`, YAML `version` wrong | next number is `n`, YAML says otherwise | — | 422, `version must be {n}` |
| `POST /versions`, YAML `name` wrong | path name != YAML name | — | 422, `name must be {name}` |
| `POST /versions`, invalid YAML | validator reports errors | — | 422 with `errors[]`, no row written |
| `POST /validate`, invalid YAML | same validator | 200 with `errors[]` (data, not refusal) | none |
| `GET /templates/{name}/{version}`, huge int | e.g. `99999999999` | — | 422 (never reaches the DB as an out-of-range `integer`) |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/templates/validate.py` — the one parser; read before planning, never duplicated.
- `backend-api/src/orchestrator/domain/entities/template.py`, `domain/ports/templates.py`, `tests/unit/fakes/templates.py` — extended in place per 3.1/3.2 carry-forward (not replaced).
- `backend-api/src/orchestrator/infrastructure/db/models/{project,repository}.py`, `db/repositories/projects.py` — the row/adapter style to copy.
- `backend-api/alembic/versions/0003_repository.py` — the migration style to copy.
- `backend-api/src/orchestrator/api/routers/{repositories,clone_check}.py` — router/response-shape and "every path needs a GET" precedent.
- `backend-api/src/orchestrator/main.py` — `migrating_lifespan`/`run_migrations`; `tests/unit/test_migrations.py` is frozen and proves "migrate before bind" by replacing `main.run_migrations` wholesale, so seeding had to share that one name rather than run as a second, unmocked step.
- `backend-api/Dockerfile`, `.dockerignore` — did not COPY the root `templates/` directory into the backend-api image; discovered via `make e2e` (container answered `GET /templates` with an empty list because `TEMPLATES_DIR` had nothing in it).

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/domain/entities/template.py` -- add `id`/`created_at` (default `None`) to `TemplateVersion`, add `TemplateSummary` -- read model for `GET /templates`, keeps 3.1 fixtures constructing without either field valid.
- `backend-api/src/orchestrator/domain/ports/templates.py`, `tests/unit/fakes/templates.py` -- add `add_version`/`list`/`list_versions`/`callers_of` -- the write surface 3.3 owns; `list` declared last in the Protocol to avoid a `list[...]` name-shadow mypy error.
- `backend-api/alembic/versions/0004_template.py`, `infrastructure/db/models/template.py`, `infrastructure/db/repositories/templates.py` -- the two tables and the adapter -- storage.
- `backend-api/src/orchestrator/application/use_cases/templates.py` -- the six use cases plus `seed_shipped`'s retry-until-no-progress loop and `_calls_of` -- the rules.
- `backend-api/src/orchestrator/infrastructure/templates_loader.py` -- reads `TEMPLATES_DIR` off disk (I/O stays out of `application/`).
- `backend-api/src/orchestrator/api/{routers,schemas}/templates.py`, `api/providers.py` -- the HTTP surface; `MAX_VERSION` bounds the path param against Postgres `integer` overflow.
- `backend-api/src/orchestrator/main.py` -- `run_migrations` now wraps the alembic step with `seed_shipped_templates`, sharing the one name the frozen migration test replaces.
- `backend-api/Dockerfile`, `.dockerignore` -- `COPY templates /app/templates`; `templates` removed from the exclusion list.
- Unit tests for every module above (fakes-driven, 100% branch on `domain`/`application`) plus `backend-api/tests/e2e/test_templates.py` -- the I/O matrix rows that only a real Postgres and a real container start-up settle.

**Acceptance Criteria:**
- Given the four shipped files and an empty database, when the app starts, then `GET /templates` lists all four at `versions: [1]`, and a second start inserts nothing (`tests/e2e/test_templates.py`).
- Given `GET /templates/epic/1`, when read, then `calls == [{story,1}]`, `called_by` includes `{initiative,1}`, `pinned_by == 0`, `inputs` has 8 entries.
- Given a name/version mismatch or invalid YAML posted to `/versions`, then 422 with the reason or the validator's own `errors[]`, and no row is written.

## Spec Change Log

## Review Triage Log

### 2026-09-05 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 3, low 3)
- defer: 4: (high 0, medium 2, low 2)
- reject: 5: (high 0, medium 0, low 5)
- addressed_findings:
  - `[medium]` `[patch]` `seed_shipped` reported only `pending[0]`'s errors when a whole
    round made no progress, hiding any other simultaneously-broken file. `ShippedTemplateInvalid`
    now carries every still-failing `(name, errors)` pair from that round.
  - `[medium]` `[patch]` `seed_shipped_templates` built its own SQLAlchemy engine and never
    disposed it. It now disposes the engine in a `finally`, so a raised `ShippedTemplateInvalid`
    still releases the pool before the process exits on that failure.
  - `[medium]` `[patch]` No size cap existed on posted YAML — the loader-hardening gap 3.1
    explicitly deferred to this story's `/validate` route. `ValidateIn.yaml` /
    `SaveVersionIn.yaml` now cap at 200,000 characters (`MAX_TEMPLATE_YAML_LENGTH`); the
    deeper alias-expansion loader guard stays deferred (see `deferred`).
  - `[medium]` `[patch]` A misconfigured or empty `TEMPLATES_DIR` produced a silently
    successful start-up with zero Templates seeded. `seed_shipped_templates` now logs a
    warning naming the directory when no `*.yaml` file is found.
  - `[low]` `[patch]` The start-up seed log line was an f-string with no structured fields.
    It now carries `name=`/`version=` alongside the same literal message the brief names.
  - `[low]` `[patch]` `TemplateVersionOut.hash` and `.pinned_by` had no `description` in the
    generated schema. Both now document what they are (a sha256 hex digest; a Epic-4 stub
    always `0` in this release).
  - reject: no guard against posting a new version under a shipped name (`epic`, `story`,
    ...) — the brief's own AC explicitly exercises exactly this on `epic`; always
    `next_cursor: null` with no real pagination — matches the existing, unconditional
    pattern already used by `list_repositories` and `list_versions`; `list()`/`callers_of()`
    full-table scans — already documented as the same accepted MVP trade-off
    `_refuse_duplicate_name` makes elsewhere; no `GET /templates/{name}/latest` convenience
    endpoint — not in the brief's enumerated endpoint list; `version` overflowing `int32`
    after 2.1 billion saves of one name — practically unreachable.

## Design Notes

**Why `run_migrations` in `main.py` wraps rather than sequences.** `test_migrations.py::test_main_migrates_before_the_socket_is_bound` replaces `main_module.run_migrations` wholesale and asserts `recorder.order == ["migrate", "bind"]` with no database reachable. A second, separately-named seeding call in the same lifespan would run for real and fail (AD-18: no unit test reaches a database). Combining migration + seed under the one name the frozen test already intercepts keeps both out of its reach; `infrastructure.db.migrations.run_migrations` stays the sole statement of *when the schema migrates*.

**Why `seed_shipped` retries rather than assumes an order.** `epic.yaml` calls `story@1`; `initiative.yaml` calls `epic@1`. A single pass over `glob()`'s alphabetical order would fail `epic` before `story` exists. Each round validates every not-yet-seeded file against whatever is already stored, inserts what passes, and only raises `ShippedTemplateInvalid` once a whole round makes no progress — genuinely bad YAML, not an ordering artifact.

**Why the `version` path param is bounded.** `template_version.version` is a Postgres `integer` (32-bit); schemathesis found that a larger value reaches `SQLAlchemyTemplateVersionRepository.get` and raises an unhandled overflow error there — a 500. `Path(gt=0, le=2_147_483_647)` refuses it as a 422 before the query runs.

## Verification

**Commands:**
- `make lint` -- ruff, mypy strict, import-linter, env-contract, test-pair and openapi-drift checks all green.
- `make test` -- 100% branch coverage on `domain/`+`application/`; whole unit suite green.
- `make coverage` -- diff-cover >= 90% on changed lines (reached 100%).
- `make openapi` -- contract regenerated, `web-client/src/api/schema.d.ts` regenerated, no drift.
- `make e2e` -- migration + seeding + the versions API against a real Postgres and a real container start-up.

## Auto Run Result

**Summary of implemented change.** Story 3.3 (SPEC CAP-3, FR-6): `template`/`template_version`
tables and their migration; the `TemplateVersionRepository` port, fake and a new SQLAlchemy
adapter extended with `add_version`/`list`/`list_versions`/`callers_of`; `use_cases/templates.py`
(`list_templates`, `list_versions`, `get_version`, `validate_text`, `validate_latest`,
`save_version`, `seed_shipped`); the `/api/v1/templates` router (six operations — the brief's
four plus two `GET` siblings the frozen "every path needs a GET" test requires); `main.py`
wiring the shipped-Templates seed into the one start-up step `test_migrations.py` already
governs; and the Dockerfile/`.dockerignore` fix that got the shipped `templates/` directory
into the image at all (found by `make e2e`, not by any unit test).

**Files changed** (new unless marked *modified*):
- `backend-api/src/orchestrator/domain/entities/template.py` *(modified)* -- `TemplateVersion.id`/`.created_at`, `TemplateSummary`.
- `backend-api/src/orchestrator/domain/ports/templates.py` *(modified)* -- `add_version`/`list`/`list_versions`/`callers_of`.
- `backend-api/tests/unit/fakes/templates.py` *(modified)* -- the same four methods on the one fake.
- `backend-api/alembic/versions/0004_template.py` -- the two tables.
- `backend-api/src/orchestrator/infrastructure/db/models/template.py` -- `TemplateRow`, `TemplateVersionRow`.
- `backend-api/src/orchestrator/infrastructure/db/repositories/templates.py` -- the SQLAlchemy adapter.
- `backend-api/src/orchestrator/infrastructure/db/__init__.py`, `db/models/__init__.py`, `db/repositories/__init__.py` *(modified)* -- export wiring.
- `backend-api/src/orchestrator/infrastructure/templates_loader.py` -- reads `TEMPLATES_DIR` off disk.
- `backend-api/src/orchestrator/application/use_cases/templates.py` -- the six use cases, `seed_shipped`, `_calls_of`.
- `backend-api/src/orchestrator/api/schemas/templates.py`, `api/routers/templates.py` -- the HTTP surface.
- `backend-api/src/orchestrator/api/providers.py` *(modified)* -- `template_ports`.
- `backend-api/src/orchestrator/main.py` *(modified)* -- `run_migrations`/`seed_shipped_templates`.
- `backend-api/Dockerfile`, `.dockerignore` *(modified)* -- ship `templates/` into the image.
- Twelve new unit test modules (fakes-driven) + `backend-api/tests/e2e/test_templates.py` (real Postgres, real container).
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` *(modified, generated)* -- `make openapi`.

**Review findings breakdown:** 6 patches applied (0 high, 3 medium, 3 low — see Review Triage
Log); 4 deferred (0 high, 2 medium, 2 low — see frontmatter `deferred`); 5 rejected, each with
a cited reason (brief's own AC, existing repo-wide precedent, or practical impossibility).

**Follow-up review recommendation:** `true`. This pass's patched findings alone score
`3×3 (medium) + 1×3 (low) = 12`, at or above the 5-point threshold regardless of severity mix;
no patched finding was `high`.

**Verification performed:**
- `make lint` -- green (ruff, ruff format, mypy --strict on `domain/`+`application/`, import-linter, env-contract, test-pair, openapi-drift).
- `make test` -- 2018 unit tests passed, 1 skipped; `domain/`+`application/` at 100% branch coverage.
- `make coverage` -- diff-cover against `origin/main`, 100% of 1217 changed lines covered (>= 90% required).
- `make openapi` -- contract and generated client regenerated; no drift on re-check.
- `make e2e` -- 67 tests + 18 subtests passed against a real Postgres and a real container start-up, including schemathesis fuzzing every published operation for 5xx (found and fixed the `version` int-overflow gap) and a dedicated `tests/e2e/test_templates.py` proving the four shipped Templates seed once, `epic@1`'s `calls`/`called_by`/`inputs` shape, and a save round-tripping byte for byte.

**Residual risks:**
- The AC "a shipped file edited on disk to a new hash is inserted as the next version on
  restart" is proven at the unit level (fake repository) only; no e2e test mutates a
  committed shipped YAML file and restarts the real container mid-suite (the intent-alignment
  reviewer flagged this as understandably hard to automate safely — rewriting a shipped
  fixture file and restarting compose from within a test run risks corrupting the working
  tree on a failure).
- The four items in frontmatter `deferred` (concurrent-write races, the `assert`/coverage-gate
  tension, the still-open alias-expansion loader guard, and stale `inputs` after a
  hypothetical future validator change) are pre-existing-pattern or speculative, not blocking.
