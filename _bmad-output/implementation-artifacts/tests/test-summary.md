# Test Automation Summary — orchestrator-run-metrics / epic-4-run-compare

Generated: 2026-11-13. This run was dispatched with an empty story id, so it covers the whole epic.
Spec: `initiatives/orchestrator-run-metrics/epic-4-run-compare/SPEC.md` (the path is relative to the hub).
Stories: 1–4 (commits `3e67332`..`b9aea28`).
Previous summary (epic-3-run-page): in git history at `84007bb`.

Framework: the project's own suites.
- pytest and httpx in `backend-api/tests/e2e`, run by `make e2e-api`.
- Playwright in `web-client/tests/e2e`, run by `make e2e-ui`.

The epic changed both the API (story 1) and the UI (stories 2–4), so this run adds one module to each suite. No existing test file was touched.

## Generated Tests

### API (e2e) tests — `make e2e-api` gate

- [x] `backend-api/tests/e2e/test_metrics_compare.py` (17 tests). It reuses the suite's helpers in the same way `test_run_metrics_versions.py` does. Its templates are fresh `e2e-metrics-<uuid>` fixtures, so it pins no shipped template content.
  - The `pair` fixture makes two `done` Runs of one project. It waits for v1 of both, then for a manual v2 on A.
  - The `cancelled` fixture makes a second project with one Run, which it cancels.
  - **Bearer** (CAP-1): spend, runs, compare, compare.csv and compare.json each return 401 problem+json without the bearer.
  - **422**: compare and both exports return 422 for fewer than two Runs, or for the same id given twice. Runs of two projects also return 422.
  - **Spend this month**: it checks the per-project shape. A cancelled Run counts in both totals and in "of which cancelled".
  - **Runs list**: it returns `{items, next_cursor}`, newest first, with the label and `label_set_by_operator` and `latest_version`. A live Run is not `selectable`; ended and cancelled Runs are.
  - **Compare**:
    - Headers come back in selection order.
    - `v=A:1` gives v1, and A's available versions read [1, 2]. With no `v`, A reads v2.
    - The "same work?" row has a base commit per Run, and `differs` is consistent with them.
    - Metrics come in catalogue order, and `methods_differ` is consistent with the methods.
  - **CSV**:
    - Content-Disposition is `{project}-compare-{yyyy-mm-dd}.csv`.
    - The header is exactly the story's 30 columns.
    - `value_num` holds only decimals and never a letter.
  - **JSON**: the top-level keys are exactly `runs`, `rows` and `catalogue`. Rows have the CSV columns, and each catalogue entry appears exactly once.
  - **Blind**: the payload, the CSV and the JSON contain no Run label and no template name. `R1`, `R2` and both Run ids are present, and the template and models read `hidden · blind`.

### E2E (UI) tests — `make e2e-ui` gate

- [x] `web-client/tests/e2e/metrics-compare-flow.spec.ts` (14 tests). Every `/api/metrics/*` call, and the Run detail read, is answered with `page.route()` through the real same-origin proxy. The fixtures are the spec's own: three Runs, two templates, one Run without `review`, and `time.machine` at @1 and @2.
  - **Story 2**:
    - The rail reads Workflows · Runs · Metrics, then CONFIGURE · Projects · Templates.
    - With no project, the page shows `choose a project above to list its Runs`.
    - One running and two ended Runs give two select boxes, with `running` and `values so far` on the live one.
    - `COMPARE 2 RUNS` is enabled from two and links to `/metrics/compare?runs=a,b`. The selection is in the URL and survives a reload, and `clear` empties it.
    - In spend this month the chosen project comes first, and the `list-price equivalent` line shows.
    - The project page has the `metrics for this project` link.
  - **Story 3**:
    - Three columns appear in selection order, with every method header field.
    - Rows show `≠ the work differs`, `≠ methods differ` with the method under the cell, `+$0.66 vs gateway`, and diff size `not run` with `recalculate`.
    - `remove` leaves two columns and updates the URL.
    - With blind on, the request carries `blind=true`, the headers read R1–R3 and `hidden · blind`, and no label is left anywhere.
    - Export is one click and gives two downloads, `familio-compare-{date}.csv` and `.json`, plus the done line. With HEADLINE on, the export still holds all 9 metrics. A blind export reads `run labels hidden`.
  - **Story 4**:
    - TOTAL shows the cost dot plot labelled `axis does not start at zero`, and every other chart starts at 0.
    - ROLE shows `no such step in this template` with no mark, and machine time is listed under `not split by role` with no chart of its own.
    - ROLE FAMILY shows `≠ step structure differs`.
    - Following a Run outlines it in every chart, and its PNG is a real 1640 px wide file.
    - `PNG · all charts` with 6 charts gives 6 files, named `{project}-compare-{title}-{date}.png`.
    - With blind on, chart keys read R1… only.

## Results

- **UI:** `E2E_PREVIEW_PORT=4399 E2E_STUB_BACKEND_PORT=8799 pnpm exec playwright test tests/e2e/metrics-compare-flow.spec.ts` passes 14/14. With `--repeat-each=3` it passes 42/42. eslint, prettier and tsc are clean on the file. Alternate ports were used, so nothing on 4321 was touched.
- **API:**
  - `ruff check` and `ruff format --check` are clean, and `pytest --collect-only` collects 17 tests.
  - The 5 bearer cases were run in-process (`create_app(Settings())` with FastAPI `TestClient`), and all returned 401 problem+json.
  - The unit meta-tests over test files (`-k "source_limit or e2e or pair or marker"`) gave 1612 passed.
  - **The other 12 API tests were not run against a stack.** The epic forbids starting or calling a running instance, and `make e2e` builds one. They will run on the next `make e2e`.

## Findings (to watch, not confirmed as defects)

1. **The export file name sanitises the project name.** The router replaces characters outside `[A-Za-z0-9._-]` with `-`, so a project called `e2e metrics x` downloads as `e2e-metrics-x-compare-….csv`. The story says `{project}`. The test uses a file-safe project name, so its assertion is exact either way. The Operator should confirm the replacement is intended.
2. **Blind may not cover every label.** It hides `scope_label` and `scope_key` only for model scope. If a run- or step-scope `scope_label` ever carries the Run label or the template name, the blind API test catches it on `make e2e`.
3. **One untested assumption.** The API module assumes that v1 of a `done` shell-only Run stores at least one value. If `make e2e` shows empty `metrics` or `rows`, check that first.

## Coverage

- API endpoints the epic added: 5/5, each with its happy path and 401. 422 is covered for both of its causes.
- Story acceptance criteria exercised end to end:
  - story 1: 8/9, with `make openapi` left to the quality gate
  - story 2: 5/5
  - story 3: 5/5
  - story 4: 5/6
- What the e2e suites leave to the unit suite:
  - that the PNG of a followed Run has no outline (a pixel check is unreliable)
  - the MODEL breakdown
  - the version selector per column
  - scrolling inside a chart past about 15 Runs
  - the "shared words printed once" line

## Next Steps

- Run `make e2e` (the disposable `aio-e2e` stack) to execute the API module against Postgres and DBOS.
- The Operator decides finding 1.
