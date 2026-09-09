---
title: 'Skip story with the re-baseline'
type: 'feature'
created: '2026-09-09'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
deferred:
  - summary: >-
      A stop whose park_path lies outside every Story frame can still advertise skip_story in
      admitted_signals, so a Skip story button posted there answers 409 rather than not being
      offered at all.
    evidence: |-
      `admitted_signals(park_kind, row_kind)` answers from the park kind and the parked row's
      kind alone and cannot run `validate`'s `extra=_has_story_frame` — its own docstring says
      so. This predates 6.4 (5.10's `blockedSignals` already renders the button on a
      `misconfigured` stop from `admitted_signals` alone); 6.4 declined to extend it, gating
      its own four new bodies on the response naming a current Story, but did not narrow the
      three bodies 5.10 landed, whose behaviour is pinned by frozen tests.
    location: >-
      backend-api/src/orchestrator/application/rules/signals.py::admitted_signals
    severity: low
  - summary: >-
      The Board card's `m/m` count is proven at the `progress()` function rather than through
      `board_view`'s own rendered Card.
    evidence: |-
      `_card` passes `progress=_progress(run, steps)` verbatim, so the two cannot disagree —
      but the assertion is one hop from the surface the brief's AC names ("the card reads
      8/8 stories").
    location: >-
      backend-api/tests/unit/application/test_run_views_summary.py
    severity: low
baseline_revision: 'aaa45d66df5c93a603df045d53b52c30c440c166'
---

<intent-contract>

## Intent

**Problem:** `skip_story` is the one AD-13 action the Operator has no way to reach: the 4.5
writer implements every effect, but `handle_signal` still refuses the kind `not available
yet`, no stop body offers a *Skip story* control, and a Run that finishes with a skipped
Story does not list it in `summary.skipped` — because that list keys on a `skipped`
commit-guard row, and an operator-skipped Story's commit-guard *runs*.

**Approach:** Widen `handle_signal`'s scope gate to `skip_story`, narrow the *offered*
signals after the `re-baseline failed after skip` park (the Story is already skipped, so the
stop admits Retry / Skip epic / Cancel run), widen `summary.skipped` to name a frame the
Operator skipped, and add a reusable inline-confirm control that renders *Skip story* on
every body the brief lists.

## Boundaries & Constraints

**Always:**
- AD-13 stays the authority on validity: `rules/signals.py::validate` is **not** changed.
  Only `run_admitted_signals` — the set a stop *offers* — drops `skip_story` after a
  re-baseline park, keyed on `run.park_reason`, which PRD §4.6 makes part of the same
  "reason-text and admitted-signal contract".
- AD-8's two writers are untouched: no new module writes a Run or Step status. The whole
  effect stays `signal_run` → `signal_effects._skip_story`, exactly as 4.5 built it.
- `summary.skipped` widens; it never narrows. A `skipped` commit-guard row keeps listing its
  Story (`test_run_views.py` pins that and stays untouched).
- A frame counts as operator-skipped only when one of its rows is `skipped` with reason
  `SKIPPED_BY_OPERATOR`. `skipped · no quality_gate_command` and the `skipped` runs an
  already-done Story leaves behind must never be mistaken for it.
- The inline confirm is a component with its own state, reusable verbatim by 6-5 for *Skip
  epic*; no modal, no `dangerouslySetInnerHTML`, and the trigger keeps the
  `wf-signal-skip_story` test id every existing spec already asserts.
- Module cap 400 lines: `run_views.py` (389) and `apply_step_result.py` (394) both need a
  real seam rather than a squeeze.
- New coverage goes in new test files. The single sanctioned edit to an existing test is the
  pending-gate registry row in `test_handle_signal.py`.

**Block If:**
- Any assertion in an existing test file other than the `skip_story` row of
  `test_every_kind_outside_this_epics_scope_is_refused_not_available_yet` would have to
  change. HALT and report the file, the test, the assertion, and the minimal edit.

**Never:**
- Do not implement, test, or shape anything for `skip_epic` (6-5), `budget_raise`/`continue`
  on `protected_path` (6-6), the terminal path (6-7), or the UJ-3 journey scenarios (6-8).
- Do not widen `stopSignals`/`hasEffect`/`EFFECTIVE_KINDS` or `blockedSignals`/
  `checkpointSignals` — all three are pinned by frozen tests. A new sibling filter is the
  precedent (`checkpoint.ts::checkpointSignals` is itself one).
- Do not change `_story_cell`'s `state`: the brief's own assumption is that a skipped Story
  counts toward `stories_done`, and the strip's `epicDoneCount` would then disagree with the
  card. The skip is named beside the link instead.
- Do not touch the Epic-7 gaps (`pgid` on a resumed dispatch, `Harness.resume`'s arguments).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Skip a blocked Story | `needs_you`, `blocked` on `stories[1].build` | `build`/`after` → `skipped · skipped by operator`, `verify` → `queued`, commit-guard message `story 2: skipped by operator`, Run `running`, `skip_story` gate record | — |
| No quality gate | frame's `verify` is `skipped · no quality_gate_command` | the frame's `git.commit` row is queued directly | — |
| Skip at a done checkpoint | park `checkpoint` on the frame's `checkpoint` row | that row → `skipped`, the walk continues past the frame | — |
| Re-baseline fails | redispatch target `skipped` | park `verify_failed · re-baseline failed after skip`; `admitted_signals == (retry, skip_epic, cancel)` | — |
| Ordinary verify failure | park `verify_failed`, any other reason | `skip_story` still offered (PRD §4.6 unchanged) | — |
| Done Run, one skipped Story | commit-guard `done`, frame holds an operator-skipped row | `summary.skipped == ["2"]`, `stories_done == stories_total` | — |
| Confirm / Keep | *Skip story* clicked | the confirm line renders; *Skip story* posts the signal, *Keep* posts nothing | — |

</intent-contract>

## Code Map

**Backend — the scope gate.**
- `application/use_cases/signals.py::_in_scope` (line ~72) — the tuple `("cancel", "retry",
  "answer")` is the whole gate; `skip_story` joins it. `handle_signal` needs nothing else:
  `signal_run` → `EFFECTS["skip_story"]` is already wired and covered.
- `tests/unit/application/test_handle_signal.py` (lines ~232-251) — the parametrized
  pending-gate registry. Remove **only** the `skip_story` tuple entry and its `ids` string
  (hard rule 1, exception 1). Nothing else in that file changes.

**Backend — the re-baseline park's offered set.**
- `application/use_cases/apply_step_result.py:123` `REBASELINE_FAILED = "re-baseline failed
  after skip"`, raised at line ~255 when `_redispatch` finds the target `skipped`. Already
  wired and covered (`test_apply_step_result.py::
  test_a_redispatch_onto_a_row_that_was_never_run_parks_with_the_skip_reason`). **Move** the
  constant to `application/rules/signals.py` and import it back here — `apply_step_result.py`
  is at 394/400 and `rules/signals.py` must not import a use case.
- `application/rules/signals.py::run_admitted_signals` (line ~260) — after delegating to
  `admitted_signals`, drop `skip_story` when `run.park_reason == REBASELINE_FAILED`.
  `admitted_signals(park_kind, row_kind)` itself is **frozen** by
  `test_signal_rules.py::test_a_stop_offers_the_actions_prd_4_6_lists`
  (`verify_failed → retry, skip_story, skip_epic, cancel`) and must not change.
- `validate` is not touched: AD-13 admits the signal, and applying it at that park is
  harmless (it re-queues the same verify row a Retry would).

**Backend — the summary, and the split that makes room.**
- `application/use_cases/run_views.py` (389/400) — `_summary` (line ~380) lists a Story only
  when its commit-guard row is `skipped`. Split the Board/summary arithmetic out to a new
  `application/use_cases/run_views_summary.py` along the seam `run_views_alert.py` already
  established: move `_PROGRESS_TEMPLATES`, `_SETTLED`, `_BRACKET_INDEX`, `_progress`,
  `_story_cells`, `_story_cell`, `_frame_is_current`, `_bracket_index`, `_summary`; re-bind
  the private names in `run_views.py` (`_progress = progress`, …) so every call site and any
  test that reaches for them keeps working. Then widen the skipped list there.
- `application/use_cases/signal_effects.py::SKIPPED_BY_OPERATOR` (`"skipped by operator"`) —
  the reason `_skip` writes; the new detector reads it. `rules/frames.py::rows_in_frame`/
  `story_frame` give the frame's rows.
- `_progress` needs **no** change: `stories_done` already counts commit rows in
  `("done", "skipped")`, and a skipped Story's commit-guard reaches `done`.

**Backend — already landed, verify only (no code change expected).** `signal_effects.py::
_skip_story`/`_skip_frame`/`_rewrite_commit_message`/`resume_from` implement every writer
rule the brief states; `test_signal_run.py` lines 180-254 already cover the agent rows, the
commit message, the next frame, the no-quality-gate case, the `verify_failed` park and the
run-out-of-rows case. The one uncovered branch is a park **on** the frame's own checkpoint
row (a done checkpoint) — add it as new coverage, do not edit that file.

**Frontend.**
- `src/lib/run/skip.ts` (new, pure) — `SKIP_STORY_STOP_KINDS` (the brief's seven: `blocked`,
  `checkpoint`, `verify_failed`, `timeout`, `protected_path`, `misconfigured`, `internal`),
  `offersSkipStory(kind, admitted)`, `skipStoryConfirmLine(storyId)` (verbatim, with the
  quoted commit message), `SKIP_STORY_LABEL`/`KEEP_LABEL`.
- `src/components/run/ConfirmAction.tsx` (new, owns its own open/closed state) — renders the
  trigger `<button data-testid="wf-signal-{kind}">`, and when open the confirm line
  (`wf-confirm-{kind}`) plus *confirm* (`wf-confirm-{kind}-yes`) and *Keep*
  (`wf-confirm-{kind}-keep`). Props only: `kind`, `label`, `line`, `confirmLabel`,
  `keepLabel`, `disabled`, `onConfirm`. Reused verbatim by 6-5.
- `src/components/run/StopBody.tsx` (215 lines) — after computing `signals`, append
  `skip_story` when `offersSkipStory` says so and it is not already there; render
  `ConfirmAction` in the button row **in place of** the plain button for `skip_story`, so
  `blocked`/`checkpoint`/`misconfigured` keep their existing ordering and test id. Story id
  from `answerTarget(detail).storyId` (`lib/run/answer.ts`).
- `src/components/run/CostBlock.tsx` — the compare-link `<li>` gains ` · skipped: {ids}` from
  `detail.summary.skipped` when the Run is `done` and the list is non-empty (brief: "the
  compare-link line on the done Run reads `{url} · skipped: {ids}`"). Keep the `href`
  assertions in `run-cost-block.test.ts` true.
- `src/styles/run-detail.css` (additive `.wf-confirm*` rules at the end, existing tokens).
- Frozen, do not touch: `run-detail-lib.test.ts` (`stopSignals`/`hasEffect`),
  `run-detail-lib-blocked.test.ts`, `run-stop-body-*.test.ts` (all assert only the
  *presence* of `wf-signal-skip_story`, which this preserves).

**E2E.** `backend-api/tests/e2e/test_skip_story.py` (new) on the `fake` harness: story 1
parks `blocked` (`fixtures/gates-repo/.fake-harness/1/attempt-1.yaml`), `skip_story` is
posted, the build row goes `skipped · skipped by operator`, the re-baseline `verify` passes
(`check.sh` on the committed `GATE_OK`), the commit guard reaches `done` and
`stories[1].sync` is queued. Copy the module shape of `tests/e2e/test_answer_signal.py`
(fixtures `settings`/`api`/`bmad_version`/`gates`/`test_mode`/`parked`, `poll_until`,
`epic_template_as`, cancel in the `finally`).

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/application/rules/signals.py` -- hold `REBASELINE_FAILED`,
  and drop `skip_story` from `run_admitted_signals` at that park -- the stop's offered set is
  the only thing the brief narrows.
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py` -- import the
  constant instead of defining it -- one definition, and the module stays under 400 lines.
- `backend-api/src/orchestrator/application/use_cases/signals.py` -- `skip_story` joins
  `_in_scope` -- the kind AD-13 admits finally has an effect to reach.
- `backend-api/src/orchestrator/application/use_cases/run_views_summary.py` (new) -- the
  moved progress/story-cell/summary arithmetic, with `summary.skipped` widened to a frame the
  Operator skipped -- makes room under the cap and fixes the list in one place.
- `backend-api/src/orchestrator/application/use_cases/run_views.py` -- import and re-bind the
  moved private names -- every existing call site keeps working unchanged.
- `backend-api/tests/unit/application/test_handle_signal.py` -- remove the `skip_story`
  registry row (and its `ids` entry) only -- the gate has landed.
- New backend test files, one concern each:
  `tests/unit/application/test_skip_story_signal.py` (the whole AC1 effect through
  `handle_signal`, the done-checkpoint park, the no-quality-gate variant),
  `tests/unit/application/test_skip_story_admitted.py` (`run_admitted_signals` at the
  re-baseline park and at an ordinary `verify_failed` park; `admitted_signals` itself
  unchanged), `tests/unit/application/test_run_views_summary.py` (an operator-skipped frame
  is listed, `no quality_gate_command` and an already-done Story are not, `stories_done`
  counts it), `tests/e2e/test_skip_story.py`.
- `web-client/src/lib/run/skip.ts`, `src/components/run/ConfirmAction.tsx` (new);
  `src/components/run/StopBody.tsx`, `src/components/run/CostBlock.tsx`,
  `src/styles/run-detail.css` -- the control, its confirm, and the compare line.
- New frontend test files: `tests/unit/run-skip-lib.test.ts`,
  `tests/unit/run-confirm-action.test.tsx`, `tests/unit/run-stop-body-skip.test.ts`,
  `tests/unit/run-cost-block-skipped.test.ts`, `tests/e2e/run-detail-skip-story.spec.ts`.
- `make openapi` -- regenerate only if a wire shape changed (none is expected) -- AD-3.

**Acceptance Criteria:**
- Given a Run parked `blocked` on `stories[1].build` with `sync done, build blocked, verify
  planned, commit-guard planned, after planned`, when `skip_story` is signalled through
  `handle_signal`, then `build` and `after` are `skipped · skipped by operator`, `verify` is
  `queued`, `commit-guard.with_resolved["message"]` is `story 2: skipped by operator`, the Run
  is `running`, and a `skip_story` gate record exists.
- Given a Run parked `verify_failed` with reason `re-baseline failed after skip`, when the
  detail is read, then `admitted_signals == ("retry", "skip_epic", "cancel")`; given the same
  park with any other reason, then `skip_story` is still offered.
- Given a `done` Run whose `stories[1]` frame holds a row `skipped · skipped by operator`,
  when the detail is read, then `summary.skipped == ["2"]` and `progress.stories_done ==
  progress.stories_total`.
- Given a Run parked `blocked` on the gates fixture's story 1, when `skip_story` is posted to
  the running stack, then the build row is `skipped · skipped by operator`, the re-baseline
  `verify` reaches `done`, the commit guard reaches `done`, and `stories[1].sync` starts.
- Given a stop body that admits `skip_story`, when *Skip story* is clicked, then the confirm
  line `skip story {id}: its remaining steps are marked skipped, the quality gate re-runs,
  leftovers are committed as "story {id}: skipped by operator"` is shown with *Skip story* and
  *Keep*; *Skip story* posts the signal and *Keep* posts nothing.
- Given a `done` Run with a skipped Story, when the Run detail renders, then the compare-link
  line reads `{url} · skipped: {ids}`.

## Spec Change Log

## Review Triage Log

### 2026-09-09 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 1, low 2)
- defer: 2: (high 0, medium 0, low 2)
- reject: 3: (high 0, medium 0, low 3)
- addressed_findings:
  - `[medium]` `[patch]` the four newly-added stop bodies could show *Skip story* on a park
    outside every Story frame, where `validate` answers 409 and the confirm line would read
    `skip story this story: … "story this story: skipped by operator"` — copy naming a
    mechanism it cannot name (NFR-8). `offersSkipStory` now takes the current Story id and
    refuses without one, the client-side twin of `rules/signals.py::_has_story_frame`; the
    three bodies 5.10 landed are left exactly as their frozen tests pin them.
  - `[low]` `[patch]` the inline confirm's sentence appeared with no announcement for a
    screen-reader user — `role="status"` added to the line.
  - `[low]` `[patch]` `skipped_stories` reads a reason `cancel` also writes; its docstring now
    records that `summary`'s own `done` gate is what keeps a cancelled Run out of the list.

Rejected as noise: the exact-string match on `park_reason` (one writer, and both sides are
pinned by `test_skip_story_admitted.py`); `skipped_stories` not sorting its rows (byte-identical
to the `_summary` it replaces, and `list_for_run` answers in `seq` order); `run_views_summary.py`
importing `SKIPPED_BY_OPERATOR` from a writer module (the alternative is a duplicated literal,
and the constant is already public there — `test_signal_run.py` imports it from the same place).

## Design Notes

**Why the narrowing is in `run_admitted_signals` and not in `validate`.** AD-13's table is
keyed on `(status, park_kind, row kind/status)` and says nothing about the park's reason;
changing `validate` would contradict the spine and break `test_signal_rules.py`'s
transcription of PRD §4.6. But PRD §4.6 is called "the reason-text **and** admitted-signal
contract", and the brief's own words for this stop are *Retry, Skip epic, Cancel run*. So the
reason narrows what the screen **offers**, while the table keeps deciding what is **valid** —
the same split `run_admitted_signals` already draws by answering `("cancel",)` for a Run that
is merely `running`.

**Why `summary.skipped` cannot key on the commit-guard row.** `_skip_story` deliberately
leaves the commit-guard row runnable, with a rewritten message, so the leftovers still land
on the branch — the whole point of the re-baseline. Its row therefore reaches `done`, not
`skipped`. The frame's own `skipped · skipped by operator` rows are the durable record that
the Operator skipped it, and the reason string is what separates them from
`skipped · no quality_gate_command` and from the `skipped` rows an already-done Story leaves.

**Why the confirm is a component, not state in `StopBody`.** `StopBody` is stateless by
design (`renderToStaticMarkup` in every one of its unit tests) and 6-5 needs the same control
for *Skip epic*. A `ConfirmAction` owning its own open/closed state keeps both true: the
static render is the closed state — exactly the `wf-signal-skip_story` button every existing
spec already asserts — and 6-5 reuses it by passing a different `kind`, `line` and label.

## Verification

**Commands:**
- `make lint` -- expected: ruff, ruff format, mypy (domain/application strict), import-linter
  (4 contracts kept), env contract, test pairs (backend + web), `gen:api --check`, eslint,
  prettier, `tsc --noEmit`, astro check all clean.
- `make test` -- expected: backend + web unit suites green; `domain/` + `application/` hold
  **100 %** branch coverage, including every new branch in `run_views_summary.py` and
  `run_admitted_signals`.
- `make openapi` -- expected: no drift (`contracts/openapi.json` and `schema.d.ts` unchanged).
- `make e2e` -- expected: green on the disposable stack (`ORCH_TEST_MODE=1`), including
  `test_skip_story.py`.
- `make e2e-ui` -- expected: green, including `run-detail-skip-story.spec.ts`. The two Epic-5
  PNGs under `_bmad-output/implementation-artifacts/epic-5-screens/` are regenerated by story
  5.10's anchor spec; commit the new bytes.

## Auto Run Result

Status: done

**Summary.** `skip_story` reaches its effect: `handle_signal`'s scope gate admits the kind
(the 4.5 writer needed no change beyond what it already did), a `verify_failed · re-baseline
failed after skip` park no longer offers a second *Skip story*, `summary.skipped` names a
frame the Operator skipped even though its commit-guard ran, and every stop body FR-20 lists
carries a *Skip story* control behind a reusable inline confirm.

**Files changed** (backend): `application/rules/signals.py` (holds `REBASELINE_FAILED`;
`run_admitted_signals` withdraws `skip_story` at that park — `validate` and `admitted_signals`
both untouched), `application/use_cases/apply_step_result.py` (imports the reason instead of
defining it), `application/use_cases/signals.py` (`skip_story` joins `_in_scope`),
`application/use_cases/run_views_summary.py` (new: `progress`/`story_cells`/`summary` moved out
of `run_views.py`, and `skipped_stories` widened to read the frame's own
`skipped by operator` rows), `application/use_cases/run_views.py` (389 → 303 lines; the moved
private names re-bound). Four new test files: `test_skip_story_signal.py`,
`test_skip_story_admitted.py`, `test_run_views_summary.py`, `tests/e2e/test_skip_story.py`.
Two pending-gate registry rows removed (see hand-back).

**Files changed** (frontend): `lib/run/skip.ts` and `components/run/ConfirmAction.tsx` (new),
`components/run/StopBody.tsx` (appends the control on the four bodies `stopSignals` cannot
reach, and renders every `skip_story` as a confirm), `components/run/CostBlock.tsx` (the
compare line reads `{url} · skipped: {ids}`), `styles/run-detail.css` (additive `.wf-confirm*`).
Five new test files: `run-skip-lib.test.ts`, `run-confirm-action.test.ts`,
`run-stop-body-skip.test.ts`, `run-cost-block-skipped.test.ts`, and
`tests/e2e/run-detail-skip-story.spec.ts`.

**Review findings breakdown:** 3 patch (1 medium, 2 low) — all applied and re-verified; 2
deferred (both low, in frontmatter `deferred`); 3 rejected as noise.

**Follow-up review recommendation:** `true` — patched severities were 0 high, 1 medium and 2
low, so the score is 3 × 1 + 1 × 2 = 5, which reaches the threshold of 5.

**Verification performed** (all five gates, foreground, real output, from a clean tree, and
re-run in full after the patches):
- `make lint` — pass: ruff, ruff format, mypy (domain/application strict), import-linter (4
  contracts kept), env contract (34/40 agree), test pairs (189 backend modules / 85 web
  modules), `gen:api --check` clean, eslint, prettier, `tsc --noEmit`, astro check (0 errors).
- `make test` — pass: 5216 backend passed, 1 skipped; `domain/`+`application/` **100 %** branch
  coverage; web-client 1111 passed across 83 files.
- `make openapi` — pass: no drift; `contracts/openapi.json` and `src/api/schema.d.ts` unchanged
  (this story adds no wire shape — `summary.skipped` and `admitted_signals` were both already
  published).
- `make e2e` — pass: 175 passed, 11 deselected, 38 subtests, on the disposable `aio-e2e` stack
  with `ORCH_TEST_MODE=1` (168 before this story; the seven new ones are `test_skip_story.py`).
- `make e2e-ui` — pass: 135 passed (130 before; the five new ones are
  `run-detail-skip-story.spec.ts`).

**Residual risks.** Two low items deferred, neither blocking an acceptance criterion. The two
Epic-5 screenshot deliverables changed again, as 6.3 documented they must: story 5.10's anchor
spec captures a full-page Run detail on every `make e2e-ui` run, and this story's action row
is inside that capture. The new bytes are committed.
