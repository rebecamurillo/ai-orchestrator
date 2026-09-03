---
story: "4-16"
epic: 4
title: Runs screen queue section
requirements: [FR-13, FR-25 (queue), NFR-8, UX-DR14, UX-DR18]
binds: [AD-1, AD-12]
---

# Story 4.16 — Runs screen queue section

As the Operator,
I want to see the queue exactly as the engine holds it, with why each Run waits and for how long,
So that "the second run is waiting for the repository lock" is a line on a screen, not a guess.

## Scope

**In:** `src/pages/runs/index.astro` with the **QUEUE** section fed by `GET /queue` on the poll store, the project and status filters in the bar (status filter applies to the history section arriving in Epic 7; render it now), the section-head parameters, tests.
**Out:** the **HISTORY** table (Epic 7; render the section head with `history arrives with the harness comparison epic` in tertiary).

## Binding rules (inlined)

- **Bar.** Surface title `RUNS`, project filter, status filter `ALL · QUE · RUN · BLK · ERR · DON` (segmented, tokens as labels).
- **Queue section (UX-DR14).** Section head `QUEUE · concurrency {max_active_runs} · one active run per repository · parked runs hold a slot`; dense table `pos · project · workflow · next step · waiting because · waiting`: `pos` = position or `—`; `workflow` = `{template} v{n} · {branch}` linking to the detail; `next step` = label; `waiting because` = the reason verbatim from the fixed set; `waiting` = duration since `waiting_since`; a parked Run's row adds the hint `not queued until then` under the reason. Empty: `nothing queued`.
- **Signal rule:** no colour in this table except a `BLK` token if a token column is shown — keep the table token-free; reasons are words.
- **Polling:** the same `$poll` store; failed fetch → the full-surface readout.
- **Test-ids:** `runs-queue`, `runs-queue-row-<id>`, `runs-filter-project`, `runs-filter-status`, `runs-history`.

## Acceptance criteria

**Given** a stubbed queue with an active Run, one waiting on the lock, one on global concurrency, and one parked
**When** `/runs` renders
**Then** four rows with positions `—, 1, 2, —`, reasons `running`, `repository lock held by …`, `global concurrency, held by …`, `waiting for your answer` (with the hint), and the section head shows the concurrency figure.

**Given** an empty queue
**When** rendered
**Then** the section reads `nothing queued`.

**Given** the page open with the poll store ticking
**When** the stub changes
**Then** the table updates on the next tick without animation.

## Implementation notes

- A small `RunsQueue` island (`client:load`) or an Astro component fed by a store; prefer the island since it polls.
- Playwright `tests/e2e/runs-queue.spec.ts`.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §4 Runs. PRD FR-13, FR-25. Spine AD-12.
