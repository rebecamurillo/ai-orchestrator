# Test Automation Summary — orchestrator-run-metrics / epic-3-run-page

Generated: 2026-11-13. Dispatch mode with an empty story id, so this covers the whole epic.
Spec: `initiatives/orchestrator-run-metrics/epic-3-run-page/SPEC.md` (path relative to the hub)
Stories: 1–6 (commits `b652211`..`91c567e`)
Previous summary (epic-2-run-versions): in git history at `da81060`.

Framework: the project's own Playwright suite in `web-client/tests/e2e` (`make e2e-ui`). It runs
against the built web-client and the stub backend. The epic made no backend change, so no API
test was added.

## Generated Tests

### E2E (UI) tests — `make e2e-ui` gate

- [x] `web-client/tests/e2e/run-detail-metrics.spec.ts` (16 tests, new file). Every metrics route
  (catalogue, versions, metrics, calculate, calculations, PATCH label) is answered with
  `page.route()` through the real same-origin proxy, as `run-detail-tabs.spec.ts` does. The
  catalogue is a fixture the spec owns, so no shipped template or catalogue content is pinned.
  - **Arrival** (CAP-3, CAP-4): an ended Run opens on METRICS. Its title is the label and the
    branch is the first meta field. The arrival URL stays untouched.
  - **Cost block** (CAP-3): it shows GATEWAY · HARNESS with both value cells. The figures-differ
    card reads `gateway $15.35 · harness $16.01 · harness is $0.66 higher (4.3 %)` and the gate
    line. Equal figures (v1 via `?v=1`) show no card, and the cost block prints the version line.
  - **Hint** (CAP-2): hover does not open it. Click and Enter do, and it shows the catalogue's
    method and source text. Escape closes it and focus returns to the control.
  - **Origin drawer** (CAP-2): a value cell opens it. It shows `{label} · {run id}`, the branch,
    and `n/a — a Run total spans 2 models`. Escape closes it.
  - **By role** (CAP-4): rows are senior, builder, reviewer (gateway descending). `senior` is a
    row, and a missing value reads `not recorded`.
  - **URL state and versions** (CAP-4): `?v=1` reads v1 (the request carries `v=1`) and shows
    `showing v1 of 2 · latest is v2`. CHART writes `tab=metrics&view=chart&v=1`, ALL METRICS
    writes `metrics=all`, and choosing `v2 latest` drops `v=`.
  - **Run label** (CAP-3): Escape sends no PATCH. Enter sends `{label: "snake round 1"}`, the
    title updates and `your label` shows. Clearing sends `{label: null}` and restores the default.
  - **Recalculate** (CAP-3): the confirm text is `Creates v3 … v1 to v2 are kept.` Next the line
    reads `calculating v3 · started 10:00:01` and the button is withdrawn. When the calculation
    is done, `v3 latest` appears on the next poll. When it fails, the page shows
    `calculation v3 failed · no version created ·`, the output appears in a command block, and
    no v3 is offered.
  - **Running Run** (CAP-3, CAP-4): it opens on GATE with no RECALCULATE METRICS. Its METRICS tab
    states `Run running · values so far, stored as each attempt ends`.
  - **CHART view** (CAP-5): `role="figure"` panels named `cost by role` and
    `where the money went, by scope`. A mark is a focusable button named `{run label} …$9.00`,
    and focusing it shows the tooltip.
  - **PNG** (CAP-6): a real download in Chromium. TRANSPARENT is the default. The file name is
    `familio-{slugged label}-cost-by-role-{yyyy-mm-dd}.png`, and the file is a PNG whose IHDR
    width is 1640. The preview switch (DARK PAGE) swaps the screen chart for the export image.
  - **Runs history** (story 4): the `cost` head carries `how recorded spend is calculated`. It
    does not open on hover, it opens on click with the catalogue text, and Escape closes it.
    The cell still reads `$0.250000`.

## Results

- `E2E_PREVIEW_PORT=4399 E2E_STUB_BACKEND_PORT=8799 pnpm exec playwright test tests/e2e/run-detail-metrics.spec.ts`
  passes: 16 tests (15 pass, 1 is the expected failure below). `--repeat-each=5` gives 80/80
  with no flake. eslint, prettier and tsc are clean on the file.
- Running the full Playwright suite once gives 338 passed, 1 skipped and **3 failed**, all in
  existing tests (see Findings).
- Environment: Playwright here pins chromium-headless-shell 1234, and only 1248 was in the
  cache. `pnpm exec playwright install chromium` (the `make install-e2e` step) fixed it.
  Alternate ports were used, so nothing on 4321 was touched.

## Findings (product defects; not fixed here — tests only)

1. **The PNG control cannot be clicked with a mouse** (CAP-6). `.chart-png` is absolutely
   positioned and comes before the `position: relative` `.chart-panel` in the DOM, so the
   panel's `.chart-head` paints over the button and catches the click. Playwright reports
   `<h4 class="chart-head"> … intercepts pointer events`. Keyboard activation works, and the
   whole export pipeline is proven that way. `the PNG control takes a mouse click` is marked
   `test.fail()` to pin the defect: once the control is stacked above the head (for example
   with `z-index` on `.chart-png` in `src/components/charts/charts.css`), Playwright will flag it
   as an unexpected pass, and the marker should then be removed.
2. **`run-diagram-error.spec.ts` regressed** (3 tests, existing and protected, not in any epic-3
   story's list of tests it may change). The stub backend 404s the new metrics reads. Since
   story 3, the cost block renders its own `fetch-failed` readout, so
   `locator('[data-testid="fetch-failed"]')` now matches two elements under strict mode. I did
   not edit it (hard rule 1). The Operator decides between scoping the cost block's readout
   differently (a product change) and a declared revision of that spec.

## Coverage

- Epic-3 capabilities with an e2e path: 6/6 (CAP-1 tokens are only checked through the
  rendered charts; their exact values and contrast stay in the unit tests).
- Story acceptance criteria exercised end to end: 16 of 32 (story 1: 0/3, story 2: 3/5,
  story 3: 5/5, story 4: 4/6, story 5: 2/7, story 6: 2/6). The rest are pure-layout or
  token checks, and the unit suite (`make test`) is where they belong: tokens and contrast,
  nice ticks, zero, partial and missing marks, the export SVG's text and background
  rectangles, the follow highlight, and the OFL file. Also left to unit tests: the
  seven-version select, a poll keeping an open drawer (needs a 30 s slow tick), the
  board-card hint, and the step-detail attempt rows.

## Next Steps

- Fix finding 1, then remove `test.fail()`.
- The Operator decides finding 2 before `make e2e-ui` is relied on as a gate for this branch.
