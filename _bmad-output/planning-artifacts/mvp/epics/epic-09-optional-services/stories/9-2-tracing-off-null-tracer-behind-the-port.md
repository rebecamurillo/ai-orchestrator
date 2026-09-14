---
title: 'Tracing off — NullTracer behind the port'
type: 'feature'
created: '2026-09-13'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
baseline_revision: 'cc4aafc3fdb7502010680c0042c083e9e0be869e'
---

<intent-contract>

## Intent

**Problem:** With `tracing_enabled` false, every `LangfuseTracer` call site still constructs a real Langfuse client, so an instance with a blank `LANGFUSE_BASE_URL` will crash or produce a malformed `cost.trace_url` (story 9-1's own deferred finding). The `Tracer` port has no off-path.

**Approach:** Add `NullTracer` (no Langfuse import) and a `build_tracer(settings)` factory in `infrastructure/tracing/`; wire all six `LangfuseTracer(settings)` call sites through the factory; widen the port's `trace_url` return to `str | None`.

## Boundaries & Constraints

**Always:**
- `build_tracer` returns `LangfuseTracer(settings)` when `settings.tracing_enabled` is `True`, `NullTracer()` when `False`. No other branching on tracing anywhere in `application/` or `domain/`.
- `NullTracer` imports no `langfuse` symbol. The trace id is `run_id.hex` (32 lowercase hex chars, valid W3C trace id, deterministic from the Run alone).
- `step_span` and `attempt_span` yield `fallback_span_ref(run.id.hex)` from `infrastructure/tracing/spans.py` — the existing schema-valid locally-generated `SpanRef`.
- `attempt_observed` returns `False` and logs `TRACE_OBSERVED` with `path="disabled"` via structlog.
- `trace_url` returns `None`. Port widened to `str | None`; `LangfuseTracer.trace_url` keeps returning `str` (narrowing is fine under the widened protocol).
- Both use-case readers (`history.py::_trace_url`, `run_views.py::run_detail`) already handle `str | None` — no use-case changes needed.
- Anchor tests (`test_api_providers_tracing.py`, `test_dbos_startup_tracing.py`) pass unchanged: with `.env.example` values, `tracing_enabled=True` so `build_tracer` returns `LangfuseTracer`, and `isinstance(_, LangfuseTracer)` stays true.
- `make openapi` produces no drift: API schemas already declare `trace_url: str | None`.
- Source-cap: `null.py` must stay well under 400 lines.

**Block If:** Any existing test file needs editing to make gates pass.

**Never:** Import `langfuse` in `null.py`. Edit `test_langfuse_tracer.py`, `test_api_providers_tracing.py`, `test_dbos_startup_tracing.py`, or any other existing test file.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Factory, tracing off | `LANGFUSE_BASE_URL=""`, `build_tracer(settings)` called | Returns `NullTracer`; `isinstance(x, Tracer)` true; `langfuse.Langfuse` never constructed | No error |
| Factory, tracing on | `.env.example` values | Returns `LangfuseTracer` | No error |
| `create_run_trace` determinism | Same `run_id` twice | Both `trace_id == run_id.hex`; two different ids give two different trace ids | No error |
| `step_span` / `attempt_span` | Normal body | Yields `SpanRef`; `traceparent` matches `00-<32 hex>-<16 hex>-01`; trace id is `run_id.hex` | No error |
| `step_span` body raises | Exception in body | Exception propagates unchanged; context manager does not swallow it | Exception re-raised |
| `attempt_observed` | Any inputs | Returns `False` | No error |
| `trace_url` | Any `trace_id` | Returns `None` | No error |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/ports/tracer.py:111` — `Tracer.trace_url` currently returns `str`; widen to `str | None`
- `backend-api/src/orchestrator/infrastructure/tracing/null.py` — NEW: `NullTracer` class; imports `structlog`, `fallback_span_ref` from `spans.py`, port types from `domain/ports/tracer.py`; no `langfuse`
- `backend-api/src/orchestrator/infrastructure/tracing/__init__.py` — currently exports only `LangfuseTracer`; add `build_tracer(settings: Settings) -> Tracer` and `NullTracer` to `__all__`; import `Settings` from `infrastructure/settings.py`
- `backend-api/src/orchestrator/api/providers.py:74` — `from orchestrator.infrastructure.tracing import LangfuseTracer` → add `build_tracer`; 4 call sites (lines 208, 233, 279, 313) `LangfuseTracer(settings)` → `build_tracer(settings)`
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py:69` — `from orchestrator.infrastructure.tracing import LangfuseTracer` → add `build_tracer`; 2 call sites: `step_ports.tracer=LangfuseTracer(settings)` (line 127) and `LangfuseTracer(settings)` inside `on_terminal=partial(readiness_evaluate_hook, ...)` (line 148) → both `build_tracer(settings)`
- `backend-api/src/orchestrator/infrastructure/tracing/spans.py:44` — `fallback_span_ref(trace_id)` — NullTracer calls this with `run.id.hex` as `trace_id`
- `backend-api/src/orchestrator/infrastructure/tracing/langfuse_tracer.py:334` — `trace_url` returns `str`; unchanged — narrowing is valid under the widened protocol
- `backend-api/tests/unit/fakes/tracer.py` — existing `FakeTracer`; not modified; used by call-site tests unchanged
- `backend-api/tests/unit/test_api_providers_tracing.py` — anchor; must not be edited; stays green because `.env.example` gives `tracing_enabled=True`
- `backend-api/tests/unit/test_dbos_startup_tracing.py` — anchor; must not be edited; same reason

## Tasks & Acceptance

**Execution (TDD order — write tests first, all fail before step 2):**
- `backend-api/tests/unit/test_null_tracer.py` — Create: tests covering all I/O matrix rows and ACs below, plus `build_tracer` factory ACs; use the `env` fixture and `monkeypatch.setenv("LANGFUSE_BASE_URL", "")` for tracing-off cases; assert `NullTracer` is not a `LangfuseTracer` and is a `Tracer`
- `backend-api/src/orchestrator/domain/ports/tracer.py` — Edit: widen `trace_url` return type from `str` to `str | None` (line 111)
- `backend-api/src/orchestrator/infrastructure/tracing/null.py` — Create: `NullTracer` implementing all five `Tracer` protocol methods as described in Boundaries
- `backend-api/src/orchestrator/infrastructure/tracing/__init__.py` — Edit: add `build_tracer` factory and `NullTracer` to `__all__`; import `Settings` from `orchestrator.infrastructure.settings`
- `backend-api/src/orchestrator/api/providers.py` — Edit: replace all four `LangfuseTracer(settings)` with `build_tracer(settings)`; update import line 74
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` — Edit: replace both `LangfuseTracer(settings)` with `build_tracer(settings)`; update import line 69

**Acceptance Criteria:**
- Given `tracing_enabled` false, when `build_tracer(settings)` is called, then it returns a `NullTracer`, `isinstance(x, Tracer)` is true, and no Langfuse client is constructed (assert by patching `langfuse.Langfuse` to raise on construction and calling every port method)
- Given the committed `.env.example` environment, when `build_tracer(settings)` is called, then it returns a `LangfuseTracer`
- Given a `NullTracer`, when `create_run_trace(run_id, slug, tags, name=...)` is called twice for one Run id, then both answers carry `trace_id == run_id.hex`, and two different Run ids give two different ids
- Given a `NullTracer`, when `step_span(...)` and a nested `attempt_span(...)` are entered, then each yields a `SpanRef` whose `traceparent` matches `00-<32 hex>-<16 hex>-01`, the trace id is the Run's `id.hex`, and leaving the block raises nothing — including when the body raises, which propagates unchanged
- Given a `NullTracer`, when `attempt_observed(...)` and `trace_url(...)` are called, then they answer `False` and `None`
- Given the run-detail and history read models built over a `NullTracer`, when rendered, then `cost.trace_url` and every history row's `trace_url` are `None`, and the exported OpenAPI is byte-identical to the committed `contracts/openapi.json`

## Spec Change Log

## Review Triage Log

### 2026-09-13 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 1, low 1)
- defer: 0
- reject: 18
- addressed_findings:
  - `[medium]` `[patch]` Verification gap: no disabled-path wiring tests at provider/startup call sites — added `test_providers_tracing_off.py` (4 tests for `create_run_ports`, `readiness_ports`, `run_view_ports`, `history_ports` each asserting `NullTracer` when `LANGFUSE_BASE_URL=""`) and `test_startup_tracing_off.py` (1 test for `walker_deps`)
  - `[low]` `[patch]` AC 6 use-case rendering not tested — appended 2 tests to `test_null_tracer.py`: `test_history_trace_url_is_none_when_null_tracer_and_trace_id_present` (exercises `history.py::_trace_url` with `NullTracer` and present `trace_id`) and `test_run_view_trace_url_is_none_when_null_tracer_and_trace_id_present` (reproduces `run_views.py:334` conditional verbatim)

## Design Notes

`run_id.hex` on a UUID is 32 lowercase hex characters with no hyphens — exactly what W3C `traceparent` requires for the trace-id field. `fallback_span_ref` generates a fresh random 16-hex span id on every call, so each `step_span`/`attempt_span` entry yields a unique span, matching the real adapter's own degraded behaviour when span opening fails.

The protocol `@runtime_checkable` check (`isinstance(x, Tracer)`) inspects only method presence, not return-type annotations. `NullTracer` satisfies it because it implements all five named methods.

`build_tracer`'s import of `Settings` in `infrastructure/tracing/__init__.py` is intra-layer (both are `infrastructure/`), so no AD-2 dependency violation.

## Verification

**Commands:**
- `make lint` -- expected: zero ruff, mypy, import-linter, env-contract violations
- `make test` -- expected: all pytest and vitest tests green, including new `test_null_tracer.py`
- `make openapi` -- expected: no drift (API payload shapes unchanged)

## Auto Run Result

**Status:** done  
**Review loop iterations:** 0  
**Patches applied:** 2 (high 0, medium 1, low 1)  
**followup_review_recommended:** false (score 4 < threshold 5)

### Summary

Implemented `NullTracer` (no-op adapter) and `build_tracer(settings)` factory for the `Tracer` port, wiring the off-path when `tracing_enabled` is `False`.

**Files created:**
- `backend-api/src/orchestrator/infrastructure/tracing/null.py` — `NullTracer` with all five protocol methods; no `langfuse` import; `create_run_trace` returns `run_id.hex` as trace id; spans yield `fallback_span_ref`; `trace_url` returns `None`
- `backend-api/tests/unit/test_null_tracer.py` — 32 tests (30 original + 2 AC-6 use-case rendering patches)
- `backend-api/tests/unit/test_providers_tracing_off.py` — 4 tests verifying `NullTracer` wired at all provider call sites when `LANGFUSE_BASE_URL=""`
- `backend-api/tests/unit/test_startup_tracing_off.py` — 1 test verifying `NullTracer` wired via `walker_deps`

**Files modified:**
- `backend-api/src/orchestrator/domain/ports/tracer.py` — `trace_url` return widened from `str` to `str | None`
- `backend-api/src/orchestrator/infrastructure/tracing/__init__.py` — `build_tracer` factory and `NullTracer` added to `__all__`
- `backend-api/src/orchestrator/api/providers.py` — 4 `LangfuseTracer(settings)` call sites replaced with `build_tracer(settings)`; stale docstring updated
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` — 2 `LangfuseTracer(settings)` call sites replaced with `build_tracer(settings)`

**Anchor tests preserved:** `test_api_providers_tracing.py` and `test_dbos_startup_tracing.py` pass unchanged — `.env.example` values give `tracing_enabled=True` so `build_tracer` returns `LangfuseTracer` and `isinstance(_, LangfuseTracer)` stays true.
