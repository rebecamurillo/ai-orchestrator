---
story: "8-2"
epic: 8
title: Active Operator time
requirements: [FR-23 (active time), SM-2, AR-24 (activity route)]
binds: [AD-1, AD-3]
---

# Story 8.2 — Active Operator time

As the Operator,
I want the Run to keep how long I actually spent on its detail,
So that cold-reload time (SM-2) is measured from facts across reloads and devices.

## Scope

**In:** `POST /api/v1/runs/{id}/activity {focused_seconds}`, `run.active_seconds` accumulation, the focus tracker in `RunDetail` batching every 60 s, the figure in the cost block, tests.
**Out:** any per-day breakdown.

## Binding rules (inlined)

- **Client.** While the Run detail tab is focused (`document.visibilityState == visible` and `window` focused), a `src/stores/activity.ts` store counts seconds; idle gaps longer than 5 minutes without pointer or key events are excluded (the counter pauses after 5 idle minutes and resumes on the next event); every 60 s, and on `pagehide`, it posts the accumulated seconds (≥ 1) and resets. Diagram and detail views both count.
- **Server.** `POST /runs/{id}/activity {focused_seconds: int (1..3600)}` → `run.active_seconds += focused_seconds` through `use_cases/activity.record`; 200 `{active_seconds}`; 422 outside the range; allowed for any Run status.
- **Read model.** `cost.active_seconds`; the kv row `your active time` prints `hh:mm:ss`; the Board is unaffected.
- **Voice:** the label is `your active time`.

## Acceptance criteria

**Given** a focused detail with fake timers
**When** 60 s pass with activity
**Then** one POST with `focused_seconds: 60` is sent and the store resets; after 6 idle minutes only the first 5 count.

**Given** the tab hidden
**When** time passes
**Then** nothing is counted; on `pagehide` the remainder is posted.

**Given** `POST /runs/{id}/activity {focused_seconds: 45}` twice
**When** applied
**Then** `active_seconds` is 90 and the cost block reads `00:01:30`.

**Given** `focused_seconds: 0` or `5000`
**When** posted
**Then** 422.

## Implementation notes

- Migration not needed (`active_seconds` exists from 4.1); router in `runs.py`; use case with the repository.
- Store unit tests with fake timers; Playwright smoke that the POST fires.

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

PRD FR-23 (active time paragraph), SM-2. Spine conventions (Routes: activity).
