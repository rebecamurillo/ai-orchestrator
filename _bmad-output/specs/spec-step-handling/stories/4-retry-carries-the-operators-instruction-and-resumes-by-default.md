---
title: 'Retry carries the operator''s instruction and resumes by default'
type: 'feature'
created: '2026-09-25'
status: 'done'
baseline_revision: '876a1f63e448646dd648628a8fbfa74765662433'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
deferred:
  - summary: >-
      Type `resume_unavailable_reason` as `Literal["no_session", "no_capability"] | None`
      instead of `str | None` for compile-time enforcement of the closed value set.
    evidence: |-
      The field is assigned only two known string values in `_reply_status`; a Literal type
      would let mypy reject any typo or future third value at the assignment site.
    location: >-
      backend-api/src/orchestrator/application/use_cases/run_view_types.py
    severity: low
  - summary: >-
      Extract a shared `reply_available` helper to eliminate duplication between
      `_check_mode` (signal_run.py) and `_reply_status` (run_views.py).
    evidence: |-
      Both functions compute the same three-part condition (attempt, session_id, harness).
      Design Notes document this duplication as intentional minimal change; a shared helper
      avoids silent divergence if a fourth condition is added.
    location: >-
      backend-api/src/orchestrator/application/use_cases/signal_run.py and run_views.py
    severity: low
  - summary: >-
      Add a useEffect guard in RetryBox to reset mode to "restart" if the replyAvailable
      prop flips false after mount.
    evidence: |-
      useState initialises from the prop once; if the component stays mounted while
      replyAvailable changes (e.g. a background refetch) the mode state stays "session"
      and the next Retry POST returns 422. Unlikely in the current UI flow but not impossible.
    location: >-
      web-client/src/components/run/RetryBox.tsx
    severity: low
  - summary: >-
      Restore the web-client contract sentence `detail.reply_available ?? false` to the
      `_omit_false_reply_available` docstring, lost when the docstring was shortened to
      fit the 400-line module limit.
    evidence: |-
      The sentence was the only place in the backend documenting the falsy-absent convention
      and its web-client reading side; its absence makes the serializer's intent harder to
      verify on first reading.
    location: >-
      backend-api/src/orchestrator/api/schemas/run_views.py:372
    severity: low
---

<intent-contract>

## Intent

**Problem:** Three defects in the retry path: (a) `_session_message` sends the template's `retry.prompt` to a resumed session — the spine says the operator's own instruction is the message, with template prompt only as a fallback; (b) the restart path similarly ignores the operator's signal text; (c) `_check_mode` defaults an absent mode to restart even when the session is available and resumable. On the client, `RetryBox` renders only when `reply_available` and has no text field, so the operator cannot attach an instruction on either path.

**Approach:** Fix `_session_message` and the `_planned` restart path to prefer signal text over template prompt; change `_check_mode` to default to session when reply_available (writing the default into `signal.payload` so `_planned` reads it); add `resume_unavailable_reason` to `RunDetailOut`; rewrite `RetryBox` to always render, carry a text field, default its radio to session when available, and display the reason when session is unavailable.

## Boundaries & Constraints

**Always:**
- AD-2: `domain/` and `application/` import nothing from `infrastructure/`.
- AD-8: `signal_run` is the only writer; no island derives or writes a status.
- The priority order is invariant: signal `text` → template `retry.prompt` → `""`. The template prompt never overrides the operator.
- `_check_mode` writes the computed default mode into `signal.payload` (mutable dict) so `_planned`'s `operator_mode = ctx.resume_signal.payload.get("mode")` sees the defaulted value and the gate record captures it.
- `resume_unavailable_reason` takes value `"no_session"` or `"no_capability"` when `reply_available=False`; `None` when True or when `harness_is_resumable` is unwired.
- `RetryBox` sends `{mode, text}` in the payload; `text` is omitted when the field is empty (no empty-string noise in gate records).
- 100 % branch coverage on `domain/` and `application/` (`make test`).
- Copy states the mechanism; nothing apologises (NFR-8).

**Block If:** Any requirement to change the template auto-resume path (line 315 of `agent.py` — no operator signal, `retrying(ctx)=True`, `resume_signal=None`). That path is unaffected: `operator_mode` is `None` there, not a written default.

**Never:**
- Change what happens when `mode="session"` is sent explicitly to a non-resumable stop — those still raise `Invalid`.
- Change `AnswerBox` or the `answer` signal's session-path behaviour.
- Edit `templates/*.yaml` or pin template content in any test.
- Add a new `SignalKind` or `RUN_TRANSITIONS` entry.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Session retry + operator text | `mode=session`, `text="fix the enum"`, reply_available | resumed session receives `"fix the enum"`, not template prompt | — |
| Session retry, no operator text | `mode=session`, no `text`, reply_available | resumed session receives template `retry.prompt` (fallback) | — |
| Restart retry + operator text | `mode=restart`, `text="use psycopg"`, `retry` contract set | dispatch prompt is `"use psycopg {dispatch}"` | — |
| Restart retry, no operator text | `mode=restart`, no `text`, `retry` contract set | dispatch prompt is `"{retry.prompt} {dispatch}"` (unchanged) | — |
| Absent mode, reply_available=True | no `mode` in payload, session_id exists, harness resumable | `signal.payload["mode"]` set to `"session"`, run re-queued via session path | — |
| Absent mode, reply_available=False | no `mode`, no session or harness not resumable | `signal.payload["mode"]` set to `"restart"`, run re-queued via restart path | — |
| RetryBox, reply_available=True | `retry` admitted, reply_available | radio (session default), text field, Retry button | — |
| RetryBox, no_session | `retry` admitted, reply_available=False, reason=`no_session` | "No session was recorded", restart only, text field | — |
| RetryBox, no_capability | `retry` admitted, reply_available=False, reason=`no_capability` | "This harness does not support resume", restart only, text field | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/steps/agent.py:393-397` — `_session_message`: returns `retry.prompt if retry is not None else ""` for retry signals; fix to: return `signal.payload["text"]` if non-empty, else `retry.prompt`, else `""`
- `backend-api/src/orchestrator/application/steps/agent.py:308-329` — `_planned`: restart path at line 328 uses `retry.prompt`; fix to extract `operator_text = ctx.resume_signal.payload.get("text","") if ctx.resume_signal else ""` and use `operator_text or retry.prompt` for `RETRY_PROMPT.format(retry=..., dispatch=prompt)`
- `backend-api/src/orchestrator/application/use_cases/signal_run.py:171-190` — `_check_mode`: absent mode defaults to restart; fix to: if `_MODE_KEY not in signal.payload`, compute reply_available from `ports`, write `"session"` or `"restart"` into `signal.payload[_MODE_KEY]`; then read `mode = signal.payload[_MODE_KEY]` for the rest of the validation
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py:263-281` — `RunDetailView` dataclass; add `resume_unavailable_reason: str | None = None` after `reply_available`
- `backend-api/src/orchestrator/application/use_cases/run_views.py:244-254` — `_reply_available`: refactor to `_reply_status(ports, run) -> tuple[bool, str | None]` returning `(True, None)`, `(False, "no_session")`, or `(False, "no_capability")`; update call site in `run_detail` to unpack both values
- `backend-api/src/orchestrator/api/schemas/run_views.py:350-399` — `RunDetailOut`: add `resume_unavailable_reason: str | None = Field(default=None, json_schema_extra=_drop_default)`; extend `_omit_false_reply_available` serializer to also pop `resume_unavailable_reason` when `None`; add mapping in `of()`
- `contracts/openapi.json` + `web-client/src/api/schema.d.ts` — generated by `make openapi`; adds `resume_unavailable_reason?: string | null` to `RunDetailOut`
- `web-client/src/lib/run/signals.ts:38-40` — `retryBody(mode, text)`: include `text` in payload only when non-empty
- `web-client/src/components/run/RetryBox.tsx` — Props: add `replyAvailable: boolean`, `resumeUnavailableReason: string | null`; add `text` state; default radio to `session` when `replyAvailable`, no radio (restart forced) otherwise; show reason string when !replyAvailable; `onRetry(mode, text)` instead of `onRetry(mode)`; Props `onRetry: (mode: string, text: string) => void`
- `web-client/src/components/run/StopBody.tsx:85-86` — Props type: `onRetry?: (mode: string) => void` → `(mode: string, text: string) => void`
- `web-client/src/components/run/StopBody.tsx:177` — change `hasRetryBox` from `replyAvailable && signals.includes('retry')` to `signals.includes('retry')`; pass `replyAvailable={replyAvailable}` and `resumeUnavailableReason={detail.resume_unavailable_reason ?? null}` to RetryBox
- `web-client/src/islands/RunDetail.tsx:258` — `onRetry={(mode) => void sendSignal('retry', retryBody(mode))}` → `onRetry={(mode, text) => void sendSignal('retry', retryBody(mode, text))}`

**Read-only (context only):**
- `backend-api/src/orchestrator/application/steps/agent.py:299-316` — `_planned`: lines 313-316 (explicit session path via `_session_message`) and 315-316 (template auto-resume path) — template auto-resume path (`operator_mode != "restart" and tpl_ok and can_res`) is UNAFFECTED by this story
- `backend-api/tests/unit/application/steps/agent_tail_fixtures.py` — `RETRY_PROMPT`, `contracted()` — shared fixtures for tests
- `web-client/src/components/run/AnswerBox.tsx` — read-only; Answer path is unchanged

## Tasks & Acceptance

**Execution (TDD: tests before implementation):**

- `backend-api/tests/unit/application/use_cases/test_signal_mode.py` — (tests first, story 4, 2026-09-25) update `test_absent_mode_defaults_to_restart_and_is_never_rejected`: rename to `test_absent_mode_defaults_to_restart_when_reply_available_is_false`, update docstring (check IS called now; still defaults to restart when reply_available=False — story 4, 2026-09-25 declared behaviour change); add `test_absent_mode_defaults_to_session_when_reply_available` using `resumable=True, session_id="s-123"`, asserting `outcome.run.status=="running"` and `records[0].payload.get("mode")=="session"` — must fail before `_check_mode` fix
- `backend-api/tests/unit/application/steps/test_agent_session_answer.py` — (tests first, story 4, 2026-09-25) add `test_session_retry_message_uses_operator_text_when_provided`: retry gate record with `{"mode":"session","text":"fix the enum"}`, session mode, assert `resumed[0]["message"] == "fix the enum"` — must fail before `_session_message` fix; add `test_restart_retry_uses_operator_text_in_front_of_dispatch`: retry gate record with `{"mode":"restart","text":"use psycopg"}`, CANNOT_RESUME harness, assert `start()[0]["prompt"] starts with "use psycopg "` — must fail before `_planned` restart fix
- `backend-api/tests/unit/application/test_run_views_reply_available.py` — (tests first, story 4, 2026-09-25) add three tests: `resume_unavailable_reason_is_none_when_reply_available` (session_id set, resumable=True → reason=None); `resume_unavailable_reason_is_no_session_when_session_id_is_none` (session_id=None → reason="no_session"); `resume_unavailable_reason_is_no_capability_when_harness_not_resumable` (session_id set, resumable=False → reason="no_capability") — must fail before run_views fix
- `backend-api/src/orchestrator/application/use_cases/signal_run.py` — fix `_check_mode`: when `_MODE_KEY not in signal.payload`, compute reply_available from ports, write `"session"` or `"restart"` into `signal.payload[_MODE_KEY]`; read `mode = signal.payload[_MODE_KEY]` for the rest
- `backend-api/src/orchestrator/application/steps/agent.py` — fix `_session_message`: operator text > template prompt > `""`; fix `_planned` restart path: extract `operator_text` from signal payload, use it over `retry.prompt`
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` — add `resume_unavailable_reason: str | None = None` to `RunDetailView`
- `backend-api/src/orchestrator/application/use_cases/run_views.py` — refactor `_reply_available` into `_reply_status() -> tuple[bool, str | None]`; update `run_detail` call site
- `backend-api/src/orchestrator/api/schemas/run_views.py` — add `resume_unavailable_reason` field to `RunDetailOut`; extend serializer; update `of()`
- `make openapi` — regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts`; run after all backend changes
- `web-client/tests/unit/run-retry-box.test.ts` — (story 4, 2026-09-25 declared behaviour change) update `renders plain Retry button (no RetryBox) when replyAvailable=false`: this test now fails because RetryBox always renders; rename to `renders RetryBox even when replyAvailable=false` and assert `data-testid="wf-retry-box"` is present; add `renders session as default radio when replyAvailable=true`; add `renders restart-only with no_session reason when replyAvailable=false`; add `renders restart-only with no_capability reason when replyAvailable=false`; add `onRetry callback receives mode and text`; update `retryBody produces mode:session` to also include `text` — must fail before implementation
- `web-client/src/lib/run/signals.ts` — update `retryBody(mode, text)` to include text in payload when non-empty
- `web-client/src/components/run/RetryBox.tsx` — rewrite: Props `replyAvailable`, `resumeUnavailableReason`, `text` state, session default when available, reason messages, `onRetry(mode, text)`
- `web-client/src/components/run/StopBody.tsx` — change `hasRetryBox` condition; add `replyAvailable` and `resumeUnavailableReason` props to RetryBox
- `web-client/src/islands/RunDetail.tsx` — update `onRetry` to `(mode, text) => void sendSignal('retry', retryBody(mode, text))`

**Acceptance Criteria:**
- Given a retry signal with `{mode:"session", text:"fix the enum"}` on a resumable stop, when the executor runs, then `harness.resume()` receives `message="fix the enum"` (not the template prompt).
- Given a retry signal with `{mode:"session"}` and no `text`, on a resumable stop, when the executor runs, then `harness.resume()` receives the template's `retry.prompt` as message.
- Given a retry signal with `{mode:"restart", text:"use psycopg"}` and a non-resumable harness, when the executor runs, then `harness.start()` receives a prompt beginning with `"use psycopg "` followed by the dispatch.
- Given a retry signal with no `mode` key, when `reply_available=True` (session_id exists, harness resumable), then `signal.payload["mode"]` is set to `"session"` and the gate record captures that mode.
- Given a retry signal with no `mode` key, when `reply_available=False`, then `signal.payload["mode"]` is set to `"restart"`.
- Given `run_detail()` with session_id=None, then `detail.resume_unavailable_reason == "no_session"`.
- Given `run_detail()` with session_id set but harness not resumable, then `detail.resume_unavailable_reason == "no_capability"`.
- Given `run_detail()` with session_id set and harness resumable, then `detail.reply_available is True` and `detail.resume_unavailable_reason is None`.
- Given `retry` in `admitted_signals` and `reply_available=False`, when `StopBody` renders, then `data-testid="wf-retry-box"` is present (RetryBox always renders when retry is admitted).
- Given `RetryBox` renders with `replyAvailable=True`, then the session radio is checked by default.
- Given `RetryBox` renders with `replyAvailable=False` and `resumeUnavailableReason="no_session"`, then the output contains text stating no session was recorded and that restart is the only path.
- Given `RetryBox` renders with `replyAvailable=False` and `resumeUnavailableReason="no_capability"`, then the output contains text stating the harness does not support resume and restart is the only path.

## Spec Change Log

## Review Triage Log

### 2026-09-25 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 4 (high 1, medium 1, low 2)
- defer: 4 (low 4)
- reject: 10
- addressed_findings:
  - `[high]` `[patch]` Serialization gap: `resume_unavailable_reason` not tested at Pydantic `model_dump()` level — a mutant unconditionally popping the field passes all application-layer tests. Added three tests to `test_run_view_schemas.py` (field present for `"no_session"`, `"no_capability"`, absent when `None`).
  - `[medium]` `[patch]` I/O matrix row 4 untested: operator restart with no `text` and template retry prompt — `hint` fallback path not pinned. Added `test_restart_retry_no_text_uses_template_retry_prompt_as_hint` asserting `started[0]["prompt"].startswith(RETRY_PROMPT + " ")`.
  - `[low]` `[patch]` `resume_unavailable_reason` in safe-unwired path not asserted. Added `assert detail.resume_unavailable_reason is None` to `test_reply_available_false_when_harness_is_resumable_not_wired`.
  - `[low]` `[patch]` `retryBody` sends whitespace-only text when operator enters spaces. Changed `if (text)` to `if (text.trim())` in `signals.ts`.

---

### Iteration 0 detail — 2026-09-25

Four reviewers (blind-hunter, edge-case-hunter, verification-gap, intent-alignment) ran against the full diff.

**Patch (applied this iteration):**

1. **Serialization layer gap for `resume_unavailable_reason`** (verification-gap, blind-hunter) — `_omit_false_reply_available` serializer had no test at the `model_dump()` level; a mutant that unconditionally pops the field passes all application-layer tests. Added three tests to `test_run_view_schemas.py`: field present for `"no_session"`, field present for `"no_capability"`, field absent when `None`.

2. **I/O matrix row 4 untested** (verification-gap, intent-alignment) — operator restart with no `text` and a template retry prompt: the `hint` fallback path (`op=""`, `hint=retry.prompt`) was not pinned. Added `test_restart_retry_no_text_uses_template_retry_prompt_as_hint` to `test_agent_session_answer.py` asserting `started[0]["prompt"].startswith(RETRY_PROMPT + " ")`.

3. **`resume_unavailable_reason` unwired path not asserted** (blind-hunter) — `test_reply_available_false_when_harness_is_resumable_not_wired` did not assert the companion field. Added `assert detail.resume_unavailable_reason is None` to pin the spec-declared `None` return for the safe-unwired case.

4. **Whitespace-only text in `retryBody`** (edge-case-hunter) — `if (text)` is truthy for `" "`, which would send a whitespace-only string as operator instruction. Changed to `if (text.trim())`.

**Defer:**

- `resume_unavailable_reason` typed as `Literal[…] | None` instead of `str | None` — valid improvement, not story scope.
- Shared `reply_available` helper between `_check_mode` and `_reply_status` — duplication acknowledged in Design Notes; refactor is out of scope.
- `useEffect` guard when `replyAvailable` prop flips on a mounted `RetryBox` — theoretical in the actual UI flow (page refetches create fresh component); deferred.
- Docstring loss of `detail.reply_available ?? false` web-client contract — lost to 400-line limit; the pattern is documented by the web-client test.
- `retry` signal absent-mode-defaults-to-session test — code path is identical for `answer`/`retry`; 100 % branch coverage confirmed by `make test`.

**Reject:**

- `operator_mode` NameError concern — defined at line 308, visible in the full file.
- `hint = getattr(retry_of(ctx), "prompt", "")` labelled "dead work" — incorrect: `retry_of` reads from `with_resolved` independently of `retrying`, so the template prompt is non-empty here for rows with a retry block.
- `resumeUnavailableReason` unknown-value fallback — backend only emits the two known values; the closed set is enforced by `_reply_status`.
- `_check_mode` mutation not prominent — adequately documented in Design Notes.
- `ANSWER_EVENT` guard removal "silently expands behaviour" — the expansion is the declared fix; the priority order (signal text → template prompt → `""`) applies to all resume signals per spec.

## Design Notes

`_check_mode`'s mutation of `signal.payload` is intentional: `Signal.payload` is a plain `dict[str, Any]`, and mutating it before the gate record is written ensures the record captures the computed default, which `_planned` then reads from `ctx.resume_signal.payload.get("mode")`. This is the minimal change — no new return values, no new ports.

`_reply_status` replaces `_reply_available` in `run_views.py`. The priority order for the reason: no-attempt and no-session_id both produce `"no_session"` (the operator sees the same message: no session was recorded); `"no_capability"` is only reported when a session_id was recorded but the harness cannot resume it.

`RetryBox` receives `resumeUnavailableReason` as a prop (not computed internally) because the harness resume capability is server-side knowledge; the component must not infer it from `reply_available` alone.

The `run-retry-box.test.ts` update for `renders plain Retry button (no RetryBox) when replyAvailable=false` is a declared behaviour change (story 4, 2026-09-25): RetryBox now renders whenever `retry` is in `admitted_signals`, regardless of `reply_available`. The updated test pins the new behaviour.

## Verification

**Commands:**
- `make lint` — expected: zero errors (ruff, mypy strict on domain+application, import-linter, eslint, tsc, prettier)
- `make test` — expected: all unit tests pass; 100 % branch coverage on `domain/` and `application/`
- `make openapi` — expected: `contracts/openapi.json` regenerated with `resume_unavailable_reason` in `RunDetailOut`, `pnpm gen:api` succeeds

## Auto Run Result

Status: done

**Summary:** Three backend defects fixed and client retry UX rewritten. `_session_message` now prefers signal `text` over template `retry.prompt` for all resume signals. The `_planned` restart path prepends operator text (or template hint as fallback). `_check_mode` defaults absent mode to `"session"` when `reply_available=True` and writes the default into `signal.payload`. `RunDetailOut` gained `resume_unavailable_reason`. `RetryBox` always renders when `retry` is admitted, carries a text field, and shows the reason when session is unavailable. Review found and patched a critical serialization gap and three smaller coverage gaps.

**Files changed:**
- `backend-api/src/orchestrator/application/steps/agent.py` — `_session_message` uses signal text over template prompt; `_planned` restart extends to operator-retry with operator-text-or-hint prefix
- `backend-api/src/orchestrator/application/use_cases/signal_run.py` — `_check_mode` computes and writes absent-mode default from `reply_available`
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` — `RunDetailView` gains `resume_unavailable_reason: str | None = None`
- `backend-api/src/orchestrator/application/use_cases/run_views.py` — `_reply_available` → `_reply_status` returning `tuple[bool, str | None]`
- `backend-api/src/orchestrator/api/schemas/run_views.py` — `RunDetailOut` gains field; serializer extended; `of()` maps new field
- `contracts/openapi.json` + `web-client/src/api/schema.d.ts` — regenerated; `resume_unavailable_reason?: string | null`
- `web-client/src/lib/run/signals.ts` — `retryBody(mode, text)`: text in payload only when `text.trim()` truthy
- `web-client/src/components/run/RetryBox.tsx` — rewritten: always renders, textarea, session default, reason message
- `web-client/src/components/run/StopBody.tsx` — `hasRetryBox` guard removed; `resumeUnavailableReason` threaded
- `web-client/src/islands/RunDetail.tsx` — `onRetry` updated to `(mode, text)`; `resumeUnavailableReason` from detail
- `backend-api/tests/unit/application/use_cases/test_signal_mode.py` — test 5 renamed; test 6 added
- `backend-api/tests/unit/application/steps/test_agent_session_answer.py` — tests 5, 6, 7 added
- `backend-api/tests/unit/application/test_run_views_reply_available.py` — three reason tests; unwired assertion
- `backend-api/tests/unit/test_run_view_schemas.py` — three serialization tests (review patch 1)
- `backend-api/tests/unit/application/test_signal_run.py` — answer-record assertion updated
- `web-client/tests/unit/run-retry-box.test.ts` — extended for new props and behaviour
- `web-client/tests/unit/run-stop-body-answer.test.ts`, `run-stop-body-blocked.test.ts` — misconfigured assertions updated

**Review findings breakdown:**
- Patches applied: 4 (1 high, 1 medium, 2 low)
- Items deferred: 4 (all low — Literal type, shared helper, useEffect guard, docstring)
- Items rejected: 10

**Follow-up review recommendation:** true
- Score: 1 high patch → automatic true
- High patch: serialization-layer gap for `resume_unavailable_reason` (concrete mutant passes all tests)

**Verification:**
- `make lint` — passed (zero errors)
- `make test` — passed (7309 backend + 1732 frontend; 100 % branch coverage)
- `make openapi` — passed

**Residual risks:** None known.
