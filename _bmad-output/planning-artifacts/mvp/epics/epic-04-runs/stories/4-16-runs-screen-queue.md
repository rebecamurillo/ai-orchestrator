---
title: 'Runs screen queue section'
type: 'feature'
created: '2026-09-07'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred:
  - summary: >-
      An unmatched or stale `?project=` id (deep-linked, but not in the SSR-fetched project
      list) leaves every project-filter link unmarked as current instead of resolving the
      real name.
    evidence: |-
      `src/pages/index.astro`'s own Board page solves the analogous case with a second,
      `GET /projects/{id}` deep-link resolve call when the bare list answers empty (its own
      module doc, "A `?project=` deep link resolves through `GET /projects/{id}`"); `src/
      pages/runs/index.astro` does not, so a valid-but-unlisted project id shows no filter
      chip as selected. Cosmetic only: the project filter has no effect on the QUEUE section
      in this story (Design Note D2), so nothing renders incorrectly, only nothing highlights.
    location: 'web-client/src/pages/runs/index.astro'
    severity: low
  - summary: >-
      Once Epic 7 lands the HISTORY table, a queue that reads empty while History still has
      rows will show the `runs-empty`/`NO RUNS` copy this story wrote, which will then be
      inaccurate (Runs did happen; the queue is just idle) — flagged independently by this
      pass's own intent-alignment auditor.
    evidence: |-
      `RunsQueue.tsx`'s zero-items branch (Design Note D3) reuses the page's frozen bare-page
      `NO RUNS` copy/testid for `GET /queue` returning zero items, because `tests/e2e/
      shell.spec.ts` (frozen) requires exactly that reading against the always-empty shared
      stub. That stub has no History either, so today the two states (no run ever vs. queue
      merely idle) are indistinguishable and the copy is accurate either way. Epic 7 gives
      the page a second signal (History rows) that can tell them apart; whichever story
      builds the HISTORY table should gate `NO RUNS` on "queue empty AND history empty," not
      on queue emptiness alone.
    location: 'web-client/src/islands/RunsQueue.tsx'
    severity: medium
baseline_revision: '8a1d1c9c208756671ac0af38551a8a9b5075845f'
---

<intent-contract>

## Intent

**Problem:** `/runs` is still 4.14-era: a static, unconditional `NO RUNS` placeholder with no
backend call at all. `GET /queue` (4.11) exists and carries position, reason, waiting time and
`max_active_runs`, but nothing renders it.

**Approach:** Build the QUEUE section of `src/pages/runs/index.astro` — the Bar's project and
status filters (chrome only, deferred to the Epic 7 History table), a `RunsQueue` island
(`client:load`) polling `GET /queue` on the shared `$poll` store, a dense table (`pos ·
project · workflow · next step · waiting because · waiting`), the fixed reasons verbatim, and
the History section head (static text; the table itself is Epic 7).

## Boundaries & Constraints

**Always:** `GET /queue`'s four reasons are printed verbatim, never reworded (SPEC CAP-16);
`max_active_runs` is read off the endpoint's own payload, never hardcoded; a parked
(`needs_you`) row shows position `—` and the hint `not queued until then` (AD-12: the
repository lock is the queue partition, held for the Run's whole life including `needs_you`);
the table carries no colour (binding rule: "keep the table token-free; reasons are words");
`$poll`/`configurePolling` (4.13/4.14) is the one polling loop; a failed poll swaps the
section for `FailedFetch` (reused unchanged).

**Block If:** none — the operator's own dispatch instructions resolved the one ambiguity that
would otherwise have blocked (see Design Notes, "The `project` cell is an id, not a name").

**Never:** add, widen, or reshape `GET /queue` or any other backend-api endpoint (explicit
operator instruction for this dispatch); build the HISTORY table (Epic 7); filter the QUEUE
section by the Bar's project or status filter (Design Notes); sync the footer/rail live
counts from this screen (Board's own concern, not this one's).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Active, lock-held, global-concurrency, and parked rows | stubbed `GET /queue`, 4 items | 4 rows, positions `—, 1, 2, —`; reasons `running` / `repository lock held by …` / `global concurrency, held by …` / `waiting for your answer` (+ hint); head shows the concurrency figure | — |
| Empty queue | `items: []` | the section reads `nothing queued` | — |
| Poll tick, stub changes | `$poll` ticks | the table updates with no reload | — |
| Bare `/runs`, fresh instance | shared stub, unconditionally empty | `data-testid="runs-empty"` reads `NO RUNS` (frozen `shell.spec.ts`) | — |
| A poll fails | 500 | full-surface `FailedFetch`; Retry restores the section | — |

</intent-contract>

## Code Map

- `web-client/src/pages/runs/index.astro` — was the 4.14-era static `NO RUNS` placeholder;
  now the Bar (project + status filters, chrome only) and the QUEUE island, mirroring
  `src/pages/index.astro`'s own SSR-`GET /projects`-for-filter-chrome pattern.
- `web-client/src/islands/RunsQueue.tsx` (new) — `client:load`, the one poll of `GET /queue`
  off the shared `stores/poll.ts` loop (4.13/4.14's own store), `Board.tsx`'s staleness-guard
  pattern (`requestSeqRef`/`mountedTickRef`) copied verbatim.
- `web-client/src/components/runs/QueueTable.tsx` (new) — the dense table, stateless
  (`StepsTable.tsx`'s own `renderToStaticMarkup` precedent).
- `web-client/src/lib/runs/queue.ts` (new) — every pure cell/head computation, kept out of
  the island and the table so both unit-test without a DOM (`web-client/AGENTS.md`).
- `web-client/src/lib/board/format.ts::ageText` (4.14) — reused unchanged for the `waiting`
  cell; `waiting_seconds` is already in the same unit that helper takes.
- `web-client/src/components/FailedFetch.tsx` (4.14) — reused unchanged for a failed poll.
- `web-client/src/stores/poll.ts` (4.13) — `configurePolling`/`$poll`/`stopPolling` reused
  whole; no second interval opened.
- `web-client/src/styles/runs.css` (new) — the table/section-head/empty-state rules, the
  `board.css`/`run-detail.css` "hand-scoped prefix" precedent (React has no `<style>`
  scoping).
- `web-client/tests/e2e/stub-backend.mjs` (test support file, additive) — `GET /api/v1/queue`
  added, unconditionally empty, the `GET /api/v1/projects` list's own precedent — needed for
  the frozen `shell.spec.ts`'s bare-`/runs` `NO RUNS` assertion.
- New tests: `tests/unit/runs-queue-lib.test.ts`, `tests/unit/runs-queue-table.test.ts`,
  `tests/unit/runs-queue-island.test.ts`, `tests/e2e/runs-queue.spec.ts`.

## Tasks & Acceptance

**Execution:**
- `web-client/src/lib/runs/queue.ts` -- every pure cell/head/path computation -- keeps
  formatting DOM-free and unit-testable.
- `web-client/src/components/runs/QueueTable.tsx` -- the dense table, stateless -- mirrors
  `StepsTable.tsx`.
- `web-client/src/islands/RunsQueue.tsx` -- fetch/poll/render, the shared `$poll` loop, the
  empty and failed-fetch readings -- the one live piece of the screen.
- `web-client/src/pages/runs/index.astro` -- Bar filters (SSR), mounts `RunsQueue`, static
  History head -- replaces the 4.14-era static placeholder.
- `web-client/src/styles/runs.css` -- tokens-only styling for the above.
- `web-client/tests/e2e/stub-backend.mjs` -- add `GET /api/v1/queue`, unconditionally empty
  -- keeps the frozen `shell.spec.ts` passing under the new real fetch.
- New unit tests for `queue.ts`, `QueueTable.tsx`, and a resolves-as-a-function-component
  proof for `RunsQueue.tsx` (`Board.tsx`'s own `board-island.test.ts` precedent — the real
  wiring is proven in the browser, by the e2e spec).
- New e2e test `runs-queue.spec.ts` -- every AC below.

**Acceptance Criteria:**
- Given a stubbed queue with an active Run, one waiting on the lock, one on global
  concurrency, and one parked, when `/runs` renders, then four rows read positions
  `—, 1, 2, —`, the four fixed reasons (parked with the hint), and the head shows the
  concurrency figure.
- Given an empty queue, when rendered, then the section reads `nothing queued`.
- Given the page open with the poll store ticking, when the stub changes, then the table
  updates on the next tick with no reload.
- Given the fresh, unmocked shared stub, when bare `/runs` is visited, then the frozen
  `shell.spec.ts` still reads `runs-empty`/`NO RUNS`, `footer-readout`'s static zero line,
  and no amber/red pixel.

## Spec Change Log

_None._ No anchor file was edited; the two Design Notes below record where this story's own
implementation diverges from a literal reading of the brief, resolved spine-first per this
run's own operating rules.

## Review Triage Log

### 2026-09-07 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 6 (medium 2, low 4)
- defer: 2 (low 1, medium 1)
- reject: 9
- addressed_findings:
  - `[medium]` `[patch]` Bar filter `href`/`aria-current` wiring for non-default `?status=`/
    `?project=` combinations had no test coverage (verification-gap; overlapping blind-hunter
    findings on missing param-preservation and populated-chip coverage) — added two
    `runs-queue.spec.ts` cases asserting `href` composition and `aria-current` flips for a
    non-default status with a project already in the URL.
  - `[low]` `[patch]` An unrecognized `?status=` value left every status link unmarked as
    current with no fallback (edge-case-hunter) — `runs/index.astro` now guards with
    `isStatusFilter`, falling back to `ALL`, with a covering `runs-queue.spec.ts` case.
  - `[low]` `[patch]` `hasRunningRow`'s doc comment claimed it restates `RunDetail.tsx`'s
    `run.status === 'running'` check but the code reads `row.reason` (blind-hunter) — comment
    corrected to state the real, deliberate reason (`reason` is the endpoint's own fixed
    sentence; `run.status` can lag it).
  - `[low]` `[patch]` The `'running'` reason literal was inline in `hasRunningRow`, unlike
    the same file's own named `REASON_WAITING_ANSWER` (blind-hunter, "inconsistent
    literal-duplication convention") — added `REASON_RUNNING` and used it.
  - `[low]` `[patch]` `.runs-section-head` (padding-based) and `.runs-history-head`
    (margin-based) used different box models for the same visual role (blind-hunter) —
    `.runs-history-head` rewritten to the same `padding: TOP HORIZONTAL BOTTOM` shape.
  - `[medium]` `[patch]` The parked-row hint relied only on a CSS `display: block` rule to
    read apart from the reason text (blind-hunter) — `QueueTable.tsx` now inserts an explicit
    `" · "` text separator so the two sentences read apart with no stylesheet at all.

Rejected as matching this story's own brief or existing, already-shipped precedent (not a
defect this diff introduces): `STATUS_FILTERS` omitting `CHK`/`CAN` (edge-case-hunter,
blind-hunter — the brief's own binding rule states this exact six-token set verbatim);
`Shell`'s dropped static `count` prop (edge-case-hunter deletion check — matches `src/pages/
index.astro`'s own `count={projects.length > 0 ? undefined : '...'}` precedent: no static
count once real content is attempted); `QueueOut.next_cursor` never read (blind-hunter —
`api/schemas/queue.py::QueueOut.of` hardcodes `next_cursor=None`, backend never paginates
this endpoint); color-only filter selection (blind-hunter — identical to the already-shipped
`board-filter`/`board-toggle` treatment in `src/pages/index.astro`; the "no colour" binding
rule this story states is scoped to the QUEUE table only); the poll-cadence "slows once
nothing runs" branch untested here (blind-hunter — `configurePolling` itself is exhaustively
covered by `poll-store.test.ts`, and `board.spec.ts` already proves the identical wiring
pattern; this island's own unique contribution, `hasRunningRow`, is unit-tested both ways);
missing `aria-label`s on filter tokens and the meaning-bearing em dash (blind-hunter, ×2 —
no such convention or test exists anywhere else in this codebase); silent SSR fetch-failure
fallback for the project-filter chrome (blind-hunter — deliberate: the primary QUEUE section
has its own explicit `FailedFetch`, and this secondary chrome degrading to "just show all"
never misleads about the primary content); the `URLSearchParams`-avoidance rationale
"unverified" (blind-hunter — empirically confirmed: `make lint` failed with `no-undef` before
the fix, exactly as the comment states).

Deferred (real, not this story's problem, or too large to be "trivially fixable"): an
unmatched/stale `?project=` id shows no filter chip as current (edge-case-hunter; would need
`index.astro`'s own `GET /projects/{id}` deep-link-resolve precedent, out of scope for chrome
with no functional effect this story); the `NO RUNS` copy's future inaccuracy once Epic 7
adds History rows to an otherwise-empty queue (intent-alignment auditor — see frontmatter
`deferred` for the full note to the History story).

## Design Notes

**D1 — the `project` cell is the Run's own id, not a name.** The brief's dense table names a
`project` column but `GET /queue`'s `QueueItemOut.run` is `RunSummaryOut` (4.4/4.9's
"minimal" read model, reused whole by 4.11), which carries `project: UUID`, never a name —
the one read model that does is `GET /runs/{id}/detail`'s own `header.meta.project` (4.12), a
second endpoint this screen must not read to fill the gap (SPEC's "a screen reads one
endpoint and aggregates nothing", AD-8, and this dispatch's explicit "do not add, widen, or
reshape" `GET /queue`). `projectCell` states the id plainly instead of inventing a join.

**D2 — neither Bar filter changes the QUEUE section; both write `?project=`/`?status=` for
the History story to read.** The brief states this outright for the status filter ("status
filter applies to the history section arriving in Epic 7; render it now") but is silent on
the project filter's own scope. Filtering the queue by project client-side is possible (the
data is already fetched) but was rejected: AD-12's queue is a system-wide partition, not a
per-project one, and CAP-16 exists precisely so an Operator can see *another* project's Run
holding the lock or the concurrency ceiling — a project filter over the QUEUE section would
hide exactly that fact. Extended by "a screen reads one endpoint and aggregates nothing"
(AD-8), which also rules out a client-side join against a second `GET /projects` read to
filter by. Both filters are chrome for the unbuilt HISTORY table.

**D3 — the empty-queue reading doubles as `/runs`'s frozen bare-page `NO RUNS` state.**
`tests/e2e/shell.spec.ts` (frozen, pre-dates this story) visits bare `/runs` and asserts
`data-testid="runs-empty"` containing `NO RUNS` — the exact copy the 4.14-era placeholder
carried. An SSR-side gate cannot substitute (an SSR read is never intercepted by Playwright's
`page.route()`, only a browser-side fetch is — `board.spec.ts`'s own module doc — so an SSR
gate would see this story's own real-content e2e mocks as permanently empty). Instead, the
island's own "queue has zero items" branch — which this story's own AC2 asks for ("the
section reads `nothing queued`") — carries both the `data-testid` and a `NO RUNS` headline
line alongside a `nothing queued` line: `Board.tsx` sets the precedent, reusing
`data-testid="board-empty"` for both its outer zero-Project state and its own inner
zero-card reading. `stub-backend.mjs` gained `GET /api/v1/queue`, unconditionally empty, the
same "`GET /api/v1/projects` answers an empty list unconditionally" precedent that
`shell.spec.ts` already depends on for every other route.

**D4 — no footer/rail sync.** `Board.tsx` patches `footer-readout`/`nav-workflows` because
those figures are its own board-wide counts; `RunDetail.tsx`/`NewWorkflow.tsx` never touch
either, because their own screens answer a narrower question. `RunsQueue.tsx` follows the
latter precedent: the queue's own figures are not the footer's, and reading them into it
would be a second aggregation this screen does not own.

## Verification

**Commands:**
- `make lint` -- ruff/mypy/import-linter/eslint/prettier/tsc/env-contract/check-test-pairs,
  all green.
- `make test` -- backend 4056 passed/23 skipped, 100% branch on domain+application; web-client
  973 passed, `src/lib/runs/queue.ts` and `src/components/runs/QueueTable.tsx` both 100%
  lines (confirmed via `coverage-summary.json`, hidden from the text table's own directory
  grouping).
- `make openapi` -- no drift (no backend-api change this story).
- `PATH="$HOME/.docker/bin:$PATH" make e2e` -- 144 passed, 34 subtests passed (includes the
  known `test_the_engine_picks_the_run_up_and_walks_it` flake target; it passed this run).
- `make e2e-ui` -- run twice (before and after the review pass's patches): 116 passed then
  118 passed (10 `runs-queue.spec.ts` cases after the two patch-added tests), and all 5
  `shell.spec.ts` `/runs` cases (frozen, unmodified) green both times. No lingering server
  left on 127.0.0.1:4321 after either run.

## Auto Run Result

**Summary.** Built the QUEUE section of `/runs` (SPEC CAP-16, FR-25, UX-DR14): a `RunsQueue`
`client:load` island polling `GET /queue` (4.11) on the shared `$poll` store, a dense table
(`pos · project · workflow · next step · waiting because · waiting`) with the fixed reasons
printed verbatim and the parked-row hint, a section head carrying the endpoint's own
`max_active_runs`, the Bar's project/status filter chrome (deferred to Epic 7's History
table, writing `?project=`/`?status=` for it to read), and the static HISTORY section head.
`GET /queue` was consumed exactly as it exists — no backend-api change this story.

**Files changed:**
- `web-client/src/pages/runs/index.astro` -- replaced the 4.14-era static `NO RUNS`
  placeholder with the Bar filters (SSR) and the `RunsQueue` island; guards an unrecognized
  `?status=` back to `ALL`.
- `web-client/src/islands/RunsQueue.tsx` (new) -- the poll/fetch/render island.
- `web-client/src/components/runs/QueueTable.tsx` (new) -- the stateless dense table, with
  an explicit text separator (not CSS-only) for the parked hint.
- `web-client/src/lib/runs/queue.ts` (new) -- every pure cell/head computation, incl. the
  named `REASON_RUNNING`/`REASON_WAITING_ANSWER` constants.
- `web-client/src/styles/runs.css` (new) -- table/section-head/empty-state styling.
- `web-client/tests/e2e/stub-backend.mjs` (test support, additive) -- `GET /api/v1/queue`,
  unconditionally empty, for the frozen `shell.spec.ts`'s bare-`/runs` reading.
- New tests: `tests/unit/runs-queue-lib.test.ts`, `tests/unit/runs-queue-table.test.ts`,
  `tests/unit/runs-queue-island.test.ts`, `tests/e2e/runs-queue.spec.ts` (10 cases).

**Review findings breakdown:** 17 total findings across blind-hunter, edge-case-hunter,
verification-gap, and intent-alignment (after deduplicating same-claim findings across
reviewers) — 6 patched (2 medium, 4 low; see Review Triage Log for each), 9 rejected as
matching this story's own brief or already-shipped codebase precedent, 2 deferred to
frontmatter `deferred` (not this story's problem: one cosmetic gap on an unmatched `?project=`
deep link, one forward-looking risk for whichever story lands Epic 7's History table).

**Follow-up review recommendation:** `true`. This pass's own patched findings: 2 medium + 4
low → `3 × 2 + 1 × 4 = 10 ≥ 5`. No patched finding was `high`.

**Verification performed:** see Commands above — `make lint`, `make test`, `make openapi`,
`make e2e` (144 passed, includes the known engine-walker flake target, which passed this
run), and `make e2e-ui` (run twice, 118 passed after the patch round, port 4321 left clean).

**Residual risks:** the two deferred items above (frontmatter `deferred`); none block this
story's own acceptance criteria, all of which are green.
