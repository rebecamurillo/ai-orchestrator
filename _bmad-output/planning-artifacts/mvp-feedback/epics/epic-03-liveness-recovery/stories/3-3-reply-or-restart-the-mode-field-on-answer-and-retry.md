---
title: 'Reply-or-restart — the mode field on Answer and Retry'
type: 'feature'
created: '2026-09-17'
status: 'done'
baseline_revision: 'db6f08fb6425c530f9609fc3495d8db412ef3fa7'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred:
  - summary: >-
      `"mode"` string key spelled inline in agent.py while _MODE_KEY constant
      exists in signal_run.py — two spellings of the same stable key.
    evidence: |-
      agent.py uses `payload.get("mode")` in two places; signal_run.py defines
      `_MODE_KEY = "mode"`. No shared export; refactoring would require
      making the constant public or creating a shared module.
    location: >-
      backend-api/src/orchestrator/application/steps/agent.py:144,321
    severity: low
  - summary: >-
      _planned docstring does not describe the new operator_mode dispatch
      branches added by this story.
    evidence: |-
      The docstring describes the original three-dispatch structure but makes no
      mention of mode=session / mode=restart overrides. A reader following the
      docstring cannot infer which path fires for operator-supplied modes.
    location: >-
      backend-api/src/orchestrator/application/steps/agent.py:311
    severity: low
  - summary: >-
      Per-request build_harnesses() call in signal_effect_ports adds latency
      to every signal request.
    evidence: |-
      build_harnesses(settings, RealProcessRunner()) is invoked on each request;
      if harness construction involves file I/O or subprocess probing, this is
      wasteful. Caching harnesses at startup would be cheaper.
    location: >-
      backend-api/src/orchestrator/api/providers.py:signal_effect_ports
    severity: low
  - summary: >-
      No database index on (run_id, started_at) for the latest_for_run query;
      full table scan on large attempt tables.
    evidence: |-
      SQLAlchemyAttemptRepository.latest_for_run filters by run_id and orders
      by started_at DESC. Without a compound index this is a sequential scan.
      Migration for the index is not part of this story.
    location: >-
      backend-api/src/orchestrator/infrastructure/db/repositories/attempts.py:156
    severity: low
---

<intent-contract>

## Intent

**Problem:** When an agent step blocks or errors, the operator's only recourse is a full restart — archiving the Story file and re-dispatching from scratch. For harnesses that support session resume (Claude, Codex), this discards recoverable in-progress work.

**Approach:** Add `mode: restart | session` to Answer and Retry signal payloads. `restart` is today's mechanism unchanged. `session` delivers the operator's input directly into the active harness session via `Harness.resume`, creating a new Attempt that inherits the session_id, with no archive, no prepare commit, and no re-plan.

## Boundaries & Constraints

**Always:**
- Two-writer rule holds (AD-8): `signal_run` records the gate; the agent executor manages Attempt lifecycle; no new writers.
- `SignalIn.payload: dict[str, Any]` is unchanged; `mode` is a key inside payload, not a top-level field; `make openapi` is not run (no API contract change).
- `mode` absent → defaults to `"restart"` (backwards-compatible); existing template `retry.resume_session` logic for Retry continues to apply when mode is absent.
- reply_available := `harness.capabilities.resume AND latest_attempt.session_id is not None` (AD-10); validated at signal time via injected callables on `SignalPorts` — never by importing harness infrastructure directly in application code (AD-2).
- Session delivery: new Attempt n+1; inherited session_id; start_sha = HEAD at delivery (captured in `_start` as today); `env_for` of new Attempt; `mark_started`/`mark_finished`, protected-path check, FR-16 routing, `Gateway.spend`, budget rule apply exactly as after a normal dispatch.
- `_prepare_writes` is skipped for session delivery (no archive, no prepare commit, no re-plan); `_wip_commit` and `_orphan_control` run normally.
- `GateRecord.payload` stores `mode` verbatim — `record()` already stores payload as-is; no extra persistence code.
- TDD with shared fakes (extend `FakeHarness` in `tests/unit/fakes/harness.py` — no new fake class); `make lint` and `make test` always apply.

**Block If:** `SignalPorts` cannot expose `latest_attempt_for_run(run_id: UUID) -> Attempt | None` and `harness_is_resumable(harness_name: str) -> bool` without violating the AD-2 dependency direction.

**Never:**
- New status token or park kind.
- Changing `SignalIn` top-level schema fields or running `make openapi`.
- Creating a new fake class for the harness port.
- Calling harness infrastructure directly from any application module.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| mode=session, reply_available | Answer/Retry payload `{"mode": "session", ...}`; harness capabilities.resume=True; latest attempt.session_id≠None | Signal accepted; gate recorded with mode in payload; executor delivers via Harness.resume; new Attempt n+1 | — |
| mode=session, no resume capability | mode=session; harness capabilities.resume=False | Signal rejected before gate is recorded | `raise Invalid("mode 'session' not available: harness does not support resume")` |
| mode=session, no session_id | mode=session; capabilities.resume=True; latest attempt.session_id=None | Signal rejected before gate is recorded | `raise Invalid("mode 'session' not available: no session recorded")` |
| mode=restart or absent | Answer/Retry with mode=restart or no mode key | Existing path: archive+re-plan for Answer; template-driven resume/restart for Retry | — |
| Unknown mode value | payload `{"mode": "bogus"}` | Signal rejected before gate is recorded | `raise Invalid("unknown mode: bogus")` |
| Session Answer: no archive | mode=session Answer; reply_available=True | `_prepare_writes` skipped; new Attempt n+1; Harness.resume called with answer text as message and inherited session_id; agent_tail.finish runs (mark_finished, protected-path, FR-16, spend, budget) | — |
| mode=restart overrides template | mode=restart Retry; template.retry.resume_session=True | Restart path taken (operator explicit choice wins over template) | — |
| mode=session overrides template | mode=session Retry; template.retry.resume_session=False; reply_available=True | Resume path taken (operator explicit choice wins over template) | — |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/use_cases/signal_run.py:87-105` — `signal_run` main entry; `SignalPorts` gains two new callables: `harness_is_resumable: Callable[[str], bool]` and `latest_attempt_for_run: Callable[[UUID], Attempt | None]`; `_check_mode(ports, run, signal)` is called after the existing `validate(...)` call and before `record(...)`, for Answer and Retry signal kinds only; raises `Invalid` on bad/unavailable mode
- `backend-api/src/orchestrator/domain/errors.py:33-34` — `Invalid` exception; already maps to HTTP 422 via `api/errors.py:59-63`; used for all mode rejections — no changes needed here
- `backend-api/src/orchestrator/application/use_cases/signals.py:236-262` — EFFECTS dict; Answer effect (line ~236) and Retry effect (line ~249) are read-only context for `_check_mode`; no EFFECTS change needed since mode check runs before `record` in `signal_run`, not inside the effect functions
- `backend-api/src/orchestrator/application/steps/agent.py:135-155` — `execute()`; add `_is_session_mode(ctx)` guard around `_prepare_writes(ctx)` call: `if not _is_session_mode(ctx): _prepare_writes(ctx)`; `_is_session_mode` reads `ctx.resume_signal.payload.get("mode") == "session"` — returns False when resume_signal is None
- `backend-api/src/orchestrator/application/steps/agent.py:325-342` — `_planned(ctx, harness, attempt, previous)`; add operator mode check at top before existing template logic: if `_is_session_mode(ctx)` and `harness.capabilities.resume` and `resumable`: return `_Dispatch(harness, attempt, _session_message(ctx), session, resumable)`; elif explicit `mode == "restart"` and `retry is not None`: skip resume path even if template says `resume_session=True`
- `backend-api/src/orchestrator/application/steps/agent.py:NEW` — `_is_session_mode(ctx) -> bool`: one-liner reading `ctx.resume_signal` and mode key; `_session_message(ctx) -> str`: for non-retry (Answer) returns `ctx.resume_signal.payload.get("text", "")`, else returns `retry_of(ctx).prompt` (same as existing resume-session path)
- `backend-api/src/orchestrator/domain/ports/harness.py:80-91` — `HarnessCapabilities.resume: bool`; used as the capability check source; no changes needed
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py:100` — `FakeHarness`; extend to assert/record when `resume()` is called (session_id, message args); already has `capabilities.resume=True`; no new class
- `backend-api/src/orchestrator/infrastructure/` (composition root / `SignalPorts` construction site) — wire `harness_is_resumable = lambda name: harnesses.get(name, _null_harness).capabilities.resume` and `latest_attempt_for_run = attempt_repo.latest_for_run` into `SignalPorts`; trace from `handle_signal` in `application/use_cases/signals.py` to find the exact construction call site
- `backend-api/src/orchestrator/infrastructure/db/repos/` (attempt repository) — add `latest_for_run(run_id: UUID) -> Attempt | None` query: most recently created Attempt row for the given run_id; used only by `SignalPorts.latest_attempt_for_run`
- `backend-api/tests/unit/application/use_cases/test_signal_mode.py` — NEW TDD: (1) mode=session accepted when harness_is_resumable=True and session_id≠None; (2) mode=session rejected (capabilities.resume=False); (3) mode=session rejected (session_id=None); (4) mode=bogus rejected; (5) mode absent treated as restart (existing behavior, no Invalid raised)
- `backend-api/tests/unit/application/steps/test_agent_session_answer.py` — NEW TDD: (1) Answer mode=session → `_prepare_writes` not called (spy/assert on archive); new Attempt n+1; `FakeHarness.resume` called with inherited session_id and answer text as message; (2) Answer mode=session → agent_tail.finish runs (mark_finished recorded)
- `backend-api/tests/unit/application/steps/test_agent_dispatch.py` — add: mode=restart Retry overrides template `resume_session=True` → fresh dispatch; mode=session Retry forces resume even when template `resume_session=False`

## Tasks & Acceptance

**Execution:**

- `backend-api/src/orchestrator/application/use_cases/signal_run.py` -- add `harness_is_resumable: Callable[[str], bool]` and `latest_attempt_for_run: Callable[[UUID], Attempt | None]` to `SignalPorts`; implement `_check_mode(ports, run, signal)`: extract mode (default "restart"), reject unknown values with `Invalid`, if mode="session" check `ports.harness_is_resumable(run.harness_name_or_latest_attempt_harness)` and `ports.latest_attempt_for_run(run.id).session_id` — raise `Invalid` naming the reason for each failure; call `_check_mode` in `signal_run` after `validate(...)` and before `record(...)` for Answer and Retry kinds -- domain-layer 422 without importing infrastructure
- `backend-api/src/orchestrator/infrastructure/db/repos/` -- add `latest_for_run(run_id: UUID) -> Attempt | None` to the attempt repository: `SELECT … ORDER BY started_at DESC LIMIT 1 WHERE run_id = ?` -- backing query for reply_available harness-name and session_id lookup
- `backend-api/src/orchestrator/infrastructure/` -- wire `harness_is_resumable` and `latest_attempt_for_run` callables into the `SignalPorts` construction site; locate by tracing from `handle_signal` caller in `application/use_cases/signals.py` -- AD-2 compliant injection
- `backend-api/src/orchestrator/application/steps/agent.py` -- add `_is_session_mode(ctx)` and `_session_message(ctx)` helpers; guard `_prepare_writes(ctx)` with `if not _is_session_mode(ctx):`; in `_planned()`, add operator mode check (session → return resume _Dispatch; explicit restart → skip template resume_session) -- session delivery routing and template override
- `backend-api/tests/unit/application/use_cases/test_signal_mode.py` -- NEW: all five TDD cases listed in Code Map -- must fail before implementation; covers the 422 gate
- `backend-api/tests/unit/application/steps/test_agent_session_answer.py` -- NEW: both TDD cases listed in Code Map -- must fail before implementation; covers no-archive and harness.resume call
- `backend-api/tests/unit/application/steps/test_agent_dispatch.py` -- add mode=restart-overrides-template and mode=session-overrides-template test cases -- extended Retry coverage

**Acceptance Criteria:**

- Given an Answer or Retry signal with `payload["mode"] = "session"`, when `harness.capabilities.resume=False` for the run's harness, then `signal_run` raises `Invalid` and the HTTP response is 422 naming the reason; the gate is not recorded.
- Given an Answer or Retry signal with `payload["mode"] = "session"`, when `capabilities.resume=True` but `latest_attempt.session_id=None`, then `signal_run` raises `Invalid` (422) naming the reason; the gate is not recorded.
- Given an Answer signal with `payload["mode"] = "session"]` and reply_available=True, when the agent executor processes the resumed step, then `_prepare_writes` is not called (no archive, no prepare commit), a new Attempt n+1 is created, `Harness.resume` is called with the inherited session_id and the answer text as message, and `agent_tail.finish` runs (mark_finished, protected-path, FR-16, spend, budget).
- Given a Retry signal with `payload["mode"] = "restart"]` and template `retry.resume_session=True`, when the executor's `_planned()` runs, then the fresh dispatch path is taken (resume_id=None), not the resume path.
- Given a Retry signal with `payload["mode"] = "session"]`, reply_available=True, and template `retry.resume_session=False`, when `_planned()` runs, then the resume path is taken (resume_id = inherited session_id).
- Given `make lint` and `make test` after all changes, then both pass with no new violations.

## Design Notes

`_check_mode` runs in `signal_run` between `validate(...)` and `record(...)`, so a bad or unavailable mode rejects the signal before any state change is committed — same guard pattern as the existing `validate` call. `SignalPorts` callables are typed with domain types only (`Attempt`, `UUID`), keeping AD-2 intact.

The `_prepare_writes` skip is guarded by `_is_session_mode(ctx)` which reads `ctx.resume_signal.payload.get("mode") == "session"`. When mode is absent from payload, `_is_session_mode` returns False and the existing path runs unchanged. `_wip_commit` still runs for session delivery (preserving uncommitted work in git is safe for a continuing session).

`_planned()` operator mode check takes precedence over `retry.resume_session`: explicit `mode=session` always takes the resume path; explicit `mode=restart` always takes the fresh path; absent mode defers to the template (existing behaviour). The `resumable` variable (`previous.session_id`) is loaded in the same way as today — no new lookup code needed in `_planned()` itself.

The `harness_name` for the `harness_is_resumable` check comes from `latest_attempt_for_run(run.id).harness` — the same attempt record that supplies the session_id for the session_id≠None check. One DB round-trip covers both checks.

## Verification

**Commands:**
- `make lint` -- expected: zero ruff/mypy/import-linter violations
- `make test` -- expected: all unit tests green, including new mode-validation and session-answer tests

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 2, low 0)
- defer: 4: (high 0, medium 0, low 4)
- reject: 6: (various low/noise)
- addressed_findings:
  - `[medium]` `[patch]` `_check_mode` fired "harness does not support resume" when `latest_attempt_for_run` returned None, because `harness_is_resumable("") → False` ran before the `attempt is None` guard. Reordered: check `attempt is None or session_id is None` first, then check harness. Added test `test_mode_session_rejected_when_no_attempt_has_ever_run`.
  - `[medium]` `[patch]` `_session_message` message for Retry mode=session was not asserted in `test_mode_session_overrides_template_resume_session_false`; added `assert resumed[0]["message"] == RETRY_PROMPT`.

## Auto Run Result

### Summary

Added `mode: restart | session` to Answer and Retry signal payloads. `mode=session` delivers the operator's input into the active harness session without archiving or re-planning. Signal-time 422 validation via `_check_mode` enforces reply_available before any gate record is written. Session delivery in the agent executor skips `_prepare_writes` while `_wip_commit`, `_orphan_control`, and `agent_tail.finish` run normally.

### Files Changed

- `backend-api/src/orchestrator/application/use_cases/signal_run.py` — Added `_check_mode` function; extended `SignalPorts` with `harness_is_resumable` and `latest_attempt_for_run` callables; reordered mode checks so `attempt is None` fires "no session recorded" rather than "harness does not support resume".
- `backend-api/src/orchestrator/application/steps/agent.py` — Guarded `_prepare_writes` with mode≠session check; added operator_mode dispatch to `_planned`; added `_session_message` helper.
- `backend-api/src/orchestrator/domain/ports/repositories.py` — Added `latest_for_run` to `AttemptRepository` protocol.
- `backend-api/src/orchestrator/infrastructure/db/repositories/attempts.py` — Implemented `latest_for_run` query (ORDER BY started_at DESC LIMIT 1).
- `backend-api/src/orchestrator/api/providers.py` — Wired `harness_is_resumable` and `latest_attempt_for_run` into `SignalPorts` at the composition root.
- `backend-api/tests/unit/fakes/runs.py` — Added `latest_for_run` to `FakeAttemptRepository`.
- `backend-api/tests/unit/application/use_cases/test_signal_mode.py` — NEW: 8 tests (5 TDD mode-validation cases + 1 attempt=None case + 2 sentinel default tests).
- `backend-api/tests/unit/application/steps/test_agent_session_answer.py` — NEW: 6 TDD tests (session answer skips archive, calls resume with correct args, mark_finished runs, result is done, mode=restart overrides template, mode=session overrides template with message assertion).
- `backend-api/tests/unit/test_run_repository_adapter.py` — Added 2 tests for `SQLAlchemyAttemptRepository.latest_for_run`.

### Review Findings Breakdown

- Patches applied: 2 (medium)
- Items deferred: 4 (low)
- Items rejected: 6 (noise/theoretical)
- Followup review recommended: true (score: 3×2 medium + 0 low = 6 ≥ 5)

### Verification Performed

- `make lint` — zero violations (ruff, mypy, import-linter, eslint, prettier, tsc, env-contract)
- `make test` — 6338 passed, 23 skipped; domain+application coverage 100%

### Residual Risks

- `latest_for_run` query has no DB index on `(run_id, started_at)`; may be slow on large attempt tables (deferred).
- `"mode"` key is spelled inline in `agent.py` rather than referencing the `_MODE_KEY` constant from `signal_run.py` (deferred).
