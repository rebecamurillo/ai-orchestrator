---
title: 'The probe — script verb, port, and route'
type: 'feature'
created: '2026-09-16'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
deferred:
  - summary: >-
      Shell probe functions (probe_output, probe_gateway_models, probe) have only
      source-text assertions in test_harness_scripts_probe.py, not execution-based tests.
    evidence: |-
      Both tests read the script file as text (regex/in-operator). Neither runs the script.
      A JSON format regression in probe_output would not be caught by the test suite.
    location: >-
      scripts/harness/_common.sh, backend-api/tests/unit/test_harness_scripts_probe.py
    severity: low
  - summary: >-
      run_probe_script has no dedicated unit test for its field-mapping logic.
    evidence: |-
      All test coverage drives FakeHarness; run_probe_script is never called in tests.
      check_test_pairs passes via transitive import, not call coverage.
      A field-name mismatch or KeyError in the adapter would ship undetected.
    location: >-
      backend-api/src/orchestrator/infrastructure/harness/probe.py
    severity: low
  - summary: >-
      Router test does not cover the adapter-fault (500) path when probe() raises.
    evidence: |-
      test_harness_probe_router.py tests 200-ok, 200-failing, and 404, but not the case
      where probe() itself raises (TimeoutExpired, JSONDecodeError, etc.).
    location: >-
      backend-api/tests/unit/test_harness_probe_router.py
    severity: low
  - summary: >-
      probe_gateway_models interpolates tmpfile path into a python3 -c string literal.
    evidence: |-
      PROBE_MODELS_JSON=$(python3 -c "...open('${tmpfile}')...") — if mktemp produced a
      path with a single quote (non-standard but possible), this would be a shell injection
      into a Python expression. In practice mktemp paths are safe.
    location: >-
      scripts/harness/_common.sh:probe_gateway_models
    severity: low
  - summary: >-
      LITELLM_BASE_URL lacks :? guard inside probe_gateway_models, asymmetric with LITELLM_API_KEY.
    evidence: |-
      LITELLM_API_KEY:? aborts on unset; LITELLM_BASE_URL expands to empty string silently.
      The call site (probe() in each harness script) runs require_harness_env first, so the
      variable is validated, but the function itself has an asymmetric safety contract.
    location: >-
      scripts/harness/_common.sh:probe_gateway_models
    severity: low
  - summary: >-
      harness_probe_ports constructs the full harness registry with RealProcessRunner on
      every request, even though probe() never uses ProcessRunner.
    evidence: |-
      build_harnesses requires a ProcessRunner. probe() calls subprocess.run directly.
      The runner construction overhead is undocumented and the dependency is invisible.
    location: >-
      backend-api/src/orchestrator/api/providers.py:harness_probe_ports
    severity: low
baseline_revision: '91397a1d84593d92e42ff25c53e197d0b8fdd08a'
---

<intent-contract>

## Intent

**Problem:** There is no machine-queryable harness-readiness check before starting a Run; failures (wrong CLI version, bad credentials, unreachable gateway) surface only during execution when they are expensive to fix.

**Approach:** Add a `probe` shell verb to each harness script (reusing doctor's checks) that emits machine-readable JSON; expose it through the `Harness` domain port as `probe() → ProbeResult`; serve it at `GET /api/v1/harnesses/{name}/probe`. The adapter shells the verb — no application or domain code touches subprocess (AD-2, AD-10).

## Boundaries & Constraints

**Always:**
- Probe failures carry a specific string reason — never a bare boolean flag (NFR-8): `"cli not at pinned version <expected>"`, `"gateway unreachable"`, `"not logged in"`.
- Adapter shells `scripts/harness/<name>.sh probe`; parses stdout JSON → `ProbeResult`. No subprocess, os, or shutil in domain or application (AD-2; import-linter enforces).
- Shared fake extends existing `tests/unit/fakes/harness.py` — do not create a second Harness fake (AD-18).
- New route lives in a new `api/routers/harness_probe.py` — never in `harnesses.py` (frozen route-count test is an anchor).
- `contracts/openapi.json` is generated only via `make openapi` — never hand-edited (AD-3).
- TDD: new test files created and failing before implementation.
- `test_harness_scripts.py` is an anchor — never modify it. Cover probe-verb presence in a new test file.

**Block If:**
- The version pin in any harness script is not a single machine-comparable string (e.g. multi-line, regex-filtered, or derived at runtime).
- The gateway `/v1/models` response does not yield a flat list of model IDs parseable in bash.

**Never:**
- Modify `test_harness_scripts.py`, `test_harnesses_router.py`, or any other existing test file.
- Add `doctor_skill_present` to the probe checks — probe covers version, credentials, and gateway reachability only.
- Return HTTP 4xx/5xx for a probe that ran but found issues (`ok: false`); HTTP errors only for unknown harness (404) or server fault (500).
- Include form integration, `create_run` gating, or readiness demotion — those are stories 2-2 through 2-4.

</intent-contract>

## Code Map

- `scripts/harness/_common.sh:65-74` -- `doctor_skill_present()`, `doctor_gateway()`, `litellm_enabled()`; `doctor_gateway` hits `LITELLM_BASE_URL/v1/models` with bearer auth; add `probe_output()` JSON emitter here
- `scripts/harness/claude.sh:84-93` -- `doctor()` at line 84; dispatcher `case` at line 90; version pin constant in preamble; add `probe()` and probe dispatcher entry
- `scripts/harness/codex.sh:78-85` -- same pattern; `codex --version`
- `scripts/harness/opencode.sh:79-86` -- same pattern; `opencode --version`
- `backend-api/src/orchestrator/domain/ports/harness.py:204-286` -- `Harness` Protocol; existing types: `HarnessResult` (line 94), `HarnessHandle` (line 122); no `ProbeResult` yet; add `@dataclass ProbeResult` and `probe() → ProbeResult` to the protocol
- `backend-api/tests/unit/fakes/harness.py` -- `FakeHarness` implements full Harness protocol without `probe()`; extend with scripted probe queue (do not create a separate fake)
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` -- `ClaudeHarness`; holds script path; add `probe()` shelling the probe verb and parsing stdout JSON
- `backend-api/src/orchestrator/infrastructure/harness/codex/adapter.py` -- same pattern for `CodexHarness`
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py` -- same pattern for `LocalHarness`
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py` -- dev-mode fake; add `probe()` returning a fixed ok ProbeResult
- `backend-api/src/orchestrator/application/use_cases/harness_probe.py` -- new; look up harness by name (404 on miss); call `harness.probe()`; follow `harness_readiness.py` Ports-wiring pattern
- `backend-api/src/orchestrator/api/schemas/harnesses.py` -- add `ProbeResultOut` Pydantic model
- `backend-api/src/orchestrator/api/routers/harness_probe.py` -- new; `GET /harnesses/{name}/probe → ProbeResultOut`; bearer auth required; 404 on unknown name; follow `harness_readiness.py` structure
- `backend-api/src/orchestrator/api/routers/harness_readiness.py:70-98` -- READ-ONLY reference for Ports dependency pattern; do not modify
- `backend-api/tests/unit/test_harness_scripts.py` -- READ-ONLY anchor; `VERBS = ("install", "configure", "doctor")`; never touch
- `backend-api/tests/unit/test_harnesses_router.py:95-99` -- READ-ONLY; frozen route-count test
- `contracts/openapi.json` -- generated artifact; run `make openapi` post-implementation; commit result

## Tasks & Acceptance

**Execution:**

Tests first — these must exist and fail before implementation:
- `backend-api/tests/unit/test_harness_scripts_probe.py` -- create -- assert each of `claude.sh`, `codex.sh`, `opencode.sh` contains `^probe\(\) \{` (regex) and a `probe)` dispatcher case entry; probe-specific counterpart to the anchor `test_harness_scripts.py`; do not import from it
- `backend-api/tests/unit/test_harness_probe_port.py` -- create -- assert `ProbeResult` dataclass has fields `ok: bool`, `failing_reason: str | None`, `version: str`, `models: list[str]`; assert `FakeHarness` satisfies `Harness` protocol (runtime check) after probe() is added; assert scripted queue pops in order and raises on empty
- `backend-api/tests/unit/application/test_harness_probe_use_case.py` -- create -- ok probe returns ProbeResult with ok=True; failing probe returns ProbeResult with non-empty failing_reason string; unknown harness name yields 404
- `backend-api/tests/unit/test_harness_probe_router.py` -- create -- `GET /api/v1/harnesses/{name}/probe` 200 on ok probe; 200 on failing probe with non-null `failing_reason` string in body; 404 on unknown name; response body has all four fields

Implementation:
- `scripts/harness/_common.sh` -- add `probe_output(ok, reason, version, models_json)` that prints `{"ok":<ok>,"failing_reason":<reason_or_null>,"version":"<version>","models":<models_json>}` to stdout as a single line
- `scripts/harness/claude.sh` -- add `probe()`: (1) capture `claude --version`, compare to pinned constant; on mismatch call `probe_output false "cli not at pinned version <expected>" "" "[]"` and exit 1; (2) if `litellm_enabled`, curl `/v1/models` with auth; network error → `"gateway unreachable"` exit 1; HTTP 401 → `"not logged in"` exit 1; parse model IDs into JSON array; (3) `probe_output true "null" "<version>" "<models_json>"` exit 0; add `probe` to dispatcher `case`
- `scripts/harness/codex.sh` -- same `probe()` with `codex` binary and its pin
- `scripts/harness/opencode.sh` -- same `probe()` with `opencode` binary and its pin
- `backend-api/src/orchestrator/domain/ports/harness.py` -- add `@dataclass class ProbeResult: ok: bool; failing_reason: str | None; version: str; models: list[str]`; add `def probe(self) -> ProbeResult` to `Harness` Protocol
- `backend-api/tests/unit/fakes/harness.py` -- add `_probe_queue: list[ProbeResult]` to `FakeHarness.__init__`; `probe()` pops and returns the next result; raise `AssertionError("probe queue empty")` on empty (test setup error, not a domain case); add helper to pre-load results
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` -- `probe()`: `subprocess.run([script_path, "probe"], capture_output=True, text=True, timeout=30)`; parse stdout JSON to `ProbeResult`; unparseable stdout raises (not swallowed); do not use `ProcessRunner` (that is for coding-agent dispatch)
- `backend-api/src/orchestrator/infrastructure/harness/codex/adapter.py` -- same probe() with codex script path
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py` -- same probe() with opencode script path
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py` -- `probe()` returns `ProbeResult(ok=True, failing_reason=None, version="0.0.0-fake", models=["fake-model"])`
- `backend-api/src/orchestrator/application/use_cases/harness_probe.py` -- create use case following `harness_readiness.py` Ports pattern; raise HTTP 404 on unknown harness name; return `harness.probe()`
- `backend-api/src/orchestrator/api/schemas/harnesses.py` -- add `class ProbeResultOut(BaseModel): ok: bool; failing_reason: str | None; version: str; models: list[str]`
- `backend-api/src/orchestrator/api/routers/harness_probe.py` -- create router with `GET /harnesses/{name}/probe → ProbeResultOut`; find registration file by checking how `harness_readiness.router` is registered and replicate the pattern; bearer auth via same dependency as other harness routes
- `make openapi` -- run after all above to regenerate `contracts/openapi.json` and `web-client/src/api/schema.d.ts`; commit both updated files

**Acceptance Criteria:**
- Given a valid harness name and all checks passing, when `GET /api/v1/harnesses/{name}/probe` is called, then HTTP 200 with `ok: true`, non-empty `version` string, non-empty `models` list, and `failing_reason: null`
- Given a valid harness with gateway unreachable, when `GET /api/v1/harnesses/{name}/probe` is called, then HTTP 200 with `ok: false` and `failing_reason: "gateway unreachable"` (exact string; never a bare flag)
- Given a valid harness with credentials rejected by the gateway (HTTP 401), when `GET /api/v1/harnesses/{name}/probe` is called, then HTTP 200 with `ok: false` and `failing_reason: "not logged in"`
- Given a valid harness with CLI at a wrong version, when the probe runs, then `failing_reason` is `"cli not at pinned version <expected version>"` with the pinned value substituted
- Given an unknown harness name, when `GET /api/v1/harnesses/{name}/probe` is called, then HTTP 404 `application/problem+json`
- Given any application or domain module, when `make lint` runs import-linter, then no subprocess, os, or shutil import is found outside infrastructure (AD-2)
- Given implementation is complete, when `make openapi` runs, then `contracts/openapi.json` gains `/api/v1/harnesses/{name}/probe` with `ProbeResultOut` schema and `pnpm gen:api` reports no drift

## Spec Change Log

## Review Triage Log

### 2026-09-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 1, medium 4, low 1)
- defer: 6: (low 6)
- reject: 3
- addressed_findings:
  - `[high]` `[patch]` Non-401 HTTP codes (403/500/503) in probe_gateway_models treated as ok=true — added non-2xx guard to _common.sh after the 401 check
  - `[medium]` `[patch]` subprocess.TimeoutExpired uncaught in run_probe_script — wrapped subprocess.run in try/except; RuntimeError raised with script path and timeout
  - `[medium]` `[patch]` Empty stdout not checked before json.loads in run_probe_script — added explicit empty-stdout check; RuntimeError includes exit code and stderr
  - `[medium]` `[patch]` data["version"] bare key access (KeyError if probe exits before emitting version) — changed to data.get("version", "")
  - `[medium]` `[patch]` CLI not found misreported as version mismatch (awk extracts last word of error output) — added command -v check before version capture in all three probe() functions
  - `[low]` `[patch]` Empty string passed as version on mismatch (version_str captured but discarded) — now passes ${version_str} in probe_output on mismatch in all three scripts

## Design Notes

**Gateway-disabled mode:** When `litellm_enabled` returns false, `probe()` skips the network call and returns `ok=true, models=[], failing_reason=null` — mirroring `doctor_gateway`'s behaviour (it logs "gateway disabled" and returns 0). Callers must not interpret an empty `models` list as a probe failure.

**Subprocess in adapters vs ProcessRunner:** The probe call is a short synchronous one-shot invocation. Use `subprocess.run(capture_output=True, text=True, timeout=30)` directly in each infrastructure adapter — `ProcessRunner` is reserved for the streaming coding-agent dispatch, not for harness script invocations.

**Probe output contract:** The shell verb always emits exactly one JSON line to stdout regardless of outcome (success or failure); the exit code mirrors `ok` (0 = true, 1 = false). The adapter uses stdout for the result and exit code as a cross-check; unparseable stdout is an adapter error, not a probe failure.

## Verification

**Commands:**
- `make lint` -- expected: ruff, mypy, import-linter all pass; no AD-2 violation in domain or application
- `make test` -- expected: all unit tests green including new probe test files
- `make e2e-api` -- expected: probe route covered in API scenarios
- `make openapi` -- expected: contracts/openapi.json has probe path and schema; no drift reported by pnpm gen:api

## Auto Run Result

Status: done

### Summary

Added the probe verb, domain port, infrastructure adapters, use case, API route, and shared test fake for the harness probe feature (story 2-1). A `probe` verb now exists in each of the three harness shell scripts (`claude.sh`, `codex.sh`, `opencode.sh`), backed by shared helpers in `_common.sh`. The `Harness` port gained `probe() → ProbeResult`; each real adapter delegates to the new `infrastructure/harness/probe.py:run_probe_script` helper; `GET /api/v1/harnesses/{name}/probe` is served by a new router; the contract was regenerated without drift.

### Files changed

- `scripts/harness/_common.sh` — added `probe_output()` JSON emitter and `probe_gateway_models()` with non-2xx gateway error handling
- `scripts/harness/claude.sh` — added `probe()` (command-v guard, version check, gateway check, model enumeration) and dispatcher case
- `scripts/harness/codex.sh` — same probe() pattern
- `scripts/harness/opencode.sh` — same probe() pattern
- `backend-api/src/orchestrator/domain/ports/harness.py` — added `ProbeResult` dataclass and `probe()` to `Harness` Protocol
- `backend-api/tests/unit/fakes/harness.py` — added `probe_results` queue and `probe()` to `FakeHarness`
- `backend-api/src/orchestrator/infrastructure/harness/probe.py` — new; `run_probe_script()` with TimeoutExpired handling and empty-stdout guard
- `backend-api/src/orchestrator/infrastructure/harness/__init__.py` — re-exports `run_probe_script`
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` — added `probe()`
- `backend-api/src/orchestrator/infrastructure/harness/codex/adapter.py` — added `probe()`
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py` — added `probe()`
- `backend-api/src/orchestrator/infrastructure/harness/fake/adapter.py` — added `probe()` (fixed ok result)
- `backend-api/src/orchestrator/infrastructure/settings.py` — added `harness_scripts_dir: Path`
- `backend-api/src/orchestrator/application/use_cases/harness_probe.py` — new; `HarnessProbePorts` and `probe()` use case
- `backend-api/src/orchestrator/api/schemas/harnesses.py` — added `ProbeResultOut`
- `backend-api/src/orchestrator/api/routers/harness_probe.py` — new; `GET /harnesses/{name}/probe`
- `backend-api/src/orchestrator/api/providers.py` — added `harness_probe_ports()`
- `backend-api/src/orchestrator/main.py` — mounted `harness_probe.router`
- `.env.example` — added `HARNESS_SCRIPTS_DIR`
- `contracts/openapi.json` — regenerated; added `ProbeResultOut` schema and probe path
- `web-client/src/api/schema.d.ts` — regenerated; added `ProbeResultOut` type and operation
- `backend-api/tests/unit/test_harness_scripts_probe.py` — new; tests probe verb presence in each script
- `backend-api/tests/unit/test_harness_probe_port.py` — new; tests ProbeResult fields and FakeHarness compliance
- `backend-api/tests/unit/test_harness_probe_router.py` — new; tests route 200/404/401 behavior
- `backend-api/tests/unit/application/test_harness_probe_use_case.py` — new; tests use case ok/fail/not-found

### Review findings breakdown

- Patches applied: 6 (1 high, 4 medium, 1 low)
- Items deferred: 6 (all low) — see frontmatter `deferred` list
- Items rejected: 3 — failing_reason comment (aspirational but accurate), create_run inline probe (story 2-2 scope), infrastructure fake dedicated test (check_test_pairs covered it)

### Follow-up review recommendation

`true` — 1 high-severity patch (non-401 HTTP errors treated as ok=true in probe_gateway_models).
Patched severity counts: high 1, medium 4, low 1. Score: 1 high → true.

### Verification performed

- `make lint`: passed — ruff, mypy, import-linter, prettier, tsc, eslint, env-contract, check_test_pairs, gen:api --check all clean
- `make test`: 6332 backend unit tests passed, 23 skipped; 1348 frontend unit tests passed (0 failures)
- `make openapi`: regenerated without drift — `gen:api: src/api/schema.d.ts matches contracts/openapi.json`
- `make e2e-api`: not run (requires running compose stack)

### Residual risks

6 deferred low-severity items (see frontmatter `deferred`). Most significant: `run_probe_script` has no dedicated unit test for field-mapping; a regression in the JSON-to-ProbeResult mapping would not be caught by the test suite.
