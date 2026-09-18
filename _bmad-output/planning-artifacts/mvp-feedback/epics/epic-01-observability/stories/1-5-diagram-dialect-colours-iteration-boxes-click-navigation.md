---
title: "Diagram dialect — colours, iteration boxes, click navigation"
type: 'feature'
created: '2026-09-16'
status: 'in-review'
review_loop_iteration: 0
baseline_revision: '26204f106beed3499db0717623d1eb038d2f4954'
followup_review_recommended: false
context: []
warnings: ['oversized']
deferred: []
---

<intent-contract>

## Intent

**Problem:** The embedded run diagram renders all nodes in one accent colour regardless of status, shows no step-count for group boxes, and clicking any node scrolls to a `?view=detail#step-{seq}` anchor on the current page — none of which matches the AD-15 dialect or the step-run detail navigation landing in story 1-2.

**Approach:** Add k/n computation to the backend `groups` payload; map stored status tokens to border colours in CSS per the AD-15 table; upgrade `DiagramGroup` to display label, chip+token, and k/n; add expand/collapse state to `DiagramSection` so group boxes expand one level per click with the path to the current node pre-expanded and graph-poll updates preserving that state; route leaf-node clicks to `/workflows/{runId}/steps/{encode(node.id)}`; retire `?view=detail#step-{seq}` from both `DiagramSection` and the retired `RunDiagram` island.

## Boundaries & Constraints

**Always:**
- TDD (AD-18): new test files exist and fail before their paired modules are touched; no new doubles for ports that already have fakes.
- `--color-signal-criterion: #6C8CD5` enters `tokens.css` exactly for the diagram surface (SPEC.md); `skipped`/`cancelled` never green (NFR-2); word token always beside colour (NFR-6 exemption applies to diagram only).
- No node carries two status colours; colour comes only from CSS `data-status` selectors, never inline style.
- AD-8: this epic reads state only; no status writes anywhere.
- AD-3: `schema.d.ts` never hand-edited; `make openapi` + `pnpm gen:api` regenerate it.
- Anchors read-only (AGENTS.md rule 1): one exception-4 revision required — `run-diagram.spec.ts` test (c), authorized by stories.yaml 1-5 "no click-scrolls behaviour remains" + "leaf node navigates to Step-run detail" (Operator ruling, 2026-09-16). Same commit asserts new navigation behaviour; comment in revised test names decision and date.
- `test_graph_schemas.py` pins template `GroupOut` (4 keys) only — `RunGroupOut` is unpinned; adding `k`/`n` is safe.
- Existing test files (`test_run_graph.py`, `run-diagram-section.test.ts`, `run-diagram-tree.test.ts`, etc.) are read-only; add new files.

**Block If:** Any pre-existing test fails after a change — classify per AGENTS.md rule 1 before proceeding.

**Never:** Navigate to `?view=detail#step-{seq}` from any node click. Expose k/n on template `GroupOut` (template graphs have no statuses). Add inline `style` colour on SVG elements.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `done` node/group | `status='done'` | green border (`--color-signal-run`) + "DON" word | No error |
| `running` node/group | `status='running'` | blue border (`--color-signal-criterion`) + "RUN" word | No error |
| `error` node | `status='error'` | red border (`--color-signal-failed`) + "ERR" word | No error |
| `blocked`/`checkpoint` | `status='blocked'\|'checkpoint'` | amber border (`--color-signal-needs-you`) + token word | No error |
| `planned`/`queued` | `status='planned'\|'queued'` | grey border + token word | No error |
| `skipped`/`cancelled` | `status='skipped'\|'cancelled'` | faint-grey border, never green | No error |
| Group k=3 n=5 | 3 done, 1 skipped, 1 planned among 5 members | group box shows "3/5 steps" | No error |
| All-skipped group | all members skipped → n=0 | group box shows no count | No error |
| Story aggregate click (collapsed) | `node.kind==='story'`, group not in `expandedGroups` | group expands; member step nodes become visible | No error |
| Leaf step click | `node.kind!=='story'`, `nodeSeq` non-null | navigate to `/workflows/${runId}/steps/${encode(node.id)}` | No error |
| Poll tick | `$poll` fires, graph re-fetched | node statuses update in place; `expandedGroups` unchanged | Preserve state |
| Current node on mount | `findCurrentStep` non-null | story group(s) containing current step start expanded | No error |

</intent-contract>

## Code Map

**Backend — modified:**
- `backend-api/src/orchestrator/application/graph_schema.py:92` — `Group` model; add `k: int = 0` and `n: int = 0` (0 defaults keep template-graph `Graph()` construction unchanged)
- `backend-api/src/orchestrator/application/graph.py:361` — `_group(prefix, rows, *, cancelled)`; after computing `members` (the `StepRun` list), add `k = sum(1 for m in members if m.status == "done")` and `n = sum(1 for m in members if m.status != "skipped")`; pass to `Group(... k=k, n=n)`; for cancelled groups, k/n are still computed from member statuses (status field on each StepRun)
- `backend-api/src/orchestrator/api/schemas/graph.py:179` — `RunGroupOut`; add `k: int` and `n: int` fields; update `RunGraphOut.of()` (or equivalent mapping) to pass `group.k` and `group.n`; template `GroupOut` at line 98 is unchanged

**Backend — new:**
- `backend-api/tests/unit/application/test_run_graph_kn.py` — WRITE FIRST; covers: all-done group (k=n=total); mixed group (k=done count, n=total−skipped); all-skipped group (k=0, n=0); k and n present on `RunGroupOut` via HTTP round-trip through `GET /runs/{run_id}/graph` router using `FakeStepRunRepository`

**Frontend CSS — modified:**
- `web-client/src/styles/tokens.css` — add `--color-signal-criterion: #6C8CD5`; place beside existing signal tokens
- `web-client/src/styles/diagram.css` — add status→colour rules AFTER the existing `.diagram-node[data-agent='true'] .diagram-node-box` rule so equal-specificity rules win. Node box selectors: `.diagram-node[data-status='X'] .diagram-node-box` (class `.diagram-node` on outer `<g>`, `.diagram-node-box` on `<rect>`, specificity 0,3,0 — matches agent rule). Group box selectors: `.diagram-group[data-status='X'] .diagram-group-box` (class `.diagram-group` on outer `<g>`, `.diagram-group-box` on `<rect>`, already present). Chip fill selectors: `.diagram-node[data-status='X'] .diagram-node-chip` and `.diagram-group[data-status='X'] .diagram-group-chip` for fill. Status map:
  - `done` → `stroke/fill: var(--color-signal-run)` (green)
  - `running` → `stroke/fill: var(--color-signal-criterion)` (#6C8CD5 blue)
  - `error` → `stroke/fill: var(--color-signal-failed)` (red)
  - `blocked`, `checkpoint` → `stroke/fill: var(--color-signal-needs-you)` (amber)
  - `planned`, `queued` → `stroke: var(--color-line)` (grey, same as default — chip fill same)
  - `skipped`, `cancelled` → `stroke: var(--color-line); opacity: 0.4` on box; chip fill same faint grey
  - No changes to the existing agent rule; status rules placed after it win by source-order

**Frontend SVG — modified:**
- `web-client/src/lib/diagram/svg.tsx:DiagramGroup` (line 185) — (1) add props `k?: number | null; n?: number | null`; (2) add `data-status={status ?? undefined}` to the existing outer `<g className="diagram-group">`; (3) add a module-level `STATUS_TOKEN` map (`{ running: 'RUN', done: 'DON', blocked: 'BLK', checkpoint: 'CHK', error: 'ERR', skipped: 'SKP', queued: 'QUE', cancelled: 'CAN', planned: 'QUE' }`) and use it to derive the 3-letter display token; (4) replace the existing `diagram-group-token` raw-status text with chip `<circle className="diagram-group-chip">` + `<text className="diagram-group-token">` showing the 3-letter token (using existing CHIP_RADIUS/TOKEN_INSET/CHIP_OFFSET_Y constants), positioned at top-right inside the box; (5) when `(n ?? 0) > 0`, add `<text className="diagram-group-kn">` showing `{k}/{n} steps` at the bottom inside the box. The `diagram-group-label` text ABOVE the box is unchanged — keep it as-is. No class changes to `<rect>` (already has `diagram-group-box`).

**Frontend diagram lib — modified:**
- `web-client/src/lib/diagram/tree.ts` — (1) export `STORY_GROUP_PATTERN` (currently unexported); (2) add second param `expandedGroups: Set<string> = new Set()` to `buildRunTree`; (3) for story groups in `expandedGroups`, skip synthesis — pass their member nodes through individually and rebuild edges through them instead of through the aggregate node; story group itself is excluded from the returned `groups` list (it's now shown as individual nodes, no collapse box)

**Frontend DiagramSection — modified:**
- `web-client/src/components/run/DiagramSection.tsx` — (1) add `import { encode } from '../../lib/step-path'`; (2) add `import { useStore } from '@nanostores/react'` and `import { $poll } from '../../stores/poll'`; (3) add `const pollTick = useStore($poll)` and a `useRef` for mounted tick; (4) add `const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())`; (5) in graph fetch success callback: compute initial expansion — find `findCurrentStep(result.data)`, then `result.data.groups.filter(g => STORY_GROUP_PATTERN.test(g.id) && g.members.includes(currentStep.id)).map(g => g.id)` → `setExpandedGroups(new Set(ancestorIds))` only on the FIRST fetch (guard with a `initializedRef`); (6) add `useEffect(() => { if (pollTick === mountedTickRef.current) return; void fetchGraph(); }, [pollTick])` — re-fetches graph on poll tick, `expandedGroups` state is NOT reset; (7) pass `expandedGroups` to `buildRunTree(graph, expandedGroups)` in `useMemo` dep array; (8) pass `k={runGroup.k ?? 0}` and `n={runGroup.n ?? 0}` to `DiagramGroup`; (9) replace click handler: story aggregate nodes (`placed.node.kind === 'story'`) → `setExpandedGroups(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; })`; step leaf nodes (`nodeSeq(placed.node.id, detail.steps) !== null`) → `window.location.assign(`/workflows/${runId}/steps/${encode(placed.node.id)}`)` ; (10) remove `?view=detail#step-${stepSeq}` navigation entirely; (11) remove stale comment about frozen test; (12) `nodeSeq` is still used only to determine whether a node is a clickable leaf step (non-null = is step)

**Frontend RunDiagram — modified:**
- `web-client/src/islands/RunDiagram.tsx` — add `import { encode } from '../lib/step-path'`; replace `window.location.assign(`?view=detail#step-${stepSeq}`)` with `window.location.assign(`/workflows/${runId}/steps/${encode(placed.node.id)}`)` using the existing `runId` from the island's own detail fetch; `nodeSeq` logic unchanged for leaf detection

**Contract:**
- `contracts/openapi.json` — regenerate via `make openapi`; `k` and `n` appear in `RunGroupOut` schema
- `web-client/src/api/schema.d.ts` — regenerate via `pnpm gen:api`

**Exception-4 revision:**
- `web-client/tests/e2e/run-diagram.spec.ts:428` — test (c) pins `?view=detail#step-\d+` click, retired by story 1-5; authorization: stories.yaml 1-5 "no click-scrolls behaviour remains" + "leaf node navigates to Step-run detail (story 1-2)" (Operator ruling, 2026-09-16). Revision: rename to `'(c) clicking a story aggregate expands it; clicking a step leaf navigates to step-run detail'`; add comment `// Revised: story 1-5 (2026-09-16) — no click-scrolls behaviour; group boxes expand; leaf nodes navigate to step-run detail`; change body to: (1) click story aggregate → assert a member step node (e.g. `diagram-node-epic-2/story-4-1/build`) becomes visible; (2) click step node → `expect(page).toHaveURL(/\/workflows\/[^/]+\/steps\//)` (URL contains `/steps/` path)

**New unit test files:**
- `backend-api/tests/unit/application/test_run_graph_kn.py` — described above
- `web-client/tests/unit/run-diagram-tree-expand.test.ts` — WRITE FIRST; imports `buildRunTree` from `../../src/lib/diagram/tree`; asserts: `buildRunTree(graph, new Set(["epic-2/story-4-1"]))` → story-4-1 members appear as individual nodes (no aggregate); `buildRunTree(graph, new Set())` → story-4-1 is collapsed as before (one node per story)
- `web-client/tests/unit/diagram-group-kn.test.ts` — WRITE FIRST (minimal AD-18 pair); `typeof DiagramGroup === 'function'`

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/application/test_run_graph_kn.py` -- WRITE FIRST (TDD): all k/n scenarios; every test must fail before Group/RunGroupOut changes
- `web-client/tests/unit/run-diagram-tree-expand.test.ts` -- WRITE FIRST (TDD): buildRunTree expansion tests; must fail before tree.ts changes
- `web-client/tests/unit/diagram-group-kn.test.ts` -- WRITE FIRST (TDD): minimal function check; must fail before svg.tsx DiagramGroup changes
- `backend-api/src/orchestrator/application/graph_schema.py` -- add `k: int = 0` and `n: int = 0` to `Group`
- `backend-api/src/orchestrator/application/graph.py` -- compute k/n in `_group()`
- `backend-api/src/orchestrator/api/schemas/graph.py` -- add `k: int` and `n: int` to `RunGroupOut`; map in `.of()`
- `contracts/openapi.json` -- run `make openapi`
- `web-client/src/api/schema.d.ts` -- run `pnpm gen:api` in `web-client/`
- `web-client/src/styles/tokens.css` -- add `--color-signal-criterion: #6C8CD5`
- `web-client/src/styles/diagram.css` -- add all `[data-status]` colour rules using existing `.diagram-node`/`.diagram-node-box`/`.diagram-group`/`.diagram-group-box`/`.diagram-node-chip`/`.diagram-group-chip` class names
- `web-client/src/lib/diagram/svg.tsx` -- add `className` to rects; update DiagramGroup with data-status, label, chip+token, k/n; update DiagramNode rect className
- `web-client/src/lib/diagram/tree.ts` -- export `STORY_GROUP_PATTERN`; add `expandedGroups` param; pass through expanded-group members
- `web-client/src/components/run/DiagramSection.tsx` -- expand/collapse state, poll hook, step-run navigation, k/n props passthrough; remove old navigation
- `web-client/src/islands/RunDiagram.tsx` -- update click handler to step-run detail URL
- `web-client/tests/e2e/run-diagram.spec.ts` -- exception-4 revision of test (c)

**Acceptance Criteria:**
- Given `GET /runs/{id}/graph` after story 1-5, when a group has 3 done members and 2 non-skipped non-done members, then `RunGroupOut.k === 3` and `RunGroupOut.n === 5`
- Given all group members are skipped, when the graph is fetched, then `k === 0` and `n === 0`; the frontend renders no count text inside that group box
- Given a `running` node, when the diagram renders, then its box border uses `--color-signal-criterion` (#6C8CD5) and the word "running" appears beside the colour
- Given a `done` node, when rendered, then green border and "DON" word; `skipped` node has faint-grey border, never green
- Given the diagram loads with a running step inside story group G, when the diagram mounts, then group G starts expanded and individual step nodes are visible
- Given a collapsed story aggregate node is clicked, when the click fires, then its member step nodes appear in the diagram without any URL change
- Given an expanded story's leaf step node is clicked, when the click fires, then the browser navigates to `/workflows/{runId}/steps/{dot-index-path}` — no `?view=detail` or `#step-` fragment in the URL
- Given `$poll` fires and the graph is re-fetched with updated statuses, when statuses change, then node border colours update in place and no previously expanded group collapses
- Given `make openapi` then `pnpm gen:api` after all changes, then both exit 0 with no schema drift (AD-3)

## Design Notes

**k/n semantics:** n = count of members with `status != "skipped"` (includes done, running, planned, queued, error, blocked, checkpoint, cancelled). k = count with `status == "done"`. An all-skipped group has n=0; the frontend suppresses the count text when `n === 0`. For cancelled runs, members still have explicit statuses so k/n are informative.

**Group border colour for aggregate nodes:** Story aggregate nodes (`kind === 'story'`) carry `status` and `token` inherited from the current member (or group status). The same `data-status` attribute and CSS rule set drives their colour. No separate code path needed — the existing `DiagramNode` `data-status` attribute already covers them.

**`expandedGroups` and `useMemo` dependency:** `const tree = useMemo(() => buildRunTree(graph, expandedGroups), [graph, expandedGroups])`. Poll re-fetches graph (new statuses) → tree recomputes with unchanged `expandedGroups` → statuses update, expansion preserved. Expand click → new `expandedGroups` → tree recomputes, group expands.

**Initial expansion guard:** Use an `initializedRef = useRef(false)` in `DiagramSection`. Set it on the first successful graph fetch after computing ancestor story groups. Subsequent graph fetches (poll) skip the init step — they must never reset `expandedGroups`.

**Exception-4 — test (c):** The revised test first clicks the story aggregate, waits for a member step node to become visible (proving expansion), then clicks that step node and asserts the URL contains `/steps/`. This is a two-step user flow that strictly exceeds the old single-click URL assertion.

## Verification

**Commands:**
- `make lint` -- expected: exit 0
- `make test` -- expected: all tests green, including `test_run_graph_kn.py`, `run-diagram-tree-expand.test.ts`, `diagram-group-kn.test.ts`
- `make openapi` -- expected: exit 0; `k` and `n` present in `RunGroupOut` in `contracts/openapi.json`
- `cd web-client && pnpm gen:api` -- expected: exit 0, no schema drift
- `make e2e-ui` -- expected: exit 0; revised test (c) passes asserting expansion then step-detail navigation

## Spec Change Log

## Review Triage Log
