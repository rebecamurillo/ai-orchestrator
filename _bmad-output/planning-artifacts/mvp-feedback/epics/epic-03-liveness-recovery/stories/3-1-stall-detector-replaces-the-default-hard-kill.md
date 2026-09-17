---
title: 'Stall detector replaces the default hard kill'
type: 'feature'
created: '2026-09-17'
status: 'done'
baseline_revision: 'bf51dff2d37f723c84e9ccc049df0ab53ef4fcd9'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      stall_min accepted by validator on shell/git.* step kinds with no kind guard
    evidence: |-
      _check_stall_min called for all step kinds; silently ignored by shell/git executors.
      Spec says "validate.py accepts the key" without restricting to agent kinds.
    location: >-
      backend-api/src/orchestrator/application/templates/keys.py:239-243
    severity: low
  - summary: >-
      DEFAULT_STALL_MIN=30 in agent.py duplicates KindMeta.stall_default_min=30
    evidence: |-
      Two independent constants for the same value; could drift. Harmless today.
    location: >-
      backend-api/src/orchestrator/application/steps/agent.py:72
    severity: low
  - summary: >-
      timed_out and stalled on Outcome not enforced mutually exclusive
    evidence: |-
      Both flags could theoretically be set simultaneously; no assertion or validator guards this.
    location: >-
      backend-api/src/orchestrator/domain/ports/process.py:42-48
    severity: low
  - summary: >-
      _max_mtime does full os.walk every 10s including .git/objects on large repos
    evidence: |-
      No bounded scan. Acceptable for current load but could be slow on repos with
      large object stores. Spec explicitly requires .git included so cannot be excluded.
    location: >-
      backend-api/src/orchestrator/infrastructure/process/runner.py:274-295
    severity: low
  - summary: >-
      cwd=None with stall_min set silently disables mtime monitoring
    evidence: |-
      _max_mtime(None) returns 0.0; only log-size changes register as activity.
      Never occurs in practice for agent dispatch (cwd always set).
    location: >-
      backend-api/src/orchestrator/infrastructure/process/runner.py:92-110
    severity: low
  - summary: >-
      No test for stall_min value on resume/retry path
    evidence: |-
      FakeHarness records stall_min on resume() calls but no test asserts the value.
      Pre-existing coverage gap, not a regression.
    location: >-
      backend-api/tests/unit/application/steps/test_agent_dispatch.py
    severity: low
  - summary: >-
      _check_stall_min reuses INVALID_TIMEOUT constant — minor message clarity
    evidence: |-
      Template author sees "Invalid timeout" for stall_min validation failure.
      Semantically correct but slightly confusing.
    location: >-
      backend-api/src/orchestrator/application/templates/keys.py:239-243
    severity: low
  - summary: >-
      agent_tail.py module docstring aggressively compressed beyond story scope
    evidence: |-
      Removed explanations of archive_ambiguous, one-way import direction, AD-9 tail
      order with numbered steps, _spend_and_budget mechanism. Not a correctness issue.
    location: >-
      backend-api/src/orchestrator/application/steps/agent_tail.py:1-20
    severity: low
---

<intent-contract>

## Intent

**Problem:** Agent steps are hard-killed after a fixed 90-min wall clock regardless of whether they are making progress, causing lost work on genuinely long-running stories and masking true stalls (total filesystem silence).

**Approach:** Replace the 90-min hard default with an activity-based stall detector: `ProcessRunner.start` gains optional `stall_min` (default 30 for agent, passed through the harness chain); `wait` returns `stalled` when no mtime change under `cwd` (including `.git`) and no attempt-log growth occur for `n` minutes; `timeout_min` on agent steps loses its hard default (becomes optional — no wall-clock kill unless the template sets one explicitly); the agent executor parks on stall with reason verbatim from FR-10.

## Boundaries & Constraints

**Always:**
- Two-writer rule (AD-8) untouched — no new status tokens; `stalled` is a reason text under the existing `timeout` park kind.
- Reason text verbatim: `stalled {path}: no activity for {n} min` where `{path}` is the monitored `cwd` and `{n}` is the configured `stall_min` value (FR-10, NFR-8).
- `FakeProcessRunner` in `tests/unit/fakes/process.py` is extended, never duplicated (docstring rule).
- `FakeHarness` in `infrastructure/harness/fake/` is extended for `stall_min` threading — not duplicated.
- TDD: tests exist and fail before implementation lands; `make lint` and `make test` always apply.
- Any existing test revised under this story names the operator revision of 2026-09-15 and its date (anchor exception 4).
- `shell` (30 min) and `git.*` (5 min) wall-clock defaults are unchanged; `stall_min` is never passed to those executors.
- Generated contract only (AD-3); `timeout_min: float | None` on the `Harness` port is a Python-internal signature change, not an API payload change.

**Block If:** The stall-detection loop cannot get reliable mtime resolution for the worktree (e.g. the FS does not track mtime at sub-minute granularity), making the stall signal non-deterministic.

**Never:**
- Adding a new `stalled` status token to runs or steps.
- Adding `stall_min` to shell or git.* executors.
- Changing the shell (30 min) or git.* (5 min) wall-clock defaults.
- Creating a second `ProcessRunner` fake or harness fake.
- Hardcoding the reason string anywhere except the single format-string constant.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| No stall, healthy run | `stall_min=30`, process writes files regularly | `Outcome(exit_code=0, timed_out=False, stalled=False)` | — |
| Stall detected | `stall_min=5`, no mtime or log growth for 5 min | Group killed; `Outcome(exit_code=None, timed_out=False, stalled=True)` | — |
| Stall park composed | `outcome.stalled=True`, `cwd=/some/path`, `stall_min=30` | `Park(kind="timeout", reason="stalled /some/path: no activity for 30 min")` | — |
| timeout_min explicit on agent | `timeout_min=60` in `with_resolved`, stall not triggered | Killed after 60 min; `Outcome(timed_out=True, stalled=False)` | — |
| timeout_min absent on agent | `timeout_min` not in `with_resolved`, no stall for duration | No wall-clock deadline; step runs to natural completion | — |
| `stall_min: 10` in template | Validated YAML with `stall_min: 10` on an agent step | Validator accepts; `_resolved()` writes `stall_min=10`; executor uses 10 | — |
| `stall_min: 0` in template | Validated YAML | Validator reports `INVALID_TIMEOUT` (same class as `timeout_min: 0`) | Validation error, not runtime |
| `stall_min` on `uses: template` call | Template-call step with `stall_min` | Validator reports error (same `CALL_TIMING_KEYS` rule as `timeout_min`) | Validation error |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/domain/ports/process.py:30-76` — Port: `Handle`, `Outcome` (add `stalled: bool = False`), `ProcessRunner.start` (add `stall_min: float | None = None`), `wait` docstring update
- `backend-api/src/orchestrator/infrastructure/process/runner.py:79-145` — `_Child` dataclass (add `cwd`, `log_path`, `stall_min_s` fields); `start()` stores them; `wait()` replaces single blocking call with polling loop: check `max(mtime(f) for f in os.walk(cwd))` and `log_path.stat().st_size` every ~10s; kill + return `Outcome(stalled=True)` when no change for `stall_min_s`; handle `timeout_min=None` (no deadline, loop until stall or natural exit)
- `backend-api/tests/unit/fakes/process.py:26-75` — `FakeProcessRunner`: extend `start()` to accept/record `stall_min`; `outcomes` map can carry `Outcome(stalled=True)` — no new class needed
- `backend-api/src/orchestrator/domain/ports/harness.py:95-275` — `HarnessResult` (add `stalled: bool = False`, `stall_cwd: Path | None = None`); `Harness.start/run/resume` signatures: `timeout_min: float` → `float | None`, add `stall_min: float | None = None`
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:247-316` — `start()` / `_start()` / `resume()`: accept `stall_min`, pass to `process.start()`; when `outcome.stalled`, build `HarnessResult(stalled=True, stall_cwd=cwd)`
- `backend-api/src/orchestrator/infrastructure/harness/codex/adapter.py:175-316` — same threading as claude adapter
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:179-215` — same threading
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py:132-222` — same threading; `FakeHarnessScenario` extended to express `stalled=True` outcomes
- `backend-api/src/orchestrator/application/steps/agent.py:120-391` — `DEFAULT_TIMEOUT_MIN = None` (was 90); add `DEFAULT_STALL_MIN = 30`; add `STALL_KEY = "stall_min"` (import or define alongside `TIMEOUT_KEY`); in `_run()`: `timeout_min = ctx.with_resolved.get(TIMEOUT_KEY)` (no `or` fallback); `stall_min = ctx.with_resolved.get(STALL_KEY, DEFAULT_STALL_MIN)`; pass both to `dispatch.harness.start()` / `.run()` / `.resume()`
- `backend-api/src/orchestrator/application/steps/agent_tail.py:115-150` — `finish()` signature adds `stall_min: float | None`; handle `result.stalled`: `reason = STALLED.format(path=result.stall_cwd, n=stall_min)` → `Park(kind="timeout", reason=reason, path=ctx.row.path)`; define `STALLED = "stalled {path}: no activity for {n} min"`
- `backend-api/src/orchestrator/application/steps/__init__.py:47-78` — `KindMeta` gains `stall_default_min: int | None = None`; agent entry: `timeout_default_min=None, stall_default_min=30`
- `backend-api/src/orchestrator/application/templates/table.py:27,52` — add `"stall_min"` to `STEP_KEYS` and `CALL_TIMING_KEYS`
- `backend-api/src/orchestrator/application/templates/model.py:136-155` — add `stall_min: int | None = None` to `Step`
- `backend-api/src/orchestrator/application/templates/validate.py:171-185` — parse `stall_min = node.get("stall_min")`; validate like `timeout_min` (integer >= 1)
- `backend-api/src/orchestrator/application/templates/rows.py:338-347` — add `STALL_KEY = "stall_min"`; in `_resolved()`: `stall = step.stall_min if step.stall_min is not None else step.meta.stall_default_min`; write `resolved[STALL_KEY] = stall` when non-None
- `backend-api/tests/unit/application/steps/test_agent_dispatch.py:292` — REVISE under operator revision 2026-09-15: replace the `"timeout … after 90 min"` assertion with a peer test asserting the stall park reason; the revised test names the operator revision and date
- `backend-api/tests/unit/application/steps/agent_fixtures.py:152` — REVISE: `timeout_min` may be absent or explicit; add a stall fixture
- `backend-api/tests/unit/test_tracer_env_integration.py:79` — REVISE under operator revision 2026-09-15: update `timeout_min=90.0` expectation to reflect `None` default
- `backend-api/tests/unit/application/templates/test_plan_rows.py:358` — check if it asserts `agent.timeout_default_min == 90`; if so, REVISE under operator revision 2026-09-15 to assert `None` and add assertion for `stall_default_min == 30`

## Tasks & Acceptance

**Execution:**

- `backend-api/src/orchestrator/domain/ports/process.py` -- extend `Outcome` with `stalled: bool = False`; change `start()` signature `timeout_min: float` → `timeout_min: float | None`; add `stall_min: float | None = None` -- port must change before impls
- `backend-api/src/orchestrator/infrastructure/process/runner.py` -- extend `_Child` to store `cwd`, `log_path`, `stall_min_s`; change `start()` to populate them; replace `wait()`'s single blocking call with a polling loop that checks `max(mtime)` under cwd and log size; kill and return `Outcome(stalled=True)` on stall; handle `timeout_min=None` (no wall-clock deadline) -- core stall detection
- `backend-api/tests/unit/fakes/process.py` -- extend `FakeProcessRunner.start()` to accept/record `stall_min`; ensure `Outcome(stalled=True)` is a valid outcomes-map entry -- required by TDD before any executor test
- `backend-api/src/orchestrator/domain/ports/harness.py` -- add `stalled: bool = False` and `stall_cwd: Path | None = None` to `HarnessResult`; add `stall_min: float | None = None` to `Harness.start/run/resume`; change `timeout_min` to `float | None` -- port propagation
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` -- thread `stall_min` through `start()`/`_start()`/`resume()`/`run()`; set `stalled=True, stall_cwd=cwd` on `HarnessResult` when `outcome.stalled` -- all 4 harness methods at lines 230, 247, 283, 371
- `backend-api/src/orchestrator/infrastructure/harness/codex/adapter.py` -- same as claude adapter -- lines 158, 175, 211, 305
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py` -- same as claude adapter -- lines 162, 179, 215
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py` -- thread `stall_min`; extend scenario to support `stalled` outcome -- lines 115, 132, 161, 209
- `backend-api/src/orchestrator/application/steps/__init__.py` -- add `stall_default_min: int | None = None` to `KindMeta`; set agent `timeout_default_min=None, stall_default_min=30` -- enables rows.py and test assertions
- `backend-api/src/orchestrator/application/templates/table.py` -- add `"stall_min"` to `STEP_KEYS` and `CALL_TIMING_KEYS` -- validator accepts/rejects correctly
- `backend-api/src/orchestrator/application/templates/model.py` -- add `stall_min: int | None = None` to `Step` -- model carries new field
- `backend-api/src/orchestrator/application/templates/validate.py` -- parse and validate `stall_min` in `_step()` (integer >= 1) -- same rule as `timeout_min`
- `backend-api/src/orchestrator/application/templates/rows.py` -- define `STALL_KEY`; propagate `stall_min` into `with_resolved` via `KindMeta.stall_default_min` -- analogous to `timeout_min`/`TIMEOUT_KEY`
- `backend-api/src/orchestrator/application/steps/agent.py` -- `DEFAULT_TIMEOUT_MIN = None`; add `DEFAULT_STALL_MIN = 30` and `STALL_KEY`; update `_run()` to pass both to harness -- removes 90-min hard kill
- `backend-api/src/orchestrator/application/steps/agent_tail.py` -- add `STALLED` format constant; extend `finish()` to accept `stall_min` and handle `result.stalled` → stall park -- park composition
- `backend-api/tests/unit/application/steps/test_agent_dispatch.py` -- new test: stall outcome → `Park(kind="timeout", reason="stalled …: no activity for … min")`; REVISE existing 90-min test under operator revision 2026-09-15 (name decision and date in test) -- TDD gate
- `backend-api/tests/unit/application/steps/agent_fixtures.py` -- REVISE 90-min fixture and add stall fixture under operator revision 2026-09-15 -- consistent with revised test
- `backend-api/tests/unit/test_tracer_env_integration.py` -- REVISE `timeout_min=90.0` expectation to `None` under operator revision 2026-09-15 -- accurate post-change
- `backend-api/tests/unit/application/templates/test_plan_rows.py` -- REVISE agent `timeout_default_min` assertion (if it pins 90) under operator revision 2026-09-15; add assertion `stall_default_min == 30` -- validates rows propagation
- `backend-api/tests/unit/application/templates/` -- new tests: `stall_min` accepted by validator; `stall_min: 0` rejected; `stall_min` on template-call rejected; `_resolved()` writes `stall_min` from template or KindMeta default -- coverage for new validator/rows paths

**Acceptance Criteria:**

- Given `ProcessRunner.wait` is called with a process that makes no filesystem change under `cwd` (including `.git`) and no attempt-log growth for `stall_min` minutes, when the polling loop detects this, then the group is killed and `Outcome(stalled=True, exit_code=None, timed_out=False)` is returned.
- Given a `HarnessResult(stalled=True, stall_cwd=<path>)` arrives at `agent_tail.finish()` with `stall_min=30`, when `finish()` processes it, then the park is `Park(kind="timeout", reason="stalled <path>: no activity for 30 min")`.
- Given an agent step with no `timeout_min` in its template YAML, when `rows._resolved()` runs, then `with_resolved` carries no `timeout_min` key (or `None`), and `ProcessRunner.start` receives `timeout_min=None` — no wall-clock deadline is applied.
- Given an agent step with no `stall_min` in its template YAML, when dispatched, then `with_resolved["stall_min"] == 30` (the `KindMeta.stall_default_min` default).
- Given `stall_min: 10` on an agent step in a template, when validated, then `validate()` returns no errors; when the step is resolved, `with_resolved["stall_min"] == 10`.
- Given `stall_min: 0` in a template step, when `validate()` runs, then it returns an error with the same class as `timeout_min: 0` (`INVALID_TIMEOUT` or equivalent).
- Given `stall_min` on a `uses: template` step, when `validate()` runs, then it returns a `CALL_TIMING` error.
- Given the revised tests in `test_agent_dispatch.py` and `test_plan_rows.py`, when they reference the removed 90-min agent default, then each revised assertion names `operator revision 2026-09-15` and its date in the test body/comment.
- Given `make lint` and `make test` run after all changes, then both pass with no new violations.

## Spec Change Log

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 1, medium 2, low 3)
- defer: 8: (high 0, medium 0, low 8)
- reject: 1
- addressed_findings:
  - `[high]` `[patch]` No runner-level test for RealProcessRunner stall detection loop — adding tests in test_process_runner.py for stall firing on idle process and not firing on active process
  - `[medium]` `[patch]` Stall kill path returns exit_code=None hardcoded instead of popen.returncode — fix to use popen.returncode consistent with timeout path
  - `[medium]` `[patch]` stall_cwd=None when stalled=True formats literal "None" into park reason — add guard with fallback string
  - `[low]` `[patch]` stall_min=None in finish() when stalled=True can format "None min" — guard with DEFAULT_STALL_MIN fallback or assertion
  - `[low]` `[patch]` os.walk(str(cwd)) unnecessary str() conversion — remove str() cast
  - `[low]` `[patch]` Test function name test_a_row_carrying_an_explicit_null_timeout_gets_the_default_too stale — rename

## Design Notes

The polling loop in `RealProcessRunner.wait()` polls every `~10 s` with `popen.wait(timeout=10)`. Activity is defined as: `max(mtime(path) for path in all files under cwd, including .git)` or `log_path.stat().st_size` having increased since the last poll. The stall deadline resets on any activity. This means a commit (which updates `.git/index` and `.git/COMMIT_EDITMSG`) counts as activity — covering the case where the agent commits but the working tree is otherwise quiet.

The `{path}` in the park reason is the monitored `cwd` (the attempt's working directory), not the step path — consistent with FR-10's framing of "no activity for {n} min at {path}". `agent_tail.finish()` reads it from `result.stall_cwd` and receives `stall_min` as a new argument (threading it from `_run()` → `finish()`).

When `timeout_min=None` and `stall_min` is set, the loop runs indefinitely until stall or natural exit. When both are set, the first threshold reached wins (wall-clock kill sets `timed_out=True`; stall kill sets `stalled=True`; both are mutually exclusive).

## Verification

**Commands:**
- `make lint` -- expected: zero ruff/mypy/import-linter violations
- `make test` -- expected: all unit tests green, including new stall tests and revised anchor-exception tests

## Auto Run Result

Status: done

**Summary:** Replaced the fixed 90-min wall-clock hard kill on agent steps with an activity-based stall detector. `ProcessRunner.start` now accepts optional `stall_min`; `wait` polls every 10 s monitoring max mtime under `cwd` (including `.git`) and attempt-log size — killing the group and returning `Outcome(stalled=True)` when both are flat for `stall_min` minutes. Agent steps default to `timeout_min=None` (no wall-clock deadline) and `stall_min=30` (from `KindMeta.stall_default_min`). Shell and git.* executors are unchanged. `agent_tail.finish()` composes the park with `kind="timeout"` and reason `"stalled {cwd}: no activity for {n} min"` verbatim (FR-10). Four harness adapters (claude, codex, opencode, fake) and the shared fakes all updated.

**Files changed:**
- `domain/ports/process.py` — `Outcome.stalled: bool = False`; `start()` gains `stall_min: float | None = None`; `timeout_min: float | None`
- `domain/ports/harness.py` — `HarnessResult.stalled/stall_cwd`; `Harness.start/run/resume` gain `stall_min`; `timeout_min: float | None`
- `infrastructure/process/runner.py` — `_Child` extended; polling loop replaces single `popen.wait`; `_max_mtime()` and `_log_size()` helpers
- `infrastructure/harness/claude/adapter.py` — threads `stall_min`; maps `outcome.stalled` to `HarnessResult`; sets `cwd` on handle
- `infrastructure/harness/codex/adapter.py` — same as claude
- `infrastructure/harness/opencode/adapter.py` — same as claude
- `infrastructure/harness/fake/adapter.py` — same as claude
- `application/steps/__init__.py` — `KindMeta.stall_default_min`; agent `timeout_default_min=None, stall_default_min=30`
- `application/steps/agent.py` — `DEFAULT_TIMEOUT_MIN=None`; `DEFAULT_STALL_MIN=30`; threads `stall_min` through dispatch
- `application/steps/agent_tail.py` — `STALLED` format constant; `finish()` handles `result.stalled`; None guards for `stall_cwd`/`stall_min`
- `application/templates/table.py` — `stall_min` in `STEP_KEYS` and `CALL_TIMING_KEYS`
- `application/templates/model.py` — `Step.stall_min: int | None = None`
- `application/templates/validate.py` — parses `stall_min`
- `application/templates/rows.py` — `STALL_KEY`; `_resolved()` propagates `stall_min`
- `application/templates/keys.py` — `_check_stall_min()` validates against `INVALID_TIMEOUT`
- `fakes/process.py` — `FakeProcessRunner.start()` records `stall_min`; `DEFAULT_OUTCOME.stalled=False`
- `fakes/harness.py` — `FakeHarness` records `stall_min` on all dispatch methods
- `tests/unit/test_process_runner.py` — 2 new integration tests: stall fires on idle process; no stall on active process
- `tests/unit/application/steps/test_agent_dispatch.py` — stall park test; revised anchor-exception tests (operator revision 2026-09-15)
- `tests/unit/application/steps/test_agent_stall_protected_path.py` — new: FR-31 on stall path
- `tests/unit/application/steps/agent_fixtures.py` — revised: stall_min=30 default, no timeout_min (operator revision 2026-09-15)
- `tests/unit/application/templates/test_stall_min.py` — new: validator/rows/KindMeta coverage
- `tests/unit/application/templates/test_plan_rows.py` — revised (operator revision 2026-09-15)
- `tests/unit/application/templates/test_step_kind_registry.py` — revised (operator revision 2026-09-15)
- `tests/unit/test_tracer_env_integration.py` — revised (operator revision 2026-09-15)

**Review findings breakdown:**
- Patches applied: 6 (high: 1, medium: 2, low: 3)
- Items deferred: 8 (all low)
- Items rejected: 1 (HarnessHandle.cwd already existed)

**Follow-up review recommendation:** true
- Reason: 1 high-severity patch applied (no runner-level test for stall detection loop)
- Score: 3×2 (medium) + 1×3 (low) = 9 ≥ 5; plus high patch → true

**Verification performed:**
- `make lint` → 0 errors, 0 warnings (ruff, mypy, import-linter, eslint, prettier, tsc, env-contract, test-pairs)
- `make test` → 6317 passed, 23 skipped, 0 failed (backend unit); 1348 passed (frontend unit)
- Matrix test audit: all 8 I/O matrix rows covered by tests that ran and passed

**Residual risks:**
- `stall_min` silently accepted and ignored on shell/git.* steps (deferred); no operator impact unless a template declares it on those kinds
- `_max_mtime` does full `os.walk` of worktree every 10 s; may be slow on repos with large object stores (deferred)
- `timed_out` and `stalled` not enforced mutually exclusive at type level (deferred; mutually exclusive by construction in the polling loop)
