# Test Automation Summary — orchestrator-run-metrics / epic-2-run-versions

Generated: 2026-11-13. Dispatch mode with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-run-metrics/epic-2-run-versions/SPEC.md` (path relative to the hub)
Stories: 1–6 (commits `167fdb9`..`4211d4b`)
Previous summary (epic-1-run-facts): in git history at `270bdfe`.

Framework: the project's own, pytest + httpx in `backend-api/tests/e2e` (`make e2e-api`). The
epic changed no UI, so no Playwright test was added.

## Generated Tests

### API (e2e) tests — `make e2e-api` gate

- [x] `backend-api/tests/e2e/test_run_metrics_versions.py` (23 tests). It reuses the suite's
  helpers (`test_run_creation`, `test_signals`, `test_clone_check.Fixtures`). Templates are
  fresh `e2e-metrics-<uuid>` fixtures owned by the test, so no shipped template content is
  pinned (hard rule 6). Every Run it creates ends terminal inside its own test.
  - **Bearer and 404** (CAP-3, CAP-5, CAP-6): each of the six new operations is checked twice.
    Without the bearer it returns 401 problem+json. With the bearer and an unknown Run it
    returns 404 problem+json. The operations are `GET …/metrics`, `GET …/metrics/versions`,
    `POST …/metrics/calculate`, `GET …/metrics/calculations/{n}`,
    `GET …/metrics/gateway-reads` and `PATCH /runs/{id}`.
  - **Migrations** (stories 1, 2, 3, 5):
    - `run_repository`, `run_commit`, `metric_calculation`, `result_version` and
      `metric_value` exist in `public`.
    - `step_run.role`, `run.label` and `run.label_set_by_operator` are NOT NULL with defaults.
    - A `metric_value` that has both a figure and `missing = 'not recorded'` is refused with
      SQLSTATE 23514. The write runs in a transaction that is rolled back.
  - **Roles** (CAP-1):
    - Saving a template with `role: build` returns 422, and `errors[]` holds
      `unknown role build` with a line.
    - With `role: implement`, the planned `step_run.role` is `implement`.
  - **Label** (CAP-3, plus the CAP-2 `.` row):
    - The default is `{project} {template} {YYYY-MM-DD HH:MM}` from the Run's `created_at`.
    - A PATCH on a `done` Run trims and sets the label, with operator `true`, and leaves the
      status `done`.
    - A label of 121 characters, or of whitespace only, returns 422 problem+json.
    - `null` restores the default, with operator `false`.
    - A label given at creation is stored with operator `true`.
    - Exactly one `run_repository` row (`.`) exists for a single-repository Run.
  - **Result versions** (CAP-5):
    - A Run that ends `done` gets v1 from the real DBOS calculation workflow. Its entry point
      is `at_attempt_end`, `calculations/1` reads `done`, and `?v=1` is not "values so far".
    - A manual `POST …/calculate` returns 202 with `target_n` 2 and entry point `manual`. v2
      appears, the versions list reads `[1, 2]`, the latest read is v2, `?v=1` is byte-equal
      to before, and `?v=3` returns 404.
    - Every stored value has a `method_id` of the form `{metric_id}@n`. It never holds both a
      figure and a non-`partial` missing word. Its origin names the Run and the template.
    - On a Run parked at `needs_you`, `GET …/metrics` returns `values_so_far: true` and
      `POST …/calculate` returns 409 problem+json. After `cancel`, the Run gets v1.
  - **Gateway reads** (CAP-6): an ended Run returns `{items, next_cursor: null}`. Each item has
    a UUID `attempt_id` and a non-empty role, `harness_usd` is null or a non-negative decimal,
    and the reads are in time order.

## Coverage

- API endpoints added by the epic: 6/6, each with happy path, 401 and 404. Also covered:
  422 on PATCH and 409 on calculate.
- Not covered at e2e, because each needs a staged race or a harness and is settled by the
  stories' unit tests:
  - the second-calculate-while-queued 409 (the real job can finish first)
  - `carried_from` after a log sweep
  - a method that raises
  - `failed: interrupted` at start-up (the durability stack's concern)
  - the instance hold against a running calculation
  - the label surviving a stale `update`
  - the hub `run_repository` and `run_commit` rows (they need agent and git commit rows)
  - the part A method values (story 4: pure functions over fixed fact sets)
- UI: none in this epic.

## Verification

- `ruff check` and `ruff format --check`: clean. `pytest --collect-only`: 23 tests collected.
- The 6 bearer scenarios were run against the in-process app (`create_app(Settings())` with
  the `.env.example` contract, FastAPI `TestClient`). All 6 return 401
  `application/problem+json`.
- Unit meta-tests over test files (`-k "source_limit or e2e or pair or marker"`): 1585 passed.
- **The other 17 tests were not run against a stack.** The epic's constraints forbid starting,
  stopping or calling a running instance, and `make e2e` builds one. Those tests need Postgres,
  DBOS and git. They run on the next `make e2e`, which is the gate.
- `mypy` on the new file reports only the `Settings()` call-arg note that the existing e2e
  modules also have. `make lint` scopes mypy to `domain/` and `application/`.

## Next Steps

- Run `make e2e` (the disposable `aio-e2e` stack) to execute the module against Postgres and
  DBOS. The first thing to watch is how long the calculation takes: `wait_for_version` waits
  90 s.
- When epics 3 and 4 add the Run page and the comparison/export endpoints, extend the e2e suite
  from there.
