# Test Automation Summary — orchestrator-initiative-steps / epic-2-run-page-review

Generated: 2026-11-23. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-2-run-page-review/SPEC.md` (relative to the hub).
Stories: 1–4 (commits `3624a257`..`000ad823`).
Previous summary (epic-1-step-logs): in git history at `a11f801d`.

Framework: Playwright (`web-client/tests/e2e`, the `make e2e-ui` gate), with `page.route` mocks as in
`run-step-drawer.spec.ts`. This epic changes no backend code, so no API test is added. The epic-1 module
`backend-api/tests/e2e/test_step_logs.py` already covers the reads it renders.

The stories wrote three specs (`run-files-by-epic`, `run-step-drawer`, the `run-diagram` additions). The new
module covers what those specs left out. No existing test file was touched, and no shipped template is read.

## Generated Tests

### E2E tests — `web-client/tests/e2e/run-page-review.spec.ts` (12 tests)

- **CAP-2, the step drawer (story 2):**
  - Agent step: the heading takes focus, `2 attempts · $1.25`, the files-read paths, `src/a.ts +3 −1`, and the
    `full page` href.
  - Deterministic step: `deterministic step · files read are not recorded; the command is in the log`,
    `no file · refs updated: …`, and `2m · exit 0`.
  - Commit step: `commit abcdef1 · {message}` comes before the files, and `{path} binary` is shown when counts
    are null.
  - A run-order row is marked `aria-current`. Clicking another row requests `seq/0` and reloads the drawer.
  - *close* removes the drawer and the row selection, and returns focus to the opener.
- **CAP-4, logs in words (story 4), in the drawer:**
  - `text`: the lines and *download raw* (`?download=true`).
  - `no_output` with no reason: `no output · the command ran and printed nothing`, with *download raw*.
  - `no_output` with a reason: `no output · no log was recorded for this attempt`, with no *download raw*.
  - `removed` with `removed_at`: `log removed by the retention sweep on 2026-11-29 · exit 1 · 42s were recorded`,
    with no *download raw*.
  - A skipped row (`not_run`): `not run · skipped · no command`, with no log viewer.
  - The step page (`StepDetail`) shows *download raw* when the log exists.
- **CAP-1, files by epic (story 1):** a story that has not started reads `no file yet`. A started story with no
  change shows neither `no file yet` nor `changed:`.

## Coverage

- UI capabilities of this epic: 4 of 4 are exercised in a browser.
  - CAP-1: the new spec and `run-files-by-epic.spec.ts`. The latter is broken; see below.
  - CAP-2: the new spec, `run-step-drawer.spec.ts` and `run-diagram.spec.ts`.
  - CAP-3: `run-diagram.spec.ts`.
  - CAP-4: the new spec.
- Covered by vitest only:
  - the epic strip `AFTER STORIES` with `+k` truncation
  - the unsplit strip for a card with no `run_order`
  - `files_read=none`
  - `removed` with `removed_at` null

## Verification

- `tsc --noEmit`, eslint and prettier pass on the new module.
- Run against the built web-client and the stub backend on spare ports (port 4321 is never bound; no running
  instance is touched):
  `pnpm build && E2E_PREVIEW_PORT=4399 E2E_STUB_BACKEND_PORT=8799 npx playwright test <specs>`
  - `run-page-review`: 12 passed.
  - `run-step-drawer`, `run-diagram`: passed.
  - `run-detail-artifacts`, `run-detail-epic-6-screens`, `run-detail-last-opened`, `step-detail`: 29 passed.
  - **`run-files-by-epic.spec.ts` (story 1): 2 of 2 fail.**
    - The spec mocks `files-by-epic` but not `/runs/{id}/detail`. The stub backend does not know its `RUN_ID`, so
      the page shows `COULD NOT REACH BACKEND-API … /detail → 404` and the panel never renders.
    - This is a defect in the test, not the product: the new spec's CAP-1 case passes once the detail and graph
      are mocked.
    - It is left unchanged. It is story 1's protected test (hard rule 1), so the fix goes to the lead or Operator.

## Next Steps

- Fix `run-files-by-epic.spec.ts`: mock `**/api/runs/${RUN_ID}/detail**` and `/graph` with
  `runDetail(withSteps(twoEpicSteps()))` and `twoEpicGraph()`, as `run-page-review.spec.ts` does.
- The lead runs `make e2e` in the disposable `aio-e2e` stack before the pull request.
