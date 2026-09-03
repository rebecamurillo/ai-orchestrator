---
id: SPEC-mvp-epic-08-readouts
companions: []
sources:
  - ../../prd.md
  - ../../architecture/ARCHITECTURE-SPINE.md
  - ../../../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
  - ../../../ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md
---

> **Canonical contract for Epic 8.** Each story's full requirements live in `briefs/<id>-<slug>.md`, named from `stories.yaml` `invoke_dev_with`. Read the brief for the story you are dispatched on; do not read the other briefs. The repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when a brief and the code disagree.

# Epic 8 — Run diagram and readout completions

## Why

A vision to complete: the Operator should read a whole Run as one tree, and every readout the PRD tiers as SHOULD or COULD should exist rather than be forgotten. This epic adds the run diagram view (the SHOULD that rides on the template graph), active Operator time (the measurement behind SM-2), changed-since-last-opened marks on the artifacts, the Board's LIST view, the login lockout, and per-Project monthly spend. Nothing here changes how a Run executes.

## Capabilities

- **CAP-1** Run diagram — the planned rows as a left-to-right tree with a token per node, groups by path, `now`, click-to-row. **success:** the diagram and the Steps table never disagree; group tokens follow the one rule computed by the backend.
- **CAP-2** Active Operator time — focused seconds reported from the Run detail and kept on the Run. **success:** the cost block prints `your active time` and the figure survives reloads and devices.
- **CAP-3** Changed-since-last-opened marks — `last_opened_at` on the Run, changed files promoted in the artifacts tree with one accent chip. **success:** files changed after the last opening are marked; opening the Run resets the mark.
- **CAP-4** Board LIST view — the same data as record rows. **success:** the toggle switches between board and list without a second request.
- **CAP-5** Login lockout — `token rejected — n attempts left`, five failures in fifteen minutes refuse for fifteen minutes. **success:** the sixth attempt within the window is refused with the disabled input and the stated line.
- **CAP-6** Per-Project monthly spend — the sum of this month's attempt costs on the Project meta line. **success:** the figure equals the sum over the Project's Runs' attempts started this calendar month.

## Constraints

- The diagram is read-only and renders the backend graph only (AD-15); the browser derives no status.
- Signal and voice rules of the experience spec; one signal colour per node or row (NFR-6).
- Read models stay one endpoint per screen (conventions).
- No new writers of Run status; `active_seconds` and `last_opened_at` are the only Run fields written outside the two writers, through their own small use cases.

## Non-goals

- No dashboard for the manual estimate (deferred by the PRD), no notifications, no SSE.

## Success signal

The Operator flips a running initiative to DIAGRAM and reads `epic 1` done, `story 4-1` amber with `now`, the rest queued; clicks the amber node and lands on its Steps row; back on the Board, switches to LIST for twenty-two Runs; and on the Project screen reads this month's spend.
