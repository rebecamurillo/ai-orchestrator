---
title: "Run detail layout rework"
type: 'feature'
created: '2026-09-16'
status: 'blocked'
review_loop_iteration: 0
baseline_revision: '49a347368cf00a81bdb446107f65fb4dc83f1d81'
context:
  - '1-1-serve-any-attempts-full-log.md'
  - '1-2-step-run-detail-page.md'
  - '1-3-helper-drawer-prompt-result-and-reach-agent.md'
warnings:
  - oversized
---

<intent-contract>

## Intent

**Problem:** The current Run detail page scatters related information across two columns with no embedded diagram. The stop zone (StopBody) and the steps table share the left column; the gate record, cost, stories, and artifacts fill the right column. The diagram is a separate page view (`?view=diagram`), requiring navigation away from the detail. The model used for the dispatch is not shown in the meta line (FR-11, EXPERIENCE-v1 §2.2 delta 26 — 2026-09-15).

**Approach:** Restructure the page into four vertical zones: (1) Banner + StopBody top zone; (2) a center diagram row with embedded diagram + summary column (StoriesStrip, CostBlock, ArtifactsPanel); (3) a tabbed bottom region with GATE (default when no terminal), STEPS, and SESSION (when `terminal` non-null, default when present) tabs — CommandBlock lives in SESSION. Retire `?view=diagram` via an Astro redirect. Add `model` to `Header`, `HeaderMetaOut`, and `metaLine()`.

## Boundaries & Constraints

**Always:**
- TDD: new unit tests written first, all failing, before any implementation task (AD-18). `DiagramSection` has a unit test pair per `check-test-pairs.mjs` rule.
- `make openapi` then `pnpm gen:api` complete with no drift after backend changes (AD-3); `schema.d.ts` never hand-edited.
- This epic reads state only; no status writes anywhere (AD-8).
- `domain/` never imports `fastapi`, `sqlalchemy`, etc. (AD-2).
- `RunDiagram.tsx` must NOT be deleted — frozen test `run-diagram-svg.test.ts` imports it.
- `CommandBlock.tsx` must NOT be modified — frozen test `run-command-block.test.ts`.
- SESSION tab is the default active tab when `detail.run.terminal` is non-null. The default is set once on first detail load via a `useRef` guard; subsequent polls must not reset the active tab.
- RunDetail passes `view={undefined}` to `Header.tsx` so the DIAGRAM toggle renders as a disabled stub.
- `data-testid="wf-terminal"` and `data-testid="wf-terminal-release"` must appear in exactly one place in the DOM: inside `CommandBlock` in the SESSION tab panel. StopBody must not render any element with these testids after this story.

**Exception-4 authorized test revision (AGENTS.md rule 1, operator decision):**
`web-client/tests/unit/run-detail-lib.test.ts:376` — the `joins every meta field in the fixed order` assertion pins the pre-model metaLine string. This assertion may be revised because the Operator explicitly authorized adding the model slot to the meta line in EXPERIENCE-v1.md delta 26 (2026-09-15). The same commit must: (a) revise only the pinning assertion, (b) add or retain a test that covers the new behaviour (model slot inserted), and (c) name the decision and its date in a comment in the revised test. No other assertion in that file may be changed under this exception.

**Block If:** Any pre-existing test (other than the exception-4 revision above) fails after these changes — classify and report per AGENTS.md rule 1 before proceeding.

**Never:** Delete `RunDiagram.tsx` or modify `CommandBlock.tsx`. Edit `schema.d.ts` by hand. Add signal actions or status transitions.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior |
|----------|--------------|---------------------------|
| Normal run, graph loads | `detail` ready; graph fetch succeeds | Diagram renders in `wf-diagram-main`; `data-testid="wf-diagram"` present; GATE tab active by default |
| Graph fetch fails | `GET /runs/{id}/graph` → error | `data-testid="fetch-failed"` inside `wf-diagram-main` only; stop zone, summary column, tabs all render normally from `detail` |
| Terminal in progress | `terminal.in_progress=true`, `TERMINAL_RELEASE` in `admitted_signals` | SESSION tab is default active; `CommandBlock` immediately visible with Release button; StopBody shows inline text note (no `wf-terminal` testid in stop zone) |
| Terminal, release not admitted | `terminal.in_progress=true`, `TERMINAL_RELEASE` NOT in `admitted_signals` | SESSION tab is default; CommandBlock visible; no `wf-terminal-release` |
| No terminal | `detail.run.terminal` is null | SESSION tab absent; GATE tab is default |
| `?view=diagram` URL | User navigates to `?view=diagram` | Astro redirects to `/workflows/{id}` (no view param); RunDetail mounts; Playwright follows redirect |
| metaLine with model | `meta.model` is set | `... · {harness} · {model} · {started_at} · ...` |
| metaLine without model | `meta.model` is null | `... · {harness} · — · {started_at} · ...` |

</intent-contract>

## Code Map

**Backend — domain / application:**
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py:122` — `Header` dataclass; add `model: str | None` field after `harness: str | None`
- `backend-api/src/orchestrator/application/use_cases/run_views.py:241` — `_header()` function; add `model=run.inputs.get("model")` to the `Header(...)` constructor call

**Backend — API schema:**
- `backend-api/src/orchestrator/api/schemas/run_views.py:164` — `HeaderMetaOut`; add `model: str | None = None`
- `backend-api/src/orchestrator/api/schemas/run_views.py:182` — `HeaderOut.of()`; add `model=header.model` to the `HeaderMetaOut(...)` constructor call

**Backend — tests (TDD, write first):**
- `backend-api/tests/unit/test_run_views.py` — add assertion covering `Header.model` populated from `run.inputs`; must fail before task 4
- `backend-api/tests/unit/test_run_view_schemas.py` — add assertion covering `HeaderMetaOut.model` round-trip; must fail before task 6

**Generated contracts:**
- `contracts/openapi.json` — regenerated by `make openapi`; `model` field appears in `HeaderMetaOut`
- `web-client/src/api/schema.d.ts` — regenerated by `pnpm gen:api`; `model?: string | null` in `HeaderMetaOut`

**Frontend — lib:**
- `web-client/src/lib/run/detail.ts:251` — `metaLine()`; add `const model = meta.model ?? '—'`; insert `· ${model}` between `${harness}` and `${started}`

**Frontend — frozen test revision (exception-4, same commit as metaLine change):**
- `web-client/tests/unit/run-detail-lib.test.ts:376` — revise `joins every meta field in the fixed order` to expect `· claude · — · 2026-09-07T09:00:05Z ·` (fixture has no `model` in inputs → `'—'`); add a comment naming `EXPERIENCE-v1.md delta 26 (2026-09-15)` as the authorizing decision

**Frontend — new component:**
- `web-client/src/components/run/DiagramSection.tsx` — new; props `{ runId: string; detail: RunDetailOut }`; fetches `GET /runs/{runId}/graph` (read graph API path from `RunDiagram.tsx` before writing); loading state → skeleton div; error → `<FailedFetch data-testid="fetch-failed" ... />`; success → SVG with `data-testid="wf-diagram"`, `data-testid="wf-diagram-footer"`, `.wf-diagram-heads`, `diagram-group-{id}`; node onClick: `window.location.assign('#step-{seq}')` (no `?view=detail` prefix — that was only needed when the diagram was a separate view); imports `layoutGraph`, `buildRunTree`, `findCurrentStep`, `DiagramNode`, `DiagramEdge`, `DiagramGroup` from their existing paths (read from `RunDiagram.tsx`)
- `web-client/tests/unit/run-diagram-section.test.ts` — new unit test pair (check-test-pairs.mjs requirement); asserts `typeof DiagramSection === 'function'`; WRITE FIRST (must fail before DiagramSection.tsx exists)

**Frontend — modified island:**
- `web-client/src/islands/RunDetail.tsx` — restructure return JSX: (1) `<Header ... view={undefined} />`; (2) `<Banner ...>`; (3) `<div className="wf-top-zone"><StopBody ... /></div>`; (4) `<div className="wf-diagram-row"><div className="wf-diagram-main"><DiagramSection runId={runId} detail={detail} /></div><div className="wf-summary-col"><StoriesStrip /><CostBlock /><ArtifactsPanel /></div></div>`; (5) `<div className="wf-tabs">` with GATE / STEPS / SESSION tab buttons and panels; import `CommandBlock` from `../components/run/CommandBlock`; import `DiagramSection`; add `activeTab` state with one-shot default via `useRef`

**Frontend — modified StopBody:**
- `web-client/src/components/run/StopBody.tsx:230-238` — read `web-client/tests/unit/run-stop-body.test.ts` first to verify no frozen assertion tests for `wf-terminal` testid inside StopBody; then remove the CommandBlock block; when `terminal?.in_progress` is true, add inline text (e.g. `<span>terminal session in progress — see SESSION tab</span>`) in the action area with no `wf-terminal` testid

**Frontend — Astro page:**
- `web-client/src/pages/workflows/[id].astro` — add early redirect: `if (Astro.url.searchParams.get('view') === 'diagram') return Astro.redirect(\`/workflows/${id}\`, 301)`; remove RunDiagram island mount; always render `<RunDetail ... />`

**Frontend — CSS:**
- `web-client/src/styles/run-detail.css` — add layout rules for `.wf-top-zone`, `.wf-diagram-row`, `.wf-diagram-main`, `.wf-summary-col`, `.wf-tabs`, `.wf-tab-btn`, `.wf-tab-panel`; keep existing classes unchanged

**Frozen files (read to understand; never modify):**
- `web-client/src/islands/RunDiagram.tsx` — read to extract graph API path, response type, SVG testids, DiagramNode/Edge/Group import paths for DiagramSection
- `web-client/src/components/run/CommandBlock.tsx` — read to understand props interface for use in RunDetail SESSION tab
- `web-client/tests/unit/run-command-block.test.ts` — frozen; tests CommandBlock in isolation with `canRelease` prop
- `web-client/tests/unit/run-diagram-svg.test.ts` — frozen; imports RunDiagram
- `web-client/tests/e2e/run-diagram.spec.ts` — frozen; tests `?view=diagram` redirect + same testids in embedded diagram
- `web-client/tests/e2e/run-diagram-error.spec.ts` — frozen; tests graph error → FailedFetch in diagram section only
- `web-client/tests/e2e/run-detail-terminal.spec.ts` — frozen; SESSION tab default, `wf-terminal-release` in one place
- `web-client/tests/unit/run-stop-body.test.ts` — frozen; read before modifying StopBody

## Tasks & Acceptance

**Phase 1 — TDD: write failing tests first (all must fail before Phase 2):**
1. `web-client/tests/unit/run-diagram-section.test.ts` — WRITE FIRST: `typeof DiagramSection === 'function'`; fails because module does not exist
2. `backend-api/tests/unit/test_run_views.py` — WRITE FIRST: assertion that `_header()` populates `Header.model` from `run.inputs.get("model")`; fails because field does not exist
3. `backend-api/tests/unit/test_run_view_schemas.py` — WRITE FIRST: assertion that `HeaderMetaOut` carries `model` from `header.model`; fails because field does not exist

**Phase 2 — exception-4 revision + metaLine (one commit):**
4. `web-client/tests/unit/run-detail-lib.test.ts:376` — revise `joins every meta field in the fixed order` assertion with model slot; add EXPERIENCE-v1.md delta 26 comment
5. `web-client/src/lib/run/detail.ts` — update `metaLine()` to insert model slot

**Phase 3 — backend model field:**
6. `backend-api/src/orchestrator/application/use_cases/run_view_types.py` — add `model: str | None` to `Header`
7. `backend-api/src/orchestrator/application/use_cases/run_views.py` — add `model=run.inputs.get("model")` in `_header()`
8. `backend-api/src/orchestrator/api/schemas/run_views.py` — add `model: str | None = None` to `HeaderMetaOut`; wire in `HeaderOut.of()`
9. `contracts/openapi.json` — `make openapi`
10. `web-client/src/api/schema.d.ts` — `pnpm gen:api`

**Phase 4 — frontend layout:**
11. `web-client/src/components/run/DiagramSection.tsx` — create component
12. `web-client/src/components/run/StopBody.tsx` — remove CommandBlock block; add inline terminal text note
13. `web-client/src/islands/RunDetail.tsx` — restructure to new layout with tabs and DiagramSection
14. `web-client/src/pages/workflows/[id].astro` — add `?view=diagram` redirect; always mount RunDetail
15. `web-client/src/styles/run-detail.css` — add new layout CSS classes

**Acceptance Criteria:**
- Given all changes are committed, when `make lint` runs, then it exits 0 with no errors across ruff, mypy, import-linter, eslint, tsc, and prettier
- Given all changes are committed, when `make test` runs, then it exits 0: new `Header.model` backend coverage passes, revised `run-detail-lib.test.ts` metaLine assertion passes, `run-diagram-section.test.ts` DiagramSection pair passes
- Given all changes are committed, when `make openapi` runs, then it exits 0 and `contracts/openapi.json` contains `model` as a nullable field under `HeaderMetaOut`
- Given `make openapi` ran, when `pnpm gen:api` runs inside `web-client/`, then it exits 0 and `schema.d.ts` contains `model?: string | null` in `HeaderMetaOut`
- Given a run whose `inputs` contains `"model": "claude-opus-5"`, when `GET /runs/{id}/detail` is called, then `header.meta.model` equals `"claude-opus-5"`
- Given a run whose `inputs` does not contain a `model` key, when `GET /runs/{id}/detail` is called, then `header.meta.model` is null
- Given `meta.model` is set, when `metaLine(detail)` is called, then the returned string contains `· {model} ·` between the harness segment and the started_at segment
- Given `meta.model` is null, when `metaLine(detail)` is called, then the returned string contains `· — ·` between the harness segment and the started_at segment
- Given a user navigates to `/workflows/{id}?view=diagram`, when the Astro page handles the request, then the response is a 301 redirect to `/workflows/{id}` with no query parameter
- Given the redirect is followed and RunDetail has loaded, when `make e2e-ui` runs `run-diagram.spec.ts`, then it exits 0 with `data-testid="wf-diagram"` found and diagram content asserted
- Given the graph endpoint returns an error and the redirect is followed, when `make e2e-ui` runs `run-diagram-error.spec.ts`, then it exits 0: `data-testid="fetch-failed"` is visible, `data-testid="wf-diagram"` is absent, and the stop zone and tab region render normally
- Given `detail.run.terminal` is non-null, when RunDetail first renders after detail loads, then the SESSION tab is the active default tab and `CommandBlock` is visible without any tab interaction
- Given the SESSION tab is active and `TERMINAL_RELEASE` is in `admitted_signals`, when `make e2e-ui` runs `run-detail-terminal.spec.ts`, then it exits 0: `data-testid="wf-terminal-release"` appears exactly once in the DOM and clicking it sends the `terminal_release` signal

## Design Notes

**SESSION tab default — one-shot guard:** A `useRef(false)` guard (`tabDefaultSetRef`) in a `useEffect([detail])` sets `activeTab` to `'session'` exactly once on first detail load when `detail.run.terminal` is non-null. Subsequent polls must not reset the tab (the operator may have switched away).

**Partial graph failure isolation:** `DiagramSection` renders `<FailedFetch>` only inside `wf-diagram-main`. The `detail` fetch is independent (already loaded by RunDetail's own poll). Stop zone, summary column, and tabbed region are unaffected by graph fetch failure — this is the partial failure the `run-diagram-error.spec.ts` test expects.

**`wf-terminal` testid placement:** `CommandBlock` owns `data-testid="wf-terminal"` and `data-testid="wf-terminal-release"`. After this story, `CommandBlock` appears only in the SESSION tab panel of RunDetail — never in StopBody. Playwright's strict locators (on `.getByTestId(...)`) require uniqueness; a second instance anywhere would throw.

**Node onClick after `?view=diagram` retirement:** `DiagramSection` uses `window.location.assign('#step-{seq}')`. The `?view=detail` prefix in `RunDiagram.tsx`'s onClick was only needed to navigate back from the diagram view; after retirement the current URL is always the detail view.

**Header `view` prop:** After this story RunDetail passes `view={undefined}` to `Header`. `Header.tsx` already handles `undefined`: when `view` is not `'detail'` or `'diagram'`, it renders `<span aria-disabled="true">DIAGRAM</span>` — a disabled stub with no link.

**`canRelease` derivation:** In the SESSION tab, `canRelease` is `(detail.admitted_signals as readonly string[]).includes(TERMINAL_RELEASE)`. This mirrors the logic StopBody used when it owned CommandBlock.

**`?view=diagram` Astro redirect:** `Astro.redirect(url, 301)` returns a `Response`; `[id].astro` must `return` it before reaching the RunDetail mount. Playwright follows 3xx redirects automatically, so `run-diagram.spec.ts` and `run-diagram-error.spec.ts` work without modification.

**Read RunDiagram.tsx before implementing DiagramSection:** The graph API path (e.g. `GET /runs/{runId}/graph`), response schema type, and SVG component import paths must be extracted from `RunDiagram.tsx` before writing `DiagramSection.tsx`. Do not assume paths — read the source.

**Read run-stop-body.test.ts before modifying StopBody:** Verify no frozen assertion checks for `wf-terminal` inside StopBody before removing CommandBlock. If any such assertion exists, report blocked per AGENTS.md rule 1.

## Verification

**Commands:**
- `make lint` — expected: exit 0
- `make test` — expected: all tests green including new model coverage and revised metaLine assertion
- `make openapi` — expected: exit 0, `model` field in `HeaderMetaOut` in `contracts/openapi.json`
- `cd web-client && pnpm gen:api` — expected: exit 0, no schema drift
- `make e2e-ui` — expected: exit 0; `run-diagram.spec.ts`, `run-diagram-error.spec.ts`, `run-detail-terminal.spec.ts` all pass

## Auto Run Result

Status: blocked
Blocking condition: two frozen assertions in `run-diagram.spec.ts` conflict with authorized story behavior — Operator exception-4 ruling required

### Implementation completed (make lint + make test both exit 0)

All backend and frontend implementation is done. `make lint` exits 0. `make test` exits 0 (6367 backend + 1383 frontend tests). `make openapi` exits 0. Schema regenerated.

### Blocked on: two frozen assertions in `web-client/tests/e2e/run-diagram.spec.ts`

Both assertions pin OLD behavior that story 1-4 explicitly replaces. Neither can be revised without Operator exception-4 authorization.

**Conflict 1 — `'?view=detail (or no view) never calls GET /graph'` (line 486-497)**

The assertion:
```ts
await page.goto(BASE_URL);
await expect(page.getByTestId('wf-header')).toBeVisible();
expect(graphCalled).toBe(false);
```

After story 1-4, `DiagramSection` mounts inside `RunDetail` on every page load and fetches `GET /runs/{id}/graph`. Therefore `graphCalled` is `true` on the base URL. The old behavior (graph only fetched on `?view=diagram`) is exactly what the story retires.

**Required revision:** Change `expect(graphCalled).toBe(false)` → `expect(graphCalled).toBe(true)`. Same commit must assert the new behavior (DiagramSection fetches graph on load).

---

**Conflict 2 — `'toggle shows DIAGRAM as aria-current when ?view=diagram'` (line 499-507)**

The assertion:
```ts
await page.goto(DIAGRAM_URL);
await expect(page.getByTestId('wf-diagram')).toBeVisible();
const toggle = page.getByTestId('wf-toggle-diagram');
await expect(toggle.locator('[aria-current="true"]')).toHaveText('DIAGRAM');
```

After the 301 redirect, `?view=diagram` → `/workflows/{id}` (no view param). `RunDetail` renders with `view={undefined}`, so `Header.tsx` shows DETAIL as `aria-current="true"` and DIAGRAM as `aria-disabled="true"`. The toggle no longer shows DIAGRAM as active — that is exactly the retirement.

**Required revision:** Change assertion to expect DETAIL (not DIAGRAM) to carry `aria-current="true"`. Same commit must assert the new behavior (disabled DIAGRAM stub after retirement).

---

**Authorization request:** Both revisions are authorized by story 1-4 itself (FR-29: `?view=diagram` retired and redirects; diagram embedded in RunDetail). Operator exception-4 classification needed to proceed.
