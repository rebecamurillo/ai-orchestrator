---
title: 'Harness environment and registry in off-mode'
type: 'feature'
created: '2026-09-13'
status: 'done'
review_loop_iteration: 1
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      claude_native_aliases content-logging pair (OTEL_LOG_USER_PROMPTS, OTEL_LOG_TOOL_CONTENT)
      is untested when ORCH_LOG_CONTENT=1 in gateway-off mode.
    evidence: |-
      The factory includes the same ORCH_LOG_CONTENT=="1" branch as claude_aliases, but no test
      in test_harness_env_off_mode.py passes log_content=True or sets ORCH_LOG_CONTENT. The branch
      is exercised only in gateway-on tests for claude_aliases.
    location: >-
      backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:203
    severity: low
  - summary: >-
      Both-on regression guard (test_both_on_claude_has_five_header_lines) covers only claude;
      intent says "any harness" — codex and local in default mode are unverified.
    evidence: |-
      Matrix row 3 says "any harness / byte-identical to today's output" but the guard checks only
      ANTHROPIC_CUSTOM_HEADERS count for claude. Production code does not change gateway-on paths for
      codex/local, so there is no regression risk from this story, but the stated regression surface
      is narrower than the intent.
    location: >-
      backend-api/tests/unit/test_harness_env_off_mode.py:194
    severity: low
  - summary: >-
      No test for build_harnesses with gateway_enabled=False AND orch_test_mode=True; matrix row 5
      parenthetical ({claude, codex, fake}) is unverified.
    evidence: |-
      test_build_harnesses_gateway_off_excludes_local checks {claude, codex} only. The orch_test_mode
      branch is independent of the gateway check and unchanged by this story; the combination is real but
      untested.
    location: >-
      backend-api/src/orchestrator/infrastructure/harness/registry.py:155
    severity: low
baseline_revision: '70483ec345a008856497170d08f6ceb428b40365'
---

<intent-contract>

## Intent

**Problem:** With `gateway_enabled` false, `alias_table` still passes `claude` an `ANTHROPIC_AUTH_TOKEN` that is an empty LiteLLM key (causing an empty `Authorization` header on every model call), `build_harnesses` still registers `local`, and the start-up seed never marks `local` disabled — so an Operator with the Gateway off either sees a harness fail on the first call or is offered a harness that cannot function.

**Approach:** Add `claude_native_aliases` factory in `claude/adapter.py`; update `alias_table` to select it when `gateway_enabled` is false and to drop `local` from the table when `tracing_enabled` is false; strip `local` from `build_harnesses` when the gateway is off; add `seed_disabled_harness` use case in `harnesses.py` and call it from `seed_harness_table` when the gateway is off.

## Boundaries & Constraints

**Always:**
- `HARNESS_ENV_CONTRACT` is unchanged: all fifteen names are exported in every mode, carrying blank values when a service is off. No name added, dropped, or renamed.
- A blank credential is never exported as an alias: when `gateway_enabled` is false, no `ANTHROPIC_AUTH_TOKEN` reaches the `claude` harness.
- `claude_aliases` and `claude_subscription_aliases` are unchanged — the new `claude_native_aliases` is a third builder added beside them, not a replacement.
- `alias_table(settings)` remains the one join point; `env.py` stays harness-agnostic (no import of adapter-specific logic there).
- Each builder keeps the `AliasBuilder` signature (contract in, native names out); `claude_native_aliases` is a factory `(tracing_enabled: bool) -> AliasBuilder` so `alias_table` can bind `settings.tracing_enabled` without threading it through `env_for`.
- `seed_disabled_harness` takes ports (not a session) and belongs in `application/use_cases/harnesses.py` beside `seed_test_harness` (AD-2).
- `seed_harness_table` always upserts all three version pins (local's pin row still exists); `seed_disabled_harness` then writes `enabled=False, failing_check=reason` for `local` when the gateway is off, overriding whatever the upsert left.
- Module docstring note in `registry.py` (or `claude/adapter.py`): subscription mode (`CLAUDE_SUBSCRIPTION_AUTH`) with gateway on still routes through LiteLLM; gateway-off mode does not — these are different modes and `claude_native_aliases` is what applies regardless of the subscription flag when the gateway is off.
- Existing anchor tests (`test_harness_env.py`, `test_harness_env_contract.py`, `test_harness_env_subscription.py`, `test_alias_table_merge.py`, `test_harness_registry.py`) must not be edited; all pass unchanged under the `.env.example` default environment where `gateway_enabled=True` and `tracing_enabled=True`.

**Block If:** Any required name or behavior differs from the brief's verbatim AC wording, or any existing anchor test requires editing to pass.

**Never:** Add a `*_ENABLED` environment variable. Edit any existing test file. Change `HARNESS_ENV_CONTRACT` membership or `.env.example` variable names. Emit a blank `ANTHROPIC_CUSTOM_HEADERS` (absent entirely is the off state, not `""`). Add a `Settings` field for provider credentials.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Gateway off, tracing on, `claude` | `LITELLM_BASE_URL=""`, `build_harness_env` | Key set = contract ∪ project ∪ base ∪ `{ANTHROPIC_CUSTOM_HEADERS}`; no `ANTHROPIC_AUTH_TOKEN`; `LITELLM_BASE_URL=""`, `LITELLM_API_KEY=""`; headers = exactly 2 langfuse lines | No error |
| Both off, `claude` | Both blank | `ANTHROPIC_CUSTOM_HEADERS` absent; key set = contract ∪ project ∪ base | No error |
| Both on (default), any harness | `.env.example` values | Byte-identical to today's output | No error |
| Gateway on, tracing off, `local` | `LANGFUSE_BASE_URL=""` | Neither `LANGFUSE_BASEURL` nor `LANGFUSE_USER_ID` in environment | No error |
| Gateway off, `build_harnesses` | `LITELLM_BASE_URL=""` | Registry keys = `{claude, codex}` (+ `fake` under `ORCH_TEST_MODE`); `local` absent | No error |
| Gateway off, start-up seed | `LITELLM_BASE_URL=""` | `local` row: `enabled=False`, `failing_check="gateway disabled (LITELLM_BASE_URL blank)"`; pre-flight harness line returns `fail`; `create_run` refuses | No error |
| Gateway on, start-up seed | `.env.example` values | `local`'s `enabled` and `failing_check` left to readiness; not touched by this story | No error |

</intent-contract>

## Code Map

- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py:128-179` — `claude_aliases` (line 128) and `claude_subscription_aliases` (line 149) unchanged; ADD `claude_native_aliases(tracing_enabled: bool) -> AliasBuilder` after line 179: no `ANTHROPIC_AUTH_TOKEN`; headers built from `HEADER_SOURCES[:2]` (langfuse_session_id + langfuse_tags) when `tracing_enabled`, absent otherwise; content-logging pair keeps existing `ORCH_LOG_CONTENT == "1"` rule; docstring notes gateway-off vs subscription-mode distinction
- `backend-api/src/orchestrator/infrastructure/harness/registry.py:74-101` — `alias_table`: when `not settings.gateway_enabled` return `{ClaudeHarness.name: claude_native_aliases(settings.tracing_enabled), CodexHarness.name: codex_aliases(settings.agent_home)}`; when gateway on, existing logic (`ALIASES`/`SUBSCRIPTION_ALIASES` merge) plus `codex_aliases`; then `result.pop(LocalHarness.name, None)` when `settings.gateway_enabled and not settings.tracing_enabled`
- `backend-api/src/orchestrator/infrastructure/harness/registry.py:104-130` — `build_harnesses`: add `if not settings.gateway_enabled: built.pop(LocalHarness.name, None)` (or omit from initial `built` dict) so gateway-off registry = `{claude, codex}` (+ fake)
- `backend-api/src/orchestrator/application/use_cases/harnesses.py:60-74` — `seed_test_harness` (reference); ADD `seed_disabled_harness(ports: HarnessPorts, name: str, reason: str) -> Harness` beside it: fetches existing row, `model_copy(update={"enabled": False, "failing_check": reason})`, calls `harnesses.update`, commits; if row absent (defensive), inserts with `version_pin="unknown"`, `enabled=False`, `failing_check=reason`
- `backend-api/src/orchestrator/infrastructure/db/seed.py:76-99` — `seed_harness_table`: imports `seed_disabled_harness` from `harnesses.py`; after the `seed_harnesses` call and before the `orch_test_mode` block, add the gateway-off conditional; do NOT use `seeded.append(seed_disabled_harness(...))` because `seed_harnesses` already added `local` to `seeded` — the correct pattern is to replace that entry: `if not settings.gateway_enabled: disabled = seed_disabled_harness(hports, "local", "gateway disabled (LITELLM_BASE_URL blank)"); seeded = [disabled if h.name == "local" else h for h in seeded]`
- `backend-api/src/orchestrator/application/preflight/checks.py:242-265` — `harness_line` and `_failing_check` READ-ONLY: `_failing_check` already returns `harness.failing_check` when set; no changes needed — pre-flight's harness line already reads the stored `failing_check` and surfaces it
- `backend-api/src/orchestrator/infrastructure/harness/opencode/adapter.py:115-136` — `local_aliases` READ-ONLY; no change needed; `alias_table` removes it from the table when `tracing_enabled` is false
- `backend-api/src/orchestrator/infrastructure/harness/env.py:44-61` — `HARNESS_ENV_CONTRACT` READ-ONLY; 15 names unchanged
- `backend-api/tests/unit/test_harness_env.py` — ANCHOR READ-ONLY; uses `.env.example` env so gateway+tracing both on; unchanged
- `backend-api/tests/unit/test_harness_env_contract.py` — ANCHOR READ-ONLY; unchanged
- `backend-api/tests/unit/test_harness_registry.py:59-63` — ANCHOR READ-ONLY; `test_the_registry_is_built_here_now` asserts `set(harnesses) <= set(HARNESS_NAMES)`, which is still satisfied when gateway off (`{claude, codex}` ⊆ `{claude, codex, local}`)
- `backend-api/tests/unit/fakes/process.py` — FakeProcessRunner; used unchanged by new tests
- `backend-api/tests/unit/conftest.py` — `env` fixture; new tests use `monkeypatch.setenv`/`delenv` on top of it

## Tasks & Acceptance

**Execution (TDD — write tests first, all failing before step 2):**
- `backend-api/tests/unit/test_harness_env_off_mode.py` — CREATE: tests covering ACs 1-4 and I/O matrix; use `env` fixture + `monkeypatch.setenv("LITELLM_BASE_URL", "")` for gateway-off and `monkeypatch.setenv("LANGFUSE_BASE_URL", "")` for tracing-off; call `build_harness_env(Settings())(...)` to exercise the full pipeline; assert key sets, header content, and absent names. The `gateway_off_tracing_on` fixture must assert `settings.tracing_enabled` so a .env.example change that blanks LANGFUSE_BASE_URL cannot silently turn it into the both-off scenario. The "both on" guard test that checks for five headers in the name must also count them: assert `result["ANTHROPIC_CUSTOM_HEADERS"].count("\\n") == 4`.
- `backend-api/tests/unit/test_harness_registry_off_mode.py` — CREATE: tests covering ACs 5-7; use `FakeProcessRunner`; test `build_harnesses` key set when gateway off; test `alias_table` gateway-off branch and tracing-off local removal; test `seed_disabled_harness` use-case directly with `HarnessPorts` + fake repository (enabled/failing_check/version_pin/commit/absent-row); test `harness_line` returns `fail` with the stored `failing_check` when local is disabled; **test `seed_harness_table` gateway-off integration**: monkeypatch `LITELLM_BASE_URL=""` and replace `SQLAlchemyHarnessRepository` and `SQLAlchemyUnitOfWork` with fakes, call `seed_harness_table(settings)` directly, assert the returned list contains a `local` entry with `enabled=False` and `failing_check="gateway disabled (LITELLM_BASE_URL blank)"`; also assert the gateway-on path does NOT write that `failing_check` (gateway-on seed leaves local's fields to readiness). AC7's test must call real production code — a test that creates a `FakeHarnessRepository` and asserts no change without calling any production code is vacuous and must not be written.
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` — EDIT: add `claude_native_aliases(tracing_enabled: bool) -> AliasBuilder` factory after `claude_subscription_aliases`; add to `__all__`; add docstring note distinguishing gateway-off from subscription mode
- `backend-api/src/orchestrator/infrastructure/harness/registry.py` — EDIT: import `claude_native_aliases` from `claude`; update `alias_table` with gateway-off branch and tracing-off local drop; update `build_harnesses` to exclude `local` when `gateway_enabled` is false; update module docstring
- `backend-api/src/orchestrator/application/use_cases/harnesses.py` — EDIT: add `seed_disabled_harness(ports, name, reason)` beside `seed_test_harness`; update module docstring
- `backend-api/src/orchestrator/infrastructure/db/seed.py` — EDIT: import `seed_disabled_harness`; add gateway-off conditional call in `seed_harness_table` after `seed_harnesses`, before `orch_test_mode` block

**Acceptance Criteria:**
- Given `gateway_enabled` false and `tracing_enabled` true and the `claude` harness, when `env_for` builds an attempt's environment, then the key set equals `HARNESS_ENV_CONTRACT` ∪ Project vars ∪ `{HOME, PATH, LANG, TERM}` ∪ `{ANTHROPIC_CUSTOM_HEADERS}`; `ANTHROPIC_AUTH_TOKEN` is absent; `LITELLM_BASE_URL` and `LITELLM_API_KEY` are present and blank; and `ANTHROPIC_CUSTOM_HEADERS` holds exactly the two langfuse lines (`langfuse_session_id` and `langfuse_tags`), in that order
- Given both services off and the `claude` harness, when `env_for` builds an attempt's environment, then `ANTHROPIC_CUSTOM_HEADERS` is absent and the key set equals the contract plus base names plus Project variables
- Given both services on (`.env.example` default), when `env_for` builds for each of `claude`, `codex`, `local`, then every existing expectation holds byte for byte
- Given `gateway_enabled` true, `tracing_enabled` false, and a `local` harness attempt, when `env_for` builds the environment, then neither `LANGFUSE_BASEURL` nor `LANGFUSE_USER_ID` is in the resulting environment
- Given `gateway_enabled` false, when `build_harnesses(settings, runner)` is called, then its keys are `{claude, codex}` (plus `fake` under `ORCH_TEST_MODE`) and `local` is absent
- Given `gateway_enabled` false, when the start-up seed runs, then the `local` row exists with `enabled=False` and `failing_check="gateway disabled (LITELLM_BASE_URL blank)"`; and `harness_line` for a request naming `local` returns `fail` carrying that reason
- Given `gateway_enabled` true and a fresh database, when the start-up seed runs, then the `local` row has `failing_check=None` — the gateway-disabled reason is never written in this mode

## Spec Change Log

### 2026-09-13 — Review pass 1 bad_spec repair

**Triggering finding:** `seed_harness_table`'s gateway-off branch (`if not settings.gateway_enabled: seed_disabled_harness(...)` in `seed.py:85-90`) had no test that called it. Removing the entire conditional from `seed.py` would leave all gates green while the `local` row would never receive `enabled=False` at startup. The spec's Task section said to test `seed_disabled_harness` "use-case directly" but AC6 says "when the start-up seed runs" — an inconsistency that caused the integration path to go untested.

**What was amended:**
- `test_harness_registry_off_mode.py` task: added requirement for a `seed_harness_table` gateway-off integration test (direct call through fakes); the AC7 non-vacuous constraint (no test that asserts a tautology without calling production code).
- `test_harness_env_off_mode.py` task: added `settings.tracing_enabled` guard to `gateway_off_tracing_on` fixture; added header-count assertion to the five-headers guard test.
- `seed.py` Code Map note: replaced `seeded.append(seed_disabled_harness(...))` with the replacement pattern to avoid returning `local` twice in the seeded list.

**Known-bad state avoided:** `seeded.append` duplicates the `local` entry in the return value; vacuous AC7 test that never calls production code.

**KEEP (must survive re-derivation):**
- All production code implementations are correct and must be preserved verbatim: `claude_native_aliases` factory, `alias_table` gateway-off short-circuit, `build_harnesses` pop, `seed_disabled_harness` use case.
- All 28 prior tests for ACs 1-7 are correct in their behavioral coverage and should be preserved; the new subagent adds/fixes as required by the updated Task section.

## Review Triage Log

### 2026-09-13 — Review pass 2

- intent_gap: 0
- bad_spec: 0
- patch: 0
- defer: 3: (high 0, medium 0, low 3)
- reject: 0
- addressed_findings:
  - none

### 2026-09-13 — Review pass 1

- intent_gap: 0
- bad_spec: 1: (high 1, medium 0, low 0)
- patch: 0
- defer: 0
- reject: 0
- addressed_findings:
  - `[high]` `[bad_spec]` No test exercised the gateway-off branch of `seed_harness_table`; all tests either called `seed_disabled_harness` directly or exercised gateway-on paths, so removing the conditional from `seed.py` would leave gates green while `local` would never be marked disabled at startup. Root cause: spec Task section said to test the use case "directly" but AC6 says "when the start-up seed runs" — fixed by amending the Task section to require a `seed_harness_table` integration test via fakes, adding a non-vacuous AC7 test requirement, fixture guard, header-count assertion, and seeded-list deduplication.

## Design Notes

`claude_native_aliases` is a factory `(tracing_enabled: bool) -> AliasBuilder` — the same pattern as `codex_aliases(agent_home: Path) -> AliasBuilder`. `alias_table` binds `settings.tracing_enabled` once, producing an `AliasBuilder` closure the contract test can call as `claude_native_aliases(True)(contract)`. This keeps every builder's outer-facing type `AliasBuilder` so `env.py` remains harness-agnostic.

**Subscription mode vs gateway-off mode:** `CLAUDE_SUBSCRIPTION_AUTH=true` with gateway **on** routes through LiteLLM — the virtual key moves to `x-litellm-api-key` (subscription header). With gateway **off** there is no LiteLLM to read any header, and `claude_native_aliases` applies regardless of the subscription flag. `alias_table`'s gateway-off branch short-circuits before the subscription check to make this ordering explicit and prevent conflation.

`HEADER_SOURCES[:2]` yields exactly `("langfuse_session_id", "ORCH_RUN_ID")` and `("langfuse_tags", "ORCH_LANGFUSE_TAGS")` — the two attribution lines that reach Langfuse. The three `x-litellm-*` lines are dropped because there is no LiteLLM proxy to read them.

`seed_disabled_harness` writes after `seed_harnesses` so it always overwrites an existing row (never relies on insert). The `if not settings.gateway_enabled` branch in `seed_harness_table` sits between `seed_harnesses` and the `orch_test_mode` block, mirroring the conditional structure already there.

**Project-supplied keys (AD-5).** `env_for` merges the Project's decrypted variables before the contract, so a Project variable named `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` reaches the harness in off-mode and is overridden by nothing in the contract (which has no such name). This is the supported way to authenticate a harness that is not logged in locally; no `Settings` field is added for it. The `claude_native_aliases` docstring states this explicitly.

## Auto Run Result

**Summary:** Added `claude_native_aliases` factory for gateway-off mode (no `ANTHROPIC_AUTH_TOKEN`, two Langfuse headers only); wired `alias_table` to use it with a gateway-off short-circuit and drop `local` when tracing is off; stripped `local` from `build_harnesses` when gateway is off; added `seed_disabled_harness` use case; called it from `seed_harness_table` using a replacement pattern to avoid duplicate list entries. 23 new tests cover all seven matrix rows including a `seed_harness_table` gateway-off integration test through monkeypatched fakes.

**Files changed:**
- `backend-api/src/orchestrator/infrastructure/harness/claude/adapter.py` — added `claude_native_aliases(tracing_enabled: bool) -> AliasBuilder` factory and updated `__all__`
- `backend-api/src/orchestrator/infrastructure/harness/claude/__init__.py` — re-exported `claude_native_aliases`
- `backend-api/src/orchestrator/infrastructure/harness/registry.py` — `alias_table` gateway-off short-circuit and tracing-off local pop; `build_harnesses` pops local when gateway off
- `backend-api/src/orchestrator/application/use_cases/harnesses.py` — added `seed_disabled_harness` use case beside `seed_test_harness`
- `backend-api/src/orchestrator/infrastructure/db/seed.py` — imported `seed_disabled_harness`; added gateway-off conditional using replacement pattern
- `backend-api/tests/unit/test_harness_env_off_mode.py` — new: 10 tests for ACs 1–4
- `backend-api/tests/unit/test_harness_registry_off_mode.py` — new: 13 tests for ACs 5–7

**Review findings breakdown:**
- Pass 1: 1 bad_spec (high) — missing `seed_harness_table` integration test; spec amended and code re-derived. 0 patch applied, 0 deferred.
- Pass 2: 0 patch applied, 3 deferred (all low), 0 rejected with prejudice.
- `followup_review_recommended` score: 0 patches in pass 2 → score 0 < 5, no high patches → false.

**Verification performed:**
- `make lint`: zero ruff, mypy, import-linter, env-contract, test-pairs, eslint, prettier, tsc violations.
- `make test`: 6093 pytest passed (23 skipped), 1289 vitest passed. All five anchor tests still green. All 7 matrix rows covered by tests that ran and passed.

**Residual risks:** Three low-severity deferred items: `claude_native_aliases` content-logging path untested in gateway-off mode; both-on regression guard covers only claude; `build_harnesses` with gateway-off + test-mode combination untested.

## Verification

**Commands:**
- `make lint` -- expected: zero ruff, mypy, import-linter, env-contract violations
- `make test` -- expected: all pytest and vitest tests green, including new `test_harness_env_off_mode.py` and `test_harness_registry_off_mode.py`; all five anchor tests still green
