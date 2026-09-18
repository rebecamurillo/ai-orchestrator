---
title: 'Probe gates create_run and pre-flight; model enforced server-side'
type: 'feature'
created: '2026-09-16'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['multiple-goals', 'oversized']
deferred: []
baseline_revision: '2b74b7426849a2fbf0651e2f859f37e85afa9d93'
---

<intent-contract>

## Intent

**Problem:** `create_run` and pre-flight's harness line both gate on the stored `enabled` flag (set only after a readiness Run passes), meaning a correctly-installed harness that has never run readiness is rejected, and a model supplied by the caller is never validated against the harness's actual model list.

**Approach:** Replace `enabled`-based gating with live probe calls in both paths: add `harness_probe_line()` to pre-flight (using the existing `probe()` port from story 2-1); have `create_run` run the probe once and reject any model not in the returned list with 422; remove the readiness-Run exemption (`skip_harness_check=True`) so readiness Runs are subject to the same probe as every other create.

## Boundaries & Constraints

**Always:**
- `harness_line()` (`checks.py:242`) is a frozen anchor — leave it untouched; it is replaced in production by the new `harness_probe_line()` called from `_lines()`, not deleted.
- The `Invalid` domain error (`domain/errors.py:33`) already maps to HTTP 422 — use it for model-not-in-list rejection; do not add a new error class.
- `harness_registry: dict[str, HarnessAdapter]` on `PreflightPorts` and `Context` must default to an empty dict so every existing frozen `PreflightPorts(...)` construction (test harnesses, existing providers) keeps compiling without change.
- `skip_harness_check` field stays on `CreateRunPorts`; only `readiness_ports` in `providers.py` stops setting it to `True` — the field is reserved for epic 5.
- `FakeHarness` in `tests/unit/fakes/harness.py` already has `probe()` (story 2-1) — use it in new tests; do not create a second Harness fake.
- TDD: new test files must exist and fail before their implementation lands.
- No model validation when `req.harness` is None, `probe.models` is empty (gateway-disabled mode), or `req.model` is None.

**Block If:**
- The `probe()` call in any adapter raises an unexpected exception type not handled by the existing story-2-1 wrapper (`run_probe_script`) — i.e., a new failure mode surfaces that neither `Conflict` nor 500 captures cleanly.

**Never:**
- Read `harness.enabled` in `harness_probe_line()` or in `create_run`'s new probe block.
- Add a new domain exception class — `Invalid` already maps to 422.
- Call `harness_probe_line()` from test code that tests `harness_line()` — they are separate functions.
- Re-run pre-flight a second time inside `create_run` — reuse `ports.preflight.harness_registry` to call probe directly after `_refuse_failing_lines`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Probe ok, model in list | `harness="claude"`, `model="gpt-4o"`, probe returns `ok=True, models=["gpt-4o"]` | Run created, status `queued` | No error |
| Probe ok, model not in list | `harness="claude"`, `model="bad-model"`, probe returns `ok=True, models=["gpt-4o","claude-3"]` | 422 `application/problem+json` naming list | `Invalid("model 'bad-model' not in probed list: ['gpt-4o', 'claude-3']")` |
| Probe fail at create_run | `harness="claude"`, probe returns `ok=False, failing_reason="gateway unreachable"` | 409 Conflict with reason | `Conflict("gateway unreachable")` |
| Gateway disabled (empty models) | `harness="claude"`, `model="any"`, probe returns `ok=True, models=[]` | Run created, no model validation | No error — empty list is not a probe failure (Design Note) |
| No model supplied | `harness="claude"`, `model=None` | Run created, probe passes ok-gate only | No model validation |
| No harness | `harness=None` | Run created (harness_probe_line skips, no probe in create_run) | No error |
| Harness not in registry | `harness="unknown"`, registry has no "unknown" | pre-flight line `fail` "harness not available"; create_run raises `Conflict` | 409 |
| Readiness Run (no exemption) | readiness_ports wiring, probe ok | Run created (probe replaces skip_harness_check bypass) | No error |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/application/preflight/checks.py:70-88` -- `Context` frozen dataclass; add `harness_registry: dict[str, HarnessAdapter] = field(default_factory=dict)` (import `Harness as HarnessAdapter` from `domain.ports.harness`; name collision with existing `domain.entities.harness.Harness` import)
- `backend-api/src/orchestrator/application/preflight/checks.py:242-258` -- `harness_line()` READ-ONLY anchor; this function is kept unchanged; its tests (`test_checks.py:479–516`) remain valid; `_lines()` in `preflight.py` is what switches to `harness_probe_line()` — not this function
- `backend-api/src/orchestrator/application/preflight/checks.py:39` -- existing `from orchestrator.domain.entities.harness import Harness`; add aliased import `from orchestrator.domain.ports.harness import Harness as HarnessAdapter` and `ProbeResult` below it (after existing imports)
- `backend-api/src/orchestrator/application/use_cases/preflight.py:42-49` -- `PreflightPorts` frozen dataclass; add `harness_registry: dict[str, HarnessAdapter] = field(default_factory=dict)` as last field; add aliased import
- `backend-api/src/orchestrator/application/use_cases/preflight.py:92-104` -- `Context(...)` construction in `preflight_and_plan`; add `harness_registry=ports.harness_registry`
- `backend-api/src/orchestrator/application/use_cases/preflight.py:148` -- `_lines()` calls `checks.harness_line(ctx)` here; change to `checks.harness_probe_line(ctx)`
- `backend-api/src/orchestrator/application/use_cases/create_run.py:129-135` -- `create_run()` function; after `_refuse_failing_lines(...)` (line 135), insert probe+model-validation block using `ports.preflight.harness_registry`
- `backend-api/src/orchestrator/domain/errors.py:33-35` -- `Invalid` READ-ONLY reference; already maps to HTTP 422 via `api/errors.py:63`
- `backend-api/src/orchestrator/api/providers.py:152-166` -- `_preflight_ports()`; add `harness_registry=build_harnesses(settings, RealProcessRunner())` to `PreflightPorts(...)` construction; `build_harnesses` and `RealProcessRunner` are already imported (see `harness_probe_ports` at line 128)
- `backend-api/src/orchestrator/api/providers.py:199-221` -- `readiness_ports()`; remove `skip_harness_check=True` from inner `CreateRunPorts`; add `skip_harness_check` field docstring update (was: readiness exemption; now: reserved for epic 5)
- `backend-api/src/orchestrator/domain/ports/harness.py` -- READ-ONLY reference; `ProbeResult` dataclass and `Harness` protocol with `probe() → ProbeResult` (story 2-1)
- `backend-api/tests/unit/fakes/harness.py` -- READ-ONLY; `FakeHarness` already has `probe_results` queue and `probe()` (story 2-1)
- `backend-api/tests/unit/application/preflight/test_checks.py:479-516` -- READ-ONLY anchor; tests `harness_line()` directly, which is kept unchanged; passes after this story
- `backend-api/tests/unit/application/test_create_run_use_case.py:313-321` -- READ-ONLY anchor; `skip_harness_check=True` test uses epic template with no agent step → `harness_probe_line()` returns skip → still passes

## Tasks & Acceptance

**Execution:**

Tests first — these must exist and fail before implementation:

- `backend-api/tests/unit/application/preflight/test_harness_probe_line.py` -- create -- `harness_probe_line()` unit tests: (1) skip when `req.harness=None`; (2) skip when `repository=None`; (3) skip when tree has no agent step; (4) ok Line when probe returns `ok=True` — text must not say "enabled"; (5) fail Line with `failing_reason` text when probe returns `ok=False`; (6) fail Line "harness not available" when name not in `ctx.harness_registry`; use `FakeHarness` from `tests/unit/fakes/harness.py` loaded via `harness_registry={"claude": FakeHarness(...)}`
- `backend-api/tests/unit/application/test_create_run_probe_gate.py` -- create -- `create_run` probe gate tests: (1) model in probe list → `run.status == "queued"`; (2) model not in non-empty probe list → raises `Invalid` containing both the model name and the list; (3) probe fail at create → raises `Conflict` with `failing_reason`; (4) `req.model=None` with non-empty probe list → `run.status == "queued"` (no model validation); (5) probe `ok=True, models=[]` with `req.model="any"` → `run.status == "queued"` (no validation on empty list); (6) readiness_ports wiring with `skip_harness_check` not set to True and probe ok → run created (verifies exemption removed); use a template fixture with an agent step so the harness line actually evaluates

Implementation (in order):

- `backend-api/src/orchestrator/application/preflight/checks.py` -- add `field` to `from dataclasses import dataclass` (→ `from dataclasses import dataclass, field`); add `from orchestrator.domain.ports.harness import Harness as HarnessAdapter` import; add `harness_registry: dict[str, HarnessAdapter] = field(default_factory=dict)` to `Context` after `plan_error`; add `harness_probe_line(ctx: Context) -> Line` after `harness_line()` with same skip guards (name None→skip, repository None→skip, no agent step→skip) then `adapter = ctx.harness_registry.get(name)` → if None: `Line(CHECK_HARNESS, "fail", "harness not available")`; else `result = adapter.probe()` → if not ok: `Line(CHECK_HARNESS, "fail", result.failing_reason or "probe failed")` → else `Line(CHECK_HARNESS, "ok", f"probe ok · {result.version}")`
- `backend-api/src/orchestrator/application/use_cases/preflight.py` -- add `from orchestrator.domain.ports.harness import Harness as HarnessAdapter` import; add `harness_registry: dict[str, HarnessAdapter] = field(default_factory=dict)` to `PreflightPorts`; thread `harness_registry=ports.harness_registry` into `Context(...)` construction; replace `checks.harness_line(ctx)` with `checks.harness_probe_line(ctx)` in `_lines()`
- `backend-api/src/orchestrator/application/use_cases/create_run.py` -- add `from orchestrator.domain.errors import Invalid` import (alongside existing `Conflict, NotFound`); after `_refuse_failing_lines(...)` at line 135, insert: if `req.harness` and `(adapter := ports.preflight.harness_registry.get(req.harness))` is not None: `probe_result = adapter.probe()`; if not `probe_result.ok`: raise `Conflict(probe_result.failing_reason or "probe failed")`; if `req.model` and `probe_result.models` and `req.model not in probe_result.models`: raise `Invalid(f"model {req.model!r} not in probed list: {list(probe_result.models)}")`
- `backend-api/src/orchestrator/api/providers.py` -- in `_preflight_ports()`: add `harness_registry=build_harnesses(settings, RealProcessRunner())` to `PreflightPorts(...)` construction; in `readiness_ports()`: remove `skip_harness_check=True` from inner `CreateRunPorts`; update docstring to note the enabled-exemption is removed (story 2-2, 2026-09-16)
- `make openapi` -- run after all above; commit `contracts/openapi.json` and `web-client/src/api/schema.d.ts` if regeneration reports drift (PreflightPorts internals do not change the API schema, but run to confirm)

**Acceptance Criteria:**

- Given `harness="claude"` and `model="gpt-4o"` and probe returns `ok=True, models=["gpt-4o"]`, when `POST /runs`, then HTTP 201 with `run.status="queued"`
- Given `harness="claude"` and `model="bad-model"` and probe returns `ok=True, models=["gpt-4o","claude-3"]`, when `POST /runs`, then HTTP 422 `application/problem+json` whose `errors[0].reason` names `"bad-model"` and the probed list
- Given `harness="claude"` and probe returns `ok=False, failing_reason="gateway unreachable"`, when `POST /runs`, then HTTP 409 with `failing_reason` text in the body
- Given `model=None` and probe returns `ok=True, models=["gpt-4o"]`, when `POST /runs`, then HTTP 201 (no model validation when model omitted)
- Given `harness="claude"` and probe returns `ok=True, models=[]` (gateway disabled), when `POST /runs` with any model, then HTTP 201 (empty list is not a probe failure)
- Given a readiness Run request and probe returns ok for the harness, when `POST /harnesses/{name}/readiness`, then HTTP 201 and the enabled-exemption (`skip_harness_check=True`) is not applied
- Given any pre-flight request with `harness="claude"` and probe returns `ok=True`, when `POST /runs/preflight`, then the harness line has `status="ok"` and its text does NOT contain the word "enabled"
- Given any pre-flight request with `harness="claude"` and probe returns `ok=False, failing_reason="cli not at pinned version 1.2.3"`, when `POST /runs/preflight`, then the harness line has `status="fail"` and `text` contains `"cli not at pinned version 1.2.3"`
- Given `make lint` runs, then import-linter reports no AD-2 violation (no subprocess/os/shutil in domain or application)

## Auto Run Result

Status: blocked

Blocking condition: anchor test conflict — two existing read-only test files pin behavior that story 2-2 explicitly replaces; Operator exception-4 authorization is required to revise their assertions.

### Conflict 1

**Test:** `backend-api/tests/unit/application/test_preflight_use_case.py::test_ac3_harness_disabled`

**What it asserts:** given a `Harness(name="claude", enabled=False)` in the DB, `run_preflight()` returns `Line(CHECK_HARNESS, "fail", "disabled: no readiness run", "re-run readiness on this screen")`.

**What story 2-2 requires:** `_lines()` in `preflight.py` now calls `harness_probe_line()` (not `harness_line()`). `harness_probe_line()` reads `ctx.harness_registry` (the adapter map) not the DB entity's `enabled` flag. With an empty registry (as this test provides — no `harness_registry` in `PreflightPorts`), the line becomes `Line(CHECK_HARNESS, "fail", "harness not available")`. The text `"disabled: no readiness run"` and the `fix` string `"re-run readiness on this screen"` can never be produced by `harness_probe_line()`.

**Why it cannot be papered over:** making `harness_probe_line()` fall back to reading `enabled` when the registry is empty would violate the story's invariant ("enabled flag is read by neither pre-flight nor create_run"). Returning `skip` when the registry is empty would change the line status from `fail` to `skip`, still failing the assertion.

**Required authorization:** Operator exception 4 — revise `test_ac3_harness_disabled` to assert the new probe-based behavior (probe returns `ok=False, failing_reason="..."` → `Line(CHECK_HARNESS, "fail", failing_reason)`); add a test that exceeds the old coverage by asserting the probe call is made.

---

### Conflict 2

**Test:** `backend-api/tests/unit/application/test_repository_init_harness.py::test_a_named_harness_reaches_the_runs_inputs`

**What it asserts:** `init_repository` (which calls `create_run`) succeeds and stores `inputs["harness"] == "fake"` when `FakeHarnessRepository` contains `Harness(name="fake", enabled=True, ...)`.

**What story 2-2 requires:** `create_run` calls `preflight_and_plan` which now calls `harness_probe_line()`. The `repo-init` template has an agent step, so the harness probe is evaluated. The test's `PreflightPorts` carries `harness_registry={}` (default empty dict). `harness_probe_line()` finds no adapter for "fake" and returns `Line(CHECK_HARNESS, "fail", "harness not available")`. `_refuse_failing_lines` then raises `Conflict: harness not available` before the run is persisted. The test fails at `world.init("fake")`.

**Why it cannot be papered over:** skipping the probe when the adapter is absent would allow the test to pass, but then any invalid harness name in production would silently skip the probe check rather than failing it. The test file's own docstring says "the named one must be enabled here" — it was explicitly written for the old `enabled` semantics.

**Required authorization:** Operator exception 4 — revise `test_repository_init_harness.py` to provide a `harness_registry={"fake": FakeHarness(probe_results=[ProbeResult(ok=True, ...)])}` in `PreflightPorts`, and assert that the run is created when the probe passes; update the docstring to replace the `enabled` reference with probe semantics (decision: story 2-2, 2026-09-16).

---

### Implementation state

All implementation changes are in the working tree (not committed). `make lint` passes. `make test` has 2 failures (the two anchor conflicts above); all other 6342 tests pass. The implementation is structurally correct for the story's intent — only the anchor test assertions stand in the way.

## Spec Change Log

## Review Triage Log

## Design Notes

**Why `harness_line()` is kept:** Existing tests in `test_checks.py` call `harness_line()` directly and pin the `enabled`-based behavior. Those tests are anchors (read-only). Rather than triggering exception (b), `harness_line()` is left in place (still compiles and passes its tests) while `_lines()` is redirected to `harness_probe_line()`. Dead code once story 2-2 lands; a future cleanup story may remove it with operator authorization.

**Gateway-disabled (empty models):** When `litellm_enabled` is false, `probe()` returns `ok=True, models=[]`. `create_run`'s model-validation block guards on `probe_result.models` being non-empty before evaluating membership — so any model is accepted in gateway-disabled mode. This mirrors story 2-1's `FakeHarness.probe()` returning `models=["fake-model"]` for test environments.

**Two probe calls (pre-flight + create_run):** `harness_probe_line()` in pre-flight calls probe to determine ok/fail. `create_run` calls probe a second time to retrieve the models list for model validation — the Line object does not carry the ProbeResult, so a second call is necessary. This is the behavior the story spec requires ("create_run re-runs the Probe inline once at create").

**Readiness exemption removal:** The `skip_harness_check=True` flag in `readiness_ports` bypassed the old `harness.enabled` fail line so an un-enabled harness could still run its own readiness Run. With `harness_probe_line()` replacing the enabled check, a correctly-installed harness returns `ok=True` from the probe regardless of `enabled`. The exemption is therefore both wrong (it would now bypass the probe, not the enabled check) and unnecessary (the probe passes for a fresh install). `skip_harness_check` remains on `CreateRunPorts` for epic 5's use.

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy, import-linter all pass; no AD-2 violation
- `make test` -- expected: all unit tests green including new probe-gate test files
- `make openapi` -- expected: no drift reported by `pnpm gen:api --check`

## Human Answer

2026-09-17T04:24:52.746806Z · operator

exception-4 authorized: revise test_ac3_harness_disabled (test_preflight_use_case.py) and test_a_named_harness_reaches_the_runs_inputs (test_repository_init_harness.py) to assert the probe-based semantics as proposed; name this decision and 2026-09-16 in the revised tests.
