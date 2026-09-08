---
title: 'Tracer port and the Langfuse adapter'
type: 'feature'
created: '2026-09-07'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - 'Per-request `LangfuseTracer` construction in `create_run_ports` builds a new `Langfuse` client (hence a new background export thread) on every successful `POST /runs`, never explicitly shut down — accepted for now (low request frequency); consolidating onto a shared `app.state` singleton needs room in `main.py` this story does not have.'
  - "`attempt_observed`'s real-adapter query pages at most 100 observations per trace when looking for the attempt's own span; a trace with more observations than that before the attempt span appears could under-report. Exercised for real only in 5.8."
  - "The Langfuse SDK's own `flush()` swallows exporter errors (verified live against a refused connection) but can still block for the client's export timeout on each call when the endpoint is unreachable; this story sets an explicit, shorter-than-default client timeout to bound that, but does not add a setting for it — a fixed implementation constant."
baseline_revision: '1832217205f82b5021f64e0f5e6a642a91268754'
---

<intent-contract>

## Intent

**Problem:** Nothing traces a Run. There is no `Tracer` port, no Langfuse adapter, and
`env_for`'s `traceparent` parameter (added by 5.1, keyword-only, defaulting to `""`) has
nothing real to fill it with, so a coding-agent's model calls can never be found under the
Run that dispatched them.

**Approach:** Add `domain/ports/tracer.py` (`Tracer` protocol, `TraceRef`, `SpanRef`),
`infrastructure/tracing/langfuse_tracer.py` (`LangfuseTracer(settings)`, verified against
the real `langfuse` SDK 4.15.1), `tests/unit/fakes/tracer.py` (`FakeTracer`). `create_run`
opens the Run's trace and stores `run.trace_id`. `walk.run_row` wraps a row's execution in
`tracer.step_span(run, row, attempt)`. The Run detail's `cost.trace_url` is filled from
`tracer.trace_url(run.trace_id)`. `attempt_span` (child of the step span, its `traceparent`
is what 5.4's executor will hand `env_for`) and `attempt_observed` are provided as port +
adapter + fake now; nothing in this story's production code calls either yet — 5.4 and 5.8
do.

## Boundaries & Constraints

**Always:**
- AD-11: `trace_id = langfuse.create_trace_id(seed=str(run_id))` — deterministic, so every
  later span for a Run finds the same trace without storing a span id anywhere.
- AD-2/AD-10: `langfuse` is imported only under `infrastructure/tracing/`; `domain/ports/
  tracer.py` holds only the protocol and its two frozen value types.
- AD-5 (FR-2): orchestrator spans carry no prompt or file content. `OTEL_LOG_*` is already
  wired by 5.1's `claude_aliases`/`env_for` from `project.log_prompt_content` — this story
  adds no second copy of that switch.
- A `Tracer`-typed port on `WalkPorts`/`StepPorts`/`CreateRunPorts`/`RunViewPorts` is
  optional (`Tracer | None = None`): several already-committed, frozen unit-test files
  construct these dataclasses without one (e.g. `tests/unit/application/
  test_walk_use_case.py`, `tests/unit/application/test_run_views.py`,
  `tests/unit/test_create_run_use_case.py`). Every call site degrades to "no span opened" /
  `trace_url = None` when unset, never raises. Production wiring always sets a real one.
- Every new source module is paired with a unit test that imports it (AD-18,
  `check_test_pairs`); every module stays ≤ 400 lines; `domain/` + `application/` stay at
  100% branch coverage.
- `main.py` stays untouched: it is at 394/400 lines (frozen cap, `test_source_limits.py`).
  The walker's own `LangfuseTracer` is built inline in `infrastructure/dbos/
  startup.py::walker_deps` (already takes `settings`); the request-serving one is built
  inline, per request, in `api/providers.py` (`create_run_ports`, `run_view_ports`) from
  `app.state.settings` — a documented deferred, not a silent restructure.

**Block If:**
- Landing this story would require editing `SPEC.md`, `stories.yaml`, an `AGENTS.md`, or any
  existing test file.
- The real `langfuse` package (pinned 4.15.1 per `research/tracing.md`) does not expose the
  calls the brief names, with no equivalent.

**Never:**
- No codex/opencode exporters (Epic 7), no spend (5.3).
- No agent executor wiring `attempt_span`/`traceparent` into a real dispatch (5.4); no
  readiness use of `attempt_observed` (5.8); no Run-detail UI additions beyond the one field
  this story's own Scope names (`cost.trace_url`) — story cards, harness/cost columns, the
  Question block are 5.10.
- No `make e2e-api`/`make e2e-ui`/`make durability`: the brief's own Verification section
  names only `make lint && make test && make openapi`, and the real-adapter e2e AC is itself
  `[ASSUMPTION: optional e2e when a Langfuse is reachable]`, gated on `E2E_LANGFUSE=1`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `create_run` with a tracer | fake tracer wired | `create_run_trace(run_id, project.slug, (), name=...)` called once; `run.trace_id` stored | No error expected |
| `create_run` with no tracer | `CreateRunPorts.tracer=None` | `run.trace_id` stays `None`; Run still created | No error expected |
| `run_row` executes a row | fake tracer wired | `step_span(run, row, attempt)` opened before `execute(context)` and closed after | No error expected |
| `run_row` executes a row | `WalkPorts.tracer=None` (frozen `test_walk_use_case.py`'s own ports) | `execute(context)` runs exactly as before, no span call | No error expected |
| `attempt_span` → `env_for` | fake tracer's `SpanRef.traceparent` | passed as `env_for(..., traceparent=...)` | appears verbatim as `TRACEPARENT` in the harness env |
| `trace_url` in the Run read model | `run.trace_id` set, tracer wired | `cost.trace_url` is `tracer.trace_url(run.trace_id)` | `run.trace_id is None` or `tracer is None` → `cost.trace_url is None` (the existing frozen assertion in `test_run_views.py`, whose `a_run()` never sets `trace_id`) |
| `attempt_observed` on the fake | scripted `True`/`False` per `(run_id, attempt_id)` | returns the scripted value | unscripted pair → `False` |
| Real adapter, endpoint unreachable | `LANGFUSE_BASE_URL` refuses the connection | `flush()`/export failure is caught inside the `langfuse`/OTel SDK, never raised | No exception reaches `create_run`/the walker |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/ports/harness.py` — the port-module style to match:
  frozen dataclasses beside a `runtime_checkable Protocol`, prose explaining what is
  deliberately *not* on the result type.
- `backend-api/src/orchestrator/infrastructure/harness/env.py:114-150` — `env_for`'s
  existing `traceparent: str = ""` keyword-only parameter (5.1); this story is "5.2 supplies
  one," per its own docstring. No change needed here.
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:93-111` —
  `claude_aliases` already wires `OTEL_LOG_USER_PROMPTS`/`OTEL_LOG_TOOL_CONTENT` from
  `ORCH_LOG_CONTENT`; the brief's content-logging AC is already fully covered by 5.1's frozen
  `tests/unit/test_harness_env.py` (lines ~224-357) — no new code or test needed for it.
- `backend-api/src/orchestrator/application/use_cases/walk.py` — `run_row` (currently: `with
  ports.writers.uow: context = _context(ports, run_id, seq, resume_event); return
  execute(context)`) is where `step_span` wraps `execute(context)`. `_context`'s signature
  changes from `(ports, run_id, seq, resume_event)` to `(ports, run, seq, resume_event)` so
  `run_row` reads `Run` once (via `require_run`) and reuses it for both the context's `cwd`
  and the tracer call — no second repository read.
  ```python
  def run_row(ports, run_id, seq, resume_event=None):
      with ports.writers.uow:
          run = require_run(ports.writers, run_id)
          context = _context(ports, run, seq, resume_event)
      tracer = context.ports.tracer
      if tracer is None:
          return execute(context)
      with tracer.step_span(run, context.row, context.attempt):
          return execute(context)
  ```
- `backend-api/src/orchestrator/application/steps/context.py:118-137` — `StepPorts` gains
  one new optional field, `tracer: Tracer | None = None`, appended after `protected_paths`
  (same "`None` until a kind that needs it" idiom the module already documents). Reached by
  `run_row` through `context.ports.tracer`, and by 5.4's agent executor the same way — one
  field, not two, so `WalkPorts` itself needs no `tracer` of its own.
- `backend-api/src/orchestrator/application/use_cases/create_run.py:65-176` —
  `CreateRunPorts` gains `tracer: Tracer | None = None`. `create_run()` builds `trace =
  ports.tracer.create_run_trace(run_id, project.slug, (), name=_trace_name(req, run_id)) if
  ports.tracer is not None else None` right after `run_id = new_id()`, then constructs `Run(
  ..., trace_id=trace.trace_id if trace is not None else None, ...)`. `_trace_name` is a new
  private helper: `f"run {req.template_name}@{req.template_version} {req.base_branch}"` —
  the brief's own AD-11 identity line names this format; the brief's literal port signature
  (`create_run_trace(run_id, project_slug, tags)`) omits it, so `name` is added keyword-only
  (5.1's own precedent for `env_for`'s `traceparent`/`story_id`: keep the brief's named
  parameters, add the missing fact as kwonly rather than inventing something unrelated).
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py:161-173` —
  `RunViewPorts` gains `tracer: Tracer | None = None`; `Cost.trace_url` field already exists
  (5.1-era placeholder, always `None`); its docstring is stale ("no tracing UI yet") and gets
  a one-line correction, nothing else about the field's shape changes.
- `backend-api/src/orchestrator/application/use_cases/run_views.py:210-231,330-344` —
  `run_detail` passes `tracer=ports.tracer` into `_cost`; `_cost` becomes `_cost(run,
  attempts_by_row, *, now, tracer)` and sets `trace_url=tracer.trace_url(run.trace_id) if
  (tracer is not None and run.trace_id) else None`. The existing frozen assertion
  `tests/unit/application/test_run_views.py:462` (`assert detail.cost.trace_url is None`)
  keeps passing untouched: its own `a_run()` fixture never sets `trace_id`.
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py:66-91` — `walker_deps` builds
  `StepPorts(..., tracer=LangfuseTracer(settings))` inline — one instance for the whole
  process's walker, exactly like `RealProcessRunner()` is built inline today. No `main.py`
  change: `walker_deps` already takes `settings`.
- `backend-api/src/orchestrator/api/providers.py:166-193` — `create_run_ports` and
  `run_view_ports` each read `settings = from_state(request, SETTINGS)` (the constant
  already exists) and pass `tracer=LangfuseTracer(settings)`. Per-request construction, not
  an app.state singleton — see Design Notes for why, and the deferred entry that records the
  tradeoff.
- `backend-api/src/orchestrator/infrastructure/settings.py:78-81` — add
  `langfuse_project_id: str` under the existing Tracing block. `.env.example` gets
  `LANGFUSE_PROJECT_ID=` beside the other `LANGFUSE_*` lines (AD-20: same change).
- `backend-api/tests/unit/test_dbos_startup.py` (frozen) — `walker_deps(Settings(), ...)`
  already runs with `.env.example` placeholder Langfuse values; constructing a `Langfuse`
  client with placeholder keys is verified (this story's own spike) to do no I/O and raise
  nothing — the two existing tests there keep passing unmodified.
- `backend-api/tests/unit/conftest.py` — `env` fixture (frozen) already puts every
  `.env.example` name into `os.environ`; `LANGFUSE_PROJECT_ID`'s new line is picked up by it
  automatically, no fixture change needed.
- `research/tracing.md` — this story's own spike against the real `langfuse==4.15.1` package
  (network-installed and inspected live, since it was not already a dependency) confirms:
  `Langfuse(public_key=, secret_key=, base_url=, environment=)` client;
  `create_trace_id(seed=...)`; `start_as_current_observation(trace_context={"trace_id":
  ...}, name=, as_type="span", metadata=...)` as a context manager yielding a span with
  `.id`/`.trace_id`; nested `start_as_current_observation` calls auto-parent via OTel's
  ambient context, which is how `attempt_span` becomes a child of `step_span` without an
  explicit parent parameter; `api.observations.get_many(trace_id=, parent_observation_id=)`
  for `attempt_observed`; `get_trace_url()` makes a **blocking API call** the first time
  (`self.api.projects.get()`) to resolve a project id — this is why `LANGFUSE_PROJECT_ID` is
  added as a setting and `trace_url()` is a pure string format, never a network call.
  Exporter failures (verified live against a refused connection) are caught inside the SDK
  and never raise.

## Tasks & Acceptance

**Execution:**
- `backend-api/tests/unit/test_tracer_port.py` — new: `Tracer` protocol shape, `TraceRef`,
  `SpanRef` construction/frozen-ness, `FakeTracer` satisfies `Tracer` — TDD first (AD-18).
- `backend-api/src/orchestrator/domain/ports/tracer.py` — new: `TraceRef`, `SpanRef`,
  `Tracer` protocol (`create_run_trace`, `step_span`, `attempt_span`, `attempt_observed`,
  `trace_url`), each exactly as the brief's Binding rules and this spec's Code Map/Design
  Notes fix them.
- `backend-api/tests/unit/fakes/tracer.py` — new `FakeTracer`: records every call; returns a
  deterministic `TraceRef`/`SpanRef` per call (`trace_id` derived from the given `run.id`/
  `run_id`, `span_id` a counter) so a test can assert the exact `TRACEPARENT` string;
  `attempt_observed` answers from a `{(run_id, attempt_id): bool}` script, `False` when
  unscripted — the one fake for the port (AD-18); 5.4/5.8 reuse it.
- `backend-api/tests/unit/test_langfuse_tracer.py` — new: `LangfuseTracer` against the real
  `langfuse` package (no network — assert on the client's own in-memory span data / on
  `create_trace_id`'s determinism / on argument shapes passed to `start_as_current_observation`
  via a lightweight stub client where a real network round-trip would be needed); `trace_url`
  format from settings alone, no client built; content-logging is *not* re-tested here (5.1
  already covers it — see Code Map).
- `backend-api/src/orchestrator/infrastructure/tracing/__init__.py` — new package marker
  re-exporting `LangfuseTracer`.
- `backend-api/src/orchestrator/infrastructure/tracing/langfuse_tracer.py` — new:
  `LangfuseTracer(settings)`; lazy `Langfuse` client (built on first use, not at
  construction — keeps a `trace_url`-only caller cheap); `create_run_trace`, `step_span`,
  `attempt_span`, `attempt_observed`, `trace_url`; a short client-side export timeout
  (documented constant) so an unreachable Langfuse cannot stall a caller for the SDK's
  10-second default.
- `backend-api/tests/unit/application/test_walk_tracing.py` — new: `run_row` opens/closes a
  `FakeTracer.step_span` around `execute`; with `WalkPorts.tracer=None` (the frozen
  `test_walk_use_case.py`'s own construction pattern) nothing about `run_row`'s existing
  behaviour changes. Also proves the `_context` signature refactor (`run` reused, not
  re-fetched) via the existing assertions this file re-derives (worktree, previous attempt,
  frame commit) rather than by touching the frozen file that already proves them.
- `backend-api/tests/unit/test_tracer_env_integration.py` — new: `FakeTracer.attempt_span`'s
  `SpanRef.traceparent` passed into `env_for(..., traceparent=...)` appears verbatim as
  `TRACEPARENT` in the dict `FakeHarness.run` receives — the mechanism 5.4 will wire for
  real, proved once here per the brief's own AC #2.
- `backend-api/tests/unit/application/test_create_run_tracing.py` — new: `create_run` with a
  `FakeTracer` calls `create_run_trace(run_id, project.slug, (), name=...)` once and stores
  `run.trace_id`; with `tracer=None`, `run.trace_id` stays `None` and the Run is still
  created (both matrix rows).
- `backend-api/tests/unit/application/test_run_views_tracing.py` — new: `run_detail` with a
  wired `FakeTracer` and a Run whose `trace_id` is set returns `cost.trace_url ==
  tracer.trace_url(run.trace_id)`; ports built exactly like the frozen file's own `harness`
  fixture, but with `tracer=FakeTracer()` and a Run carrying `trace_id="t-1"`.
- `backend-api/src/orchestrator/application/use_cases/walk.py` — edit per Code Map.
- `backend-api/src/orchestrator/application/steps/context.py` — edit per Code Map.
- `backend-api/src/orchestrator/application/use_cases/create_run.py` — edit per Code Map.
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py` — edit per Code Map.
- `backend-api/src/orchestrator/application/use_cases/run_views.py` — edit per Code Map.
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` — edit per Code Map.
- `backend-api/src/orchestrator/api/providers.py` — edit per Code Map.
- `backend-api/src/orchestrator/infrastructure/settings.py` — add `langfuse_project_id`.
- `.env.example` — add `LANGFUSE_PROJECT_ID=` (AD-20).
- `backend-api/pyproject.toml` — add `"langfuse==4.15.1"` to `[project].dependencies` (it is
  currently only an import-linter `forbidden_modules` entry, not an actual dependency — this
  story's own discovery, made while verifying the SDK calls above).

**Acceptance Criteria:**
- Given `create_run` with a fake tracer, when a Run is created, then `create_run_trace` was
  called with the Run id and tags, and `run.trace_id` is stored.
- Given the walker executing a row, when the executor runs, then a step span named by the
  path wraps the execution, and for a row an attempt span opened via `tracer.attempt_span`
  yields a `traceparent` that appears as `TRACEPARENT` in the env a fake harness receives
  (`00-{trace_id}-…-01` with the run's trace id) — proved as the mechanism `env_for` +
  `FakeHarness` exercise, since no production `agent` executor exists before 5.4.
- Given a Project with `log_prompt_content` false/true, an agent env already carries/omits
  `OTEL_LOG_*` correctly — pre-existing, frozen coverage from 5.1; no new test.
- Given `attempt_observed` on the fake, when scripted true/false, then it answers exactly
  that (interface test only, per the brief).
- Given `make lint`, then `check_test_pairs`, ruff, mypy --strict, lint-imports, the
  env-contract check and every module's 400-line cap all pass, `main.py` unmodified at 394
  lines.
- Given `make test`, then every unit test passes and `domain/` + `application/` stay at
  100% branch coverage.
- Given `make openapi`, then the exported contract is unchanged (this story adds no new
  request/response field to any router — `cost.trace_url`'s shape was already `str | None`).

## Design Notes

**Why `step_span`/`attempt_span` are plain context managers with no separate
"close-with-status" call.** The brief's Binding rule reads "(context manager: opened before
the executor runs, closed with the result status)". The `Tracer` protocol the brief spells
has exactly five methods — no sixth one to report a status back onto an already-open span —
so "closed with the result status" is read here as *temporal*: the span's lifetime is
exactly the width of one execution, closing when the result is known, not as a payload the
caller pushes back in. `start_as_current_observation`'s own `__exit__` already sets `ERROR`
when an exception escapes the block and `DEFAULT` otherwise, which is what a `with
tracer.step_span(...): execute(context)` gets for free. No AC tests span-level status
content, so this reading is not adopted over a competing one that would have produced a
different observable result — it is the only one the five-method protocol supports.

**Why `attempt_span` needs no explicit parent parameter.** Verified live against
`langfuse==4.15.1`: `start_as_current_observation` sets the span it opens as OTel's *current*
span for the width of its own `with` block via `contextvars`. `run_row`'s `step_span` call
and 5.4's future `attempt_span` call both happen inside one Python call (`walk.attempt_row`
→ `run_row` → `execute` → the row's executor), all within one DBOS step, never split across
a replay boundary (a replay re-runs `attempt_row` from the top, so the ambient context is
always freshly established). A nested `attempt_span` therefore auto-parents under the
currently-open `step_span` without carrying its span id explicitly — which is also why the
brief's own signature omits one.

**Why `create_run_trace` gains a keyword-only `name`.** AD-11 requires the root
observation's name (`run {template}@{v} {branch}`), but the brief's literal port signature —
`create_run_trace(run_id, project_slug, tags)` — has nowhere to carry it. Same resolution
5.1 used for `env_for`'s `traceparent`/`story_id`: keep every brief-named parameter, add the
one missing, stated fact as a keyword-only addition rather than inventing an unrelated
shape. `create_run` already holds `req.template_name`, `req.template_version`,
`req.base_branch` — nothing new is read to supply it.

**Why `attempt_observed`'s real implementation is not AC-gated.** The brief itself marks
this "interface test only here" and "used only by readiness (5.8)" — no AC exercises the
real adapter's query semantics, and the only e2e AC covering the real adapter at all is
itself `[ASSUMPTION: optional]`. The real `LangfuseTracer.attempt_observed` is implemented
by finding the attempt's own span among a bounded page of the trace's observations (matched
by the `attempt_id` metadata `attempt_span` writes), then checking whether any observation
names it as `parent_observation_id` — a defensible reading of "parent span id match" that
needs no new storage on `Attempt`, recorded as a deferred (low severity) item: the 100-row
page cap could miss data on an unusually large trace, and 5.8 is where this gets exercised
for real.

**Why no `main.py` change, and what that trades away.** `main.py` is at 394/400 lines
(frozen `test_source_limits.py`). A conventional `app.state.tracer` (matching `git`/
`engine`/`crypto`) would touch `create_app`'s signature, `_serve`, and `main()` — a handful
of lines this file no longer has room for. Instead, `walker_deps` (in `infrastructure/dbos/
startup.py`, which already takes `settings`) builds one `LangfuseTracer` for the whole
process's walker, and `api/providers.py` builds a fresh, cheap one per request for
`create_run_ports`/`run_view_ports` — cheap because `LangfuseTracer`'s real `Langfuse`
client is lazy (built only by `create_run_trace`/`step_span`/`attempt_span`/
`attempt_observed`, never by `trace_url`). The one place this still costs something: every
successful `POST /runs` builds one real `Langfuse` client (for `create_run_trace`) that is
never explicitly shut down — an accepted, low-frequency (operator-initiated, not polled)
resource cost, recorded below as deferred rather than solved by restructuring `main.py`
unasked. A later story that already needs to touch `main.py`'s structure (5.4 was already
flagged for this by 5.1) is the natural place to consolidate onto one app.state singleton.

**`tags` at `create_run_trace` time.** The brief's identity line pins `run:{id}` and
`project:{slug}` on the root observation; both are synthesized inside the adapter from
`run_id`/`project_slug` themselves, so the `tags` parameter `create_run` passes is `()` —
no extra tags exist at Run-creation time in this epic.

## Spec Change Log

## Review Triage Log

### 2026-09-07 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 13: (high 2, medium 6, low 5)
- defer: 0
- reject: 9: (high 0, medium 0, low 9)
- addressed_findings:
  - `[high]` `[patch]` The root trace opened by `create_run_trace` never set `session_id`/`user_id` to the Run id (only `run_id` landed, in generic `metadata`), breaking Langfuse's Sessions-view grouping the brief's own identity line and `research/tracing.md`'s "Universal floor" both require. Rewrote to use the SDK's public `langfuse.propagate_attributes(session_id=, user_id=, tags=, trace_name=)`, wrapped around the root observation's own creation; a new test asserts the real span carries `session.id`/`user.id`/`langfuse.trace.tags`/`langfuse.trace.name`.
  - `[medium]` `[patch]` Tags (`run:{id}`, `project:{slug}`) were stuffed into generic `metadata` instead of the SDK's real tag mechanism, so traces would not be filterable by tag in the Langfuse UI. Fixed by the same `propagate_attributes(tags=...)` change above.
  - `[medium]` `[patch]` `step_span` opened with no attributes at all, though the brief requires `run_id`/`path`/`kind`/`attempt` on every Step span. Added `metadata={"run_id":..., "path":..., "kind":..., "attempt":...}`; a new test asserts these land on the real span.
  - `[medium]` `[patch]` `attempt_span` only carried `attempt_id`, though the brief requires `harness`/`model`/`story_id` too, and `attempt.harness`/`attempt.model`/`row.story_id` were simply unread. Added all three (omitted, not stringified, when `None`); new tests cover both the carried and the omitted case.
  - `[high]` `[patch]` `create_run`'s call into `create_run_trace` had no exception isolation: any Langfuse SDK failure beyond the one verified "refused connection" case (bad client construction, an SDK behaviour change) would take down Run creation entirely, turning an observability side channel into a hard dependency of a core write path. `create_run_trace`/`step_span`/`attempt_span` now each catch, log, and degrade — the deterministic `TraceRef`/a locally-generated fallback `SpanRef` is still returned/yielded so the caller always proceeds; a row's own exception (raised inside an open `step_span`) is still re-raised untouched. New tests cover the SDK-raises case for all three methods, including the row-also-raises compound case.
  - `[medium]` `[patch]` `run_row`'s `step_span` call was equally unguarded against a non-network tracer failure, which could error a row that otherwise executed fine. Covered by the same fix and tests as the finding above.
  - `[low]` `[patch]` `attempt_observed`'s real query (`api.observations.get_many`) had no exception handling. Wrapped to answer `False` on failure — the same thing an unscripted/not-yet-observed pair already means; new test covers it.
  - `[low]` `[patch]` `LangfuseTracer._client_ref`'s lazy client construction was not thread-safe, and the walker can run more than one Run's rows concurrently (`MAX_ACTIVE_RUNS` > 1), risking two separate `Langfuse` clients for what the docstring calls "one instance for the whole process's walker." Added double-checked locking with a `threading.Lock`.
  - `[low]` `[patch]` `_attempt_id_of` had a real (if ungated — `infrastructure/` is outside `[tool.mypy].files`) type-narrowing gap, returning `Any` instead of `str | None`. Tightened the isinstance narrowing.
  - `[low]` `[patch]` No test exercised `trace_url`'s trailing-slash normalization. Added one.
  - `[medium]` `[patch]` No test asserted `api/providers.py`'s real `create_run_ports`/`run_view_ports` actually wire a `LangfuseTracer` — both default `tracer=None`, so dropping the wiring line would silently stop all production tracing with zero test failures anywhere (every router test injects fakes). Added `test_api_providers_tracing.py` (a new file — the coordinator caught that the first attempt at this fix had edited the frozen, pre-existing `test_api_providers.py` directly; reverted that file to `HEAD` via `git checkout` and moved the two tests into their own new module instead, per root `AGENTS.md` hard rule 1).
  - `[medium]` `[patch]` No test asserted `infrastructure/dbos/startup.py::walker_deps` wires a `LangfuseTracer` into `StepPorts.tracer` — same silent-regression risk for the walker's own production path. Added `test_dbos_startup_tracing.py` (new file; `test_dbos_startup.py` itself is frozen and untouched).
  - `[reject]` Nothing in this story's own production code calls `attempt_span` from the walker (intent-alignment audit's R-A). Matches this story's own explicit Scope/Intent: "Nothing in this story's own production code calls `attempt_span` yet; 5.4's executor does."
  - `[reject]` `create_run_trace` gained a keyword-only `name` parameter beyond the brief's literal three-argument signature (R-C). Precedented by 5.1's own `env_for` `traceparent`/`story_id` addition; recorded in this spec's Design Notes before implementation.
  - `[reject]` No separate process-shutdown flush hook exists beyond the per-call `flush()` in `create_run_trace`/`step_span`/`attempt_span` (R-D). Nothing is ever left pending in the batch queue longer than the width of one method call under this design, so a shutdown hook would be a no-op.
  - `[reject]` Content-logging (`OTEL_LOG_*`) was not re-tested by this story (R-E). Verified directly: fully covered by 5.1's frozen `test_harness_env.py`.
  - `[reject]` No `E2E_LANGFUSE`-gated e2e artifact exists (R-F, brief's own AC #3). Matches this spec's explicit "Never: No `make e2e-api`/`make e2e-ui`/`make durability`" and the brief's own `[ASSUMPTION: optional]` hedge on that AC.
  - `[reject]` `Settings.langfuse_project_id` is a new required setting with no default (blind-hunter). Matches every other `LANGFUSE_*` setting's own convention exactly (AD-20); not a deviation.
  - `[reject]` Three new test files each hand-roll their own `a_run()`/`a_row()`/`an_attempt()` builders instead of sharing one (blind-hunter). Matches the established, accepted convention across this test suite (over a dozen existing files already do the same).
  - `[reject]` `attempt_observed`'s port signature has no `limit`/cursor escape hatch for the 100-row page cap (blind-hunter). Duplicate of this story's own already-recorded frontmatter `deferred` item; 5.8 is where it is exercised for real.
  - `[reject]` `flush()`'s blocking latency when Langfuse is unreachable is not proven bounded by an elapsed-time test (blind-hunter). Inherent, accepted cost of the brief's own "flush... after each step span" binding rule, not a new gap; `EXPORT_TIMEOUT_SECONDS` bounds it by construction.

## Verification

**Commands:**
- `make lint` -- expected: exit 0; every gate including `check_test_pairs` and the 400-line
  cap; `main.py` unchanged.
- `make test` -- expected: exit 0; `domain/` + `application/` at 100% branch coverage.
- `make openapi` -- expected: exit 0, no contract drift (`cost.trace_url`'s shape does not
  change).
- `git status --porcelain` -- expected: only the files this spec's Execution list names.

**Deferred (recorded in frontmatter `deferred` on completion):**
- Per-request `LangfuseTracer` construction in `create_run_ports` builds a new `Langfuse`
  client (hence a new background export thread) on every successful `POST /runs`, never
  explicitly shut down — accepted for now (low request frequency); consolidating onto a
  shared `app.state` singleton needs room in `main.py` this story does not have.
- `attempt_observed`'s real-adapter query pages at most 100 observations per trace when
  looking for the attempt's own span; a trace with more observations than that before the
  attempt span appears could under-report. Exercised for real only in 5.8.
- The Langfuse SDK's own `flush()` swallows exporter errors (verified live against a refused
  connection) but can still block for the client's export timeout on each call when the
  endpoint is unreachable; this story sets an explicit, shorter-than-default client timeout
  to bound that, but does not add a setting for it — a fixed implementation constant.

## Auto Run Result

Status: done

**What was implemented.** The `Tracer` port (`create_run_trace`, `step_span`, `attempt_span`,
`attempt_observed`, `trace_url`) and its real adapter, `LangfuseTracer`, verified live
against the real `langfuse==4.15.1` package (not previously an actual dependency — only an
import-linter `forbidden_modules` entry — this story added it for real). `create_run` opens
one deterministic trace per Run (`trace_id = Langfuse.create_trace_id(seed=str(run_id))`)
and stores `run.trace_id`; the root observation carries `session_id`/`user_id` (both
`run_id`), tags `run:{id}`/`project:{slug}`, and name `run {template}@{v} {branch}` via the
SDK's public `propagate_attributes`. `walk.run_row` wraps every row's execution in
`tracer.step_span(run, row, attempt)`, itself carrying `run_id`/`path`/`kind`/`attempt`
metadata. `attempt_span` (child of the open `step_span`, carrying `attempt_id`/`harness`/
`model`/`story_id`) and `attempt_observed` are provided as port + adapter + fake but called
by no production code yet — 5.4 and 5.8 wire them. `cost.trace_url` in the Run detail read
model now formats a real Langfuse UI link from `Settings.langfuse_project_id` (new setting)
whenever a Run has a `trace_id` and a `Tracer` is wired. Every port field that carries a
`Tracer` (`StepPorts.tracer`, `CreateRunPorts.tracer`, `RunViewPorts.tracer`) is optional
and defaults to `None`, degrading to "no span/no trace/no URL" — never raising — for every
frozen unit-test construction that predates this story. Tracing is a genuine side channel
(SM-3): every adapter method catches an SDK-level failure, logs it, and degrades rather than
propagating — a row's own exception is still always re-raised untouched.

**Files changed (12 added, 11 modified):**
- `backend-api/src/orchestrator/domain/ports/tracer.py` — added: `TraceRef`, `SpanRef`, the
  `Tracer` protocol.
- `backend-api/src/orchestrator/infrastructure/tracing/__init__.py`,
  `infrastructure/tracing/langfuse_tracer.py` — added: `LangfuseTracer`, the real adapter.
- `backend-api/tests/unit/fakes/tracer.py` — added: `FakeTracer`, the one fake for the port.
- `backend-api/tests/unit/test_tracer_port.py`, `test_langfuse_tracer.py`,
  `test_tracer_env_integration.py`, `test_api_providers_tracing.py`,
  `test_dbos_startup_tracing.py`, `application/test_create_run_tracing.py`,
  `application/test_run_views_tracing.py`, `application/test_walk_tracing.py` — added: the
  port's own tests, the real adapter's tests (verified against a real in-memory-exporter
  client and against SDK-failure stubs), the traceparent → `env_for` mechanism test, and the
  composition-root wiring tests (`api/providers.py`, `infrastructure/dbos/startup.py`).
- `backend-api/src/orchestrator/application/use_cases/walk.py` — modified: `run_row` wraps
  `execute(context)` in `tracer.step_span(...)`; `_context` takes the already-read `Run`.
- `backend-api/src/orchestrator/application/steps/context.py` — modified: `StepPorts.tracer`.
- `backend-api/src/orchestrator/application/use_cases/create_run.py` — modified:
  `CreateRunPorts.tracer`, trace opened at Run creation, `_trace_name`.
- `backend-api/src/orchestrator/application/use_cases/run_view_types.py`,
  `application/use_cases/run_views.py` — modified: `RunViewPorts.tracer`, `cost.trace_url`
  filled from the tracer.
- `backend-api/src/orchestrator/infrastructure/dbos/startup.py` — modified: `walker_deps`
  builds one `LangfuseTracer` for the whole process's walker.
- `backend-api/src/orchestrator/api/providers.py` — modified: `create_run_ports`/
  `run_view_ports` each build a `LangfuseTracer` per request (lazy client — see Design Notes
  on why `main.py`, untouched at 394/400 lines, has no room for a fourth `app.state`
  singleton).
- `backend-api/src/orchestrator/infrastructure/settings.py`, `.env.example` — modified:
  `LANGFUSE_PROJECT_ID` (AD-20: same change).
- `backend-api/pyproject.toml`, `backend-api/uv.lock` — modified: real `langfuse==4.15.1`
  dependency.

**Review findings:** 13 patched (2 high, 6 medium, 5 low), 0 deferred by this review pass
(the story's own 3 frontmatter `deferred` items were recorded during planning, not by
review), 9 rejected. No `intent_gap` and no `bad_spec`, so no repair loopback ran.

One correction mid-review: the implementation subagent's first attempt at the two
composition-root wiring-test findings edited the frozen, pre-existing
`backend-api/tests/unit/test_api_providers.py` directly (+41/−1) — an anchor violation
(root `AGENTS.md` hard rule 1). Caught before commit: `git checkout -- test_api_providers.py`
restored it byte-identical to `HEAD` (verified: empty diff), and the two tests moved into a
new file, `test_api_providers_tracing.py`, with the same coverage. No other pre-existing
test file was touched.

**Follow-up review recommended:** true. Two patched findings were `high` severity
(missing `session_id`/`user_id` on the root trace; `create_run`'s tracer call having no
exception isolation), which sets the flag on its own; the medium/low score was
`3 × 6 + 1 × 5 = 23`, also over the threshold.

**Verification performed:**
- `make lint` — exit 0. ruff check, ruff format --check, mypy --strict over `domain/` +
  `application/`, all four import-linter contracts KEPT (`langfuse` stays under
  `infrastructure/tracing/` only), env-contract check (31 settings fields / 37
  `.env.example` variables agree), `check_test_pairs` 156/156 paired, `gen:api --check` no
  drift, web-client lint (0 errors/warnings/hints, Prettier clean).
- `make test` — exit 0. 4269 backend unit tests passed, 1 skipped (up from 4195 before this
  story); `domain/` + `application/` at 100% branch coverage under `--fail-under=100`;
  web-client 973 passed.
- `make openapi` — exit 0. `contracts/openapi.json`/`web-client/src/api/schema.d.ts`
  regenerated with no diff (`cost.trace_url`'s shape was already `str | None`).
- `main.py` untouched: still exactly 394 lines (frozen 400-line cap).
- `git status --porcelain` after `git add`: only the files this section's own list names.
- Matrix audit: all 8 I/O matrix rows are covered by named tests that ran and passed,
  including the real adapter's "unreachable endpoint never raises" row
  (`test_an_unreachable_langfuse_never_raises_out_of_step_span`, verified live against a
  refused connection at plan time before being written as a regression test).

**Residual risks (the story's own recorded `deferred`):**
- Per-request `LangfuseTracer` construction in `create_run_ports`/`run_view_ports` builds a
  new `Langfuse` client (and, for `create_run_ports`, a new background export thread once a
  trace is actually opened) on every request that reaches it, never explicitly shut down —
  accepted for low request frequency; a shared `app.state` singleton needs room in `main.py`
  this story does not have (flagged, not silently solved by restructuring it).
- `attempt_observed`'s real-adapter query pages at most 100 observations per trace; a trace
  with more before the attempt's own span appears could under-report. Exercised for real
  only in 5.8.
- `EXPORT_TIMEOUT_SECONDS` (2s, shorter than the SDK's own 10s default) is a fixed
  implementation constant, not a setting — bounds `flush()`'s worst-case blocking latency
  against an unreachable Langfuse but is not operator-tunable.
