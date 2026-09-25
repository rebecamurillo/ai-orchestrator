---
title: 'Skip one step'
type: 'feature'
created: '2026-09-25'
status: 'in-review'
baseline_revision: 'f8b9909311863aef6cd0d8fd68d81a20ad9e496c'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** The operator has no way to skip a single parked step; the only step-level escapes skip the entire story or epic, which discards more work than the situation warrants.

**Approach:** Add `skip_step` as a `SignalKind` and `RunEvent` with a `needs_you → running` transition, a `Rule` that admits it on every park kind (any row in `blocked|checkpoint|error`), a one-row effect that marks the parked row `skipped` and resumes the Run at the next row, and a confirm button in StopBody beside *Skip story* and *Skip epic*.

## Boundaries & Constraints

**Always:**
- `STEP_TRANSITIONS` already holds `(blocked|checkpoint|error, skip) → skipped`; add no new step-machine edge (no `(running, skip)`, no `(planned, skip)`, no `(queued, skip)`).
- `park_kinds = ANY_PARK` (all 12 park kinds); `row_statuses = frozenset({"blocked","checkpoint","error"})` per AD-13 ratified 2026-09-25.
- `signal_run` is the only writer (AD-8); the effect touches one row: the parked one.
- No dispatch, no worktree write; the walker resumes at the next row via `resume_from`.
- `domain/` and `application/` import nothing from infrastructure (AD-2).
- `VALID` dict order must match `SIGNAL_KINDS` exactly (`test_signals_table.py::test_the_two_modules_share_one_table_object`); `skip_step` goes after `retry`, before `skip_story`.
- The spine's AD-13 table row for `skip_step` is ratified 2026-09-25; the rule is: "park_path names a row whose status is `blocked|checkpoint|error`".
- 100 % branch coverage on `domain/` and `application/` (`make test`).

**Block If:** any requirement to skip more than one row, touch the step machine beyond the three existing skip edges, or reach a running step.

**Never:**
- A `(running, skip)` step transition or any path that kills a running step.
- Skipping a `done` row or a null `park_path` silently — both must produce a 409 with the INVALID sentence naming the park kind.
- Any change to what `skip_story` or `skip_epic` do.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal skip (error row) | Run `needs_you`, any park_kind except `dependency`, park_row status `error` | park row → `skipped (skipped by operator)`, Run → `running`, next unfinished row → `queued`, gate_record written | — |
| Normal skip (blocked row) | park_row status `blocked` | same as above | — |
| Normal skip (checkpoint row) | park_row status `checkpoint` | same as above | — |
| Last step remaining | park_row is the only unfinished row | park row → `skipped`, Run → `done` (Effect.finished=True) | — |
| Dependency park | Run `needs_you`, `park_kind="dependency"`, `park_row=None` | 409 "signal skip_step invalid for status needs_you / park dependency" | API 409 Conflict |
| Budget/done row | Run `needs_you`, `park_kind="budget"`, `park_row.status="done"` | 409 "signal skip_step invalid for status needs_you / park budget" | API 409 Conflict |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/statuses.py:61-74` — `SignalKind` Literal and `SIGNAL_KINDS`; add `"skip_step"` after `"retry"` at line 66; also `RunEvent` Literal (lines 136-151), add after `"retry"` (line ~143); `RUN_TRANSITIONS` (lines 181-197), add `("needs_you", "skip_step"): "running"` after the `retry` entry.
- `backend-api/src/orchestrator/domain/statuses.py:202-221` — `STEP_TRANSITIONS` already holds `(blocked, skip)`, `(checkpoint, skip)`, `(error, skip)` → `skipped`; read-only for this story.
- `backend-api/src/orchestrator/application/rules/signals_table.py:247-349` — `VALID` dict; insert `"skip_step"` entry after `"retry"` (line ~281), before `"skip_story"`. Rule fields: `park_kinds=ANY_PARK`, `row_statuses=frozenset({"blocked","checkpoint","error"})`, `run_event="skip_step"`, `text="step skipped by the operator"`. `ANY_PARK` constant is already defined at line 73.
- `backend-api/src/orchestrator/application/rules/signals.py:100-114` — `admitted_signals` iterates `VALID`; no code change needed — `skip_step` appears automatically. `_skippable` (lines 163-170) drops only `skip_story`/`skip_epic` by frame; `skip_step` is unaffected. `run_admitted_signals` returns early for dependency parks at line 155, so `skip_step` is not offered there.
- `backend-api/src/orchestrator/application/use_cases/signal_effects.py:181-343` — add `_skip_step` function after `_retry` (before `_skip_story`): `row = _parked(park_row); _skip(ports, row); return Effect(finished=not resume_from(ports, row))`. Add `"skip_step": _skip_step` to `EFFECTS` dict after `"retry"`.
- `backend-api/tests/unit/application/test_signal_rules.py:31-46` — `STOPS` dict (PRD §4.6 transcription, story 1, 2026-09-25 behavior change); add `"skip_step"` to all 11 park-kind entries. Also add three new tests: admitted on all parks, dependency refusal, done-row refusal.
- `backend-api/tests/unit/application/test_signal_run.py:184+` — new `# ── skip_step` section before `# ── skip_story`; two tests: normal skip (parked row → skipped, Run → running), last-step skip (Run → done).
- `web-client/src/lib/run/signals.ts:26-33` — `signalLabel`; add `if (kind === 'skip_step') return 'Skip step';` before the fallback.
- `web-client/src/lib/run/skip.ts` — add three exports: `SKIP_STEP_LABEL = 'Skip step'`, `skipStepConfirmLine(path: string | null): string` (returns `"skip ${path ?? 'this step'}: marks it skipped and continues at the next row"`), `offersSkipStep(admitted: readonly SignalKind[]): boolean` (returns `admitted.includes('skip_step')`).
- `web-client/src/components/run/StopBody.tsx:141-144` — after the `signals` const (which appends skip_epic), rewrite to: rename the skip_epic result `withSkipEpic`, then `const signals = offersSkipStep(detail.admitted_signals) && !withSkipEpic.includes('skip_step') ? [...withSkipEpic, 'skip_step' as SignalKind] : withSkipEpic;`. Also add `const skipStepLine = skipStepConfirmLine(path);` (path is already computed). In `buttons.map`, add `s === 'skip_step'` branch rendering a `<ConfirmAction>` with `label={SKIP_STEP_LABEL}`, `line={skipStepLine}`, `confirmLabel={SKIP_STEP_LABEL}`, `keepLabel={KEEP_LABEL}`, `onConfirm={() => onSignal(s)}` — same shape as skip_story.
- `web-client/tests/unit/run-stop-body-skip-step.test.ts` — new test file (test pair for StopBody skip_step control): verify the ConfirmAction renders when `admitted_signals` includes `"skip_step"`, that confirming posts the signal, and that it does not render when `skip_step` is absent.

## Tasks & Acceptance

**Execution:**
- `backend-api/src/orchestrator/domain/statuses.py` — add `"skip_step"` to `SignalKind` Literal (after `"retry"`), `RunEvent` Literal (after `"retry"`), and `("needs_you", "skip_step"): "running"` to `RUN_TRANSITIONS` after the retry entry — this is the AD-13 contract (ratified 2026-09-25)
- `backend-api/tests/unit/application/test_signal_rules.py` — (tests first, story 1, 2026-09-25) update `STOPS` dict: add `"skip_step"` to all 11 park-kind signal tuples; add `test_a_skip_step_is_admitted_on_every_non_dependency_park_kind`, `test_a_skip_step_on_a_dependency_park_is_refused`, `test_a_skip_step_on_a_done_row_is_refused` — these must fail before the Rule is added
- `backend-api/tests/unit/application/test_signal_run.py` — (tests first, story 1, 2026-09-25) add `test_a_skip_step_marks_the_parked_row_skipped_and_resumes_the_run` and `test_a_skip_step_with_nothing_left_ends_the_run` — must fail before the effect is added
- `web-client/tests/unit/run-signals-lib-skip.test.ts` — (tests first, story 1, 2026-09-25) add `signalLabel('skip_step')` case: `expect(signalLabel('skip_step')).toBe('Skip step')` — must fail before the signals.ts change
- `web-client/tests/unit/run-skip-lib.test.ts` — (tests first, story 1, 2026-09-25) add tests for `SKIP_STEP_LABEL`, `skipStepConfirmLine('some/path')`, `skipStepConfirmLine(null)`, `offersSkipStep(['skip_step'])`, `offersSkipStep([])` — must fail before the skip.ts change
- `web-client/tests/unit/run-stop-body-skip-step.test.ts` — (tests first, story 1, 2026-09-25) new test file: `test_skip_step_confirm_renders_when_admitted`, `test_skip_step_confirm_absent_when_not_admitted`, `test_skip_step_confirm_posts_skip_step_on_confirm` — must fail before the StopBody change
- `backend-api/src/orchestrator/application/rules/signals_table.py` — add `"skip_step": Rule(park_kinds=ANY_PARK, row_statuses=frozenset({"blocked","checkpoint","error"}), run_event="skip_step", text="step skipped by the operator")` to `VALID` after `"retry"`, before `"skip_story"` — makes signal_rules tests pass
- `backend-api/src/orchestrator/application/use_cases/signal_effects.py` — add `_skip_step` (skip the one parked row, call `resume_from`) and `"skip_step": _skip_step` to `EFFECTS` after `"retry"` — makes signal_run tests pass
- `web-client/src/lib/run/signals.ts` — add `if (kind === 'skip_step') return 'Skip step';` to `signalLabel`
- `web-client/src/lib/run/skip.ts` — add `SKIP_STEP_LABEL`, `skipStepConfirmLine`, `offersSkipStep`
- `web-client/src/components/run/StopBody.tsx` — import new skip.ts exports; rewrite the `signals` const to chain through `withSkipEpic` then append skip_step; add `skipStepLine`; add skip_step branch in `buttons.map`
- run `make openapi` — regenerate `contracts/openapi.json` and `pnpm gen:api` so `skip_step` appears in `SignalIn.kind`; run after all backend changes are in place

**Acceptance Criteria:**
- Given a Run is parked on an `error` step with any non-dependency park kind, when `POST /runs/{id}/signals {kind: "skip_step"}` is sent, then that row's status is `"skipped"` with reason `"skipped by operator"`, the Run status is `"running"`, the next unfinished row is `"queued"`, and a gate_record with `event: "skip_step"` and `actor: "operator"` is written.
- Given a Run is parked on the last unfinished step (`error`), when `skip_step` is posted, then the Run reaches `"done"`.
- Given a Run is parked on a `dependency` stop (`park_path` null), when `skip_step` is posted, then the response is 409 with detail `"signal skip_step invalid for status needs_you / park dependency"`.
- Given a Run is parked on a `budget` stop where the park row's status is `done`, when `skip_step` is posted, then the response is 409 with detail `"signal skip_step invalid for status needs_you / park budget"`.
- Given `admitted_signals("blocked", "agent")` is called after the Rule is added, then `"skip_step"` is in the returned tuple.
- Given a Run detail where `detail.admitted_signals` includes `"skip_step"`, when `StopBody` renders, then a `data-testid="wf-signal-skip_step"` element appears (the ConfirmAction's closed trigger button), and clicking it opens the confirm; clicking the confirm label posts `{kind: "skip_step"}` via `onSignal`.
- Given `detail.admitted_signals` does not include `"skip_step"`, when `StopBody` renders, then no `data-testid="wf-signal-skip_step"` element appears.

## Spec Change Log

## Review Triage Log

## Design Notes

`_skip_step` is the simplest of the skip effects: one `_skip(ports, row)` call, then `resume_from` to queue the next unfinished row starting from the parked seq. No frame traversal, no commit-message rewrite, no story-frame logic. `validate`'s `row_statuses` check handles both refusal cases (dependency: `park_row is None`; budget/done: `park_row.status not in {"blocked","checkpoint","error"}`), so the effect function can assert `_parked(park_row)` without additional guards.

The `signals` chain in `StopBody` must rename the intermediate skip_epic result `withSkipEpic` to leave `signals` as the final combined list, so the four downstream references (`accepting`, `hasRetryBox`, `buttonsAfterAccept`, `buttons`) need no change.

## Verification

**Commands:**
- `make lint` — expected: zero errors (ruff, mypy strict on domain+application, import-linter, eslint, tsc)
- `make test` — expected: all unit tests pass including new skip_step tests; 100 % branch coverage on `domain/` and `application/`
- `make openapi` — expected: `contracts/openapi.json` regenerated with `skip_step` in `SignalIn.kind` enum, `pnpm gen:api` succeeds
