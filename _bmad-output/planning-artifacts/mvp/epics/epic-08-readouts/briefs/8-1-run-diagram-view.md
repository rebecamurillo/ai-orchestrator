---
story: "8-1"
epic: 8
title: Run diagram view
requirements: [FR-29, NFR-2, NFR-6, UX-DR11, UX-DR16, UX-DR18]
binds: [AD-1, AD-15]
---

# Story 8.1 — Run diagram view

As the Operator,
I want to switch the Run detail to a tree that shows what ran, where it is, and what is scheduled,
So that a two-epic, eight-story Run reads from start to finish in one picture that cannot disagree with the table.

## Scope

**In:** the `DIAGRAM · DETAIL` toggle (`?view=diagram`, survives reload), the `RunDiagram` island reusing the `Diagram` island (3.6) with status props, `GET /runs/{id}/graph` on the poll, the footer readout, click-to-row, states, tests.
**Out:** any change to the graph builder (4.12) beyond bug fixes.

## Binding rules (inlined)

- **Layout (UX-DR11).** Same header and banner as the detail; column heads `RUN · EPICS · STORIES · STEPS`; left-to-right tree via dagre with orthogonal `line-strong` connectors and square `surface` nodes; root = the Run (initiative: branch, token, progress; epic Run: the epic); the `plan` row between root and the first epic; level 1 = epic nodes (`epics[i]`, each holding `checkout · baseline` before and `push · link` after its stories); level 2 = story nodes in `stories.yaml` order grouped by path; level 3 = the story's steps.
- **Node.** `row-title` label (the human label), `meta` kind or duration, chip + token right-aligned from the graph's `token`; a story node adds a `micro` row of sub-steps as words (`sync done · build done · verify — · commit —`, `checkpoint` when declared), never as coloured dots; the current node (`current: true`) is promoted to `text` and carries the word `now` in `eyebrow`; scheduled nodes read `QUE` in tertiary. No node carries more than one signal colour.
- **Group tokens** come from the graph's `statuses` (backend rule); the browser derives none; a cancelled Run's groups show no token and the root reads `CAN`.
- **Interaction.** Read-only; clicking a node switches to DETAIL with `#step-{seq}` (7.5's anchor) so the Steps row is scrolled into view.
- **Footer readout** under the tree: `step {seq} of {total} · {label} · {status word} {age} · {stories_done}/{stories_total} stories`.
- **States.** `RUN`: one green node; `BLK`/`CHK`: the stopped node amber, banner above; `DON`: all grey, each `link` node `DON` with its compare link; queued Run: every node `QUE`, root `waiting: {reason}`.
- **Polling:** the same `$poll` store; the graph request only while the diagram view is active.
- **Accessibility:** `role="img"`, `aria-label` `run {branch} · {done}/{total} steps`.
- **Test-ids:** `wf-toggle-diagram`, `wf-diagram`, `diagram-node-<path>`, `diagram-group-<prefix>`, `wf-diagram-footer`.

## Acceptance criteria

**Given** a stubbed initiative graph with two epics, eight stories, story `4-1` blocked
**When** `?view=diagram` renders
**Then** the four column heads appear, the root shows the branch and `BLK`, epic 1's group reads `DON`, epic 2's group `BLK`, story `4-1`'s node is amber with `now` and its sub-step words, the other stories read `QUE`, and the footer reads `step 15 of 22 · epic 2 · story 4-1 · build · blocked 2d 04h · 5/8 stories`.

**Given** the same graph
**When** the Playwright colour scan runs
**Then** exactly one element uses the amber token in the tree (the current node's chip + token) and none the red.

**Given** a node click
**When** it fires
**Then** the URL becomes `?view=detail#step-15` and the Steps row 15 is in view.

**Given** a cancelled Run
**When** rendered
**Then** groups carry no token and the root reads `CAN`.

**Given** a reload with `?view=diagram`
**When** the page loads
**Then** the diagram view is active.

## Implementation notes

- `src/islands/RunDiagram.tsx` composing `Diagram` with `statuses`; `src/lib/diagram/tree.ts` (pure: graph → the four-level layout inputs, unit-tested).
- Extend `Diagram`'s `Node` renderer (3.6 left the props) for `status`, `token`, `current`, sub-step words.
- Playwright `tests/e2e/run-diagram.spec.ts`.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §2.3 Run diagram (verbatim rules), §Naming rule. PRD FR-29. Spine AD-15 (run graph, group rule).
