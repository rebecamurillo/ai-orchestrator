---
title: 'Harness scripts configure and doctor what exists'
type: 'feature'
created: '2026-09-13'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred:
  - summary: >-
      Test file lives in tests/unit/ but spawns bash processes and has integration-test characteristics.
    evidence: |-
      File uses pytestmark skipif(shutil.which("bash") is None) and real subprocess invocations.
      This matches the pre-existing convention in test_harness_scripts.py.
    location: >-
      backend-api/tests/unit/test_harness_scripts_off_mode.py
    severity: low
  - summary: >-
      JSON/TOML output in harness configure scripts is not safe against operator-controlled env vars
      containing double-quotes or backslashes (LITELLM_BASE_URL, LANGFUSE_ENVIRONMENT).
    evidence: |-
      Scripts interpolate these values directly into JSON/TOML double-quoted strings without escaping.
      This is a pre-existing issue in the original scripts, not introduced by story 9-5.
    location: >-
      scripts/harness/claude.sh, scripts/harness/codex.sh, scripts/harness/opencode.sh
    severity: medium
baseline_revision: 'b2799748e6e590a6c36d599295f8af63d09028d6'
---

<intent-contract>

## Intent

**Problem:** With `LITELLM_BASE_URL=""`, `require_harness_env`'s unconditional `:?` expansions refuse every `configure` and `doctor` call, so a blank-URL (disabled) instance cannot start. The three harness scripts have no conditional logic to skip the Gateway route or OTLP section when a service is off.

**Approach:** Add `litellm_enabled` / `langfuse_enabled` helpers and update `require_harness_env` in `_common.sh` to distinguish declared-blank (skip) from unset (refuse); update `doctor_gateway` to return success without a network call when disabled; update each script's `configure` to write only the sections for services that are actually on.

## Boundaries & Constraints

**Always:**
- `require_harness_env`'s four `:?` expansions must remain verbatim inside the guard body — anchors grep for `${NAME:?` in the function text (`test_the_guard_names_every_variable_configure_needs`) and run configure with no env to prove refusal (`test_configure_refuses_with_nothing_configured`)
- `litellm_enabled()` and `langfuse_enabled()` are the sole conditionals — no script re-derives the rule
- `require_harness_env` stays in the `configure|doctor` dispatch, not in `install` (anchors: `test_configure_and_doctor_check_the_environment_first`, `test_install_does_not_check_the_gateway_environment`)
- `${LITELLM_API_KEY` never appears in a config file (anchor: `test_a_config_file_is_written_with_variable_names_not_values`)
- `GITHUB_TOKEN` and `LITELLM_SPEND_KEY` absent from all scripts (AD-5, anchor)
- `HARNESS_ENV_CONTRACT` array unchanged (AD-10; 9-4 depends on it)
- Every config file written `chmod 600` after the file write — the redirect form `> "${` must precede `chmod` in script text (anchor: `test_harness_config_permissions.py` greps for `> "${` then asserts `chmod` comes after)
- Each `configure` logs `"gateway disabled"` / `"tracing disabled"` via `log` (stderr) once per disabled service, then still writes a valid file
- `doctor_gateway` probes only when `litellm_enabled`; returns 0 with `log "gateway disabled"` when disabled; version check and `doctor_skill_present` are unconditional in each `doctor()`
- claude.sh assembles env entries as a bash array joined with `,\n    ` — guarantees well-formed JSON in all four service combinations

**Block If:** any anchor test requires editing to pass

**Never:** expand `${LITELLM_API_KEY` into a config file; include `GITHUB_TOKEN` or `LITELLM_SPEND_KEY` in any script; leave a trailing comma in any JSON or TOML; add a `*_ENABLED` env var; edit any existing test file

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Unset env | only PATH, HOME | each script exits non-zero; stderr names one of the four guard vars | `:?` fires unchanged |
| Gateway off, tracing on | `LITELLM_BASE_URL=""`, Langfuse vars set | exit 0; claude's settings.json parses, no `ANTHROPIC_BASE_URL`, has OTEL entries; codex's config.toml parses, no `model_provider`/`[model_providers.litellm]`, has `[otel]`; opencode.json parses, no `"provider"`, has `"plugin"`/`"experimental"` | No error |
| Tracing off, gateway on | `LANGFUSE_BASE_URL=""`, gateway vars set | exit 0; no OTEL/OTLP entries in any file; gateway route present in claude/codex/opencode; all files parse | No error |
| Both blank | both blank, all other vars set | exit 0; every file parses; no gateway route, no tracing config; each file is mode 600 | No error |
| Both on (default) | `.env.example` values intact | each file is structurally identical to current output — all expected keys/sections present with correct values | No error |
| doctor_gateway disabled | `LITELLM_BASE_URL=""` | exits 0; stderr contains `"gateway disabled"`; no network request made | No error |

</intent-contract>

## Code Map

- `scripts/harness/_common.sh:16-21` — `require_harness_env()`: replace the 4 unconditional `:?` lines with two conditional blocks: `if [ -z "${LITELLM_BASE_URL+declared}" ] || [ -n "${LITELLM_BASE_URL}" ]; then : "${LITELLM_BASE_URL:?...}"; fi` and `if [ -z "${LANGFUSE_BASE_URL+declared}" ] || [ -n "${LANGFUSE_BASE_URL}" ]; then : "${LANGFUSE_BASE_URL:?...}"; : "${LANGFUSE_PUBLIC_KEY:?...}"; : "${LANGFUSE_SECRET_KEY:?...}"; fi` — the four `${NAME:?` strings stay in the body so the anchor grep passes; unset fires `:?` because `${VAR+declared}` expands to empty when unset → `-z` true; blank skips the block
- `scripts/harness/_common.sh` (after `require_harness_env`) — ADD: `litellm_enabled() { [ -n "${LITELLM_BASE_URL:-}" ]; }` and `langfuse_enabled() { [ -n "${LANGFUSE_BASE_URL:-}" ]; }` — these are the only service-state tests in the entire script family
- `scripts/harness/_common.sh:59-62` — `doctor_gateway()`: ADD at top: `if ! litellm_enabled; then log "gateway disabled"; return 0; fi`; the curl check that follows is reached only when gateway is on
- `scripts/harness/claude.sh:23-49` — `configure()`: declare `local env_entries=()`; push `"ANTHROPIC_BASE_URL"` entry only when `litellm_enabled` (else `log "gateway disabled"`); push all OTEL/telemetry entries only when `langfuse_enabled` (else `log "tracing disabled"`); push `"DISABLE_AUTOUPDATER": "1"` unconditionally; join into `env_json` with `,\n    ` separator; embed in heredoc as `    ${env_json}` so the first entry gets 4-space indent from the heredoc literal and subsequent entries from the separator; write via `cat > "${AGENT_HOME}/.claude/settings.json" <<JSON ... JSON` then `chmod 600`; the `> "${` pattern is preserved for `test_harness_config_permissions.py`
- `scripts/harness/codex.sh:17-52` — `configure()`: replace the single heredoc with a brace group `{ ...; } > "${CODEX_HOME}/config.toml"`; inside: `printf 'model_provider = "litellm"\n'` only when `litellm_enabled` (else `log "gateway disabled"`); static block for `approval_policy` and `sandbox_mode` (unconditional, quoted heredoc `<<'STATIC'`); `cat <<LITELLM ... LITELLM` for the `[model_providers.litellm]` table only when `litellm_enabled`; `cat <<OTEL ... OTEL` for `[otel]` and `[otel.span_attributes]` only when `langfuse_enabled` (else `log "tracing disabled"`); `langfuse_otlp_endpoint` and `langfuse_basic_auth` called only inside the `langfuse_enabled` block; `chmod 600` after the brace group (preserves anchor: `> "${` appears in the redirect, chmod comes after)
- `scripts/harness/opencode.sh:21-48` — `configure()`: declare `local entries=()`; push `'  "\$schema": "https://opencode.ai/config.json"'` unconditionally; push `"plugin"` and `"experimental"` entries only when `langfuse_enabled` (else `log "tracing disabled"`); push the full `"provider"` multi-line entry only when `litellm_enabled` (else `log "gateway disabled"`); models loop stays inside the `litellm_enabled` block; push `"permission"` entry unconditionally; join entries in a loop appending `,\n` between them; write `{...}` via `printf '%s\n' "${json}" > "${OPENCODE_CONFIG_DIR}/opencode.json"` then `chmod 600`
- `scripts/harness/claude.sh:61-65` — `doctor()`: READ-ONLY; calls `doctor_gateway` which now handles disabled case internally
- `scripts/harness/codex.sh:59-63` — `doctor()`: READ-ONLY; same
- `scripts/harness/opencode.sh:57-61` — `doctor()`: READ-ONLY; same
- `backend-api/tests/unit/test_harness_scripts.py` — ANCHOR READ-ONLY; all anchors listed in Boundaries must stay green
- `backend-api/tests/unit/test_harness_config_permissions.py` — ANCHOR READ-ONLY; greps for `> "${` redirect then asserts `chmod 600 .*config` comes after; the brace-group and printf-redirect forms both contain the `> "${` substring

## Tasks & Acceptance

**Execution (TDD — write tests first; AC 5 passes immediately against current scripts; ACs 1-4 and 6 fail until implementation):**
- `backend-api/tests/unit/test_harness_scripts_off_mode.py` — CREATE: helper `run_configure(name, env_overrides, tmp_path)` that calls `bash scripts/harness/{name}.sh configure` with a temp `AGENT_HOME`, `CODEX_HOME`, and `env` fixture values merged with overrides; tests for ACs 1-5 call `run_configure` and parse the output file with `json.loads` (claude, opencode) or `tomllib` (codex); for AC 6 write a small wrapper script into `tmp_path` that does `source _common.sh; doctor_gateway`, run it with `LITELLM_BASE_URL=""`, assert exit 0 and `"gateway disabled"` in stderr; `pytestmark = pytest.mark.skipif(shutil.which("bash") is None, ...)`
- `scripts/harness/_common.sh` — EDIT: update `require_harness_env` with two conditional service blocks; add `litellm_enabled` and `langfuse_enabled` helpers immediately after; update `doctor_gateway` with the disabled-path early return
- `scripts/harness/claude.sh` — EDIT: update `configure` with array-based env assembly per Code Map
- `scripts/harness/codex.sh` — EDIT: update `configure` with brace-group conditional sections per Code Map
- `scripts/harness/opencode.sh` — EDIT: update `configure` with array-based top-level key assembly per Code Map

**Acceptance Criteria:**
- Given only PATH and HOME in environment, when each script runs configure, then it exits non-zero naming one of LITELLM_BASE_URL / LANGFUSE_BASE_URL / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
- Given `LITELLM_BASE_URL=""` and Langfuse variables set, when each script runs configure, then it exits 0; claude's settings.json parses as JSON and has no `ANTHROPIC_BASE_URL` key; codex's config.toml parses and has no `model_provider` key and no `[model_providers.litellm]` table; opencode's opencode.json parses and has no `"provider"` key; and all three still contain their OTLP/Langfuse configuration
- Given `LANGFUSE_BASE_URL=""` and gateway variables set, when each script runs configure, then it exits 0; no output file contains `OTEL_EXPORTER_OTLP_ENDPOINT`, an `[otel]` table, or the Langfuse plugin entry; and all three still contain their gateway route
- Given both blank and all other variables set, when each script runs configure, then it exits 0, every output file parses (JSON / TOML), each contains neither the gateway route nor the tracing configuration, and each is mode 600
- Given the committed `.env.example` values, when each script runs configure, then the output file contains all expected keys and sections with their correct values (gateway route, OTEL config, permissions — structurally identical to current output)
- Given `LITELLM_BASE_URL=""`, when a script sourcing `_common.sh` calls `doctor_gateway`, then it exits 0 and stderr contains `"gateway disabled"` without making a network request

## Spec Change Log

## Review Triage Log

### 2026-09-13 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 1, low 1)
- defer: 2: (high 0, medium 1, low 1)
- reject: 11
- addressed_findings:
  - `[medium]` `[patch]` "gateway disabled"/"tracing disabled" log not tested in configure: added stderr assertions to AC 2, AC 3, and AC 4 `_exits_zero` tests
  - `[low]` `[patch]` test_ac3_tracing_off_codex_has_model_provider missing `model_providers` assertion: added `assert "model_providers" in cfg`

## Design Notes

`${VAR+declared}` expands to the string `declared` when VAR is set (even to empty), and to empty string when VAR is unset. So `[ -z "${LITELLM_BASE_URL+declared}" ]` is true only when the variable is unset. Combined with OR: `if [ -z "${LITELLM_BASE_URL+declared}" ] || [ -n "${LITELLM_BASE_URL}" ]` — enters the `:?` block for unset (fires and refuses) or non-blank (passes the check); skips it when declared-blank (off-switch). `${VAR:-}` used in `litellm_enabled` is safe when VAR is unset (expands to empty); `[ -n "" ]` is false, so the function returns non-zero (disabled) for unset and blank alike.

For claude.sh's JSON, entries are strings in a bash array. After the conditional pushes, the join loop writes the first entry bare and prepends `,\n    ` before each subsequent entry. The heredoc writes `    ${env_json}` — the 4-space literal provides the first entry's indent; the separator carries 4 spaces for subsequent lines. Any combination yields syntactically valid JSON with no trailing comma.

For the permissions anchor, the redirect form must contain `> "${` before the `chmod` line. Brace-group redirect (`} > "${CODEX_HOME}/config.toml"`) and printf redirect (`printf ... > "${OPENCODE_CONFIG_DIR}/opencode.json"`) both satisfy this.

## Verification

**Commands:**
- `make lint` -- expected: zero ruff, mypy, import-linter, env-contract violations
- `make test` -- expected: all pytest and vitest tests green, including new `test_harness_scripts_off_mode.py`; anchor `test_harness_scripts.py` and `test_harness_config_permissions.py` still green

## Auto Run Result

**Summary:** Added `litellm_enabled`/`langfuse_enabled` helpers to `_common.sh`; updated `require_harness_env` to skip declared-blank services while still refusing unset ones; gated all configure sections and `doctor_gateway` on the service predicates; created 33 off-mode tests covering all 6 ACs.

**Files changed:**
- `scripts/harness/_common.sh` — added `litellm_enabled`/`langfuse_enabled` predicates, updated `require_harness_env` with conditional blocks, added early return to `doctor_gateway`
- `scripts/harness/claude.sh` — replaced heredoc with array-based conditional env assembly
- `scripts/harness/codex.sh` — replaced single heredoc with brace-group conditional sections piped to cat
- `scripts/harness/opencode.sh` — replaced single heredoc with entries-array approach; provider block via heredoc to preserve literal double-quotes
- `backend-api/tests/unit/test_harness_scripts_off_mode.py` — new file: 33 tests covering ACs 1–6 across all three harnesses

**Review findings breakdown:**
- Patches applied: 2 (medium: log assertions in configure; low: model_providers assertion)
- Items deferred: 2 (low: test file category convention; medium: pre-existing JSON/TOML injection risk in env var interpolation)
- Items rejected: 11

**Follow-up review recommendation score:** 1 medium patch × 3 = 3, 1 low patch × 1 = 1 → score 4/5, threshold not reached → `false`

**Verification performed:**
- `make lint`: passed — zero ruff, mypy, import-linter, env-contract, tsc, eslint, prettier violations
- `make test`: 6125 passed, 23 skipped, 0 failed — new `test_harness_scripts_off_mode.py` and all anchor tests green

**Residual risks:**
- JSON/TOML injection if operator configures `LITELLM_BASE_URL` or `LANGFUSE_ENVIRONMENT` with double-quotes or backslashes (pre-existing; deferred)
