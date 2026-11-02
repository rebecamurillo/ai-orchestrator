---
title: 'Operator senior session on the Run page'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'a7b5b9adf2c571febb8d226a731fa8bb21302d3d'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 2-3 and 2-5 built the Operator's senior session (lock, close, turns) behind `session_start`, `session_end`, `GET /runs/{id}/session` and `POST /runs/{id}/session/messages`, and the Run page offers none of it. The Operator still has no way to open the session, read it, or close it without writing the requests by hand.

**Approach:** The Run page reads `GET /runs/{id}/session` beside the detail on every poll. At a stop that admits `session_start` it offers *Senior session*: scope, harness and model, then the conversation, the message box, and *Close session*. While the session is open the stop shows only what `admitted_signals` still admits (`cancel`, `session_end`), so the lock on the page is the server's. A refused close for unconfirmed anchor edits lists each file with *Confirm* and *Revert*; the confirmed paths travel with `session_end`.

## Boundaries & Constraints

**Always:**
- The offer comes from the session read: `available` and not `active`. It is not derived from the park kind. The scopes offered are the read's `scopes`, the narrowest preselected.
- Harness choices are the enabled entries of `GET /harnesses`. Choosing one runs `GET /harnesses/{name}/probe`. The model control is the New Workflow form's `ModelField` over that probe's `models`; blank means the harness default. A failed probe prints its `failing_reason` and keeps *Start session* disabled.
- *Start session* posts `session_start` with `{scope, harness, model?}`. Close posts `session_end`, with `{confirmed_paths}` once files are confirmed. Neither carries `stop`.
- A message posts `POST /runs/{id}/session/messages {text}` and the draft clears only on success. The message box and *Send* are disabled while `turn_running` and while a request is in flight. The turn running is shown as a status line naming the turn.
- Each turn shows its number, the Operator's message and the senior's reply. An empty reply on a finished turn reads `no reply file` beside a link to the attempt's log. A turn that ended `error` states its exit code.
- *Revert* on an anchor edit posts a message asking the senior to restore that file, and clears that file's confirmation. *Close* with edits listed is enabled only when every listed file is confirmed and no turn is running.
- A 409 or 422 from a start, a close or a message shows its `detail` verbatim in the existing `wf-signal-error` readout (`sendSignal`'s `signalError`).
- Polling stays at 5 s while a turn runs on a parked Run, so the box re-enables within one tick of the turn ending.
- Copy states facts and mechanisms (NFR-8).

**Never:** No hand edit of `src/api/schema.d.ts`. No derived status, and no client-side lock rule: the page hides what `admitted_signals` omits. No existing test file is edited. `AGENTS.md` is not touched. No backend change.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected | Error Handling |
|---|---|---|---|
| Offer | Parked Run, session read `available` | *Senior session* button under the stop | N/A |
| No offer | `dependency` park, running Run, `available` false | No button | N/A |
| Choose | Open the form | Scope list from `scopes`, enabled harnesses, model control empty until a harness is probed | N/A |
| Probe ok | Harness chosen | `ModelField` lists the probe's models; *Start session* enabled | N/A |
| Probe fails | `ok: false` | `failing_reason` shown; *Start session* disabled | N/A |
| Start | Scope, harness, model chosen | `session_start` posted; page refetches; conversation shown | 409 or 422 `detail` in `wf-signal-error`; form stays |
| Locked | `admitted_signals` is `["cancel","session_end"]` | Answer, Retry, Continue and Skip absent; *Cancel run* present; lock line shown | N/A |
| Turn running | `turn_running` true | Box and *Send* disabled; running line; polling 5 s | N/A |
| Turn ends | `turn_running` false after a poll | Box and *Send* enabled; reply shown | N/A |
| Send | Text typed | Message posted; draft cleared; session refetched | 409 or 422 `detail`; draft kept |
| Close, clean | No anchor edit | `session_end` with no paths; stop's own controls return | N/A |
| Close, unconfirmed | 409 `anchor edits neither confirmed nor reverted: …` | Each edit listed with kind, path, *Confirm*, *Revert* | `detail` also in the readout |
| Confirm all | Every edit confirmed | *Close with confirmed files* posts `session_end {confirmed_paths}` | N/A |
| Revert | *Revert* on one file | Message posted asking for the revert; the file leaves the list on a later poll | N/A |
| Cancel | Session open | *Cancel run* works as ever | N/A |

</frozen-after-approval>

## Code Map

Under `web-client/` unless stated.

- `src/lib/run/session.ts` -- new, pure: constants and copy, `offersSession`, `sessionOpen`, `defaultScope`, `startableHarnesses`, `reconcileModel`, `canStart`, `startBody`, `endBody`, `messageBody`, `canSend`, `turnState`, `isUnconfirmedRefusal`, `revertMessage`, `toggleConfirmed`, `confirmedFor`, `allConfirmed`, `logHref`, `keepsFastPoll`, the two request paths.
- `src/components/run/SessionPanel.tsx` -- new: the offer, the open conversation and the close; owns the draft, the confirmed set and the review flag.
- `src/components/run/SessionStart.tsx` -- new: scope, harness, probe and model, reusing `ModelField`.
- `src/components/run/SessionTurns.tsx`, `SessionAnchors.tsx` -- new: the turn list and the anchor review list.
- `src/islands/RunDetail.tsx` -- reads the session beside the detail (only on `needs_you`), posts messages, passes the panel its callbacks, and keeps polling fast while a turn runs. `sendSignal` returns the problem it set.
- `src/styles/run-detail.css` -- the panel's classes, tokens only.
- `tests/unit/run-session-lib.test.ts`, `tests/unit/run-session-panel.test.ts` -- new.
- `tests/e2e/run-detail-session.spec.ts` -- new, mocks the session endpoints with `page.route()`.

## Tasks & Acceptance

**Execution:**
- [x] `tests/unit/run-session-lib.test.ts`, `tests/unit/run-session-panel.test.ts`, `tests/e2e/run-detail-session.spec.ts` -- new; every matrix row, seen failing first -- TDD.
- [x] `src/lib/run/session.ts` -- the pure logic -- keeps `src/lib` over 90 % lines.
- [x] The four components, the island wiring and the CSS -- per Code Map.
- [x] `make openapi` -- confirm no drift; the contract is not changed here.

**Acceptance Criteria:**
- Given a parked `blocked` Run whose session read is `available`, when the Operator opens *Senior session*, picks scope, harness and model, and starts it, then `session_start` carries those three and the conversation appears.
- Given an open session with a turn running, when the poll returns `turn_running: false`, then the message box is enabled again.
- Given a close refused for unconfirmed anchors, when each file is confirmed and the Operator closes, then `session_end` carries every path and the stop's answer, retry, continue and skip controls return.

## Implementation Notes

Built tests first at baseline `a7b5b9a`.

**Decisions.**
- The offer is a separate panel under the stop body, not a button inside `StopBody`: `admitted_signals` never lists `session_start` (story 2-3), so `StopBody`'s filters cannot carry it, and the stop body stays untouched.
- The session is read only while the Run is `needs_you`: `scopes` is empty otherwise and a terminal Run holds no session.
- A refused close opens the review when the read's `anchor_edits` is non-empty; the server computes it while the session is active and the page never parses the refusal's text.
- A revert is a plain message (CAP-7). The page does not claim the file is restored: it leaves the list when a later poll no longer lists it.
- The Run read models carry `senior_session` (omitted when false), so the artifact modal withholds *Edit* during a session.

**Gates.** `make lint` passes; `make test` passes (9170 backend with 1 skipped, 1768 web-client; `src/lib/run/session.ts` at 100 % lines); `make openapi` leaves no drift. `run-detail-session.spec.ts` was written against mocked endpoints and not run in this session: `make e2e-ui` is the parent's gate, so the story stays `in-review` until it passes.

## Spec Change Log

- 2026-11-02, review. The frozen "No backend change" gave way to one read-model field, `senior_session` on the Run summary, at the lead's direction (triage row 3). KEEP: every matrix outcome.

## Review Triage Log

| Finding | Layer | Verdict | Route | Evidence and action |
| --- | --- | --- | --- | --- |
| `SessionPanel` unkeyed while `StopBody` is keyed on `park_seq`: form scope, probe and an unsent draft survive into the next stop, and a kept `story` scope gets a 422 where only `run` is offered | edge, blind | high | patch | Reproduced by reading `RunDetail.tsx`. The panel is keyed on `park_seq`; neither `session_start` nor `session_end` moves it, so a session does not reset mid-way. Browser specs move the stop through a stale-stop 409 and assert a clean form and an empty draft. |
| Close refusal recognised by the server's sentence (`UNCONFIRMED_PREFIX`) | blind | medium | patch | The text can change without a contract change. `opensReview` opens the list on any refused `session_end` when the read's `anchor_edits` is non-empty, and re-checks on each newer read. The prefix and its test are removed. |
| Artifact modal *Edit* offered during a senior session; the Run summary carried no flag | edge | medium | patch | `senior_session` added to `RunStateOut`, omitted when false (the `pause_requested` pattern), so frozen exact-key tests pass; `make openapi` regenerated; `canEditFile` also checks `!run.senior_session`. Backend tests in `test_run_senior_session_read_model.py`. |
| `session_start` still offered during a terminal session, then refused 409 | verification | none | reject | Not reproduced: `run_admitted_signals` returns `cancel`, `terminal_release` while `terminal_session` is set and never lists `session_start`; `can_start_session` makes the read's `available` false. Pinned by a new test rather than changed. |
| Per-row *Confirm*/*Revert* share names; *Confirm* changes its word; focus drops when the form or Close unmounts | blind | medium | patch | `aria-label` carries the file; the word stays *Confirm* and `aria-pressed` alone states it. Focus moves to the scope select, the offer, the message box or the anchor list, once the post in flight ends (a disabled control cannot take focus). Browser spec asserts each. |

## Verification

**Commands:**
- `make lint` -- expected: passes, including the test-pairs check and `gen:api --check`.
- `make test` -- expected: passes, with `src/lib` over 90 % lines.
- `make openapi` -- expected: no drift.
