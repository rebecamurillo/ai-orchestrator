---
title: 'Cancel a Run while it is running'
type: 'feature'
created: '2026-09-25'
status: 'in-progress'
baseline_revision: '4729fa749433e389c8fbabe73096c8967b053e24'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** A Run in `running` or `queued` status offers no Cancel control; `StopBody` returns `null` when `stopKind` is `null` (the Run is not parked), and the only element that calls `onCancelClick` lives inside that early return.

**Approach:** Change the early return in `StopBody` so it renders just the Cancel button when `admitted_signals` includes `cancel` and `stopKind` is `null`; at every parked stop the component is unchanged.

## Boundaries & Constraints

**Always:**
- This is a client-only change; no backend modifications (server already admits `cancel` for running/queued Runs and the effects are in place).
- `StopBody` at a stop: behavior is identical to today — cancel button still renders as part of the stop body.
- `CancelModal` and its `RunDetail` wiring (`branch={detail.run.branch}`, `onConfirm={() => sendSignal('cancel')}`) stay unchanged; the confirm still names the branch.
- `data-testid="wf-cancel"` is the same testid in both paths (stop and non-stop).
- AD-8: `signal_run` is the only writer; this island never predicts the cancel outcome.

**Block If:** any requirement to modify the backend, re-run `make openapi`, or change `CancelModal.tsx`.

**Never:**
- Render any stop-body content (park reason, log tail, signal buttons) when `stopKind` is `null`.
- Duplicate the Cancel button (it renders in exactly one place for any given render: inside `StopBody`'s stop path when parked, or in the early-return path when running/queued).
- Touch `run-stop-body.test.ts` assertions that do not contradict the new behavior.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Running + cancel admitted | `status: running`, `admitted_signals: ['cancel']`, no alert | `data-testid="wf-cancel"` present, label "Cancel run", no `wf-stop-*` wrapper | — |
| Queued + cancel admitted | `status: queued`, `admitted_signals: ['cancel']`, no alert | same as above | — |
| Running + cancel not admitted | `status: running`, `admitted_signals: []`, no alert | component renders nothing (`''`) | — |
| Parked stop + cancel admitted | `status: needs_you`, `admitted_signals: ['continue','cancel']`, alert present | stop body renders (unchanged); cancel button present inside stop body | — |
| Done/cancelled | `status: done`/`cancelled`, `admitted_signals: []`, no alert | component renders nothing (`''`) | — |

</intent-contract>

## Code Map

- `web-client/src/components/run/StopBody.tsx:121-122` — early return `if (kind === null) return null;`; this is the one line to split: when `admitted_signals` includes `cancel`, render the cancel button instead of null
- `web-client/src/components/run/StopBody.tsx:167` — `const canCancel = detail.admitted_signals.includes('cancel');` in the main stop path; stays at its current position (used by the stop body's cancel button rendering at lines 325–334)
- `web-client/src/components/run/StopBody.tsx:325-334` — cancel button inside `wf-stop-actions`; read-only for this story, no change
- `web-client/src/components/run/CancelModal.tsx` — names the branch (`cancel run {branch}?`), confirmed by `run-cancel-modal.test.ts`; read-only
- `web-client/src/islands/RunDetail.tsx:250-264` — `StopBody` invocation; `onCancelClick={() => setCancelOpen(true)}` already wired; read-only
- `web-client/tests/unit/run-stop-body.test.ts:257-267` — `renders nothing for running, done, cancelled or queued`; the four-status loop uses the base fixture whose `admitted_signals: ['continue','cancel']` contradicts the new behavior for running/queued; must be updated to use `admitted_signals: []` for all four cases (story 2, 2026-09-25 declared behaviour change — running/queued now render cancel when admitted; this test pins the no-cancel path)
- `web-client/tests/unit/run-stop-body-cancel.test.ts` — new test file (test pair supplement for `StopBody.tsx`'s new non-stop cancel path)

## Tasks & Acceptance

**Execution:**
- `web-client/tests/unit/run-stop-body-cancel.test.ts` — (tests first, story 2, 2026-09-25) new file: `cancel button renders when running and cancel admitted`, `cancel button renders when queued and cancel admitted`, `nothing renders when running without cancel` — must fail before StopBody change
- `web-client/tests/unit/run-stop-body.test.ts` — (story 2, 2026-09-25 declared behaviour change) update `renders nothing for running, done, cancelled or queued`: add `admitted_signals: []` override to all four detail objects so the test pins the no-cancel path without contradiction
- `web-client/src/components/run/StopBody.tsx` — change the early return: after `const kind = stopKind(detail, token);`, replace `if (kind === null) return null;` with: `if (kind === null) { if (!detail.admitted_signals.includes('cancel')) return null; return (<div className="wf-stop-actions"><button type="button" className="wf-signal wf-cancel" data-testid="wf-cancel" disabled={posting !== null} onClick={onCancelClick}>Cancel run</button></div>); }`

**Acceptance Criteria:**
- Given a Run is `running` with `admitted_signals: ['cancel']`, when `StopBody` renders, then `data-testid="wf-cancel"` and text "Cancel run" appear, and no `data-testid="wf-stop-*"` is present.
- Given a Run is `queued` with `admitted_signals: ['cancel']`, then the same Cancel button appears with no stop body.
- Given a Run is `running` with `admitted_signals: []`, when `StopBody` renders, then the output is empty.
- Given a Run is parked (`needs_you`) with `admitted_signals: ['continue','cancel']`, when `StopBody` renders, the stop body is present (unchanged) and `data-testid="wf-cancel"` appears within it.
- Given `CancelModal` receives `branch: 'feat/step-handling-1'`, the confirm text contains `cancel run feat/step-handling-1?` — verified by `run-cancel-modal.test.ts` (no change needed).

## Design Notes

The cancel-only path returns a `<div className="wf-stop-actions">` with one button — the same wrapper the stop body uses for its action row. This keeps the button's visual position consistent (same CSS class) whether the Run is parked or running.

The `canCancel` declaration at line 167 is left in place; it is used by the stop body's cancel rendering at lines 325–334. The new early-return path uses `detail.admitted_signals.includes('cancel')` inline to avoid a declaration before the early-return block.

## Verification

**Commands:**
- `make test` — expected: all unit tests pass; web-client 90% line coverage maintained
- `make lint` — expected: zero errors (eslint, tsc, prettier --check)
