# Test Automation Summary — orchestrator-run-metrics / epic-1-run-facts

Generated: 2026-11-13 (dispatch mode with an empty story id, so it covers the whole epic)
Spec: `initiatives/orchestrator-run-metrics/epic-1-run-facts/SPEC.md` (path relative to the hub)
Stories: 1–6 (commits `4f1b36e`..`9f838a3`)
Previous summary (orchestrator-instance-guide epic 3): in git history at `fb299d7`.

Framework: the project's own, pytest + httpx in `backend-api/tests/e2e` (`make e2e-api`). The
epic changed no UI, so no Playwright test was added.

## Generated Tests

### API (e2e) tests — `make e2e-api` gate

- [x] `backend-api/tests/e2e/test_metrics_catalogue.py` (8 tests, story 1 / CAP-1). The unit
  suite covers the validator and the router with a fake catalogue. This module covers what
  only the built image can show: the YAML ships as package data, start-up validated it, and the
  route is mounted behind the bearer.
  - Without a bearer: 401 `application/problem+json`.
  - With one: `{items}` is non-empty. Each entry has exactly the 13 catalogue fields. Ids match
    `group.name` and are unique. `level` ∈ {H, A}, `scopes` is non-empty and drawn from the 13
    declared scopes, `additive` ∈ {true, false, `within_scope_type`}. Every `component_of`
    names a catalogued id. The three relations the story declares (`tokens.thinking` →
    `tokens.output`, `tokens.cache_write_5m|1h` → `tokens.cache_write`) are served. Every
    entry has at least one method, numbered ascending from ≥ 1, each with a description and a
    `parameters` object.
  - Structural only: no id list, count or label from the shipped files is pinned.
- [x] `backend-api/tests/e2e/test_run_facts_schema.py` (5 tests, stories 2 and 5 / CAP-2,
  CAP-5). The unit migration tests read the revisions; this module checks what only a migrated
  Postgres can show:
  - The seven fact tables exist in schema `public`.
  - Money (`gateway_read.usd`, `usage_fact.usd` and the three `run.*_spend_usd`) is `numeric`.
  - The five Run figure columns are `NOT NULL` with a `0` / `false` default.
  - A `usage_fact` with neither parent, or with both, is refused with SQLSTATE 23514 by the
    one-parent check. Postgres evaluates CHECK before FK triggers, so the "both" case reaches
    the check even though its parent ids don't exist.
  - Every write runs in a transaction that is rolled back and is refused anyway, so the shared
    stack is left unchanged.

## Coverage

- API endpoints added by the epic: 1/1 (`GET /api/v1/metrics/catalogue`), happy path + 401.
- Database constraints the epic's ACs name: one-parent check (both cases), money as numeric,
  Run figures NOT NULL with defaults. The `fact_set` unique constraint and the story 6 data
  revision are not covered at e2e. Exercising either would need real attempts written into the
  shared stack. Both are covered by unit tests (`test_fact_repository_adapter.py`,
  `test_migrated_attempt_facts_migration.py`).
- Extractors (stories 3–4), the facts sweep and the budget-gate figure (story 5) are pure or
  log-reading logic with no new endpoint. They are covered by the stories' unit tests, and an
  e2e module would add nothing a stack alone can show.
- UI: none in this epic.

## Verification

- `ruff check` and `ruff format --check`: clean on both files. `pytest --collect-only`:
  13 tests collected.
- The 8 catalogue scenarios were run against the in-process app (`create_app(Settings())`
  with the `.env.example` contract, FastAPI `TestClient`): 8/8 pass.
- Unit meta-tests over test files (`-k "source_limit or e2e or pair or marker"`): 1466 passed.
- **Not run against a stack.** The epic's standing rule says never to start, stop or call a
  running instance, and `make e2e` builds one. Both modules run on the next `make e2e`, which
  is the gate. The schema module has no in-process stand-in because it needs Postgres.
- `mypy` on the new files reports only the `Settings()` call-arg note that the existing
  `tests/e2e/test_migrations.py` also has. `make lint` scopes mypy to `domain/` and
  `application/`.

## Next Steps

- Run `make e2e` (disposable `aio-e2e` stack) to execute both modules against Postgres.
- When epic 2 adds result versions and its endpoints, extend the e2e suite from there.
