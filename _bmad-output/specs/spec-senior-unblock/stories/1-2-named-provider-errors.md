---
title: 'Named provider errors'
type: 'feature'
created: '2026-11-02'
status: 'done'
route: 'dispatch'
baseline_commit: 'c7a6d9154ae6a8c674467978b2fee3c9782b60d7'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A past Run stopped on an OpenRouter 402 (out of credits) after 14 minutes of work. The park read `harness exit 1`, as `misconfigured`, so the Operator could not tell what was wrong and the stop sat for 13h08. The real message was in the attempt's log. `gateway_unreachable` declines an attempt that produced output tokens, so a failure after real work fell through to routing's `harness exit {code}`.

**Approach:** AD-13's amendment. A failed attempt whose result object, or log tail when the object lacks it, reports a provider credit or rate failure parks with `provider error: {message}` in place of `harness exit {code}`. Classification is a pure rule in `application/rules/`; the log is read through the existing `LogReader` port.

## Boundaries & Constraints

**Always:** The stop stays `misconfigured`. Only an attempt with a non-zero exit is read. The message is collapsed, scrubbed of anything shaped like a credential, and cut to `MAX_MESSAGE`; at most `LOG_LINES` lines of at most `MAX_LINE` characters are examined. The result object is read first and the log only when it names nothing.

**Never:** No new park kind. No retry beyond the row's declared `retry` (hard rule 7); the provider reason takes the same retry path `harness exit {code}` took. `gateway_unreachable` is unchanged for a harness that never reached its model. A `done` file with exit 0 is unaffected. A `blocked` file keeps its own question. No consult. No adapter interprets anything (AD-10). No edit to an existing test file; new behaviour gets new test files. `AGENTS.md` is not touched.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| The past Run | exit 1, output tokens, result `is_error` with `API Error: 402 … Insufficient credits`, no Story file | Park `misconfigured`, reason `provider error: API Error: 402 …` | N/A |
| Error only in the log | exit 1, result object absent or silent, log tail holds the error | Same reason, read from the log | N/A |
| Rate failure | `429`, `rate limit`, `too many requests` in the result or an error line | `provider error: …` | N/A |
| Other harness shapes | `turn.failed` or `error` event with `error.message`, or `error.data.message` plus `statusCode` 402 or 429 | `provider error: …`, with `HTTP 402:` prefixed when the message names no wording | N/A |
| Done file, failed exit | `done` file, exit 1, provider failure | Reason is the provider's, through the row's declared `retry`, then the `misconfigured` park | N/A |
| Failure not from the provider | exit 1, `connection reset` | `harness exit 1`, as today | N/A |
| Clean exit | exit 0, `done` file, log mentions a rate limit | `done`; the log is not read | N/A |
| Clean exit, no file | exit 0, no Story file | `no story file`, as today | N/A |
| Agent prose about limits | `is_error` false, assistant text or a plain line without `error` | Not a provider error | N/A |
| Half-written file | exit 1, provider failure, file status `in-progress` | `provider error: …`, not `unexpected status: in-progress` | N/A |
| Blocked file | exit 1, `blocked` file | The agent's own question | N/A |
| Never reached the model | `is_error`, zero output tokens | `gateway unreachable: …`, as today | N/A |
| No log reader or log | `StepPorts.logs` unset, or log garbage-collected | The result object alone decides | N/A |
| Secret in the message | `sk-…`, `ghp_…`, `xox…`, `AKIA…`, `Bearer …`, `api_key=…`, a 32-character token | `[redacted]` in the reason | N/A |
| Long message | over 200 characters | Collapsed, cut at `MAX_MESSAGE` with `…` | N/A |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/application/` unless stated.

- `rules/provider_failure.py` -- new. `from_raw(raw)` and `from_log(lines)` return `provider error: {message}` or `None`; markers, scrub and bounds live here. Reuses `harness_failure.MAX_MESSAGE`.
- `steps/agent_failure.py` -- new. `provider_reason(ctx, result)`: `None` unless the exit code is non-zero; the result object first, then `ctx.ports.logs.tail(log_path, LOG_LINES)` if `StepPorts.logs` is set.
- `rules/routing.py::route` -- new keyword `exit_reason`, used for a failed exit in place of `harness exit {code}` (the empty glob in `_liveness`, and a `done` file overruled by the exit) and of `unexpected status` (review, 2026-11-02).
- `steps/agent_tail.py::_route` -- passes `exit_reason=agent_failure.provider_reason(ctx, result)`. The module was at the 400-line cap; one narrating comment line was folded to make room.
- `rules/harness_failure.py` -- unchanged.
- `backend-api/AGENTS.md` and the spine -- not touched; AD-13's amendment already states the behaviour.

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/application/test_provider_failure_rule.py` -- new; markers, shapes, scrub, bounds, log -- seen failing first (module absent) -- TDD.
- [x] `backend-api/tests/unit/application/test_routing_exit_reason.py` -- new; the two sentences and the retry path.
- [x] `backend-api/tests/unit/application/steps/test_agent_failure.py` -- new; through `AgentExecutor.execute` with the shared fakes and `FakeLogReader`.
- [x] `rules/provider_failure.py`, `steps/agent_failure.py`, `rules/routing.py`, `steps/agent_tail.py` -- per Code Map.
- [x] `test_provider_failure_review.py`, `test_routing_provider_status.py`, `steps/test_agent_failure_status.py` -- new; the review findings below, seen failing first.

**Acceptance Criteria:**
- Given a fixture attempt that exited 1 after output tokens, whose log holds a provider credit error and which wrote no Story file, when the row finishes, then the Run parks `misconfigured` with a reason beginning `provider error:` that names the 402, not `harness exit 1`, and no consult is requested.
- Given an attempt that exited 0 with a `done` file, when its log mentions a rate limit, then the row is `done` and the log is not read.

## Implementation Notes

The path was confirmed by reading, not by the past Run's log: with `tokens_out` non-zero `gateway_unreachable` returns `None`, `agent_tail._route` calls `routing.route`, and an empty glob with a non-zero exit is `_liveness`'s `harness exit {code}`; a `done` file with a non-zero exit is the same sentence from the overrule.

Widened by the Operator's decision after review (2026-11-02): a failed exit with a provider failure also replaces `unexpected status: {status}`, so exit 1, a 402 and an `in-progress` file name the provider error. A clean exit never does. A 402 retried by a row's declared `retry` is wasted spend, but removing the retry would be a template decision, not this story's.

Verified by `make lint` and `make test`. `make e2e` is the parent's gate.

## Spec Change Log

## Review Triage Log

| Finding | Layer | Verdict | Route | Evidence and action |
| --- | --- | --- | --- | --- |
| Credentials reach a park reason: `Basic` scheme, quoted names, prefixed names (`LITELLM_API_KEY=`, `ANTHROPIC_AUTH_TOKEN=`) kept their value, and `raw_result` bypasses the log reader's scrub | independent review | high | patch | Hard rule 5. Redaction allows a name prefix, an optional quote and `Bearer` or `Basic`; tested through both sources. |
| A retried event (`system/api_retry`, `error: "rate_limit"`) parked as a provider error | independent review | high | patch | `error` and `message` are read only on an `error` or `turn.failed` event. |
| Marker too loose: `app.py:402`, `npm error code 402`, `credit card`, exporter `Too Many Requests`, JSON prose behind a warning | independent review | medium | patch | Status number must follow `status`, `http` or `error` within three separator characters; bare `credit` dropped; telemetry exporters excluded; prefixed JSON is an event only with a `type`. The OpenRouter 402 case is a test. |
| Misses: `monthly spend limit`, `Quota exceeded`, `Budget has been exceeded`, `errors[]` | independent review | medium | patch | Wordings added; `errors` of a failed result read. |
| `unexpected status` hid a provider failure after a failed exit | independent review | decision | patch | Operator decision 2026-11-02; guarded by a non-zero exit. Statement above revised. |
| Surviving mutants: both `MAX_SCAN` uses, the `Bearer` alternative, a redundant `402\|429` prefix alternative | independent review | medium | patch | Boundary tests at the scan bound; standalone `Bearer` test; the redundant alternative removed. |
| Narrating comments in `provider_failure.py` and `agent_failure.py` | independent review | low | patch | Reworded. |

## Verification

**Commands:**
- `make lint` -- expected: passes, including import-linter and test pairs.
- `make test` -- expected: passes, with domain and application at 100% branch coverage.
