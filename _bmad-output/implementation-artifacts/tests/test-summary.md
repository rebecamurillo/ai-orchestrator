# Test Automation Summary — orchestrator-run-metrics / epic-6-analysis-tier2

Generated: 2026-11-13. This run was dispatched with an empty story id, so it covers the whole epic.
Spec: `initiatives/orchestrator-run-metrics/epic-6-analysis-tier2/SPEC.md` (the path is relative to the hub).
Stories: 1–4 (commits `2b51768`..`a7fd657`).
Previous summary (epic-5-analysis-tier1): in git history at `994ab1a`.

Framework: the project's own suites.
- pytest and httpx in `backend-api/tests/e2e`, run by `make e2e-api`.
- Playwright in `web-client/tests/e2e`, run by `make e2e-ui`.

Stories 1 and 2 are analysis logic over the `ProcessRunner` and `AnalysisTools` ports. Their unit suites cover them with fakes and recorded Opengrep SARIF. End to end, this run reaches them where a stack adds something: their `n/a` words on a real Run, and the findings route. No existing test file was touched. No shipped template is read.

## Generated Tests

### API (e2e) tests — `make e2e-api` gate

- [x] `backend-api/tests/e2e/test_run_analysis_tier23.py` (11 tests). It reuses the helpers of `test_run_analysis.py` and `test_run_metrics_versions.py`. Its templates are fresh `e2e-tier3-<hex>` fixtures defined inline in the module.
  - **The `stepped` fixture** runs a template that declares `metrics: step.{name}.heldout_tests` (format `junit`, path `out/heldout.xml`). Its rows are `git.worktree` → shell → `git.commit` → `git.push` → `metrics.analyse`.
    - The shell row writes `out/heldout.xml` (18 passed, 2 failed) and `out/other.xml`, which no entry declares.
    - The fixture waits for v1.
  - **Findings route (story 4)**:
    - Without the bearer: 401 problem+json.
    - Unknown Run or analysis: 404 problem+json.
    - Analysis id that is not a UUID: 422.
    - The real analysis of a repository with no `sast.rules`: 404, and `rule_pack_hash` is null.
  - **Stories 1 and 2 with no declaration**:
    - All five Tier 2 ids read `n/a — tier 2 not declared` with no number.
    - Both finding ids read `n/a — no rules declared`.
  - **Story 3, the template store**:
    - `heldout_tests` without the prefix is refused with 422 and the reason `metric id must be step.{template}.{name}`, at an integer line.
    - Another template's prefix is refused in the same way.
  - **Story 3, import**:
    - v1 holds passed 18, failed 2, errored 0 and skipped 0 under the declared id, with method `{id}@1`.
    - The analysis response's `step_entries` lists the entry by its label.
    - The calculation output contains `not catalogued: out/other.xml` and does not contain the declared path.

### E2E (UI) tests — `make e2e-ui` gate

- [x] `web-client/tests/e2e/static-signals-tier23.spec.ts` (6 tests). Every read is answered with `page.route()` through the real same-origin proxy, following the `static-signals.spec.ts` precedent. The fixture is a hub Run: repository `.` declared no Tier 2, and `repos/app` ran Tier 2 and Opengrep.
  - **Partial totals**:
    - The Run row of new linter warnings reads `partial · 1 of 2 repositories`.
    - `.` reads `n/a — tier 2 not declared`.
    - `repos/app` has no partial word.
  - **Security findings**:
    - The row reads `3 possible high`, `0 possible medium`, `0 possible low` and `unchanged 1`, and is partial.
    - Clicking the count opens the drawer. It lists only the three new security findings (rule, path:line, severity, CWE), leaving out the unchanged one and the bug.
    - The link `SARIF · opengrep · repos/app` points to `/api/runs/{id}/analysis/{aid}/sarif/opengrep`.
  - **Footer**: `rule packs: opengrep abcdef12`.
  - **Test-first**:
    - The line reads `test-first order · method followed, not quality · 6 of 8 stories readable from the logs` (4/2/0/2 outcomes).
    - Its hint opens on the three limits.
  - **Step metric**: `held-out tests` reads `passed 18` and `failed 2`.
  - The Tier 2 and step rows appear only under ALL METRICS, so the spec opens that set first.

## Results

- **UI:** after `pnpm build`, ran `E2E_PREVIEW_PORT=4399 E2E_STUB_BACKEND_PORT=8799 pnpm exec playwright test tests/e2e/static-signals-tier23.spec.ts`.
  - It passes 6/6, and 18/18 with `--repeat-each=3`.
  - eslint, prettier and `tsc --noEmit` are clean.
  - Nothing on 4321 was touched.
- **API:**
  - `ruff check` and `ruff format --check` are clean, and `pytest --collect-only` collects 11 tests.
  - The unit meta-tests over test files (`-k "source_limit or e2e or pair or marker"`) gave 1779 passed.
  - The fixture template was validated offline:
    - With `validate()`, the declared id passes. Both refusals give line 9 and the expected reason.
    - The shell row was run under `sh`. `import_junit` reads its report as 18/2/0/0, and `sniff` reads `out/other.xml` as `junit`.
  - The bearer case was run in-process (`create_app(Settings())` with `TestClient`) and returned 401 problem+json.
  - **The other 10 API tests were not run against a stack.** The epic forbids starting or calling a running instance, and `make e2e` builds one. They will run on the next `make e2e`.

## Findings (to watch, not confirmed as defects)

1. **The `stepped` fixture assumes the shell row's cwd is the Run's worktree**, as in the epic 5 module. If `git.commit` finds nothing to commit, check this first.
2. **The `n/a` assertions assume a summary row exists** for each Tier 2 and finding id at some scope on a single-repository Run. If `make e2e` reports `assert rows`, look at whether `summarise` writes words at repository scope only. The test accepts any scope.

## Coverage

- API endpoints the epic added: 1/1 (`GET /runs/{id}/analysis/{aid}/findings`): 401, 404 (unknown, and no listing), and 422. A 200 with listed findings needs an image that carries Opengrep and a repository that declares rules. That case is left to the unit router test.
- Story acceptance criteria exercised end to end:
  - story 1: 1/7 (no declaration → `tier 2 not declared`). Matching, Cobertura, JUnit, fail-to-pass, the timeout and the env are unit-only, on fakes.
  - story 2: 1/6 (`n/a — no rules declared`). Matching, rename, severity, CWE, `baselineState` and the Dockerfile are unit-only.
  - story 3: 3/5 (validates and refuses, 18/2 imported, `not catalogued`). The test-first orders need harness `event_fact` rows and stay unit-only.
  - story 4: 3/3 on screen (partial `1 of 2`, `3 possible` with CWE in the drawer, `6 of 8` with the limits).

## Next Steps

- Run `make e2e` (the disposable `aio-e2e` stack) to execute the API module against Postgres, DBOS and the image.
- Run `make e2e-ui` for the full UI suite.
