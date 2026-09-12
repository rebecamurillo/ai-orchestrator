---
title: 'Run diagram view'
type: 'feature'
created: '2026-09-11'
status: 'in-progress'
baseline_revision: 'f5eee3807bb5b4e1062356f2f67fa0e4f68ede71'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** The `DIAGRAM · DETAIL` toggle on the Run detail is a disabled stub (`aria-disabled`). The Operator has no way to view the planned execution graph of a Run as a navigable tree.

**Approach:** Activate `?view=diagram`: create a `RunDiagram` island that polls `GET /runs/{id}/graph` and renders the four-level tree; extend `DiagramNode` in `svg.tsx` with status token, `current` promotion, and sub-step words; wire `[id].astro` to mount `RunDiagram` or `RunDetail` based on `?view=`.

## Boundaries & Constraints

**Always:**
- Group tokens come exclusively from `RunGroupOut.status` (AD-15); the browser derives no status.
- Max one signal colour per node (NFR-6): `data-signal` set only on the wrapping `<g>`, nowhere else.
- `status` has exactly two writers (AD-8); this island never writes or derives Run/Step status.
- Graph endpoint polled only while `?view=diagram` active (handled by conditional island mount in Astro page).
- `schema.d.ts` never hand-edited (AD-3); `RunGraphOut`/`RunNodeOut`/`RunGroupOut` are already generated.

**Block If:**
- Backend `RunGraphOut` nodes do not follow the invariant that story steps have two-segment paths (`epic-X/story-Y/step`) while epic-level steps have one-segment paths (`epic-X/step`); `tree.ts` synthesis depends on this to distinguish story groups from epic-level nodes.

**Never:**
- Change the graph builder beyond bug fixes; modify or delete any pre-existing test file.
- Derive status in the browser; add a second poll interval.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|----------|--------------|-----------------|----------------|
| Running initiative, story 4-1 blocked/current | `?view=diagram`, 2-epic 8-story graph, story 4-1 `current=true token=BLK` | 4 column heads; root `BLK`; epic-1 group `DON`; epic-2 group `BLK`; story 4-1 amber, `now` eyebrow, sub-step words; footer: `step 15 of 22 · epic 2 · story 4-1 · build · blocked 2d 04h · 5/8 stories` | — |
| Cancelled run | Root `status=cancelled`, all groups `status=null` | Groups render no token; root reads `CAN` | — |
| Node click | Any `diagram-node-<path>` clicked | URL becomes `?view=detail#step-{seq}`; `RunDetail` mounts; step row scrolled into view | — |
| Reload with `?view=diagram` | `?view=diagram` in URL | `RunDiagram` mounts; `wf-diagram` testid present | — |
| Graph fetch error | Network failure on `/graph` | `FailedFetch` with Retry; polling stopped | Retry handler calls `fetchGraph` again |

</intent-contract>

## Code Map

- `web-client/src/lib/diagram/svg.tsx:74-83` — `DiagramNodeProps`: has `status?` and `current?` since story 3.6 ("Epic 8 extends these renderers"); add `token?` and `substeps?` here; `DiagramNode:85` renders the node body to extend
- `web-client/src/lib/diagram/svg.tsx:125-135` — `DiagramGroup`: extend with `status?: string | null`; render group token word when not null
- `web-client/src/lib/diagram/layout.ts:93` — `layoutGraph(graph: Graph)`: accepts `{nodes: NodeOut[], edges: EdgeOut[], groups: GroupOut[]}`; `tree.ts` output casts via structural compatibility since `RunNodeOut` extends `NodeOut`
- `web-client/src/islands/Diagram.tsx:34` — existing island; read-only reference; `RunDiagram.tsx` mirrors its SVG render loop
- `web-client/src/islands/RunDetail.tsx:99-108` — mount+poll+unmount pattern to replicate exactly in `RunDiagram`; staleness guard `requestSeqRef` pattern at lines 74,83
- `web-client/src/components/run/Header.tsx:36-39` — toggle stub; add `view?: 'diagram' | 'detail'` prop; replace `aria-disabled` with functional `<a href>` links
- `web-client/src/pages/workflows/[id].astro:17` — currently mounts only `RunDetail`; add `Astro.url.searchParams.get('view')` conditional
- `web-client/src/stores/poll.ts` — `$poll`, `configurePolling(hasRunning)`, `stopPolling()`
- `web-client/src/lib/board/format.ts` — `tokenSignal(token)` maps token string → signal class; already imported by `Header.tsx`
- `web-client/src/lib/run/anchor.ts` — `stepAnchorId(seq)` → `step-{seq}`; used for click-to-row href
- `web-client/src/api/schema.d.ts:1755-1848` — `RunGraphOut`, `RunNodeOut` (fields: `id`, `kind`, `label`, `gate`, `agent`, `human`, `call`, `status: string|null`, `token: string|null`, `current: bool`), `RunGroupOut` (fields: `id`, `label`, `kind`, `members`, `status: string|null`); no changes needed
- `web-client/tests/unit/diagram-svg.test.ts` — existing; MUST NOT modify; new `run-diagram-svg.test.ts` alongside it
- `web-client/src/islands/RunDiagram.tsx` — NEW island (attempt 1); polls both `/detail` and `/graph`; calls `buildRunTree` + `layoutGraph`
- `web-client/src/lib/diagram/tree.ts` — NEW pure module (attempt 1); `buildRunTree` + `findCurrentStep`
- `web-client/tests/unit/run-diagram-tree.test.ts` — NEW unit tests (attempt 1)
- `web-client/tests/unit/run-diagram-svg.test.ts` — NEW unit tests (attempt 1)
- `web-client/tests/e2e/run-diagram.spec.ts` — NEW Playwright e2e tests (attempt 1); 7 tests covering all 5 ACs
- `web-client/tests/e2e/run-diagram-error.spec.ts` — NEW Playwright test (attempt 2); covers the "graph fetch error" I/O matrix row (fetch-failed visible, retry re-calls /graph)

## Tasks & Acceptance

**Execution:**

1. `web-client/src/lib/diagram/svg.tsx` — extend `DiagramNodeProps` with `token?: string | null` and `substeps?: string[] | null`; in `DiagramNode`: (a) add `data-signal={token ? tokenSignal(token) : undefined}` to the wrapping `<g>`; (b) when `current` is true, override eyebrow to `now`; (c) render chip + token right-aligned when `token` present; (d) render substep words when non-empty. All already implemented in attempt 1.

2. `web-client/src/lib/diagram/svg.tsx` — extend `DiagramGroup` with `status?: string | null`; render group token when not null. Already implemented in attempt 1.

3. `web-client/src/lib/diagram/tree.ts` — pure module; `buildRunTree` + `findCurrentStep`. Already implemented in attempt 1.

4. `web-client/src/islands/RunDiagram.tsx` — island polling both endpoints; renders column heads, SVG, footer with current-step data, node click navigates to `?view=detail#step-{seq}`. Already implemented in attempt 1.

5. `web-client/src/components/run/Header.tsx` — `view?` prop; functional toggle `<a href>` links with `aria-current`. Already implemented in attempt 1.

6. `web-client/src/pages/workflows/[id].astro` — conditional mount of `RunDiagram` or `RunDetail` based on `?view=`. Already implemented in attempt 1.

7. `web-client/tests/unit/run-diagram-tree.test.ts` — unit tests for `buildRunTree` and `findCurrentStep`. Already implemented in attempt 1.

8. `web-client/tests/unit/run-diagram-svg.test.ts` — unit tests for extended `DiagramNode`/`DiagramGroup`. Already implemented in attempt 1.

9. `web-client/tests/e2e/run-diagram.spec.ts` — Playwright e2e covering all 5 ACs. Already implemented in attempt 1. Verification requires `make install-e2e` (browser install) before `make e2e-ui`.

**Acceptance Criteria:**
- Given `?view=diagram` in the URL, when the page loads, then `[data-testid="wf-diagram"]` exists and `[data-testid="wf-toggle-diagram"] [aria-current="true"]` reads `DIAGRAM`
- Given a 2-epic 8-story initiative graph with story 4-1 blocked and current, when rendered, then exactly one element inside `[data-testid="wf-diagram"]` carries the amber signal, epic-1's group shows `DON` token, story 4-1's node has `data-current="true"` with sub-step words, and `[data-testid="wf-diagram-footer"]` text matches `step 15 of 22 · … · blocked … · 5/8 stories`
- Given a node click, when it fires, then `window.location.href` contains `?view=detail#step-{seq}`
- Given all `RunGroupOut.status` values are `null` (cancelled run), when rendered, then no group element shows a token and root node `data-testid` reads token `CAN`
- Given `?view=diagram` on reload, when mounted, then `RunDiagram` is active (not `RunDetail`)
- Given `?view=detail` or no view param, when active, then `GET /runs/{run_id}/graph` is never called

## Spec Change Log

## Review Triage Log

## Design Notes

**Story-node synthesis (`tree.ts`):** The brief requires sub-step words inside each story box — not separate coloured dots. Collapsing 4+ step nodes into one story node per story group keeps the dagre rank count manageable (a 2-epic 8-story run would otherwise produce 32+ leaf nodes) and directly models the four column-head layout. The function is pure and unit-tested independently of rendering.

**`Header.tsx` view prop and `<a>` links:** `Header` stays stateless; `RunDetail` omits the prop (defaults to `'detail'`), `RunDiagram` passes `view="diagram"`. Native `<a href>` links mean the Astro SSR page re-renders with the correct island on click — no JS router or `pushState` needed for the toggle itself.

**Attempt 2 context:** Implementation is complete (all files committed in attempt 1). The blocking condition was missing browser OS dependencies for Playwright. The operator has installed the dependencies and requests `make install-e2e` followed by `make e2e-ui`.

## Verification

**Commands:**
- `make install-e2e` — expected: Playwright chromium browser installed successfully
- `make lint` — expected: zero ruff/mypy/eslint/tsc/import-linter errors
- `make test` — expected: all unit tests pass, including `run-diagram-tree.test.ts` and `run-diagram-svg.test.ts`
- `make e2e-ui` — expected: `run-diagram.spec.ts` 7 tests pass
