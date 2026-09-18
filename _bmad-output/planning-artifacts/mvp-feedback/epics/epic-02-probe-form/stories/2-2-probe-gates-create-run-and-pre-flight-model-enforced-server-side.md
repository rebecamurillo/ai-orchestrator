---
title: 'Probe gates create_run and pre-flight; model enforced server-side'
type: 'feature'
created: '2026-09-17'
status: 'in-progress'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
baseline_revision: '8a436bc938b772c09b29bcbbe55d6ceac64d5ad8'
---

<intent-contract>

## Intent

**Problem:** Pre-flight and `create_run` guard harness readiness by reading the `enabled` flag written by the readiness job — stale state that cannot detect a drifted CLI version, bad credentials, or a failed gateway until a run is already executing.

**Approach:** Replace the `enabled`-flag check with live probe calls in both pre-flight (`harness_probe_line`) and `create_run` (inline probe); validate the requested model against the probed list at create time; remove the readiness-run probe exemption so the readiness Run is subject to the same probe as any other create. Two anchor tests that pinned the old `enabled` semantics are revised under Operator exception-4 (decision 2026-09-16).

## Boundaries & Constraints

**Always:**
- `harness_probe_line()` in `checks.py` is the pre-flight harness check — it consults `ctx.harness_registry` (live adapters), never the DB `harnesses` table or the `enabled` field.
- `create_run` calls `probe()` once inline after pre-flight, with separate `ProbeResult`; 422 names the probed list on model mismatch.
- `probe_result.models` empty (gateway-disabled) → model check skipped even if `req.model` is set.
- `queued`/`parked` runs keep their harness name in `run.inputs["harness"]` (written at create time); no probe is re-run at resume time.
- The two-writer rule (AD-8) is untouched.
- TDD: new test files created and failing before implementation; anchor test revisions are exception-4 only.
- No new settings or `.env.example` changes — `harness_registry` wiring uses existing `build_harnesses()`.
- `make lint` import-linter must pass: no `fastapi`, `sqlalchemy`, `subprocess`, `os`, or `shutil` in `domain/` or `application/`.

**Block If:**
- A probed model list format change in `ProbeResult.models` requires redefining what "model in list" means.
- The `FakeHarness._probe_queue` raises `AssertionError` on empty in an unexpected path — investigate before adding more entries.

**Never:**
- Read `harness.enabled` in `create_run`, pre-flight, or any newly added path.
- Re-probe after the inline create probe (only one inline probe per create call).
- Add `skip_harness_check=True` to the readiness ports.
- Modify test files other than the two exception-4 authorised revisions.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Probe ok, model in list | `harness="claude"`, `model="claude-3-5"`, probe `ok=True`, `models=["claude-3-5"]` | Run created | No error |
| Probe ok, model not in list | `harness="claude"`, `model="gpt-4"`, probe `ok=True`, `models=["claude-3-5"]` | 422 Invalid naming the list | `Invalid(f"model 'gpt-4' not in probed list: ['claude-3-5']")` |
| Probe ok, gateway disabled | `harness="claude"`, `model="any"`, probe `ok=True`, `models=[]` | Run created (no model check) | No error |
| Probe fails at create | `harness="claude"`, probe `ok=False`, `failing_reason="gateway unreachable"` | 409 Conflict | `Conflict("gateway unreachable")` |
| Harness not in registry | `harness="claude"`, registry empty | Pre-flight line `fail "harness not available"` | `create_run` raises 409 (pre-flight fail blocked) |
| No harness set | `harness=None` | Pre-flight harness line skipped; `create_run` skips inline probe | No error |
| Readiness Run | `harness="claude"`, project "readiness" | Same probe path as any create; no exemption | Same 422/409 as any create |

</intent-contract>

## Code Map

Most of this story is already implemented in the WIP commits. The remaining work is two exception-4 anchor test revisions.

**Already implemented (WIP):**
- `backend-api/src/orchestrator/application/preflight/checks.py:272` — `harness_probe_line()`: reads `ctx.harness_registry`, not DB; returns `Line(CHECK_HARNESS, "fail", "harness not available")` when adapter missing, `Line(CHECK_HARNESS, "fail", failing_reason)` when probe fails, `Line(CHECK_HARNESS, "ok", f"probe ok · {version}")` on success
- `backend-api/src/orchestrator/application/use_cases/preflight.py:61` — `PreflightPorts.harness_registry: dict[str, HarnessAdapter]`; `preflight.py:154` — `_lines()` calls `harness_probe_line(ctx)`, not `harness_line(ctx)`
- `backend-api/src/orchestrator/application/use_cases/create_run.py:141-149` — inline probe block: `probe()`, 409 on `not ok`, 422 on model not in list
- `backend-api/src/orchestrator/api/providers.py:166` — `_preflight_ports` wires `harness_registry=build_harnesses(settings, RealProcessRunner())`; `providers.py:203` — readiness ports do NOT set `skip_harness_check=True`
- `backend-api/tests/unit/application/test_create_run_probe_gate.py` — new; covers all probe-gate scenarios
- `backend-api/tests/unit/application/preflight/test_harness_probe_line.py` — new; 5 tests covering skip/fail/ok/version

**Read-only anchors (never touch):**
- `backend-api/src/orchestrator/application/preflight/checks.py:246` — `harness_line()` (old reader of `harness.enabled`); present but no longer called by `_lines()`
- `backend-api/src/orchestrator/application/use_cases/create_run.py:80` — `skip_harness_check` field (reserved, stays)
- `backend-api/tests/unit/fakes/harness.py` — `FakeHarness`; `FakeHarness(probe_results=[...])` seeds the queue; `probe()` pops; `AssertionError` on empty

**Remaining exception-4 revisions:**
- `backend-api/tests/unit/application/test_preflight_use_case.py:151` — `test_ac3_harness_disabled`: currently asserts `Line(CHECK_HARNESS, "fail", "disabled: no readiness run", "re-run readiness on this screen")` — old `enabled` semantics; must assert probe-based semantics
- `backend-api/tests/unit/application/test_repository_init_harness.py:33` — `World` class: `PreflightPorts` has no `harness_registry`, so `harness_probe_line` returns `fail "harness not available"` and `create_run` raises 409; `test_a_named_harness_reaches_the_runs_inputs` fails; World must wire a `FakeHarness("fake")` with two ok probe results into `harness_registry`

**Supporting types:**
- `backend-api/src/orchestrator/domain/ports/harness.py:66` — `ProbeResult(ok, failing_reason, version, models)` dataclass
- `backend-api/tests/unit/fakes/harness.py:49` — `FakeHarness(name, probe_results=[ProbeResult(...), ...])` constructor

## Tasks & Acceptance

**Execution:**

Exception-4 test revisions (Operator authorization 2026-09-16 — these are the ONLY remaining tasks):

- `backend-api/tests/unit/application/test_preflight_use_case.py` — revise `test_ac3_harness_disabled` (lines 151–161): remove `FakeHarnessRepository` seeding and `harnesses` kwarg; keep `harness_registry` absent (defaults `{}`); change assertion to `Line(CHECK_HARNESS, "fail", "harness not available")`; add a comment naming the decision and date 2026-09-16 per exception-4 requirement. No other change to this file.

- `backend-api/tests/unit/application/test_repository_init_harness.py` — revise `World.__init__`: add imports `from tests.unit.fakes.harness import FakeHarness` and `from orchestrator.domain.ports.harness import ProbeResult`; wire `harness_registry={"fake": FakeHarness(name="fake", probe_results=[ProbeResult(ok=True, failing_reason=None, version="test", models=[]), ProbeResult(ok=True, failing_reason=None, version="test", models=[])])}` into `PreflightPorts`; two results are required: one consumed by `harness_probe_line` in pre-flight, one consumed by `create_run`'s inline probe block. `FakeHarnessRepository` seeding can remain (harmless). Add a comment naming the decision and date 2026-09-16 per exception-4 requirement. No other change to this file; `test_no_harness_still_dispatches_the_default` requires no change (harness=None skips probe).

**Acceptance Criteria:**
- Given `harness="claude"` and no `harness_registry` entry for it, when `run_preflight` is called, then `line(result, CHECK_HARNESS) == Line(CHECK_HARNESS, "fail", "harness not available")` with no fix text (probe semantics, not enabled-flag semantics; Operator decision 2026-09-16)
- Given `harness="fake"` and a `FakeHarness` for "fake" with two ok `ProbeResult` entries in `harness_registry`, when `init_repository(ports, repo_id, "fake")` is called, then `stored.inputs["harness"] == "fake"` (probe semantics; Operator decision 2026-09-16)
- Given any `create_run` call with a harness in the registry and `req.model` not in `probe_result.models` (non-empty), when `create_run` is called, then 422 `Invalid` is raised naming both the model and the probed list
- Given `req.model=None` or `probe_result.models=[]`, when `create_run` is called, then the model-check branch is skipped and no 422 is raised
- Given `readiness_ports` in `providers.py`, when called, then `skip_harness_check` is not set to `True` and the readiness Run goes through the same probe path as any create
- Given implementation complete, when `make lint` runs, then ruff, mypy, and import-linter pass with no AD-2 violations

## Design Notes

**Probe call count per `create_run`:** When `req.harness` is set and the adapter is in `harness_registry`, `probe()` is called twice total: once inside `harness_probe_line` (pre-flight), once in the inline block (`create_run`). The `FakeHarness._probe_queue` must have exactly two `ProbeResult` entries for any test that calls `create_run` with a named harness in the registry. `test_no_harness_still_dispatches_the_default` (harness=None) calls `probe()` zero times.

**`enabled` field lifecycle:** `harness.enabled` remains on the entity and DB schema (written by `harness_readiness_evaluate.py`), but is no longer read by any active code path — `harness_line()` (the only reader) is present in `checks.py` but no longer called by `_lines()`.

## Verification

**Commands:**
- `make lint` — expected: ruff, mypy, import-linter, prettier, tsc, eslint, env-contract, check_test_pairs, gen:api --check all pass
- `make test` — expected: all unit tests green including both revised anchor tests and the already-passing probe-gate/harness-probe-line test files
