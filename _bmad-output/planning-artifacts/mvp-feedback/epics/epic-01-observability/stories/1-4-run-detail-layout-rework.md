---
title: "Run detail layout rework"
type: 'feature'
created: '2026-09-16'
status: 'in-progress'
review_loop_iteration: 0
baseline_revision: '0247b2f62e190978897c390f971dc31a3bb5166b'
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The Run detail page scatters information across two views — the detail at `?view=detail` and a separate diagram at `?view=diagram` — and the meta line omits the model used for dispatch (EXPERIENCE-v1.md §2.2 item 11). In addition, two e2e assertions in `run-diagram.spec.ts` pin the old standalone-diagram behavior that story 1-4 explicitly retires.

**Approach:** All backend and frontend restructuring is already committed (attempt 1, commit `ecbcbae`): `Header.model`/`HeaderMetaOut.model` added, `DiagramSection.tsx` embedded in `RunDetail`, `?view=diagram` retired via 301 redirect in `[id].astro`, `metaLine()` updated, `run-detail-lib.test.ts` revised under exception-4, CSS added, openapi/schema regenerated. The sole remaining work is updating the two stale e2e assertions in `run-diagram.spec.ts` that now fail because the diagram is embedded on every page load.

## Boundaries & Constraints

**Always:**
- AGENTS.md rule 1 exception-4 (Operator ruling 2026-09-16): revise exactly the two pinning assertions in `run-diagram.spec.ts`, assert the new behaviour in the same change, and name the decision and its date in a comment in each revised test.
- No other assertion in `run-diagram.spec.ts` may change — only the two lines identified below.
- `make lint` and `make test` green before and after the change.

**Block If:** Any test other than the two targeted assertions fails after the edit — classify and report per AGENTS.md rule 1.

**Never:** Modify `run-diagram-error.spec.ts`, `run-detail-terminal.spec.ts`, `run-command-block.test.ts`, or `run-diagram-svg.test.ts`. Delete `RunDiagram.tsx`. Hand-edit `schema.d.ts`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior |
|----------|--------------|---------------------------|
| Base URL (no view param) | `GET /workflows/{id}` | `DiagramSection` mounts; `GET /runs/{id}/graph` is called; `wf-header` visible |
| Base URL, graph aborted | Graph interceptor aborts call | `graphCalled=true`; `data-testid="fetch-failed"` visible in diagram zone |
| `?view=diagram` URL | Astro 301 redirect | Lands on `/workflows/{id}`; `RunDetail` mounts with embedded diagram; `view={undefined}` passed to `Header` → DETAIL has `aria-current="true"`, DIAGRAM has `aria-disabled="true"` |

</intent-contract>

## Code Map

**Already implemented (commit `ecbcbae` — do not re-implement):**
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` — `Header.model: str | None` added
- `backend-api/src/orchestrator/application/use_cases/run_views.py` — `_header()` wires `model=run.inputs.get("model")`
- `backend-api/src/orchestrator/api/schemas/run_views.py:173` — `HeaderMetaOut.model: str | None = None`
- `backend-api/tests/unit/test_run_view_schemas_model.py` — new; covers `HeaderMetaOut.model` round-trip
- `backend-api/tests/unit/test_run_views.py` — extended with `Header.model` assertion
- `contracts/openapi.json` — regenerated; `model` field in `HeaderMetaOut`
- `web-client/src/api/schema.d.ts` — regenerated; `model?: string | null` in `HeaderMetaOut`
- `web-client/src/lib/run/detail.ts:251` — `metaLine()` inserts `· ${model} ·` between harness and started_at
- `web-client/tests/unit/run-detail-lib.test.ts:376` — exception-4 revision: metaLine assertion updated; EXPERIENCE-v1.md delta 26 comment added
- `web-client/src/components/run/DiagramSection.tsx` — new; props `{ runId, detail }`; fetches graph; renders SVG or FailedFetch
- `web-client/tests/unit/run-diagram-section.test.ts` — new; AD-18 pair for DiagramSection
- `web-client/src/islands/RunDetail.tsx:40` — imports `DiagramSection`; embeds it in `wf-diagram-main`; three tabs (GATE default, STEPS, SESSION when terminal)
- `web-client/src/components/run/StopBody.tsx` — `CommandBlock` removed from stop zone; inline terminal text note added
- `web-client/src/pages/workflows/[id].astro:19` — 301 redirect: `if view=diagram → /workflows/{id}`
- `web-client/src/styles/run-detail.css` — layout classes for `wf-top-zone`, `wf-diagram-row`, `wf-diagram-main`, `wf-summary-col`, `wf-tabs`, `wf-tab-btn`, `wf-tab-panel`

**Remaining work (two assertions only):**
- `web-client/tests/e2e/run-diagram.spec.ts:486–507` — the two stale assertions described below

## Tasks & Acceptance

**Execution:**

- `web-client/tests/e2e/run-diagram.spec.ts` — apply the two exception-4 test revisions:

  **Revision 1 — lines 486-497** (test name: `'?view=detail (or no view) never calls GET /graph'`):
  - Rename test to: `'?view=detail (or no view) calls GET /graph for the embedded diagram'`
  - Add comment: `// Revised: FR-29 + story 1-4 (2026-09-16) — ?view=diagram retired; diagram embedded in RunDetail; graph is always fetched`
  - Change `expect(graphCalled).toBe(false)` → `expect(graphCalled).toBe(true)`
  - Replace `await expect(page.getByTestId('wf-header')).toBeVisible()` with:
    ```ts
    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByTestId('fetch-failed')).toBeVisible(); // graph aborted → DiagramSection error state
    expect(graphCalled).toBe(true);
    ```

  **Revision 2 — lines 499-507** (test name: `'toggle shows DIAGRAM as aria-current when ?view=diagram'`):
  - Rename test to: `'?view=diagram redirects; toggle shows DETAIL as aria-current and DIAGRAM as disabled'`
  - Add comment: `// Revised: FR-29 + story 1-4 (2026-09-16) — ?view=diagram retired via 301; RunDetail renders with view=undefined`
  - Change `await expect(toggle.locator('[aria-current="true"]')).toHaveText('DIAGRAM')` →
    ```ts
    await expect(toggle.locator('[aria-current="true"]')).toHaveText('DETAIL');
    await expect(toggle.locator('[aria-disabled="true"]')).toHaveText('DIAGRAM');
    ```

**Acceptance Criteria:**
- Given `page.goto(BASE_URL)` with the graph route intercepted and aborted, when `wf-header` is visible and the graph fetch settles, then `graphCalled` is `true` and `data-testid="fetch-failed"` is visible
- Given `page.goto(DIAGRAM_URL)` (301 redirect to `/workflows/{id}`), when `wf-diagram` is visible, then `[aria-current="true"]` inside `wf-toggle-diagram` reads `DETAIL` and `[aria-disabled="true"]` reads `DIAGRAM`
- Given all changes, when `make test` runs, then it exits 0 with no failures
- Given all changes, when `make lint` runs, then it exits 0

## Design Notes

**Why `fetch-failed` is visible:** The test aborts the graph call (`route.abort()`). After the redirect lands RunDetail, `DiagramSection` fetches graph, gets an abort error, and renders `<FailedFetch>`. Waiting on `fetch-failed` is the hydration gate confirming the island mounted and the fetch completed — only then is `graphCalled` reliably `true`.

**No `await` ordering issue on `graphCalled`:** `await expect(page.getByTestId('fetch-failed')).toBeVisible()` implies the graph fetch completed before the assertion passes; by the time the `expect(graphCalled).toBe(true)` synchronous check runs, the interceptor has already set the flag.

## Verification

**Commands:**
- `make lint` -- expected: exit 0
- `make test` -- expected: exit 0, all 6367+ backend and 1383+ frontend tests green
