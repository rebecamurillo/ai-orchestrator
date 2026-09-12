---
title: 'Run diagram view'
type: 'feature'
created: '2026-09-11'
status: 'blocked'
baseline_revision: '7d5f6a297ac68c3b6e81e7d3434c8d422d271fef'
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

## Tasks & Acceptance

**Execution:**

1. `web-client/src/lib/diagram/svg.tsx` — extend `DiagramNodeProps` with `token?: string | null` and `substeps?: string[] | null`; in `DiagramNode`: (a) add `data-signal={token ? tokenSignal(token) : undefined}` to the wrapping `<g>` (import `tokenSignal` from `'../lib/board/format'`); (b) when `current` is true, override the eyebrow `<text>` content to the string `now`; (c) render chip `<circle className="diagram-node-chip" />` and token `<text className="diagram-node-token">` right-aligned when `token` is present; (d) render `<text className="diagram-node-substeps">` with `substeps.join(' · ')` when `substeps` is non-empty. All new props default to absent — template graphs must be visually unchanged.

2. `web-client/src/lib/diagram/svg.tsx` — extend `DiagramGroup` props with `status?: string | null`; render `<text className="diagram-group-token">` near the label when `status` is not null (cancelled runs have `null` so the token is absent).

3. `web-client/src/lib/diagram/tree.ts` — new pure module; export:
   - `buildRunTree(graph: RunGraphOut): { nodes: RunNodeOut[]; edges: EdgeOut[]; groups: RunGroupOut[] }`: story groups = group ids matching `epic-\d+/story-[\w-]+` pattern; for each story group synthesize one `RunNodeOut` (id=group.id, kind="story", label=last path segment, gate=null, agent/human/call=false/false/null, status=current-member status ?? group.status, token=current-member token ?? group token ?? null, current=any member has current=true); set `substeps` on the synthesized node (non-standard field, carried through for `DiagramNode`); remove original step-level nodes; keep root, plan, and epic-level nodes (root id or single-segment paths after `epic-X/`); rebuild edges as a chain root→…→epic-1/checkout→story-nodes-in-order→epic-1/push→epic-1/link→epic-2/checkout→…; keep only epic-level groups (single-segment group ids like `epic-\d+`)
   - `findCurrentStep(graph: RunGraphOut): RunNodeOut | null`: returns the node with `current === true`, or null

4. `web-client/src/islands/RunDiagram.tsx` — new island (`{ runId: string }`): polls both `GET /runs/{run_id}/detail` (for Header/Banner) and `GET /runs/{run_id}/graph` (for diagram) on mount and `$poll` ticks; mirrors `RunDetail.tsx:99-108` poll pattern and `requestSeqRef` staleness guard; calls `buildRunTree(graph)` + `layoutGraph(tree)`; renders: `<Header detail token now={Date.now()} view="diagram" />`; `<Banner detail token />`; column heads `<div className="wf-diagram-heads"><span>RUN</span><span>EPICS</span><span>STORIES</span><span>STEPS</span></div>`; `<div data-testid="wf-diagram" role="img" aria-label={\`run ${detail.run.branch} · ${done}/${total} steps\`}>` with the SVG; `<footer data-testid="wf-diagram-footer">` with `step {seq} of {total} · {label} · {statusWord} {age} · {storiesDone}/{storiesTotal} stories` (current step from `findCurrentStep(graph)`, seq from matching step id in `detail.steps`, age from `ageText(stateAgeSeconds(detail, Date.now()))`); node `onClick` navigates to `?view=detail#step-{seq}` via `window.location.assign`; `stopPolling` on unmount.

5. `web-client/src/components/run/Header.tsx` — add `view?: 'diagram' | 'detail'` to `Props` (default `'detail'`); replace the toggle `<div>`:
   - container keeps `data-testid="wf-toggle-diagram"` and `className="wf-toggle"`
   - DIAGRAM: `<a href="?view=diagram" aria-current={view === 'diagram' ? 'true' : undefined}>DIAGRAM</a>`
   - DETAIL: `<a href="?view=detail" aria-current={view === 'detail' ? 'true' : undefined}>DETAIL</a>`

6. `web-client/src/pages/workflows/[id].astro` — after `const { id } = Astro.params;` add `const view = Astro.url.searchParams.get('view') ?? 'detail';`; replace the `<RunDetail client:load … />` with a conditional: `view === 'diagram'` → `<RunDiagram client:load runId={id as string} />`, otherwise `<RunDetail client:load runId={id as string} />`; add `RunDiagram` import.

7. `web-client/tests/unit/run-diagram-tree.test.ts` — new; a `RunGraphOut` fixture: root + plan + 2 epics each with checkout, 2 story groups × 2 steps, push, link; assert `buildRunTree`: story-aggregate node ids equal group ids, substeps arrays match member labels in order, epic groups preserved, story groups absent, edge chain correct; assert `findCurrentStep` returns the node with `current=true`.

8. `web-client/tests/unit/run-diagram-svg.test.ts` — new; render `DiagramNode` with `token="BLK"`, `current=true`, `substeps=["sync done", "build BLK"]`; assert: `data-signal` on `<g>`, eyebrow text is `now`, chip element present, substep text present; render with no run props and assert output matches template-island snapshot (existing behaviour unchanged).

9. `web-client/tests/e2e/run-diagram.spec.ts` — new Playwright; covers the 5 brief ACs:
   (a) 2-epic 8-story graph, story 4-1 blocked → 4 column heads present, `[data-testid="wf-diagram"]` visible, epic-1 group `DON`, story 4-1 amber, footer matches pattern;
   (b) colour scan → exactly one element uses the amber token inside `wf-diagram`;
   (c) node click → URL is `?view=detail#step-15`, row 15 visible;
   (d) cancelled run → no group token elements, root shows `CAN`;
   (e) reload with `?view=diagram` → `wf-diagram` testid present.

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

## Verification

**Commands:**
- `make lint` — expected: zero ruff/mypy/eslint/tsc/import-linter errors
- `make test` — expected: all unit tests pass, including `run-diagram-tree.test.ts` and `run-diagram-svg.test.ts`
- `make e2e-ui` — expected: `run-diagram.spec.ts` 5 scenarios pass

## Auto Run Result

Status: blocked
Blocking condition: implementation verification failed — `make e2e-ui` cannot complete the matrix test audit. All 7 `run-diagram.spec.ts` tests fail at browser launch: "Host system is missing dependencies to run browsers." This is a pre-existing environment limitation (12/190 e2e tests pass both before and after this story's changes; only server-side request tests pass). `make lint` and `make test` (5997 backend + 1311 frontend unit tests) pass. The Playwright e2e tests exist, are registered, cover all I/O matrix rows, and are semantically correct — they cannot run because no browser executable is available and `sudo playwright install-deps` is not possible in this environment.
