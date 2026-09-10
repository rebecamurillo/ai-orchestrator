---
status: done
---

# Runs history

`GET /api/v1/steps` — one row per attempt, newest first, cursor-paged, filtered by project,
status token and harness — and the **HISTORY** table on `/runs` that reads it, whose rows
link to the Run detail scrolled to the step they name.

## Anchor ruling

**Granted by the Operator, in session, on 2026-09-10.** The story halted `blocked` first;
nothing was implemented until the ruling came back.

- **File:** `web-client/tests/e2e/runs-queue.spec.ts`, landed by `a7bf037 story 4-16: Runs
  screen queue section (orchestrator)` on 2026-09-07.
- **Assertion:** the tail of the test *the bar carries the project and status filters, and
  the History section head* asserted that `data-testid="runs-history"` contained the
  deferral copy `history arrives with the harness comparison epic`.
- **What replaced it:** `await expect(page.getByTestId('runs-history')).toContainText('HISTORY');`
  — the section head is *served*, which is what a placeholder test is supposed to assert
  (root `AGENTS.md` hard rule 1, second exception, and its own "do not write the assertion
  that needs it" note). Exactly that assertion changed. Nothing else in the file did: no
  other test, no docstring, no reordering, no deletion, no skip.
- **Why a ruling was needed:** the copy named the *epic* rather than a story, so the
  exception's own precondition ("names a later story") was not met by the letter. The
  Operator read "the harness comparison epic" as naming this story — Epic 7 has exactly one
  story that owns CAP-5, and `runs/index.astro`'s own docstring already said "the table
  itself is Epic 7".
- **Strictly-exceeding coverage, in the same commit:** `web-client/tests/e2e/runs-history.spec.ts`
  (new, 9 scenarios) pins the section head, the ten columns, an agent row and a non-agent
  row cell by cell, the signal rule, the row link to `/workflows/{run_id}#step-{seq}`, the
  detail scrolling to and briefly promoting that row (both by click and by direct arrival),
  *more* appending the next page with the cursor in the request, the two filters reaching
  the history request while the queue's request carries neither, the section's own empty
  reading, and its own failed-read readout with Retry.

## Code Map

**backend-api — a new router/use-case/schema trio, the Epic 6 `run_files.py` pattern:**

- `src/orchestrator/domain/ports/history.py` (new) — `HistoryQuery`, `HistoryQuerySpec`,
  `HistoryCursor`, `HistoryEntry`. A query port rather than a fifth `AttemptRepository`
  method: the unit of this read is the attempt, its order spans every Run, and each row needs
  attempt + `step_run` + `run` + project name at once. Keyset, not offset.
- `src/orchestrator/application/use_cases/history.py` (new) — `list_history`,
  `HistoryFilters`, `HistoryRow`, `HistoryPage`, `STATUS_FILTERS`, `encode_cursor` /
  `decode_cursor`.
- `src/orchestrator/api/schemas/history.py` (new) — `HistoryRowOut`, `HistoryPageOut`
  (`Page` with nothing added).
- `src/orchestrator/api/routers/history.py` (new) — `GET /steps`, and the `history_filters`
  dependency that parses its five query parameters.
- `src/orchestrator/infrastructure/db/repositories/history.py` (new) —
  `SQLAlchemyHistoryQuery`: one statement, four inner joins, `started_at IS NOT NULL`, the
  filters, `tuple_(started_at, id) < tuple_(...)`, `ORDER BY started_at DESC, id DESC`.
- `src/orchestrator/api/providers.py` — `history_ports`.
- `src/orchestrator/main.py` — mounts `history.router` after `queue.router`.
- `src/orchestrator/infrastructure/db/{__init__.py,repositories/__init__.py}` — the export.
- `tests/unit/fakes/history.py` (new) — `FakeHistoryQuery`, the one double for the new port.
- New tests: `tests/unit/application/test_history.py`, `tests/unit/test_history_port.py`,
  `tests/unit/test_history_router.py`, `tests/unit/test_history_schema.py`,
  `tests/unit/test_history_repository_adapter.py`, `tests/e2e/test_history.py`.

**web-client:**

- `src/lib/runs/history.ts` (new) — the ten columns, each cell's text, `rowHref`, the query
  and request path, `promoted`.
- `src/lib/run/anchor.ts` (new) — `stepAnchorId`, `anchoredSeq`, `PROMOTED_MS`.
- `src/components/runs/HistoryTable.tsx` (new) — the dense table.
- `src/islands/RunsHistory.tsx` (new) — the poll, the *more* control, the empty reading, the
  failed read.
- `src/pages/runs/index.astro` — the placeholder head is replaced by the island, with the
  bar's two filters passed as props.
- `src/components/run/StepsTable.tsx` — `id="step-{seq}"` on every row, `data-anchored`.
- `src/islands/RunDetail.tsx` — the one-shot `#step-{seq}` arrival (235 lines, under the 300
  cap; nothing needed splitting).
- `src/styles/runs.css`, `src/styles/run-detail.css` — the table and the promotion.
- `tests/e2e/stub-backend.mjs` — `GET /api/v1/steps` answers empty unconditionally.
- New tests: `tests/unit/runs-history-lib.test.ts`, `runs-history-table.test.ts`,
  `runs-history-island.test.ts`, `run-anchor-lib.test.ts`, `run-steps-table-anchor.test.ts`,
  `tests/e2e/runs-history.spec.ts`.

## Design Notes

**The six findings the Operator settled, as built.**

1. **`seq` is on `HistoryRow`.** The brief's field list omits it; its own link rule
   (`/workflows/{run_id}#step-{seq}`) cannot be built from one read without it.
2. **The history's empty reading is `runs-history-empty`,** never `runs-empty` — that id
   belongs to the queue section, and `shell.spec.ts` and `runs-queue.spec.ts` each assert a
   single match for it under Playwright's strict mode.
3. **The history's failed read is `runs-history-failed`,** for the same reason, and
   `stub-backend.mjs` answers `GET /api/v1/steps` empty unconditionally so a bare `/runs`
   never produces a second `fetch-failed` element.
4. **`GET /steps` is its own trio.** `tests/unit/test_runs_router.py` pins `runs.py` at two
   operations; nothing was added there.
5. **`log_tail_url` resolves to `/api/v1/runs/{run_id}/detail`, and the gap is documented at
   the field.** No per-attempt log resource is served anywhere in this system — the tail
   lives inside the Run detail read as `StepRowOut.latest.log_tail` — so the brief names a
   resource that does not exist. No route was invented for it (Scope: "Out: nothing else").
   Carried to the Epic 7 handoff for Epic 8, the read-model epic.
6. **`trace_url` is the *Run's* trace, and says so at the field.** Nothing stores a
   per-attempt trace id; `Run.trace_id` is the only one there is.

**Two decisions this story had to take on its own:**

- **`BLK` selects `blocked` *and* `error`,** which is the brief's own acceptance ("only
  attempts whose row ended `blocked` or `error`"), and `ERR` narrows to the errored ones.
  The tokens are therefore not a partition — deliberately, and documented at
  `STATUS_FILTERS`. The bar offers no `CHK` and no `SKP`, so a `checkpoint` or `skipped`
  attempt is reachable only with no status filter at all. That is a gap in the bar UX-DR14
  fixed for *Run* statuses, not a gap in this endpoint.
- **A full page always carries a cursor; a short one never does.** The brief's first
  acceptance is "the third page is empty with `next_cursor null`", which a `limit + 1`
  look-ahead cannot produce — a look-ahead reports the end on page two. The cost is one
  empty read at the end of a history whose length divides exactly by the page size, and the
  *more* control surviving one click past the end. Stated in `list_history`'s docstring.

**One regression this story caused and fixed properly.** `/runs` is the first screen with
two islands on the shared `$poll` loop, and `configurePolling` is last-writer-wins: a
history reporting "nothing executing" slowed the queue beside it from 5 s to 30 s and broke
`runs-queue.spec.ts`'s frozen poll-tick scenario. The fix is that `RunsHistory` subscribes to
`$poll` and never re-times it — the queue is the right authority anyway, since an executing
attempt belongs to a Run `GET /queue` already reports as `running`. No frozen test was
touched to accommodate it.

## Verification

Every gate run in the foreground, exit code observed directly.

- `make lint` — exit 0. ruff check/format, `mypy --strict` over `domain/` + `application/`
  (121 files), import-linter 4/4 contracts kept, env contract (37 settings / 43 vars),
  `check_test_pairs` 209 backend + 95 web-client modules paired, `gen:api --check` no drift,
  astro check 0 errors, eslint, prettier, tsc.
- `make test` — exit 0. 5934 backend unit tests passed, 1 skipped; `domain/` + `application/`
  at 100 % branch coverage (`--fail-under=100`); 1286 web-client vitest tests passed.
- `make openapi` — exit 0; `contracts/openapi.json` and `web-client/src/api/schema.d.ts`
  regenerated and committed.
- `make e2e-api` — exit 0, via `make e2e` in its own disposable `aio-e2e` stack: 215 passed,
  11 deselected, 39 subtests, including this story's own `tests/e2e/test_history.py` and
  schemathesis over the new route.
- `make e2e-ui` — exit 0: 177 passed, 1 skipped, including the 9 new `runs-history.spec.ts`
  scenarios. The Epic 5/6 deliverable PNGs it rewrites were restored; none is committed.

## Auto Run Result

Status: done
Blocking condition: none. The one anchor conflict was ruled on by the Operator on
2026-09-10 and applied exactly as ruled.
