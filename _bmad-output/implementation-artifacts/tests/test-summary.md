# Test Automation Summary — orchestrator-run-metrics / epic-5-analysis-tier1

Generated: 2026-11-13. This run was dispatched with an empty story id, so it covers the whole epic.
Spec: `initiatives/orchestrator-run-metrics/epic-5-analysis-tier1/SPEC.md` (the path is relative to the hub).
Stories: 1–5 (commits `a8d8b2d`..`6686103`).
Previous summary (epic-4-run-compare): in git history at `48a4271`.

Framework: the project's own suites.
- pytest and httpx in `backend-api/tests/e2e`, run by `make e2e-api`.
- Playwright in `web-client/tests/e2e`, run by `make e2e-ui`.

Stories 1–3 are pure analysis logic over ports. Their unit suites cover them on fakes and recorded tool outputs. End to end, they are reached through story 4's step and story 5's screens. This run adds one module to each suite. No existing test file was touched.

## Generated Tests

### API (e2e) tests — `make e2e-api` gate

- [x] `backend-api/tests/e2e/test_run_analysis.py` (17 tests). It reuses the suite's helpers in the same way `test_metrics_compare.py` does. Its templates are fresh `e2e-analysis-<uuid>` fixtures inline in the module, so it pins no shipped template content.
  - **The `analysed` fixture** owns a Template with these rows: `git.worktree` → shell writing `src/app.ts` (3 lines, 1 `as any`) → `git.commit` → `git.push` → `metrics.analyse` → a shell row after it.
    - The analysis therefore fetches a commit the Run really pushed to its `file://` origin, and runs the tools in the image.
    - The fixture waits for v1, then for a manual v2.
  - **The `plain` fixture** is a shell-only Run of the same project. It has no analysis row and no push. It also gets v1 and a manual v2.
  - **Bearer**: the analysis list and the SARIF download each return 401 problem+json without the bearer.
  - **Refusals**:
    - An unknown Run returns 404 problem+json.
    - `v=0` and a non-UUID analysis id return 422.
    - A tool with no SARIF (`no-such-tool`, `summary`) returns 404.
    - Another Run's analysis id returns 404.
  - **Story 4, the step**:
    - The `metrics.analyse` row is `done` with gate `unvalidated`.
    - The row after it ran and is `done`.
    - v1's `entry_point` includes `workflow_step`.
  - **Story 1, inputs**: the analysis of `.` is `ok`/`partial`, and the rest holds on the real stack:
    - base ≠ head, both stored.
    - `base_branch` is `main`.
    - `commits_outside_run` is 0.
    - The toolset names gitleaks, osv-scanner, jscpd and lizard.
  - **Story 2, counts**: the run-scope `code.lines_added` for production is 3, and type escapes are 1 raw. The rate row reads `raw only` (3 < 50), and the method ids are `code.*`.
  - **SARIF**: every tool in `sarif_tools` downloads as `application/sarif+json` with a `runs` key, and gitleaks is among them.
  - **Manual calculation**:
    - On the analysed Run, v2 holds a new analysis id with the same base and head, plus `code.*` values.
    - On the plain Run, v1 holds no analysis.
    - Also on the plain Run, v2 is `failed` with reason `commit missing: no pushed head` and `head` null.
    - With no `v`, the newest version is read.
  - **Story 5, comparison**: comparing the analysed Run with the plain Run's v1 gives diff size `not run` for the plain Run and `+3 …` for the analysed one.

### E2E (UI) tests — `make e2e-ui` gate

- [x] `web-client/tests/e2e/static-signals.spec.ts` (9 tests). Every `/api/runs/{id}/*` and `/api/metrics/*` read is answered with `page.route()` through the real same-origin proxy (the `run-detail-metrics.spec.ts` precedent).
  - **Run page**:
    - The Run row (`all repositories`) is followed by `.` and `repos/app`, in both tiers.
    - Each repository row has its detail line: `base aaaaaaa (merge base with main) → head …`, then `no commits outside this Run` / `2 commits this Run did not make`.
    - The table has `raw` and `per 100 prod. lines` columns. 40 production lines read `raw only`, and `small change` sits beside duplication.
    - The tier heads are 1A, then `1B · LOOKUPS 2026-11-12`, then 2 and 3.
    - The footer prints tools and versions, rule packs, the vulnerability database date, the registry lookup date and the declaration, with no hint opened.
    - The secrets count opens the origin drawer. The drawer lists the SARIF finding and links to `/api/runs/{id}/analysis/{aid}/sarif/gitleaks`.
    - v1 with no analysis reads `not run in v1 · RECALCULATE METRICS runs it`, with no table and no footer.
  - **Comparison**:
    - `code.duplication_added` is flagged `≠ tool versions differ: jscpd 4.0.5 (Run 1) vs 4.0.6 (Run 2)`, and each cell carries its own jscpd version.
    - Suppressions, measured with the same toolset, are not flagged.
    - A Run with no analysis reads `not run` with a `recalculate` link to `/workflows/{id}?tab=metrics&recalculate=1`.
    - CHART with `metrics=all`:
      - `suppressions added` is a bar chart labelled `per 100`, with `not run` for the third Run.
      - `duplicated lines added` keeps the flag.

## Results

- **UI:** `E2E_PREVIEW_PORT=4399 E2E_STUB_BACKEND_PORT=8799 pnpm exec playwright test tests/e2e/static-signals.spec.ts` (after `pnpm build`) passes 9/9. With `--repeat-each=3` it passes 27/27.
  - eslint, prettier and `tsc --noEmit` are clean.
  - Alternate ports were used, so nothing on 4321 was touched.
  - The first run caught one selector defect in the spec itself: the tier heads are `colgroup` headers, so the column-head assertion is now scoped to `thead`.
- **API:**
  - `ruff check` and `ruff format --check` are clean, and `pytest --collect-only` collects 17 tests.
  - The unit meta-tests over test files (`-k "source_limit or e2e or pair or marker"`) gave 1733 passed.
  - The 2 bearer cases were run in-process (`create_app(Settings())` with FastAPI `TestClient`), and both returned 401 problem+json.
  - The two 422 cases could not run in-process. FastAPI resolves the database-backed ports dependency before the query and path validation, so they need a stack.
  - **The other 15 API tests were not run against a stack.** The epic forbids starting or calling a running instance, and `make e2e` builds one. They will run on the next `make e2e`.

## Findings (to watch, not confirmed as defects)

1. **The analysed fixture assumes the image's tools run cleanly** on a 3-line TypeScript change, and that gitleaks writes a SARIF for it. If `make e2e` shows the analysis `partial` with gitleaks missing from `sarif_tools`, read the row's log before suspecting the test.
2. **The `change` row assumes a shell row's cwd is the Run's worktree** after `git.worktree`. That matches `shell.py` (`cwd = ctx.cwd`). If the commit row finds nothing to commit, check this first.
3. **The comparison's `tool_versions_differ` is not exercised against a stack.** Two Runs on one image share one toolset, so a real flag needs two tool versions. The flag is covered by unit tests and by the UI spec.

## Coverage

- API endpoints the epic added: 2/2 (`GET /runs/{id}/analysis` and the SARIF download), each with its happy path, 401, 404 and 422. `POST …/metrics/calculate`, which this epic extended with part C, is exercised on both Runs.
- Story acceptance criteria exercised end to end:
  - story 1: 2/12 (the base rule and both ids stored; `commit missing: no pushed head`). The rest are classifier and declaration rules, which the unit suite covers.
  - story 2: 1/5 (production counts with `raw only`)
  - story 3: 0/7. All of them use recorded outputs and the lookup fake. The only stack check is that the toolset names the four pinned tools.
  - story 4: 5/7 (plan, run and continue; v1 `workflow_step`; manual part C; SARIF 200 and 404). `make openapi` is left to the quality gate, and the two-repository row is unit-only (a hub fixture would be needed).
  - story 5: 5/5
- What the e2e suites leave to the unit suite:
  - the classifier precedence
  - the lock-file diff
  - `ANALYSIS_LOOKUPS=off`
  - the private registry reading `not checked`
  - the jscpd and lizard intersection with added lines
  - the scratch folder's removal

## Next Steps

- Run `make e2e` (the disposable `aio-e2e` stack) to execute the API module against Postgres, DBOS and the pinned tools.
- Run `make e2e-ui` for the full UI suite.
