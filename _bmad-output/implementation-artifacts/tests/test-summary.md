# Test Automation Summary — orchestrator-initiative-steps / epic-10-initiatives-board

Generated: 2026-11-26. Dispatched with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-initiative-steps/epic-10-initiatives-board/SPEC.md` (relative to the hub).
Stories: 1–5 (through commit `f85e1685`).
Previous summary (epic-9-initiative-reopen): in git history at `c6fa0368`.

Framework: Playwright (`web-client/tests/e2e`, the `make e2e-ui` gate). The epic is web-client
only, with no backend or contract change, so no API test is added. Each story already wrote
its smoke spec (B14). The two new files cover the flows the smokes leave out. They mock the
browser-side reads with `page.route()`, following the `board.spec.ts` precedent. No existing
test file and no stub route was touched, and no shipped template is read (hard rule 6).

## Generated Tests

### E2E tests — `web-client/tests/e2e/initiatives-flows.spec.ts` (6 tests, CAP-1)

- [x] Cards sit in the column of their current workflow. An empty column reads `—`. A `done`
  item sits in `DONE`. A card links to `/initiatives/{id}`.
- [x] Two cancelled items: `DONE` reads `2 cancelled, hidden · show`, and the items appear only
  after `show`.
- [x] The rail's `nav-initiatives-needs-you` reads `1 need you`, taken from the response counts.
  The readout reads `2 ongoing · 1 need you`.
- [x] `NEEDS YOU` requests `filter=needs_you` and writes `?filter=needs_you` to the URL. The mount
  request used `filter=ongoing`.
- [x] An empty response reads `NO INITIATIVES`, links to `/initiatives/new`, and shows no rail
  need-you line.
- [x] A 503 swaps the board for the failed-fetch readout, which names
  `/api/initiatives?filter=ongoing` and offers Retry.

### E2E tests — `web-client/tests/e2e/new-initiative-refusals.spec.ts` (4 tests, CAP-3)

- [x] Create stays disabled until both the name and the first message are filled. It then reads
  `Create and start spec`.
- [x] A 409 with an open holder renders the exact `newini-slug-taken` line, and the holder link
  goes to `/initiatives/{id}`. Create is disabled, and editing the name clears the line and
  enables create.
- [x] A 409 with no open holder (`… waits for its branch cleanup: …`) renders the problem's
  `detail`, and create is disabled.
- [x] A package read that answers 404 shows the line
  `no package installed · install one in the project's Package section`. No sequence is shown,
  and create stays disabled with both fields filled.

## Results

The specs were run locally on spare ports (`E2E_PREVIEW_PORT=4399 E2E_STUB_BACKEND_PORT=8799`).
Port 4321 was not bound and no running service was touched (hard rule 9).

- New specs plus the epic's own smokes (`initiatives.spec.ts`, `new-initiative.spec.ts`):
  **13 passed**.
- `prettier --check` and `eslint` pass on both new files.
- Related existing specs (`board`, `board-list`, `projects`, `repository-init`, `templates`,
  `run-detail`, `shell`): **58 passed, 6 failed**. The failures are two pre-existing defects
  that stories 2, 4 and 5 left. They are reported here and were not fixed: they are outside a
  QA dispatch's write scope.

### Defect 1 — `templates.spec.ts`: 5 tests time out on `/templates/demo/1`

- The SSR render throws `TypeError: Cannot read properties of undefined (reading
  'toUpperCase')` in `src/components/templates/TemplateTypeLine.astro:9`.
- Cause: the stub's template version payloads (`tests/e2e/templates-fixtures.mjs` /
  `stub-backend.mjs`) carry no `type`. Story 3.1 added `type` to the contract, and story 10.4
  reads it without a fallback.
- Fix: add `type: 'auto'` to the stub's template version fixtures. This is a stub fixture that
  drifted from the contract (case c, maintenance), not a change to the code.

### Defect 2 — `projects.spec.ts:203` "paints no amber or red pixel when every Repository is ok"

- The CLEAN project now paints amber from two sources:
  - the `INITIATIVES` section (story 10.2): the stub's `GET /projects/{id}/initiatives` always
    answers a `waiting for her` row, so the `BLK` token and the amber age appear;
  - the *Remove package* button's `::before` / `::after` pseudo-elements. Story 10.5's
    exclusion filter matches only the exact selector, so these slip through.
- Fix: decide whether the CLEAN fixture should answer an empty initiatives list, and widen the
  exclusion to the button's pseudo-elements. Both change an existing test, so this goes to the
  lead or Operator under hard rule 1.

## Coverage

- CAP-1 (board, rail): smoke, plus filter, cancelled toggle, rail need-you line, empty state and
  failed read.
- CAP-2 (list view, project section): smoke only (`initiatives.spec.ts`, `projects.spec.ts`).
- CAP-3 (New initiative): smoke, plus the empty-field guard, both 409 paths and the missing
  package.
- CAP-4 (initiative tag, type): the board's linked card (`board.spec.ts`). The Run header
  `wf-initiative-tag` and the templates type are unit-tested only. The templates e2e is blocked
  by defect 1.
- CAP-5 (Package section, folder): `projects.spec.ts` (package kv, refused remove, folder save).
- UI features with an e2e flow: 5 of 5 capabilities touched; 10 new tests.

## Next Steps

- Fix defects 1 and 2, then run `make e2e` in `aio-e2e` before the pull request (B14).
- Once the stub's templates carry `type`, add a `templates-type` e2e assertion. Once a stub Run
  fixture carries `initiative`, add one for `wf-initiative-tag`.
- Epic 11 (the initiative page): a click-through from a card to `/initiatives/{id}`.
