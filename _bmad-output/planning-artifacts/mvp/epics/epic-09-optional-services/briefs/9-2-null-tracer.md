---
story: "9-2"
epic: 9
title: Tracing off — NullTracer behind the port
requirements: [NFR-7, NFR-8]
binds: [AD-2, AD-11]
---

# Story 9.2 — Tracing off, behind the port

As the Operator,
I want an instance with no Langfuse to execute every Run exactly as one with Langfuse, minus the traces,
So that turning tracing off costs me a link, not a behaviour.

## Scope

**In:** `infrastructure/tracing/null.py` (`NullTracer`), `build_tracer(settings)` in `infrastructure/tracing/__init__.py`, the `Tracer` port's `trace_url` widened to `str | None`, and every construction site wired through the factory — `api/providers.py` (each `LangfuseTracer(settings)`) and `infrastructure/dbos/startup.py` (the walker's `StepPorts` tracer and the second instance beside it).
**Out:** the Gateway (9-3), the harness environment and the Langfuse variables a harness process receives (9-4), the scripts' OTLP blocks (9-5), the screen (9-6).

## Binding rules (inlined)

- **`Settings.tracing_enabled` (9-1) is the only condition.** `build_tracer` returns `LangfuseTracer(settings)` when it is true and `NullTracer()` when it is false. Nothing else branches on tracing anywhere in `application/` or `domain/` — the port is the seam (AD-2).
- **`null.py` imports no SDK.** `langfuse` stays imported only by `langfuse_tracer.py`. The trace id is `run_id.hex` — 32 lowercase hex characters, which is a valid W3C trace id and is deterministic from the Run alone, the same property AD-11 wants and the same one `LangfuseTracer` gets from `Langfuse.create_trace_id(seed=...)`.
- **Reuse, do not re-derive.** `step_span` and `attempt_span` yield `infrastructure/tracing/spans.py::fallback_span_ref(trace_id)` — the schema-valid, locally generated `SpanRef` the real adapter already yields when opening a span fails. A harness process is handed a well-formed `TRACEPARENT` in both modes; nothing downstream can tell which produced it, which is exactly what makes the mode safe.
- **`attempt_observed` answers `False`**, and its own log line says `path=disabled`. `False` already means "not observed" everywhere it is read (5.8), and no caller treats it as an error.
- **`trace_url` answers `None`.** The port's return type becomes `str | None`; both readers are already `str | None` (`application/use_cases/history.py::_trace_url`, `application/use_cases/run_views.py`), and both API schemas already declare `trace_url: str | None`, so **the OpenAPI contract does not change** and `pnpm gen:api` produces no drift. `LangfuseTracer.trace_url` keeps returning a string; only the protocol widens.
- **`create_run_trace` still returns a `TraceRef`** and `Run.trace_id` is still stored. An instance that turns tracing back on then has real spans hanging under the ids its earlier Runs already recorded, and nothing has to be migrated.
- **Never raises.** The same rule the real adapter states as "a side channel, never a hard dependency" (AD-11): every method here is total, and there is no code path in which the absence of tracing can fail a row.
- **The default environment is unchanged.** With `.env.example`'s values, `build_tracer` returns a real `LangfuseTracer`, which is what `tests/unit/test_api_providers_tracing.py` and `test_dbos_startup_tracing.py` assert today and must keep asserting.

## Acceptance criteria

**Given** `tracing_enabled` false
**When** `build_tracer(settings)` is called
**Then** it returns a `NullTracer`, the instance satisfies `isinstance(x, Tracer)`, and no Langfuse client is constructed (assert by patching `langfuse.Langfuse` to raise on construction and calling every port method).

**Given** the committed `.env.example` environment
**When** `build_tracer(settings)` is called
**Then** it returns a `LangfuseTracer`.

**Given** a `NullTracer`
**When** `create_run_trace(run_id, slug, tags, name=...)` is called twice for one Run id
**Then** both answers carry `trace_id == run_id.hex`, and two different Run ids give two different ids.

**Given** a `NullTracer`
**When** `step_span(...)` and a nested `attempt_span(...)` are entered
**Then** each yields a `SpanRef` whose `traceparent` matches `00-<32 hex>-<16 hex>-01`, the trace id is the Run's, and leaving the block raises nothing — including when the body raises, which propagates unchanged.

**Given** a `NullTracer`
**When** `attempt_observed(...)` and `trace_url(...)` are called
**Then** they answer `False` and `None`.

**Given** the run-detail and history read models built over a `NullTracer`
**When** rendered
**Then** `cost.trace_url` and every history row's `trace_url` are `None`, and the exported OpenAPI is byte-identical to the committed `contracts/openapi.json`.

## Implementation notes

- New test file: `backend-api/tests/unit/test_null_tracer.py`; if the factory needs its own, `test_tracer_factory.py`. Do not touch `test_langfuse_tracer.py` or the two provider tests.
- `tests/unit/fakes/tracer.py` already exists — use it for call-site tests; the `NullTracer` is production code and gets its own tests, not a fake.
- Keep `null.py` small enough to stay under the 400-line source cap `tests/unit/test_source_limits.py` enforces; it should be well under it.
- Widening the port is a `mypy` change across the two readers only; both already narrow `None`.

## Verification

```bash
make lint && make test && make openapi
```

`make openapi` must report no drift: this story changes no payload shape.

## Sources for detail only

Spine AD-2 (dependency direction), AD-11 (one trace per Run, deterministic ids). `infrastructure/tracing/langfuse_tracer.py` — the "side channel, never a hard dependency" section states the degradation contract this story makes explicit. `infrastructure/tracing/spans.py` — `fallback_span_ref`.
