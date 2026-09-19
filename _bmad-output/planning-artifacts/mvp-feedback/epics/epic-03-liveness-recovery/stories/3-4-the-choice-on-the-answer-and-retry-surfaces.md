---
title: 'The choice on the Answer and Retry surfaces'
type: 'feature'
created: '2026-09-17'
status: 'done'
baseline_revision: '19cb2a93465cde56f131a8092bab9f9edca0d5f9'
review_loop_iteration: 1
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - '[low] Mode typed as plain string — no shared discriminated union (pre-existing pattern throughout signals layer; low risk)'
  - '[low] Island integration test does not cover replyAvailable prop wiring to StopBody — TypeScript-checked prop, trivially correct, pre-existing gap in island test coverage'
---

<intent-contract>

## Intent

**Problem:** When an agent step blocks or errors, story 3-3 wired the backend `mode: restart | session` field on Answer and Retry signals, but the UI always sends the restart path — the operator has no way to choose session delivery, and the gate record does not surface which mode was chosen.

**Approach:** Add `reply_available: bool` to `RunDetailOut` (computed server-side from harness capabilities + recorded session_id); surface a mode selector in `AnswerBox` and a new `RetryBox` component only when `reply_available` is true; expose `mode` on `GateRecordOut` so the gate record display names it.

## Boundaries & Constraints

**Always:**
- Generated contract only (AD-3): `make openapi` → `pnpm gen:api` after every backend schema change; no hand-edits to `schema.d.ts`.
- Two-writer rule (AD-8) untouched; no new status token or park kind.
- `reply_available` is computed from `ports.attempts.latest_for_run(run.id)` (already in `RunViewPorts.attempts`) and a new `harness_is_resumable` callable (same defaulted-to-None pattern as `terminal` in `RunViewPorts`).
- When `reply_available` is false or absent, the existing Answer-only-restart path is shown unchanged — no mode selector, no `RetryBox`.
- `onAnswer` callback signature widens to `(text: string, mode: string) => void`; the default no-op in `StopBody` accepts two args.
- Mode copy is verbatim from spec requirements: restart names the archive path and states re-plan; session states the session continues with the answer/prompt and the Story file stays in place.
- TDD: all new tests exist and fail before implementation; `make lint` and `make test` always apply.

**Block If:** `ports.attempts.latest_for_run` is not available on `RunViewPorts` (verify it exists from story 3-3).

**Never:**
- Adding `reply_available` to `RunDetailSummaryOut.run` — it belongs on `RunDetailOut` directly.
- Changing `GateRecord` domain entity or the `signals_table` `text`/`text_key` rules.
- Running `make openapi` before all backend schema changes are done.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| reply_available=true, mode=session Answer | `reply_available=true`, operator picks session, submits answer | `answerBody(text, 'session')` → `{ kind: 'answer', payload: { text, mode: 'session' } }` | Server 422 on bad state (story 3-3) |
| reply_available=true, mode=restart Answer | `reply_available=true`, operator picks restart | `answerBody(text, 'restart')` → payload includes `mode: 'restart'` | — |
| reply_available=false, Answer | `reply_available` absent/false | No mode selector; `answerBody(text, 'restart')` as default | — |
| reply_available=true, mode=session Retry | `reply_available=true`, operator picks session in RetryBox | `retryBody('session')` → `{ kind: 'retry', payload: { mode: 'session' } }` | — |
| reply_available=false, Retry | `reply_available` absent/false | Plain Retry button; `sendSignal('retry')` with no mode in payload | — |
| Gate record with mode | Answer/Retry gate record has `payload.mode` | `GateRecordOut.mode` shows `"session"` or `"restart"` | — |
| Gate record without mode | Legacy record with no mode in payload | `GateRecordOut.mode` is `null`/absent; display unchanged | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/use_cases/run_view_types.py:11-14,35-53` — `RunViewPorts`: add `from collections.abc import Callable`; add `harness_is_resumable: Callable[[str], bool] | None = None` (defaulted, same pattern as `terminal`); `RunDetailView:242-256`: add `reply_available: bool = False`
- `backend-api/src/orchestrator/application/use_cases/run_views.py:186-212` — `run_detail()`: compute `reply_available = ports.harness_is_resumable is not None and (lambda: (a := ports.attempts.latest_for_run(run.id)) is not None and a.session_id is not None and ports.harness_is_resumable(a.harness or ""))()` — pass to `RunDetailView`
- `backend-api/src/orchestrator/api/schemas/run_views.py:297-316` — `GateRecordOut`: add `mode: str | None = Field(default=None, json_schema_extra=_drop_default)`; `of()`: `mode=record.payload.get("mode") or None`
- `backend-api/src/orchestrator/api/schemas/run_views.py:338-367` — `RunDetailOut`: add `reply_available: bool = Field(default=False, json_schema_extra=_drop_default)`; `of()`: `reply_available=detail.reply_available`
- `backend-api/src/orchestrator/api/providers.py:224-251` — `run_view_ports()`: share the `build_harnesses` call already made for `terminal`; add `harness_is_resumable=lambda name: name in harnesses and harnesses[name].capabilities.resume` to `RunViewPorts()`
- `web-client/src/lib/run/answer.ts:1-77` — add `SESSION_ANSWER_HINT = 'The session continues with your answer; the Story file stays in place.'`; update `answerBody(text: string, mode = 'restart'): SignalIn` to `{ kind: 'answer', payload: { text, mode } }`
- `web-client/src/lib/run/signals.ts:1-33` — add `retryBody(mode: string): SignalIn` → `{ kind: 'retry', payload: { mode } }`
- `web-client/src/components/run/AnswerBox.tsx:1-62` — add `replyAvailable: boolean` to `Props`; add `const [mode, setMode] = useState<'restart' | 'session'>('restart')`; when `replyAvailable`: render two labelled radio inputs with their hint texts above the button; `onAnswer(text.trim(), mode)` on click; when `!replyAvailable`: existing hint + `onAnswer(text.trim(), 'restart')`; widen `onAnswer` type to `(text: string, mode: string) => void`
- `web-client/src/components/run/RetryBox.tsx` — NEW: props `target: AnswerTarget`, `onRetry: (mode: string) => void`, `posting: boolean`, `error: ProblemDetail | null`; owns `mode` state (default `'restart'`); renders two labelled radio inputs with copy (`RETRY_RESTART_HINT`/`RETRY_SESSION_HINT`) and the `Retry` button; constants live here
- `web-client/src/components/run/StopBody.tsx:68-98,150-160` — add `onRetry?: (mode: string) => void` and `replyAvailable?: boolean` to `Props` (both optional, defaults to no-ops/false); compute `hasRetryBox = (replyAvailable ?? false) && buttons.includes('retry')`; filter `retry` out of `buttons` when `hasRetryBox`; render `<RetryBox>` in the `wf-stop-actions` block when `hasRetryBox`; pass `replyAvailable={detail.reply_available ?? false}` and `onRetry` to `StopBody` from the island; update `onAnswer` default to accept 2 args
- `web-client/src/islands/RunDetail.tsx:167-230` — `onAnswer={(text, mode) => void sendSignal('answer', answerBody(text, mode))}`; add `onRetry={(mode) => void sendSignal('retry', retryBody(mode))}` and `replyAvailable={detail.reply_available ?? false}` to `<StopBody>`
- `web-client/src/components/run/GateRecord.tsx:26-40` — render `record.mode` after `record.text` when present: `{record.mode ? <span>{record.mode}</span> : null}`

## Tasks & Acceptance

**Execution:**

- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` -- add `Callable` import; add `harness_is_resumable: Callable[[str], bool] | None = None` to `RunViewPorts`; add `reply_available: bool = False` to `RunDetailView` -- enables run_detail to compute and surface the flag
- `backend-api/src/orchestrator/application/use_cases/run_views.py` -- compute `reply_available` in `run_detail()`: if `ports.harness_is_resumable` is not None, call `ports.attempts.latest_for_run(run.id)` and check session_id + capability; else False -- the flag that drives the UI choice
- `backend-api/tests/unit/application/test_run_views_reply_available.py` -- NEW: (1) `reply_available=True` when harness resumable and session_id recorded; (2) `reply_available=False` when harness not resumable; (3) `reply_available=False` when session_id is None; (4) `reply_available=False` when `harness_is_resumable=None` (unwired) -- TDD gate before implementation
- `backend-api/src/orchestrator/api/schemas/run_views.py` -- `GateRecordOut`: add `mode: str | None` with `_drop_default`; `of()` extracts from payload; `RunDetailOut`: add `reply_available: bool` with `_drop_default`; `of()` passes it through -- API contract carries both new fields
- `backend-api/src/orchestrator/api/providers.py` -- extract `harnesses` from the existing `terminal` block; add `harness_is_resumable` lambda to `RunViewPorts()` construction -- wires capability check into the detail read path
- `make openapi` -- regenerate `contracts/openapi.json` and `pnpm gen:api` in web-client -- AD-3 contract sync; run after all backend schema changes
- `web-client/src/lib/run/answer.ts` -- add `SESSION_ANSWER_HINT`; update `answerBody` signature to include `mode` param (default `'restart'`); payload carries `{ text, mode }` -- enables mode-aware answer signal
- `web-client/src/lib/run/signals.ts` -- add `retryBody(mode: string): SignalIn` -- enables mode-aware retry signal
- `web-client/tests/unit/run-stop-body-answer.test.ts` -- EXTEND: (1) `replyAvailable=true` renders two radio inputs; (2) session hint text appears when `replyAvailable=true`; (3) existing restart hint shown for both modes when appropriate; (4) `answerBody(text, 'session')` includes `{ text, mode: 'session' }` in payload; (5) `answerBody(text)` defaults to `mode: 'restart'` -- TDD gate
- `web-client/tests/unit/run-retry-box.test.ts` -- NEW: (1) `RetryBox` renders two radio inputs with correct copy; (2) restart hint names archive path and re-plan; (3) session hint states session continues; (4) `StopBody` renders `RetryBox` (not plain Retry button) when `replyAvailable=true` and `retry` is admitted; (5) plain Retry button when `replyAvailable=false` -- TDD gate
- `web-client/src/components/run/AnswerBox.tsx` -- add `replyAvailable` prop and `mode` state; conditional mode-choice UI; widen `onAnswer` callback -- mode choice for Answer
- `web-client/src/components/run/RetryBox.tsx` -- NEW: mode choice + Retry button with copy -- mode choice for Retry
- `web-client/src/components/run/StopBody.tsx` -- add `onRetry`/`replyAvailable` props; `hasRetryBox` filter; `RetryBox` rendering -- wires RetryBox into the stop body layout
- `web-client/src/islands/RunDetail.tsx` -- update `onAnswer` to pass mode; add `onRetry` and `replyAvailable` -- island sends mode-aware signal bodies
- `web-client/src/components/run/GateRecord.tsx` -- render `record.mode` when present -- gate record names the mode
- `web-client/tests/unit/run-gate-record.test.ts` -- EXTEND: gate record row shows mode when `record.mode` is set; absent mode shows no mode span -- TDD gate

**Acceptance Criteria:**

- Given `GET /runs/{id}/detail` where the latest attempt has a `session_id` and the harness supports resume, when the response arrives, then `reply_available` is `true`.
- Given `GET /runs/{id}/detail` where `reply_available` is false (or absent), when `AnswerBox` and `StopBody` render, then no mode selector is shown and the existing restart hint is the only hint displayed.
- Given `reply_available=true`, when `AnswerBox` renders, then two radio options appear; above the Restart button the copy names the archive path (`stories/.answers/{id}-attempt-{n}.md`) and states the story is re-planned; the Session option states "The session continues with your answer; the Story file stays in place."
- Given `reply_available=true`, when `StopBody` has `retry` in admitted signals, then `RetryBox` renders (not a plain Retry button); restart copy names the archive path and re-dispatch; session copy states "The session continues with the retry prompt; the Story file stays in place."
- Given operator selects session and submits an Answer, when `onAnswer` fires, then `answerBody(text, 'session')` produces `{ kind: 'answer', payload: { text, mode: 'session' } }` and that body is posted.
- Given operator selects session and submits a Retry, when `onRetry` fires, then `retryBody('session')` produces `{ kind: 'retry', payload: { mode: 'session' } }` and that body is posted.
- Given an Answer or Retry gate record entry whose payload contains `mode`, when `GateRecord.tsx` renders that row, then the mode value is displayed in the row.
- Given `make lint` and `make test` after all changes, then both pass with no new violations.

## Design Notes

`reply_available` is `False` when `harness_is_resumable` is not wired into `RunViewPorts` (the same safe-unwired pattern as `terminal`). This means existing `RunViewPorts(...)` constructions in tests keep compiling.

`_drop_default` on both `reply_available` and `mode` means existing TypeScript test fixtures that omit these fields still compile. Frontend code reads `detail.reply_available ?? false` and `record.mode` (optional chaining safe).

The `RetryBox` copy constants are co-located in `RetryBox.tsx` since they are not shared with `answer.ts`. The `SESSION_ANSWER_HINT` lives in `answer.ts` since it is Answer-box-specific.

In `providers.py:run_view_ports()`, `build_harnesses(settings, RealProcessRunner())` is already called for the `terminal` block — extract it to a local `harnesses` variable so `harness_is_resumable` reuses it rather than calling `build_harnesses` a second time.

## Verification

**Commands:**
- `make lint` -- expected: zero ruff/mypy/import-linter/eslint/tsc violations
- `make test` -- expected: all unit tests green, including new reply_available and mode-choice tests

## Review Triage Log

**Review loop 1 (2026-09-17)**

Sources: blind-hunter (15 findings), edge-case-hunter (6 findings), verification-gap (2 findings), intent-alignment (4 findings).

**Patches applied:**

- `[medium]` `GateRecordOut.of()` mode extraction from payload had no Python-layer test — added `test_gate_record_of_extracts_mode_from_payload` and `test_gate_record_of_mode_is_none_when_payload_has_no_mode` to `test_run_view_schemas.py`
- `[medium]` `RunDetailOut._omit_false_reply_available` True-case (where `reply_available` IS emitted) had no test — added `test_run_detail_out_includes_reply_available_true_in_serialized_output` and `test_run_detail_out_omits_reply_available_when_false` to `test_run_view_schemas.py`
- `[low]` Gate record positive-case test used `toContain('session')` instead of checking `data-testid="wf-gate-mode"` element — strengthened to `toMatch(/data-testid="wf-gate-mode"[^>]*>session/)`

**Rejected:**

- Operator precedence bug in `_reply_available` — false positive; Python parses `a.harness or "" if a is not None else ""` as `(a.harness or "") if (a is not None) else ""` (conditional expression has lower precedence than `or`; guard is correct)
- `"mode": null` in responses for records without mode — consistent with existing `attempt_n: int | None` pattern; frontend checks truthiness correctly
- `_reply_available=True` on terminal runs — `admitted_signals` excludes `answer`/`retry` for terminal runs; neither box renders; not a real scenario
- `harnesses[name].capabilities` is None — harness always constructed with capabilities; pre-existing pattern also used in `signal_effect_ports`
- `build_harnesses` raises during `run_view_ports()` — pre-existing risk, not introduced by this story
- `record.payload is None` — Pydantic `Field(default_factory=dict)` guarantees dict
- `retryBody` accepts arbitrary string — backend rejects unknown modes with 422 (story 3-3); no client-side defense needed
- `onReject` hardcodes `restart` — RejectBox is checkpoint rejection (FR-19), not blocked-step Answer; session delivery inapplicable; correct
- `SESSION_ANSWER_HINT` vs `RETRY_SESSION_HINT` wording divergence — intentionally different ("with your answer" vs "with the retry prompt")
- `build_harnesses` called per request — pre-existing pattern in terminal wiring

**Deferred:**

- `[low]` Mode typed as plain `string` — no shared discriminated union; pre-existing pattern throughout signals layer
- `[low]` Island integration test does not cover `replyAvailable` prop wiring — TypeScript-checked prop, pre-existing gap in island test coverage

## Auto Run Result

**Date:** 2026-09-17
**Status:** done
**Verify:** green — `make lint` zero violations; `make test` 6346 backend + 1365 frontend all passed
**Review loop iterations:** 1
**Patches applied:** 3 (0 high, 2 medium, 1 low)
**Deferred:** 2 (both low)
**followup_review_recommended:** true
