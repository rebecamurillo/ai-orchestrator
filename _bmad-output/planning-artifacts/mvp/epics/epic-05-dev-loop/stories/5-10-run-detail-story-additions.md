---
title: 'Run detail additions for story steps'
type: 'feature'
created: '2026-09-08'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

# Run detail additions for story steps

## Auto Run Result

Status: done

**What was implemented.** The Run detail's own read model and screen now carry every field
and surface SPEC CAP-10 asks for.

- **`Alert.attribution` / `AlertOut.attribution`** (`{harness, model, ended_at}`) — the
  parked row's own latest `Attempt`, read once in `run_views.py::run_detail` off
  `run.park_path` and passed through `_alert`/`_attribution`. `None` for a park kind whose
  row never ran an attempt (`checkpoint` reached with no agent dispatch, for instance).
  `attempt.harness`/`.model`/`.ended_at` are already settled by the time a Story can block —
  `steps/agent_tail.py::finish` calls `mark_finished` before `tail`/`route` ever produce a
  `blocked` park — so reading them at `run_detail` time is never a race.
- **`LatestAttempt.cost_provisional` / `LatestAttemptOut.cost_provisional`** — a straight
  passthrough of `Attempt.cost_provisional` (5.3), so the Steps table can mark an estimated
  cost without a second read.
- **`QuestionBlock.tsx`** (new): for `alert.park_kind === 'blocked'`, the eyebrow `Agent ·
  {harness} · {model} · {ended_at}` then the whole `## Auto Run Result` section
  (`alert.reason`) rendered from a small allowlist Markdown parser (`lib/run/markdown.ts`,
  new) — headings, lists, fenced and inline code, plain paragraphs. Link/image syntax
  (`[x](y)`, `![x](y)`) is never parsed at all, so it prints as literal text; nothing in
  either file ever calls `dangerouslySetInnerHTML`, so an agent's own story-file text cannot
  become live markup by construction, not by escaping. Unit-tested directly against a
  `<script>` payload and a `javascript:` link/image payload (`run-question-block.test.ts`).
- **`StopBody.tsx`** extended: `kind === 'blocked'` renders `QuestionBlock`; `kind ===
  'misconfigured'` renders the condition line (`bannerText`, i.e. `alert.reason`) and — when
  the condition names files (only `ambiguous story file: a.md, b.md` does,
  `rules/routing.py::AMBIGUOUS_STORY_FILE`) — a file list (`misconfiguredFiles`, new pure
  fn). Neither path renders a textarea; Epic 6's Answer box does not exist anywhere in this
  codebase yet, so "no Answer box" is true by construction, proven by an explicit
  `not.toContain('<textarea')` assertion. The button row for both kinds now uses
  `blockedSignals` (new, `lib/run/detail.ts`) instead of `stopSignals` — `retry` (admitted
  for `misconfigured` only) plus the two skips, `answer` never rendered even though
  `admitted_signals` carries it for `blocked` (Epic 6 non-goal). `blockedSignals` is a
  **separate** filter from `EFFECTIVE_KINDS`/`hasEffect`: the frozen `run-detail-lib.test.ts`
  asserts `hasEffect('skip_epic') === false` and lists "only cancel, retry and continue have
  any effect this epic" — that assertion had to stay true, so the two skips get their own
  small allowlist rather than joining the one that test pins.
- **`signalLabel`** gains `Skip story`/`Skip epic` (`lib/run/signals.ts`).
- **`StepsTable.tsx`** cost cell fixed: it was reading `latest.cost_usd` (one attempt);
  now reads `step.cost_usd` (5.3's own row-summed field) with ` provisional` appended when
  `latest.cost_provisional`. No frozen test asserted the old (wrong) text.
- **`CostBlock.tsx`**: the spent/budget cell appends a `provisional` span
  (`wf-cost-provisional`) when `cost.provisional`; the trace link moved from a bare paragraph
  to its own kv row (label `trace`, link text `open in Langfuse`, `wf-trace`), still entirely
  inside `{cost.trace_url ? … : null}` — the frozen `run-cost-block.test.ts`'s
  `not.toContain('trace')` assertion on a null `trace_url` stays true because the whole row,
  not just the link, is conditional.
- **The signal rule** ("the question block's rule and the current strip cell are the only
  amber elements a `blocked` detail shows"): `Banner.tsx`'s top alert and `GateRecord.tsx`'s
  last-row marker both read `detail.alert?.park_kind === 'blocked'` and go neutral for that
  one park kind only — every other `BLK`/`CHK` case (`plan_stale`, `timeout`, `checkpoint`,
  …) keeps its existing amber unchanged. Both frozen tests (`run-banner.test.ts`,
  `run-gate-record.test.ts`) only ever exercise `plan_stale` or a null `alert`, so neither
  special case touches them.
- **Stories strip, harness/cost columns, "readiness"/"repo-init" cards, the compare/branch
  links**: all pre-existing (4.14/4.15/5.3) and verified rather than rebuilt — see "What was
  verified, not rebuilt" below. The one literal mismatch between the brief's own binding
  rules and the shipped 4.15 component is `StoriesStrip.tsx`'s cell test-id: the brief's own
  Test-ids list names `wf-stories-cell-<id>`, but the component (predating this story) uses
  `wf-story-<id>`, and the frozen `run-stories-strip.test.ts` asserts exactly
  `data-testid="wf-story-4-1"`. Root `AGENTS.md` hard rule 1 (anchors are read-only, no
  exception fits a plain naming mismatch) makes the frozen test's name binding; the existing
  `wf-story-<id>` test-id was kept unchanged rather than renamed.

**What was verified, not rebuilt** (the brief's own "4.14 already reads `kind_label`;
verify" instruction, and the Stories-strip/cost-kv/harness-column binding rules already
satisfied by earlier stories):
- `RunCard.tsx` reads `card.kind_label` generically — no `repo-init`/`readiness` special
  case anywhere in it — so `readiness` already renders exactly like `repo-init` did. New
  test: `run-card-readiness.test.ts` (the frozen `run-card.test.ts` only ever asserts
  `repo-init`).
- `StoriesStrip.tsx` already renders done/current/future/skipped with the right
  `data-state`, and `_frame_is_current` (`run_views.py`, pre-existing) already marks a
  `blocked` story's own frame `current` via `run.park_path`, not `row.status` — so "a
  blocked story's cell is the current one" needed no code change, only the e2e coverage this
  story adds.
- `StepsTable.tsx`'s harness column (`latest?.harness ?? '—'`) already reads "empty
  otherwise" correctly — it is `null` on every non-agent row already.

**Files changed:**
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` — added:
  `Attribution`; `Alert.attribution`, `LatestAttempt.cost_provisional` (both defaulted).
- `backend-api/src/orchestrator/application/use_cases/run_views.py` — added: `_attribution`,
  `_latest_of` (shared by `_step_row`); modified: `_alert` (new `attempt` param),
  `run_detail` (computes the parked row's own latest attempt), `_latest_attempt` (carries
  `cost_provisional`). `run_graph_for` moved out — see "What was moved" below. 400/400.
- `backend-api/src/orchestrator/application/use_cases/run_graph.py` — **new** (32 lines):
  `run_graph_for`, split out of `run_views.py` on line count alone; re-exported from there
  so `api/routers/graph.py` and the frozen `test_run_views.py` (which imports it off
  `run_views`) keep resolving unchanged.
- `backend-api/src/orchestrator/api/schemas/run_views.py` — added: `AttributionOut`;
  `AlertOut.attribution`, `LatestAttemptOut.cost_provisional` (both `_drop_default`-schema-
  optional, matching `StepRowOut.cost_usd`'s own precedent). Board classes moved out — see
  below. 344/400.
- `backend-api/src/orchestrator/api/schemas/board_view.py` — **new** (115 lines):
  `ProgressOut`, `CardOut`, `BoardColumnsOut`, `BoardCountsOut`, `BoardOut`, split out of
  `run_views.py` on line count alone; re-exported from there so `api/routers/run.py` and the
  frozen `test_run_view_schemas.py` (which imports `BoardOut`/`CardOut` off `run_views`) keep
  resolving unchanged. One-directional import (`run_views.py` imports `board_view.py`, never
  the reverse) — no cycle.
- `backend-api/tests/unit/application/test_run_views_attribution.py` — **new**: the
  attribution/`cost_provisional` acceptance criteria through `run_detail(...)`, plus a direct
  `run_graph_for` import off its own new module (AD-18 pairing).
- `backend-api/tests/unit/test_run_view_schemas_attribution.py` — **new**: `AttributionOut`/
  `AlertOut`/`LatestAttemptOut` `.of()` coverage, plus a direct `board_view` import proving
  the re-exported Board classes are the same objects `board_view.py` defines (AD-18 pairing).
- `web-client/src/lib/run/markdown.ts` — **new** (67 lines): `parseQuestionMarkdown`.
- `web-client/src/components/run/QuestionBlock.tsx` — **new** (69 lines).
- `web-client/src/lib/run/detail.ts` — added: `AttributionOut` type, `questionEyebrow`,
  `misconfiguredFiles`, `blockedSignals`. 345 lines.
- `web-client/src/lib/run/signals.ts` — modified: `signalLabel` gains two cases.
- `web-client/src/components/run/StopBody.tsx` — modified: the `blocked`/`misconfigured`
  branches, the `blockedSignals`-aware button row.
- `web-client/src/components/run/StepsTable.tsx` — modified: `costText`.
- `web-client/src/components/run/CostBlock.tsx` — modified: the provisional span, the trace
  kv row.
- `web-client/src/components/run/Banner.tsx` / `GateRecord.tsx` — modified: the `blocked`
  neutral-signal special case.
- `web-client/src/styles/run-detail.css` — added: `.wf-question*`, `.wf-stop-files`.
- Nine new web-client unit test files (`run-markdown-lib`, `run-question-block`,
  `run-detail-lib-blocked`, `run-signals-lib-skip`, `run-stop-body-blocked`,
  `run-cost-block-provisional`, `run-steps-table-cost`, `run-banner-blocked`,
  `run-gate-record-blocked`) and one (`run-card-readiness`) verifying pre-existing behaviour.
- `web-client/tests/e2e/run-detail-story-additions.spec.ts` — **new**: the `blocked` and
  `misconfigured` screens end to end (mocked `page.route()`, `run-detail.spec.ts`'s own
  precedent — that file is frozen and predates both park kinds), and this epic's own
  screenshot capture.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` — regenerated (`make openapi`).

**Verification performed** (every gate run in the foreground, its exit code observed
directly):
- `make lint` — exit 0: ruff check/format clean, `mypy --strict` over `domain/`+
  `application/` clean (119 pre-existing errors elsewhere — `main.py`, `api/routers/run.py`
  — confirmed identical via `git stash` against origin/main's own baseline, none of them in
  a file this story touches), all four import-linter contracts KEPT, env contract unchanged
  (no new setting), `check_test_pairs` 179 backend modules paired (up from 177), `gen:api
  --check` no drift, web-client astro-check/eslint/prettier/tsc all clean, web-client's own
  `check-test-pairs.mjs` 73 modules paired.
- `make test` — exit 0: 4933 backend unit tests passed (up from 4869 at 5-9), 1 skipped;
  1014 web-client unit tests passed (up from 973 at the last epic-4 count), across 75 files.
- `make openapi` — exit 0, no drift: `contracts/openapi.json` and `schema.d.ts` regenerated
  and committed with the new `AttributionOut` schema and the two new optional fields.
- `make e2e-api` (via `make e2e`, its own disposable `aio-e2e` stack) — exit 0: 145 passed,
  11 deselected, 36 schemathesis subtests passed.
- `make e2e-ui` — exit 0: 120 passed, including both new
  `run-detail-story-additions.spec.ts` cases. Screenshots captured (see below); the seven
  `ai-orchestrator-host-*` containers were left running throughout.

**Anchor check** (the literal command from the dispatch instructions):
```
for f in $(git diff --name-only origin/main..HEAD; git diff --name-only); do case "$f" in *test*|*tests/*|*.spec.ts) git cat-file -e origin/main:"$f" 2>/dev/null && echo "FLAG: $f"; esac; done
```
Flags exactly the five files the dispatch names as pre-existing and none of them mine:
`backend-api/tests/unit/fakes/{clock,git,workspace}.py`, `backend-api/tests/e2e/
test_harnesses.py`, `backend-api/tests/unit/test_harnesses_router.py`. No pre-existing test
file, `SPEC.md`, `stories.yaml`, `epics.yaml` or any `AGENTS.md` was touched. Every test
module this story adds — backend and web-client alike — is a brand-new file.

**Screenshots** (`_bmad-output/implementation-artifacts/epic-5-screens/`, captured by
`run-detail-story-additions.spec.ts` while `make e2e-ui` ran):
- `01-run-detail-blocked-question.png` — a `blocked` story: the whole Question block with
  the `Agent · claude · claude-opus-4 · {time}` eyebrow, the Stories strip showing all four
  states (done filled, current amber, future hollow, skipped struck), the cost kv with
  `provisional` and the `open in Langfuse` trace link, and the step row's own
  `$3.20 provisional` cost cell.
- `02-run-detail-misconfigured.png` — a `misconfigured` park (`ambiguous story file:
  1-2-a.md, 1-2-b.md`): the condition line, the two-file list, the log tail, *Retry* /
  *Skip story* / *Skip epic* / *Cancel run*, and no Answer box.
No state was skipped or faked — both are reachable from the stub backend via `page.route()`
mocking, `run-detail.spec.ts`'s own established pattern for this screen.

**The Question block's copy** (from `01-run-detail-blocked-question.png`'s own fixture):
eyebrow `Agent · claude · claude-opus-4 · 2026-09-07T09:12:00Z`; body — heading `Auto Run
Result`, paragraph `Which database migration tool should this story use?`, a two-item list
(`alembic`, `raw SQL`), and a closing paragraph. Agent attribution is the eyebrow line alone,
directly off `alert.attribution`, never inferred from the header's own `harness` field
(which names the Run's harness, not necessarily the one that ran the blocking attempt).

**The `misconfigured` body's proof of no Answer box:** `web-client/tests/unit/
run-stop-body-blocked.test.ts` asserts `expect(html).not.toContain('<textarea')` on the
rendered `misconfigured` body, and `web-client/tests/e2e/run-detail-story-additions.spec.ts`
asserts `expect(page.locator('textarea')).toHaveCount(0)` against the real browser DOM. Both
pass because no `<textarea>` element exists anywhere in this codebase yet — Epic 6 has not
landed.

**What was moved to make room, and final line counts.** `run_views.py` (application) was
398/400 before this story and needed roughly 15 new lines (`_attribution`, `_latest_of`,
the widened `_alert`, `cost_provisional` on `_latest_attempt`, the `run_detail` wiring) —
`run_graph_for` (14 lines) moved out to the new `run_graph.py`, landing the module at
400/400 exactly. `api/schemas/run_views.py` (399/400) needed roughly 15 new lines
(`AttributionOut`, the two field additions) — the five Board classes (~85 lines) moved out
to the new `board_view.py`, landing at 344/400, comfortably clear. Neither split changes any
public import path: both new modules are re-exported from the module they were split out of,
the exact precedent `run_view_types.py`'s own module doc already set for this repository
(and, for the API-schema split specifically, the one-directional import direction that
precedent implies — `board_view.py` never imports `run_views.py`, only the other way,
so there is no cycle). Final line counts: `run_views.py` (application) 400/400,
`run_view_types.py` 217, `run_graph.py` 32; `api/schemas/run_views.py` 344/400,
`board_view.py` 115. `lib/run/detail.ts` 345, `QuestionBlock.tsx` 69, `markdown.ts` 67,
`StopBody.tsx` 157 — all comfortably under web-client's own 300-line component cap (the two
`.ts` lib files are not components and carry no such cap).

**What 5-11 must know.**
- `run_views.py` (application) is at 400/400 — zero headroom. A story that needs to add to
  it should expect to split something out first, following the `run_graph.py`/
  `board_view.py` precedent this story set: a new module, re-exported from the original for
  every existing import path, one-directional (never import back).
- `Alert.attribution` and `LatestAttempt.cost_provisional` are both defaulted (`None`/
  `False`) specifically so no existing construction site anywhere in the codebase needed a
  fourth argument — 5-11 (or any later story) building on `Alert`/`LatestAttempt` should keep
  that pattern for its own new fields, the same reason `StepRowView.cost_usd` (5.3) already
  established.
- The `blockedSignals`/`EFFECTIVE_KINDS` split in `lib/run/detail.ts` is deliberate, not an
  oversight: `hasEffect`/`stopSignals` stay exactly the three kinds 4.15 gave (the frozen
  `run-detail-lib.test.ts` pins this), and `skip_story`/`skip_epic` render only through
  `blockedSignals`, only for `blocked`/`misconfigured`. A future epic that gives
  `skip_story`/`skip_epic` an effect on some other park kind should extend `blockedSignals`'s
  own allowlist, not fold it into `EFFECTIVE_KINDS`.
- `StoriesStrip.tsx`'s cell test-id is `wf-story-<id>`, not the brief's own
  `wf-stories-cell-<id>` — see "What was implemented" above for why it was kept. Any story
  writing a new test against that cell should use the actual `wf-story-<id>` id.
- Real-credential verification (Claude readiness end to end against the real host LiteLLM/
  Langfuse) is explicitly 5-11's own job, per the epic's stories.yaml entry — nothing in this
  story touched `.env` or read real credentials; every test here runs against fakes and the
  e2e stub backend.

**Operator decisions needed:** none. No anchor conflict was hit; the one brief-vs-frozen-test
naming mismatch (`StoriesStrip.tsx`'s test-id) was resolved by the anchor rule itself, not by
a judgment call, and is recorded above for visibility rather than as an open question.

**Follow-up review recommended:** false. Self-reviewed against the brief's five acceptance
criteria (all five pass as unit and e2e tests) and the epic's own CAP-10 success line ("the
whole `## Auto Run Result` is shown as the Question with agent attribution"); no subagent
review pass was run for this dispatch.
