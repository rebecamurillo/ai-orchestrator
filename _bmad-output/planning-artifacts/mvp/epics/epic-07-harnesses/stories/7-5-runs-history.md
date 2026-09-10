---
status: blocked
---

# Runs history

## Auto Run Result

Status: blocked
Blocking condition: frozen placeholder assertion pins `data-testid="runs-history"` to the
deferral copy this story must replace — `web-client/tests/e2e/runs-queue.spec.ts:248`.

Nothing was implemented. The working tree carries only this record.

## The anchor

**File** — `web-client/tests/e2e/runs-queue.spec.ts`, landed by `a7bf037 story 4-16: Runs
screen queue section (orchestrator)` on 2026-09-07. An existing test file, therefore frozen
under root `AGENTS.md` hard rule 1.

**Assertion** — lines 234–251, the tail of the test
`the bar carries the project and status filters, and the History section head`:

```ts
    await expect(page.getByTestId('runs-history')).toContainText(
      'history arrives with the harness comparison epic',
    );
```

**What it pins** — that the element carrying `data-testid="runs-history"` on `/runs`
renders the sentence `history arrives with the harness comparison epic`. Today that element
is the deferral heading in `web-client/src/pages/runs/index.astro:102-104`:

```astro
  <h2 class="runs-history-head" data-testid="runs-history">
    HISTORY · history arrives with the harness comparison epic
  </h2>
```

**Why story 7-5 cannot land beside it** — the brief
(`briefs/7-5-runs-history.md`) fixes both the test-id and the copy this story must put
there:

- *Test-ids:* `runs-history`, `runs-history-row-<attempt_id>`, `runs-history-more`. The
  HISTORY table itself is required to carry `runs-history`; the row and *more* test-ids are
  namespaced beneath it, so it is the table's id and not a wrapper's.
- *Table (UX-DR14):* "Section head `HISTORY`". The head is exactly the word `HISTORY`, with
  no deferral clause after it.

The two cannot both hold. Any element carrying `runs-history` after this story is the
history table (or its section), and the only way `toContainText('history arrives with the
harness comparison epic')` still passes is to keep that sentence on the screen — a statement
of fact that would be false the moment the table renders, which root `AGENTS.md` forbids
independently ("Product copy states facts and mechanisms"). Re-parenting the id onto a
wrapper that still contains the old heading has the same effect and is the same false copy.
There is no arrangement of markup that satisfies the brief and the assertion at once.

**Which exception it is near, and why the agent did not take it.** Root `AGENTS.md` hard
rule 1's second exception covers "a placeholder assertion: where a test names a later story
as the thing that replaces what it asserts, exactly that story may revise that assertion,
and only if the same commit adds coverage that strictly exceeds it." The same rule adds:
"Do not write the assertion that needs the second exception: a test covering a placeholder
asserts that the route is served, not the placeholder's copy" — which is exactly the shape
of this assertion.

It falls one word short of the exception's own precondition: the copy names *the harness
comparison epic* (Epic 7), not a story. Epic 7 contains exactly one story that replaces it —
7-5, the CAP-5 owner — and `src/pages/runs/index.astro`'s own module docstring already says
"the table itself is Epic 7". So the exception's intent is met and its letter is not. That
is a ruling, and only the Operator makes it.

## What a ruling would unblock

If the Operator authorises the revision, the same commit lands coverage that strictly
exceeds the assertion: a new `web-client/tests/e2e/runs-history.spec.ts` asserting the ten
columns, the row link to `/workflows/{run_id}#step-{seq}`, the *more* control appending the
next page, and the status filter reaching the history section — and the frozen test's own
line becomes a `HISTORY` section-head reading rather than a deferral reading.

## Neighbouring constraints found while confirming the conflict

These are **not** anchor conflicts — they are solvable inside the story — but they shape the
implementation and are recorded so the next dispatch does not rediscover them:

- `web-client/tests/e2e/shell.spec.ts:18` (frozen) visits bare `/runs` and asserts a single
  `data-testid="runs-empty"` reading `NO RUNS`, and `runs-queue.spec.ts:299-303` asserts the
  same element also contains `nothing queued`. The history section's own empty reading must
  therefore carry a **different** test-id, or Playwright's strict mode fails both.
- `runs-queue.spec.ts:204-231` (frozen) asserts a single `data-testid="fetch-failed"` while
  `GET /api/queue` 500s. `tests/e2e/stub-backend.mjs` must answer `GET /api/v1/steps` with an
  empty page unconditionally — the precedent story 4-16 set for `GET /api/v1/queue` — or the
  history island's own `FailedFetch` becomes a second match and breaks that test too.
- `backend-api/tests/unit/test_runs_router.py` pins `api/routers/runs.py` at exactly two
  operations, so `GET /steps` needs its own router module beside it — Epic 6's
  `run_files.py` / `use_cases/run_files.py` / `schemas/run_files.py` trio is the pattern.
- `HistoryRow` as the brief lists it has no `seq`, yet the brief's own link rule is
  `/workflows/{run_id}#step-{seq}`. The row needs `seq` for the link to be buildable without
  a second read; that addition should be confirmed rather than assumed.
- No attempt-level trace id is stored (`domain/entities/attempt.py`); `Tracer.trace_url`
  takes a trace id and `Run.trace_id` is the only one there is. `trace_url` on a history row
  therefore resolves per Run, not per attempt.
- There is no endpoint serving an attempt's log tail; `log_tail_url` in the brief's field
  list has no existing referent, and the brief's own Scope is "Out: nothing else". What that
  field should point at needs deciding before the schema is written.
