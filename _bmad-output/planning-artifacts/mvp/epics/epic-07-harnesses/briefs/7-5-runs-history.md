---
story: "7-5"
epic: 7
title: Runs history
requirements: [FR-25 (history), FR-28, NFR-6, UX-DR14, UX-DR16, UX-DR18, AR-24]
binds: [AD-1, AD-3, AD-6 (attempt_record)]
---

# Story 7.5 — Runs history

As the Operator,
I want every execution of every step, newest first, in one table with its harness, tokens, cost, and trace,
So that comparing harnesses on the same work is a scroll, not a query.

## Scope

**In:** `GET /api/v1/steps` (one row per attempt, cursor pagination, filters `project_id`, `status`, `harness`), the **HISTORY** table on `/runs` under the queue section, the status filter wired, tests.
**Out:** nothing else.

## Binding rules (inlined)

- **Endpoint.** `GET /steps?project_id=&status=&harness=&cursor=&limit=50` → `{items: [HistoryRow], next_cursor}`; `HistoryRow{attempt_id, run_id, started_at, ended_at, seconds, project_name, run_label ({template} v{n} · {branch}), path, kind, harness | null, model | null, session_id | null, status (attempt status), token, tokens_in | null, tokens_out | null, cost_usd | null, cost_provisional, trace_url | null, log_tail_url}`; ordered by `started_at desc, attempt_id desc`; cursor = opaque base64 of `(started_at, attempt_id)`; `status` filter maps the UI tokens `QUE RUN BLK ERR DON` to attempt/row statuses. Harness, session, and tokens are null on non-agent rows.
- **Table (UX-DR14).** Section head `HISTORY`; dense table `time · project · workflow · path · kind · harness · status · time · cost · trace`; current (running) rows promoted; rows link to `/workflows/{run_id}#step-{seq}` (the detail scrolls to the row by path; add the anchor handling in `RunDetail`); *more* control loads the next page (SHOULD; implement); the token is the only coloured cell.
- **Filters.** The bar's project and status filters apply to history; the queue section ignores the status filter.
- **Naming (UX-DR16):** this table prints the path.
- **Test-ids:** `runs-history`, `runs-history-row-<attempt_id>`, `runs-history-more`.

## Acceptance criteria

**Given** three Runs with twelve attempts across agent and git rows
**When** `GET /steps?limit=5` is read twice with the cursor
**Then** ten distinct rows arrive newest first, agent rows carry harness, session, tokens, cost, and non-agent rows carry nulls; the third page is empty with `next_cursor null`.

**Given** `?status=BLK`
**When** read
**Then** only attempts whose row ended `blocked` or `error` appear; `?harness=codex` only Codex attempts.

**Given** the Runs screen with a stubbed history
**When** rendered
**Then** rows show the ten columns, clicking one navigates to the Run detail scrolled to that step, and *more* appends the next page.

**Given** the detail opened with `#step-7`
**When** rendered
**Then** row 7 is scrolled into view and promoted briefly.

## Implementation notes

- `application/use_cases/history.py` over a repository query joining attempt, step_run, run, project; keyset pagination.
- `RunsHistory` island on `/runs` (polls like the queue, but only the first page).

## Verification

```bash
make lint && make test && make openapi && make e2e-api && make e2e-ui
```

## Sources for detail only

PRD FR-25 (history), FR-28. `EXPERIENCE-v1.md` §4 Runs (history table), §Naming rule. Spine conventions (Lists, Read models).
