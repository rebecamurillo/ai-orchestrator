---
story: "8-4"
epic: 8
title: Board LIST view
requirements: [FR-22 (LIST), NFR-6, UX-DR7, UX-DR16, UX-DR18]
binds: [AD-1]
---

# Story 8.4 — Board LIST view

As the Operator,
I want the Board's Runs as record rows when there are too many cards to scan,
So that twenty or more Runs still read top to bottom like a log.

## Scope

**In:** the BOARD/LIST toggle wired (`?view=list`), the list rendering from the same board response, tests.
**Out:** sorting controls (rows follow column order then age).

## Binding rules (inlined)

- **Rows (UX-DR7).** Record rows `token · project · repository · branch · step label · progress · age`, grouped in the column order `Needs you · Running · Queued · Done · Failed` with a `column-head` line per group `[ASSUMPTION: needs-you first in the list, since the list exists for scanning]`, newest first within a group; the whole row links to the detail; the token is the only coloured cell, aged waits amber as on cards.
- **Toggle.** Segmented `BOARD · LIST` in the bar; the choice is written to `?view=` and restored on load; no second request — the island re-renders the same data.
- **Signal rule** as the board.
- **Test-ids:** `board-toggle-list`, `board-list`, `board-list-row-<id>`.

## Acceptance criteria

**Given** a stubbed board with Runs in every column
**When** LIST is selected
**Then** the rows appear grouped with heads in the order above, each with the seven fields, and the URL carries `?view=list`; selecting BOARD restores the columns without a new request.

**Given** a reload with `?view=list`
**When** the page loads
**Then** the list view is active.

**Given** a `BLK` Run older than 48 h
**When** listed
**Then** its token and age are amber and nothing else in the row is.

## Implementation notes

- `src/components/RunListRow.tsx`; the `Board` island switches on `view`.

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §2 (LIST toggle), §Naming rule. PRD FR-22. `DESIGN.md` record row.
