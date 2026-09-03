---
story: "3-6"
epic: 3
title: Template diagram rendered from the backend graph
requirements: [FR-7, NFR-2, NFR-6, UX-DR15, UX-DR11 (shared drawing rules), UX-DR18]
binds: [AD-1, AD-15]
---

# Story 3.6 — Template diagram rendered from the backend graph

As the Operator,
I want the Template's graph drawn beside the YAML, left to right, updating each time the editor validates and holding the last valid picture when it does not,
So that I read the structure of a workflow at a glance without trusting the browser to interpret it.

## Scope

**In:** the reusable `Diagram` island (`src/islands/Diagram.tsx`: dagre layout + SVG rendering of a `Graph`), its use in the Templates screen fed by `GET /templates/{name}/{v}/graph` and by the validate response, the last-valid rule, tests.
**Out:** run statuses, tokens, `now`, click-to-row (Epic 8 extends the same island); any editing in the diagram.

## Binding rules (inlined)

- **Layout.** `@dagrejs/dagre` 3.1.1, `rankdir: LR`, orthogonal hairline connectors in `line-strong`, square nodes on `surface` with a `line` border, radius 0, no shadows; groups (`for_each`) drawn as a dashed `line-strong` rectangle around their members with the loop id as a `column-head` label; the SVG scales to the column width and scrolls horizontally inside its own container when wider (the page never scrolls horizontally).
- **Node anatomy (UX-DR15).** Eyebrow line: the kind (`git.worktree`, `agent`, `template`, …) in `eyebrow` type; title: the node label in `row-title`; footer: the gate as a word (`deterministic`, `liveness`, `human`, `unvalidated`) in `meta`. An `agent` node has an `accent` border. A collapsed `template` call shows `{name}@{version}` as its title and `template` as its eyebrow. A `human` gate node shows the word `human` and a `line-strong` hairline under it, never amber. `unvalidated` is a plain word.
- **No signal colour anywhere** in the template diagram (nothing is running).
- **Refresh rule (FR-7).** The screen loads the stored version's graph on open. Every successful validation of the editor content replaces the diagram with a graph built from the validated text: the island calls `POST /templates/{name}/validate` and, when there are no errors, `GET`s the graph for… (the graph endpoint takes a stored version; for unsaved text add `POST /api/v1/templates/{name}/graph` with `{yaml}` → `Graph` or 422, in this story, backend included). When validation has errors the diagram is unchanged and the line `diagram from last valid version` appears above it.
- **Read-only.** No drag, no add, no edit; nodes are not interactive here (Epic 8 adds click for the run diagram).
- **Accessibility.** The SVG has `role="img"` and an `aria-label` `template {name} v{n} · {nodes} steps`; node text uses the type tokens.
- **Test-ids:** `templates-diagram`, `diagram-node-<id>`, `diagram-group-<id>`, `templates-diagram-stale`.

## Acceptance criteria

**Given** `/templates/epic/1`
**When** rendered
**Then** the diagram shows nodes `checkout`, `baseline`, `stories.story` (title `story@1`), `stories.after` (word `human`), `push`, `link`, left to right, with the dashed group `stories` around the two loop nodes, and no amber or red pixel.

**Given** the editor content changed to something valid with a new step
**When** validation succeeds
**Then** the diagram redraws with the new node within the same poll cycle and no `templates-diagram-stale` line is shown.

**Given** the editor content changed to something invalid
**When** validation fails
**Then** the diagram is unchanged and the line `diagram from last valid version` is shown.

**Given** a graph with an `unvalidated` node
**When** drawn
**Then** the node's footer reads `unvalidated` in plain text.

**Given** `story@1`
**When** drawn
**Then** the `build` node has the accent border and the eyebrow `agent`.

**Given** the backend
**When** `POST /templates/story/graph` is called with valid YAML text
**Then** it returns the graph; with invalid YAML it returns 422 with the validator's errors.

## Implementation notes

- `src/islands/Diagram.tsx` props `{graph, ariaLabel}`; `src/lib/diagram/layout.ts` (pure: graph → positioned nodes/edges/groups, unit-tested with dagre); `src/lib/diagram/svg.tsx` renderers. Design the `Node` renderer to accept an optional `status` and `current` prop (unused now) so Epic 8 adds tokens without restructuring.
- Backend: `POST /api/v1/templates/{name}/graph` `{yaml}` in `api/routers/templates.py` calling `validate()` then `build_template_graph()`; run `make openapi`.
- Playwright `tests/e2e/template-diagram.spec.ts`; Vitest for `layout.ts` and the stale rule.

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §5 Templates (diagram), §2.3 (drawing rules shared with the run diagram). PRD FR-7, NFR-2. Spine AD-15. `DESIGN.md` (hairlines, shapes, typography roles).
