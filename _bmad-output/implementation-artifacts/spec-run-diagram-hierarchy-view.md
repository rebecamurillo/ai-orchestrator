---
title: 'Run diagram: ranked-column hierarchy on React Flow'
type: 'feature'
created: '2026-09-24'
status: 'done'
review_loop_iteration: 1
baseline_commit: 'a992aa35613c8f281cd86215fe37ecb5232e492e'
context:
  - '{project-root}/web-client/AGENTS.md'
  - '{project-root}/_bmad-output/designs/EXPERIENCE-v1.md'
  - '{project-root}/_bmad-output/designs/mockups/RunDiagram-v3.html'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The run diagram renders every planned row as one node in a single dagre rank, so it draws one meaningless horizontal line. Two causes: the backend graph's edges are a pure `seq` chain with no hierarchy, and `web-client/src/lib/diagram/tree.ts` matches group ids with `/^epic-\d+\/story-[\w-]+$/` while the backend emits `epics[0].stories[3]` — those patterns can never match, so no story ever collapses. The operator cannot see which agents ran for which story, nor that a step was retried.

**Approach:** Rebuild the diagram on React Flow as a left-to-right **ranked-column hierarchy** derived from group-id path prefixes, not from edges. Only agent steps are nodes; deterministic and `checkpoint` rows become a guardrail strip on the epic or story that owns them. Failed attempts draw as chips with dashed retry edges looping back. Cards drag (session-only); an explicit *Open step* CTA replaces click-to-navigate. Spine: EXPERIENCE-v1.md §2.2 *The diagram* (v3, 2026-09-24) and `mockups/RunDiagram-v3.html` are the authority on every visual and behavioural question.

## Boundaries & Constraints

**Always:**
- The four ranks are **R0** run root · **R1** epic · **R2** story + epic-level agents (`spec-gate`, `gen-e2e`, `retro`) · **R3** story agents (`build`). Siblings stack vertically in spec order. Edges join parent rank to child rank only — **never between sibling stories**.
- **Ranks collapse to what exists** *(Operator amendment, 2026-09-24 — intent gap: `DiagramSection` mounts for every Run, but `story@1`, `task@1` and `repo-init@1` plan bare top-level rows and the backend emits no groups, so a fixed four-rank model put an agent under the `EPICS` head and hid every deterministic row).* An empty rank is not drawn and **its column head is not printed**: a Run with no `epics[i]`/`stories[j]` frames draws `RUN · AGENTS`, its agent rows one rank right of the root, and its deterministic rows as the root card's guardrail strip. The heads always describe the columns actually drawn.
- Hierarchy comes from `RunGroupOut.id` path prefixes (`epics[0]`, `epics[0].stories[3]`) and node-id prefix matching. The graph's `edges` array is a `seq` chain and must be ignored for layout.
- A node is drawn only when `RunNodeOut.agent === true`, or it is the root / an epic group / a story group. Everything else is a guardrail entry.
- Failure data comes from a **client-side join** on `path` against `RunDetailOut.steps[]` (already fetched by `RunDetail`). Failed-attempt count is derived: **`attempts` only when the row is `error` or `blocked`** — the agent failed, or handed back unable to finish — and **`attempts - 1` for `done`, `skipped`, `running` and `checkpoint`**, where the newest attempt has not failed. *(Operator correction, 2026-09-24, twice: the original bullet said `attempts` for every non-`done | skipped` row, which contradicted the matrix and the artboard — `StepRowOut.attempts` counts the in-flight attempt. The second correction removes `checkpoint` from the failing set: a checkpoint park is the designed stop, so red `failed` chips there would state a failure the run never had.)* Only the latest failed attempt can state an `exit_code`.
- The blue border belongs to the **current step alone**; a `running` epic or story gets a `line-strong` border plus the blue `RUN` word token. `error | blocked | checkpoint` aggregates keep their coloured border at every level.
- A truncated guardrail strip **never hides a stop**: when more entries exist than fit, any `error | blocked | checkpoint` entry is kept in the visible set ahead of `done | queued | skipped` ones, so the invariant that the path to a stop is findable by colour survives truncation. Visible entries otherwise stay in plan order. *(Operator amendment, 2026-09-24.)*
- A strip that is built is a strip that is **drawn**: no owner may collect guardrail entries it has no renderer for — the root card included.
- Every node carries its word token; colour is never the sole carrier. `skipped`/`cancelled` are never green.
- Layout maths lives in pure `src/lib/` modules, unit-tested under `environment: 'node'` — React Flow is never imported there.
- Import `@xyflow/react/dist/base.css` only; all cosmetics in a repo-owned `src/styles/flow.css` that obeys the stylesheet gate (radius `0`, no `@media`, colours only via `var(--color-*)` from `tokens.css`).
- Keep the React Flow attribution watermark visible.

**Ask First:**
- Any change to an existing file under `web-client/tests/` beyond those named in Execution (these are AD-17 protected paths; the deletions and rewrites below are the declared behaviour change that authorises exactly those).
- Any backend change, contract regeneration, or new field on `RunNodeOut` — this story is front-end only.
- Adding `<MiniMap>`, `<Controls>`, or hiding the attribution.

**Never:**
- No cross-Run initiative DAG (`depends_on`, `after_run_ids`) on this surface.
- No persisted drag positions — session-only, reset on reload.
- No step-level dependency arrows; there is no such data.
- Do not touch the **template** diagram path (`src/islands/Diagram.tsx`, `TemplateDiagram.tsx`, `src/lib/diagram/{layout,svg,diagram-state}.ts`) — it keeps dagre + SVG.
- Do not lower any coverage threshold, add `pragma: no cover`, or weaken the stylesheet gate.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Hierarchy build | graph with groups `epics[0]`, `epics[0].stories[1]`; agent node `epics[0].stories[1].build` | `build` at R3 under story R2 under epic R1 under root R0 | N/A |
| Guardrails | story group whose members include `sync`, `verify`, `commit-guard` (non-agent) | one guardrail strip, 3 entries, each with its status dot; no nodes emitted | N/A |
| Guardrail overflow | epic group with 8 deterministic members | 4 entries then `+4` | N/A |
| Retry chips | step row `attempts: 3`, status `running` | 2 retry chips (`try 1`, `try 2`), each with a dashed edge back | N/A |
| No retries | step row `attempts: 1`, status `done` | no chips, no gutter | N/A |
| Derived failures | step row `attempts: 2`, status `done` | 1 retry chip | N/A |
| Unjoinable node | agent node whose `path` has no matching step row | node renders with token from the graph; no attempts, no CTA target | render node, omit CTA |
| Collapsed epic | epic not on the path to the current step | epic node only, no children, `k/n steps` on the card | N/A |
| Empty plan | `nodes: []` | the words `no steps planned`, no canvas | N/A |
| Graph fetch fails | `GET /runs/{id}/graph` non-2xx | full-surface failed-request readout + retry control; no half-drawn tree | existing `FailedFetch` |
| Poll tick | statuses change while a card is dragged | statuses swap in place; positions and expansion preserved | N/A |
| Run with no frames | graph with no groups; rows `sync`, `build` (agent), `verify`, `commit-guard` | two ranks only, heads `RUN · AGENTS`; `build` one rank right of root; the three deterministic rows in the root card's guardrail strip | N/A |
| Root-owned rows | graph whose `plan` row sits outside every frame | visible as a guardrail entry on the root card | N/A |
| Checkpoint park | agent row `attempts: 2`, status `checkpoint` | 1 retry chip — the newest attempt did not fail | N/A |
| Blocked park | agent row `attempts: 2`, status `blocked` | 2 retry chips — the agent handed back unable to finish | N/A |
| Stop in an overflowing strip | epic strip of 8 rows where the 6th is `blocked` | the blocked entry is among the 4 shown; `+4` covers the rest | N/A |

</frozen-after-approval>

## Code Map

- `web-client/src/components/run/DiagramSection.tsx` (245 L) -- **the live renderer**; mounted by `src/islands/RunDetail.tsx:268`. Owns the `/graph` fetch, `expandedGroups` state, poll re-fetch. Rewrite.
- `web-client/src/lib/diagram/tree.ts` (153 L) -- `buildRunTree`, `findCurrentStep`, and the **broken** `STORY_GROUP_PATTERN` at L25-27. Delete; replaced by `run-tree.ts`.
- `web-client/src/islands/RunDiagram.tsx` (275 L) -- unreachable duplicate of `DiagramSection`; survives only to satisfy `scripts/check-test-pairs.mjs`. Delete.
- `web-client/src/components/run/Header.tsx:24,53-70` -- `view` prop and the `wf-toggle-diagram` DIAGRAM/DETAIL stub. Remove both.
- `web-client/src/pages/workflows/[id].astro:18-20` -- the `?view=diagram` 301 redirect. Remove.
- `web-client/src/lib/step-path.ts` -- `encode`/`decode` bracket ↔ dot-index. Reuse verbatim for the CTA href.
- `web-client/src/lib/diagram/layout.ts` -- existing dagre driver, `rankdir: 'LR'`, no DOM measurement. **Reuse the pattern**, do not modify (template diagram depends on it).
- `web-client/src/lib/run/detail.ts` -- `StepRowOut` type for the client-side join.
- `web-client/src/api/schema.d.ts` -- GENERATED. `RunNodeOut` = `{id, kind, label, gate, agent, human, call, status, token, current}`; `RunGroupOut` = `{id, label, kind, members, status, k, n}`; `StepRowOut` carries `attempts: number` and `latest`. Never hand-edit.
- `web-client/tests/unit/stylesheets.test.ts` -- globs `src/**` only; a `node_modules` CSS import is invisible to it. `src/styles/flow.css` **is** scanned.
- `web-client/scripts/check-test-pairs.mjs` -- every new `src/**/*.{ts,tsx}` must be named by a string in some `tests/unit/` file; deletions are unconstrained.
- `web-client/vitest.config.ts:41-49` -- 90 % lines on `src/lib/**` and `src/stores/**` only; `environment: 'node'`.
- Read-only evidence: `backend-api/src/orchestrator/application/graph.py:389` (`_chain`, the linear edge list) and `:350-358` (`_group_prefixes`, the bracket-index group ids).

## Tasks & Acceptance

**Execution:**
- [x] `web-client/package.json` -- add `@xyflow/react@12.11.6` -- React 19 peer-compatible, MIT, ESM.
- [x] `web-client/src/lib/diagram/run-tree.ts` -- NEW pure module: `buildHierarchy(graph, steps, expanded)` → `{ranks, guardrails, retries}`; derives ranks from group-id prefixes, filters non-agent rows into guardrails, derives failed-attempt counts -- the whole v3 model, node-testable.
- [x] `web-client/src/lib/diagram/flow-layout.ts` -- NEW pure module: hierarchy → React Flow `{nodes, edges}` with dagre-computed positions and the retry gutter -- keeps layout out of the component so the 90 % `src/lib/**` threshold is met without a DOM.
- [x] `web-client/src/components/run/diagram/FlowCanvas.tsx` -- NEW: the `<ReactFlow>` element, `nodeTypes` defined at module scope, `nodesConnectable={false}`, attribution kept.
- [x] `web-client/src/components/run/diagram/nodes.tsx` -- NEW: custom node components (root, epic, story, agent, retry) per the v3 anatomy; the CTA and expand caret are real `<button>`s carrying `nodrag`.
- [x] `web-client/src/components/run/DiagramSection.tsx` -- rewrite: fetch, expansion state, **mount guard** (skeleton until `useEffect` fires, so React Flow never renders server-side — `client:only` cannot reach a child of the `RunDetail` island), footer readout, `fit` / `reset layout` controls.
- [x] `web-client/src/styles/flow.css` -- NEW: `--xy-*` overrides mapped to design tokens; token-only, radius `0`, no `@media`.
- [x] `web-client/src/components/run/Header.tsx`, `web-client/src/pages/workflows/[id].astro` -- delete the `view` prop, the toggle stub and the `?view=diagram` redirect.
- [x] `web-client/src/islands/RunDiagram.tsx`, `web-client/src/lib/diagram/tree.ts` -- delete.
- [x] `web-client/tests/unit/run-tree.test.ts`, `flow-layout.test.ts`, `diagram-nodes.test.ts`, `flow-canvas.test.ts`, `run-diagram-section.test.ts` -- NEW/rewritten unit tests covering every I/O Matrix row; own their fixtures with **real bracket-index group ids**.
- [x] `web-client/tests/unit/run-diagram-tree.test.ts`, `run-diagram-tree-expand.test.ts` -- delete with their module.
- [x] `web-client/tests/unit/run-diagram-svg.test.ts:157-160`, `run-header.test.ts:91` -- remove the `RunDiagram` pairing stub and the `wf-toggle-diagram` assertion; keep every template-diagram assertion intact.
- [x] `web-client/tests/e2e/run-diagram.spec.ts` -- rewrite `twoEpicGraph()` to the real id shape and re-assert against the v3 grammar; `run-diagram-error.spec.ts` keeps its two cases; `run-detail-toggle.spec.ts` deleted; `run-activity.spec.ts` drops `?view=diagram` from its URL.

**Acceptance Criteria:**
- Given a run with 2 epics × 2 stories, when the diagram loads, then the DOM contains four distinct rank columns and no edge joins two sibling story nodes.
- Given a story whose deterministic rows are `sync`, `verify`, `commit-guard`, when it renders, then those three appear only inside `wf-diagram-guardrail-<path>` and emit no node.
- Given an agent step with 3 attempts, when it renders, then 2 retry chips are present, each joined to the agent node by a dashed edge.
- Given any agent node, when its card body is clicked, then no navigation occurs; when `wf-diagram-open-<path>` is clicked, then the browser navigates to `/workflows/{runId}/steps/{dot-path}`.
- Given a dragged card, when the 5 s poll returns new statuses, then tokens update and the card stays where it was put; when the page reloads, then the computed layout returns.
- Given a running run, when the diagram renders, then exactly one node carries a blue border and every running ancestor carries `line-strong` plus the `RUN` token.
- Given `/workflows/:runId?view=diagram`, when requested, then the route serves the run detail with no redirect and no toggle control in the header.

## Spec Change Log

### 2026-09-24 · iteration 1 — two intent gaps, operator-ratified; extended, not reverted

- **Triggering findings.** (a) The verification-gap reviewer executed `buildHierarchy` on a `story@1`-shaped graph (no groups) and got `ranks = [[root], [], [build], []]`, root meta `0 epics · 0 stories`, the agent under the `EPICS` head, every deterministic row invisible — and `DiagramSection` mounts for every Run. (b) Edge-case and blind reviewers both found a `checkpoint`-parked agent row drawing red `try n / failed` chips. (c) All three found the root card building a guardrail strip it never renders, so `plan` — and a hub Run's `checkout`/`submodules` — vanish.
- **Amended.** Frozen `Always` gained the rank-collapse rule, the corrected failed-attempt rule (`error | blocked` count fully, `checkpoint` does not), the stop-survives-truncation rule and the build-implies-draw rule; the matrix gained five rows.
- **Known-bad state avoided.** A diagram that mislabels which column an agent sits in for three shipped templates, hides their deterministic rows outright, and paints a red failure on a run that is merely waiting at a checkpoint.
- **KEEP — must survive re-derivation.** The prefix-derived hierarchy (`parentOf` over bracket-index paths, graph edges ignored) and its 42 tests; the pure `src/lib/` split that keeps layout node-testable without a DOM; the one-blue-node border rule; session-only drag with the `resetKey` merge that holds positions across a poll but re-lays out on expand; the dagre shared-object mutation fix; the real-bracket-id fixtures. The operator chose to extend rather than revert precisely to preserve these.

## Design Notes

Testids per EXPERIENCE-v1 §id grammar, paths in dot-index form: `wf-diagram` · `wf-diagram-node-root` · `wf-diagram-node-<path>` · `wf-diagram-open-<path>` · `wf-diagram-toggle-<path>` · `wf-diagram-guardrail-<path>[-<step-id>]` · `wf-diagram-retry-<path>-<n>` · `wf-diagram-footer` · `wf-diagram-fit` · `wf-diagram-reset`.

Hierarchy is derived by prefix, never by regex on a slugged id — the previous build's defect:

```ts
// epics[0].stories[3].build -> parent epics[0].stories[3] -> parent epics[0] -> root
const parentOf = (id: string) => id.replace(/\.[^.]+$/, '') || ROOT_ID
```

Files stay under the 300-line component limit by splitting `FlowCanvas` (the React Flow element) from `nodes.tsx` (the five card renderers) from `DiagramSection` (fetch + state).

## Verification

**Commands:**
- `cd web-client && pnpm lint` -- expected: eslint, prettier, tsc, `astro check` and `check-test-pairs.mjs` all clean; every new `src/` module named by a test.
- `cd web-client && pnpm test` -- expected: green, `src/lib/**` ≥ 90 % lines, no threshold lowered.
- `make lint && make test` (repo root) -- expected: green, including the stylesheet gate over `src/styles/flow.css`.
- `cd web-client && pnpm e2e` -- expected: green. **Binds 4321, which the running `aio-dev` stack holds — ask the Operator before anything that would free the port (hard rule 9); prefer running the suite against a different port.**

**Manual checks:**
- Open a real run in the dev stack and confirm the tree matches `mockups/RunDiagram-v3.html`: four ranks, guardrail strips quiet, exactly one blue border, retry chips where attempts > 1.

## Suggested Review Order

**The model — hierarchy from path prefixes**

- Start here: the whole design intent. Ranks derived from ids, edges ignored.
  [`run-tree.ts:434`](../../web-client/src/lib/diagram/run-tree.ts#L434)

- The prefix walk that replaces the regex which could never match.
  [`run-tree.ts:275`](../../web-client/src/lib/diagram/run-tree.ts#L275)

- One blue border per run: the current step owns it, ancestors get the word.
  [`run-tree.ts:306`](../../web-client/src/lib/diagram/run-tree.ts#L306)

- `error | blocked` count every attempt; `done | skipped | running | checkpoint` do not.
  [`run-tree.ts:332`](../../web-client/src/lib/diagram/run-tree.ts#L332)

- Keeps the newest chips so the exit code survives an overflowing gutter.
  [`run-tree.ts:345`](../../web-client/src/lib/diagram/run-tree.ts#L345)

- Heads are computed from the columns that exist, so they cannot lie.
  [`run-tree.ts:85`](../../web-client/src/lib/diagram/run-tree.ts#L85)

- Two status vocabularies on purpose: a Run is `failed`, a Step is `error`.
  [`run-tree.ts:71`](../../web-client/src/lib/diagram/run-tree.ts#L71)

**Layout — pure, DOM-free, node-testable**

- Columns from rank, rows from spec order, retry gutter to the right.
  [`flow-layout.ts:204`](../../web-client/src/lib/diagram/flow-layout.ts#L204)

**The surface**

- Fetch, expansion that follows the Run, mount guard, footer.
  [`DiagramSection.tsx:65`](../../web-client/src/components/run/DiagramSection.tsx#L65)

- Node types at module scope; the page scrolls, the canvas pans by drag.
  [`FlowCanvas.tsx:53`](../../web-client/src/components/run/diagram/FlowCanvas.tsx#L53)

- The only navigation: a real link inside a draggable card.
  [`nodes.tsx:75`](../../web-client/src/components/run/diagram/nodes.tsx#L75)

- Guardrails: shape and hue, so colour is never the sole carrier.
  [`strips.tsx:27`](../../web-client/src/components/run/diagram/strips.tsx#L27)

- React Flow cosmetics mapped to design tokens only.
  [`flow.css:1`](../../web-client/src/styles/flow.css#L1)

**Peripherals**

- Fixtures with real bracket-index ids — the wrong shape is what hid the bug.
  [`run-graph.ts:1`](../../web-client/tests/fixtures/run-graph.ts#L1)

- The model's 42 cases, including the frame-less and nested-frame plans.
  [`run-tree.test.ts:1`](../../web-client/tests/unit/run-tree.test.ts#L1)

- 28 browser cases on a frozen clock.
  [`run-diagram.spec.ts:1`](../../web-client/tests/e2e/run-diagram.spec.ts#L1)
