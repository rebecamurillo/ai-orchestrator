---
story: "4-14"
epic: 4
title: Board with polling and the failed-fetch readout
requirements: [FR-22, FR-24, NFR-6, NFR-8, UX-DR2, UX-DR3, UX-DR4, UX-DR7, UX-DR16, UX-DR18, AR-25]
binds: [AD-1, AD-3]
---

# Story 4.14 — Board with polling and the failed-fetch readout

As the Operator,
I want the home screen to show every Run as a card in the column of its status, refreshed without anything moving under my cursor, and to tell me plainly when it cannot reach the server,
So that coming back cold I see in one glance where everything is and what needs me (UJ-2, UJ-3).

## Scope

**In:** the `Board` island on `/`, the `$poll` interval store and `$board` data store, the rail and footer counts fed by the store, the project filter (query string), the full-surface failed-fetch readout component (reusable), empty states, Playwright and Vitest.
**Out:** the LIST toggle (Epic 8; render the toggle disabled with the word `LIST` in tertiary), Run detail (4.15).

## Binding rules (inlined)

- **Data.** `GET /runs?view=board&project_id=` through `client.ts`; the island renders the response as is.
- **Polling (FR-24, conventions).** One nanostores interval store `src/stores/poll.ts`: ticks every 5 s while `counts.running > 0`, else every 30 s; every island subscribes with `useStore`; each tick replaces state in one swap (no per-card animation, no transition CSS); the footer prints `updated hh:mm:ss` from `generated_at`; a *refresh* control forces a tick.
- **Failed fetch (UX-DR4).** A non-2xx or network error replaces the whole surface with `src/components/FailedFetch.tsx`: a command block showing `{method} {path} → {status or "network error"}` and a *Retry* control; nothing else moves; polling pauses until Retry succeeds.
- **Columns (UX-DR7).** Five equal fluid columns `Queued · Running · Needs you · Done · Failed`, never collapsing; header counts; the Running header in green, the Needs-you header in amber only when its count > 0 `[the header colour is one of the allowed signal placements]`; empty column body `—`; `cancelled` cards under Failed with the grey `CAN` token and the word `cancelled`.
- **Card (fixed order).** chip + token (harness name right, tertiary) · branch · project · repository · current or last step **label** · progress `n/n epics · m/m stories · k links` (epic figure omitted when `epics_total` is null; `repo-init` / `readiness` in place of progress) · `{template} v{version}` · age. A `BLK`/`ERR` card carries the 2px left rule in its signal colour; an age > 48 h on a `BLK`/`CHK` card renders in amber; cards are not draggable; the whole card links to `/workflows/{id}`.
- **Bar and shell.** Surface title `WORKFLOWS`, readout `{n} runs · {k} need you · oldest wait {age}`, project segmented filter written to `?project=`, BOARD/LIST toggle, *+ New workflow*. Rail: *Workflows* count and `{k} need you` in amber when k > 0; footer `{running} running · {queued} queued / {k} need you / updated hh:mm:ss · refresh`.
- **Empty states.** No Runs: `NOTHING RUNNING` + the queued list (none) + link `new workflow`; no Project registered: `NOTHING REGISTERED` + link to `/projects/new` (the page checks `GET /projects` server-side once).
- **Signal rule (UX-DR2).** Exactly one coloured element per card (chip + token; the aged age is the tolerated pair); a board with nothing `needs_you` or `failed` shows no amber or red pixel (Playwright colour scan).
- **Test-ids:** `board`, `board-column-<status>`, `board-card-<id>`, `board-filter-project`, `board-toggle-list`, `board-new`, `board-empty`, `nav-needs-you`, `footer-readout`, `fetch-failed`, `fetch-retry`.

## Acceptance criteria

**Given** a stubbed board response with Runs in every column and one `cancelled`
**When** `/` renders
**Then** five columns show the right counts and cards in the fixed field order, the cancelled card sits under Failed with `CAN · cancelled`, and clicking a card navigates to its detail.

**Given** `counts.running > 0`
**When** the page is open for 12 s (fake timers)
**Then** the endpoint is polled at 5 s intervals; with `running = 0` at 30 s; each response replaces the state with no CSS transition on cards.

**Given** the stub returns 500 on a poll
**When** it happens
**Then** the surface is replaced by the failed-fetch readout showing `GET /api/runs?view=board → 500` and *Retry*; after a successful Retry the board returns and polling resumes.

**Given** a board with no `needs_you` and no `failed` Runs
**When** scanned
**Then** no element uses the amber or red token; **and** with one `BLK` card older than 48 h both its token and its age are amber and nothing else is.

**Given** no Runs at all
**When** rendered
**Then** the body reads `NOTHING RUNNING`; with no Projects `NOTHING REGISTERED` linking to Projects.

**Given** `?project=<id>`
**When** the page loads
**Then** the filter is active and the request carries `project_id`.

## Implementation notes

- `src/islands/Board.tsx`, `src/stores/{poll.ts, board.ts}` (unit-tested with fake timers), `src/components/FailedFetch.tsx` (React, reused by RunDetail), `src/components/RunCard.tsx`.
- Rail and footer become islands-aware: `AppRail` reads the counts from a tiny `$counts` store hydrated by the Board or the Run detail.
- Playwright `tests/e2e/board.spec.ts`.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §2 Workflows board, §Attention model, §Shell, §Refresh, §Naming rule. PRD FR-22, FR-24, NFR-6. `DESIGN.md` board card and column, empty state. `web-client/AGENTS.md` (one polling loop).
