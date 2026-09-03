---
story: "5-2"
epic: 5
title: Tracer port and the Langfuse adapter
requirements: [FR-2 (log_prompt_content), FR-27, NFR-5, AR-16]
binds: [AD-2, AD-11]
---

# Story 5.2 — Tracer port and the Langfuse adapter

As the Operator,
I want one trace per Run in Langfuse that holds every Step span and every model call the agents made,
So that a Run is one place to read, and cost, time, and outcome per story can be compared later (SM-3).

## Scope

**In:** `domain/ports/tracer.py`, `infrastructure/tracing/langfuse_tracer.py`, `tests/unit/fakes/tracer.py`; `create_run` creating the trace and storing `run.trace_id`; the walker opening a span per row execution and a child span per attempt; `TRACEPARENT` handed to `env_for`; `attempt_observed`; the trace URL in the Run read model; content-logging wiring.
**Out:** codex and opencode exporters (Epic 7), spend (5.3).

## Binding rules (inlined)

- **Port.** `Tracer{create_run_trace(run_id, project_slug, tags) -> TraceRef{trace_id}, step_span(run, row, attempt) -> SpanRef{trace_id, span_id, traceparent}` (context manager: opened before the executor runs, closed with the result status), `attempt_span(run, row, attempt) -> SpanRef` (child of the step span; its `traceparent` is what the harness receives), `attempt_observed(run_id, attempt_id) -> bool`, `trace_url(trace_id) -> str`}`.
- **Trace identity (AD-11).** `trace_id = langfuse.create_trace_id(seed=run_id)` (deterministic from the Run id) `[per the Langfuse Python SDK 4.15 API; verify the call name in research/tracing.md]`; the root observation carries `session_id = run_id`, `user_id = run_id`, tags `run:{id}`, `project:{slug}`, name `run {template}@{v} {branch}`; the Run stores `trace_id` at `create_run`. Every Step span is named by the row's `path` with attributes `run_id`, `path`, `kind`, `attempt`; the attempt span carries `attempt_id`, `harness`, `model`, `story_id`. `TRACEPARENT = 00-{trace_id}-{attempt span_id}-01`.
- **Exporter.** The SDK exports OTLP to `LANGFUSE_BASE_URL/api/public/otel` with the public/secret keys; `LANGFUSE_ENVIRONMENT` as environment; flush on shutdown and after each step span (short-lived steps must not lose spans on a kill).
- **Content logging (FR-2, AD-5).** Orchestrator spans never contain prompt or file content; the harness's content switches (`OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_TOOL_CONTENT`, later Codex and plugin equivalents) are set by `env_for` only when `project.log_prompt_content` is true.
- **`attempt_observed(run_id, attempt_id)`** queries the Langfuse public API (`GET /api/public/observations?traceId={trace_id}&...` `[endpoint and filter per research/tracing.md]`) and returns true when at least one observation exists under the attempt span (parent span id match) for `claude`/`codex`, or — Epic 7 — with `userId == run_id` for `local`. Used only by readiness (5.8).
- **Read model.** `GET /runs/{id}.cost.trace_url = tracer.trace_url(run.trace_id)` (`{LANGFUSE_BASE_URL}/project/…/traces/{trace_id}` `[verify the URL shape; a settings value LANGFUSE_PROJECT_ID may be needed — add it and its .env.example line if so]`).
- **Layering:** `langfuse` imported only under `infrastructure/tracing/`; the walker calls the port; unit tests use the fake.

## Acceptance criteria

**Given** `create_run`
**When** a Run is created with the fake tracer
**Then** `create_run_trace` was called with the Run id and tags, and `run.trace_id` is stored.

**Given** the walker executing a row
**When** the executor runs
**Then** a step span named by the path wraps the execution, and for an `agent` row an attempt span is opened whose `traceparent` appears as `TRACEPARENT` in the env the fake harness received (`00-{trace_id}-…-01` with the run's trace id).

**Given** the real adapter against a Langfuse test endpoint (e2e, `E2E_LANGFUSE=1`) `[ASSUMPTION: optional e2e when a Langfuse is reachable]`
**When** a `repo-init` Run completes
**Then** a trace with `session_id == run_id` exists holding one span per row, and `trace_url` opens it.

**Given** a Project with `log_prompt_content` false
**When** an agent env is built
**Then** no `OTEL_LOG_*` key is present; true → both present.

**Given** `attempt_observed` on the fake
**When** scripted true/false
**Then** readiness (5.8) can consume it (interface test only here).

## Implementation notes

- `infrastructure/tracing/langfuse_tracer.py::LangfuseTracer(settings)`; `research/tracing.md` documents the SDK calls and the OTLP endpoint; read it before planning.
- Walker: wrap `execute_row` in `tracer.step_span(...)`; the agent executor opens `attempt_span` right before dispatch and passes its `traceparent` to `env_for` (5.4 consumes; here provide the port and the walker span).
- `.env.example`: add `LANGFUSE_PROJECT_ID` only if required for `trace_url`.

## Verification

```bash
make lint && make test && make openapi
```

## Sources for detail only

PRD FR-27, FR-2, NFR-5. Spine AD-11 (identity, parenting), AD-5 (content switches). `research/tracing.md`. `addendum.md` §A Tracing.
