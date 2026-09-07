---
title: 'Run detail core'
type: 'feature'
created: '2026-09-07'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred: []
baseline_revision: '7fd13c6b1897cd9636522bb3c7b50447c5f5bd65'
---

<intent-contract>

## Intent

**Problem:** `/workflows/:id` does not exist. `GET /runs/{run_id}/detail` (4.12) and
`POST /runs/{run_id}/signals` (4.9) both exist and carry everything the screen needs, but
nothing renders either.

**Approach:** Build `src/pages/workflows/[id].astro` and the `RunDetail` island (header,
alert banner / done-summary / cancelled line, stop body per park kind, Steps table, Stories
strip, Cost block, Gate record, the Cancel confirm), composed from `src/components/run/*`
and driven entirely by one poll of `GET /runs/{id}/detail` — no second read, no derived
status (AD-8: `signal_run`/`apply_step_result` are the only writers; this screen only ever
reads what they already wrote).

## Boundaries & Constraints

**Always:** every planned row from `steps[]` visible from the start; the current row's
status cell and Gate-record marker are the only coloured elements outside the token itself
(NFR-6); `SKP`/`unvalidated` render as plain grey words, never green; a signal button is
offered only for a kind that both `admitted_signals` carries *and* has a real effect this
epic (`cancel`, `retry`, `continue` — SPEC Non-goals name the other seven as validated-but-
refused); Cancel run is the one modal in the product and states the real effect in mechanism
(NFR-8); `$poll`/`configurePolling` (4.13/4.14) is the only interval, keyed off
`run.status === 'running'`; a failed poll swaps the whole surface for `FailedFetch` (reused
unchanged from 4.14) and pauses polling until Retry.

**Block If:** none — the operator's own dispatch instructions resolved the one ambiguity that
would otherwise have blocked (see Design Notes, "No `plan-diff` endpoint").

**Never:** add, widen or reshape `GET /runs/{run_id}/detail`, `POST /runs/{run_id}/signals`,
or any other backend-api endpoint (explicit operator instruction for this dispatch — the
backend for this epic is complete); render a control for `answer`/`skip_story`/`skip_epic`/
`budget_raise`/the three `terminal_*` kinds, even where `admitted_signals` carries one — none
has an effect this epic; the run-graph `DIAGRAM` toggle (rendered, disabled, Epic 8); the
"Or continue in the session" placeholder and the artifacts placeholder (both absent, Epic 6);
active time (Epic 8, rendered as a fixed em dash).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 12 rows, row 5 running | stubbed detail | all 12 listed by path with tokens; row 5 promoted; no cell colour but the token | — |
| `plan_stale` park | `alert.park_kind='plan_stale'` | banner `plan stale: stories.yaml`; body shows the reason and path (no diff panel — see Design Notes), a `start a new run` link, and exactly *Continue*/*Cancel run* | Continue posts `{kind: continue}`, banner clears after the next poll |
| `push_rejected` park, `admitted_signals=[retry,cancel]` | stubbed detail | body shows the log tail and the resolve line | *Retry* posts `{kind: retry}` |
| Cancel run clicked | modal open | confirm posts `{kind: cancel, payload:{confirm:true}}`; dismiss posts nothing | — |
| `failed` Run | `run.status='failed'` | red banner; log tail of the failing row (found via the `failed` gate record — no `alert` is published for `failed`); only control is `start a new run` | no Retry/Cancel — `admitted_signals` is empty once terminal |
| `done` Run, 1 skipped story, 2 links | `summary` populated | summary line replaces the banner, lists links and the skipped id; no amber/red pixel anywhere | — |
| Skipped row, reason `no quality_gate_command` | `step.status='skipped'` | status cell reads `SKP · skipped — no quality_gate_command`, grey | — |
| A poll fails | 500 | full-surface `FailedFetch`; Retry restores the screen | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/api/routers/run_detail.py`,
  `backend-api/src/orchestrator/api/schemas/run_views.py` — read-only (4.12): `RunDetailOut`
  and everything it carries. **No backend file in this story's diff** — see Design Notes.
- `web-client/src/api/schema.d.ts` — read-only, already generated: `RunDetailOut`,
  `RunDetailSummaryOut`, `HeaderOut`/`HeaderMetaOut`, `AlertOut`, `StepRowOut`,
  `LatestAttemptOut`, `StoryCellOut`, `CostOut`, `GateRecordOut`, `SummaryOut`, `SignalIn`.
- `web-client/src/stores/poll.ts` — read-only (4.13/4.14): `$poll`/`configurePolling`/
  `forceTick`/`stopPolling`, called from this island's own fetch exactly as `Board.tsx` does.
- `web-client/src/components/FailedFetch.tsx` — read-only (4.14), reused verbatim.
- `web-client/src/lib/board/format.ts` — read-only: `ageText` and `tokenSignal` reused
  directly rather than re-derived (both are already generic three-hue/duration helpers).
- `web-client/src/lib/run/detail.ts` — new, pure, unit-tested: `runToken`, `bannerLevel`,
  `stopKind`, `currentStepPath`, `bannerText`, `cancelledAtText`, `summaryLine`, `logTail`,
  `moneyRatio`, `tokensText`, `wallClockText`, `hasEffect`, `stopSignals`, `storiesByEpic`,
  `epicDoneCount`, `storiesProgressText`, `stepStatusText`, `stepAt`, `metaLine`, `crumbText`,
  `branchLinkHref`, `stateEnteredAt`, `stateAgeSeconds`, `detailRequestPath`.
- `web-client/src/lib/run/signals.ts` — new: `signalBody`, `signalsRequestPath`,
  `signalLabel` — the `POST /runs/{id}/signals` half, split from `detail.ts` the way
  `lib/newwf/state.ts` splits `preflightBody`/`runBody` from the response-reading half.
- `web-client/src/components/run/{Header,Banner,StopBody,StepsTable,StoriesStrip,CostBlock,
  GateRecord,CancelModal}.tsx` — new, stateless, `renderToStaticMarkup`-tested.
- `web-client/src/islands/RunDetail.tsx` — new: the poll, the signal POST + re-fetch, the
  Cancel-confirm open/close state, composition. 1 prop (`runId`).
- `web-client/src/pages/workflows/[id].astro` — new: `Shell` + `<RunDetail client:load
  runId={id} />`, no server-side read of its own (`index.astro`'s own precedent for `Board`).
- `web-client/src/styles/run-detail.css` — new: tokens-only styling for all of the above.
- `web-client/tests/unit/run-*.test.ts` (11 files) — new unit coverage, one per module above.
- `web-client/tests/e2e/run-detail.spec.ts` — new: the brief's own AC scenarios in a real
  browser, `page.route()`-stubbed the way `new-workflow.spec.ts`/`board.spec.ts` are.

## Tasks & Acceptance

**Execution:**
- `web-client/src/lib/run/{detail,signals}.ts` -- pure derivations and the signal-POST body -- unit-testable without a DOM
- `web-client/src/components/run/*.tsx` -- presentational, DOM-free unit coverage
- `web-client/src/islands/RunDetail.tsx` -- fetch loop, staleness guard, signal POST + re-fetch, Cancel-confirm state -- CAP-15
- `web-client/src/pages/workflows/[id].astro` -- mounts the island -- SPEC CAP-15
- `web-client/src/styles/run-detail.css` -- tokens-only styling
- `web-client/tests/unit/run-*.test.ts` -- coverage for every module above
- `web-client/tests/e2e/run-detail.spec.ts` -- the brief's own AC scenarios in a real browser

**Acceptance Criteria:** the seven Given/When/Then scenarios in
`_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/briefs/4-15-run-detail-core.md`,
adjusted for the `plan_stale` body's own diff panel per Design Notes below (the reason and
path are shown; the line-diff itself is not, since no endpoint may be added to serve it).

## Spec Change Log

## Review Triage Log

## Design Notes

**No `plan-diff` endpoint — the brief's own `[ASSUMPTION]` does not survive contact with the
landed backend.** The brief's implementation notes ask this story to add
`GET /runs/{id}/plan-diff` (`api/routers/runs.py`, `difflib`). The operator's dispatch
instructions for this run state plainly, and specifically about this endpoint category: "The
endpoints you consume already exist — do not add, widen, or reshape one," immediately
followed by naming the exact two endpoints this screen consumes. Verified independently
against the landed backend: `backend-api/src/orchestrator/application/steps/plan_check.py`
reads both the original and the current copy of a stale list file only to compare them —
neither is persisted anywhere, so a new endpoint would have nothing to read even if one were
added, and `application/use_cases/writers.py::park_run` records only `PLAN_STALE.format(path=
stale)` ("plan stale: {path}") as the park's own reason, byte-identical to what
`AlertOut.reason` already carries. Resolution, spine-first the same way a brief/AD-n conflict
is resolved (this is the exact analogue for this dispatch's own explicit endpoint
constraint): the `plan_stale` stop body shows the reason and the affected path — both already
on the wire — plus a note standing in for the diff, and the pre-filled `start a new run` link
the binding rule also asks for. No endpoint was added; nothing in `backend-api/` changed.

**No `run.park_path` on the wire either — "the current row" is read off `gate_record[]`
instead.** `RunDetailSummaryOut` does not publish `park_path` (only the domain-side `Run`
entity carries it). `gate_record[]` is: `park_run`/`apply_step_result.py::_fail`/`_cancel`
each append one record naming the row's own `path` the moment the Run stops, and
`infrastructure/db/repositories/gate_records.py::list_for_run` orders it `at`-ascending. So
`src/lib/run/detail.ts::currentStepPath` reads the *last* record matching the relevant event
(`alert.park_kind` while `needs_you`, `'failed'` while `failed`) back off that same array —
the same fact, published through data the endpoint already returns, with no widening.

**A signal control renders only for a kind with a real effect this epic, even where
`admitted_signals` carries more.** SPEC Non-goals: "No answer, skip, budget raise, accept, or
terminal signals (Epic 6); `signal_run` validates them but their effects are absent." The
operator's dispatch instructions state the same rule explicitly: "Do not offer a control for
a kind with no effect." `application/rules/signals.py::admitted_signals` computes purely off
`park_kind`/`row_kind` and can legitimately include e.g. `skip_epic` for a real
`push_rejected` park (`skip_epic`'s own `park_kinds` excludes only `budget`/`plan_stale`).
The brief's own binding rule asks for a disabled, admitted-gated *Skip epic* button on that
park; this deviates from it per the operator's explicit, more specific instruction —
`src/lib/run/detail.ts::stopSignals` filters `admitted_signals` down to `{retry, continue}`
(`cancel` is its own always-present control, gated on `admitted_signals.includes('cancel')`
directly) before the Stop body ever sees the list, so a real `push_rejected` park with
`skip_epic` admitted still renders only *Retry*/*Cancel run*.

**The Alert banner's "right-aligned progress" is reconstructed from `stories[]`, not read off
a `progress` field.** `RunDetailOut` carries a `progress` figure only inside `summary`, which
is `null` until `done` (`_summary`). `stories[]` is present at every status, so
`storiesProgressText` counts its own cells (`state==='done'`) the same way
`application/use_cases/run_views.py::_progress` does server-side, including the same
`template==='initiative'` gate on whether an epics clause is shown at all. `''` (no clause)
for a Run with no Story frame (`repo-init`) — the same case `_progress` itself returns `None`
for.

**"The branch link" (COST & TRACE) is derived from the first compare URL.**
`RunDetailOut` carries no repository host URL. `git.push`'s own compare link is
`.../compare/{base}...{branch}`; `branchLinkHref` rewrites that same host+path prefix to
`.../tree/{branch}`. `null` (no link rendered) before any compare URL exists — a Run's branch
has nothing to link to until it has been pushed at least once.

## Verification

**Commands:**
- `make lint` -- ran; clean (ruff, ruff format, mypy strict on domain/application,
  import-linter, env-contract, test-pairs both components, `pnpm gen:api --check` — no drift,
  `pnpm lint` — astro sync/check, tsc, eslint, prettier, check-test-pairs)
- `make test` -- ran; backend 100% domain/application branch coverage maintained (unchanged —
  no backend file in this story's diff); web-client 942/942 unit tests passed;
  `src/lib/run/detail.ts`/`signals.ts` covered (aggregate `src/lib/**` stays ≥ 90% lines, the
  gate `vitest.config.ts` enforces)
- `make openapi` -- ran; no drift (no backend route touched, `contracts/openapi.json` and
  `src/api/schema.d.ts` both byte-identical to before this story)
- `PATH="$HOME/.docker/bin:$PATH" make e2e` -- ran; 144 passed, 34 subtests passed, against a
  disposable `aio-e2e` stack, cleaned up after; the known `test_the_engine_picks_the_run_up_
  and_walks_it` flake (4.17's own fix) did not fire this run
- `make e2e-ui` -- ran twice (once caught a test-fixture merge-order bug in this story's own
  `run-detail.spec.ts`, fixed, re-ran clean); 109 passed the second time (101 existing/frozen
  + 8 new `run-detail.spec.ts` tests); port 4321 left clean afterward, no long-lived server

## Auto Run Result

Status: done

**Summary.** `/workflows/:id` now renders the Run detail: header (crumb, chip+token+branch+
age of the current state, unabridged meta line, `DIAGRAM · DETAIL` toggle), the Alert banner
(`needs_you`/`failed` only) with the reason verbatim and right-aligned progress/spend, the
`done` summary line and the `cancelled` line as the two other banner-area states, the Steps
table (every planned row, current row promoted, only the token ever coloured), the Stories
strip (per-epic, per-story cells), the Cost & Trace kv (ratio, tokens, wall-clock, compare
and branch links), the Gate record timeline (current row `■` in the signal colour), the stop
bodies for all seven park kinds this epic has (`plan_stale`, `push_rejected`, `timeout`,
`misconfigured`, `internal`, `verify_failed`, `checkpoint`) plus the `failed` "Other states"
body, and the Cancel-run confirm (the one modal in the product, stating its real effects in
mechanism). Every status shown is read verbatim off one `GET /runs/{id}/detail` poll (reusing
4.13/4.14's `$poll` store); `POST /runs/{id}/signals` is the only write, always followed by a
re-fetch.

**No backend change.** Confirmed against the operator's explicit dispatch instructions and
independently against the landed code (Design Notes): no endpoint was added, widened, or
reshaped. The brief's own `[ASSUMPTION]`-tagged `plan-diff` endpoint was not built; the
`plan_stale` stop body shows the reason, the path, and a `start a new run` link instead of a
line-diff panel — the only place this story's behaviour narrows what the brief literally
asked for, and it is called out above rather than silently dropped.

**Files changed** (web-client, all paths relative to `web-client/`):
- `src/lib/run/detail.ts`, `src/lib/run/signals.ts` — new, pure, unit-tested.
- `src/components/run/{Header,Banner,StopBody,StepsTable,StoriesStrip,CostBlock,GateRecord,
  CancelModal}.tsx` — new, presentational.
- `src/islands/RunDetail.tsx` — new: the poll, the signal POST + re-fetch, composition.
- `src/pages/workflows/[id].astro` — new.
- `src/styles/run-detail.css` — new.
- `tests/unit/run-{detail-lib,signals-lib,detail-island,header,banner,stop-body,steps-table,
  stories-strip,cost-block,gate-record,cancel-modal}.test.ts` — new unit coverage.
- `tests/e2e/run-detail.spec.ts` — new: the brief's own AC scenarios, in a real browser.

**Review findings:** none — no review pass has run yet over this diff (`bmad-build-auto`'s
review step, if invoked separately).

**Follow-up review recommended:** true (no review has run over a story of this size yet).

**Verification performed:** see `## Verification` above.

**Residual risks / hand-off to 4.16:**
- `src/lib/run/detail.ts`'s `stepAt`/`logTail`/`stepStatusText` and `src/components/
  FailedFetch.tsx` (reused unchanged) are the pieces most likely useful to 4.16's own queue
  section; `$poll`/`configurePolling` is still the one shared interval — call it from 4.16's
  own fetch rather than opening a second one.
- The "current row via the last matching `gate_record[]` entry" technique
  (`currentStepPath`/`stateEnteredAt` in `src/lib/run/detail.ts`) is this story's own answer
  to `run.park_path` not being on the wire; any future screen needing "what row is this Run
  stopped on" should reuse it rather than re-deriving it.
- The `plan_stale` stop body's missing line-diff is a known, deliberate narrowing (Design
  Notes) — if a later story is authorised to add a small backend endpoint for it, `src/
  components/run/StopBody.tsx`'s `PlanStaleBody` is the one place to extend.
- No review layer has run over this diff yet — `followup_review_recommended: true` reflects
  that gap, not a specific known defect.
