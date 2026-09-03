---
story: "8-6"
epic: 8
title: Per-Project monthly spend
requirements: [FR-28 (per-Project monthly), UX-DR12, NFR-6]
binds: [AD-1, AD-11]
---

# Story 8.6 — Per-Project monthly spend

As the Operator,
I want each Project to show what its Runs have cost this month, and the Projects list to show at a glance which Project has something needing me,
So that spend is visible where it is decided, even though it is not capped there.

## Scope

**In:** `monthly_spend_usd` on the Project read model (sum of `attempt.cost_usd` over the Project's Runs' attempts with `started_at` in the current UTC calendar month), the meta line figure, the one amber or red count on Projects list rows (`needs_you` count amber, else `failed` count red, else nothing), tests.
**Out:** budgets per Project (deferred by the spine).

## Binding rules (inlined)

- **Figure.** Computed in SQL at read time; `provisional` word appended when any attempt in the sum is provisional; printed `this month ${x.xx}` on the Project meta line after `created`.
- **List rows (UX-DR12).** Each Project row gets at most one coloured count: `{n} need you` in amber when the Project has `needs_you` Runs; else `{n} failed` in red when it has `failed` Runs in the last 7 days `[ASSUMPTION: seven-day window for the red count]`; else nothing. The Projects list read model gains `needs_you_count`, `failed_recent_count`.
- **Signal rule:** the count is the only coloured element on the row; a list with nothing needing the Operator has no amber or red pixel.

## Acceptance criteria

**Given** a Project with attempts costing 12.30 this month and 40.00 last month
**When** `GET /projects/{id}` is read
**Then** `monthly_spend_usd == "12.30"` and the meta line reads `this month $12.30`.

**Given** one provisional attempt in the sum
**When** rendered
**Then** the figure carries the word `provisional`.

**Given** Projects with a parked Run, a recently failed Run, and neither
**When** the list renders
**Then** the rows show `1 need you` in amber, `1 failed` in red, and nothing, respectively; the colour scan finds nothing else.

## Implementation notes

- Queries in the SQLAlchemy project repository; read model fields in `api/schemas/projects.py`; run `make openapi`.

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

PRD FR-28 (per-Project monthly), §11 Cost. `EXPERIENCE-v1.md` §3 Projects (list row count, meta line). Spine AD-11 (cost sums).
