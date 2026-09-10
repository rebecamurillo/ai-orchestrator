---
story: "9-5"
epic: 9
title: Harness scripts configure and doctor what exists
requirements: [NFR-7, AR-16]
binds: [AD-5, AD-10, AD-20]
---

# Story 9.5 — The scripts configure and probe what exists

As the Operator,
I want `docker-entrypoint.sh` to finish on an instance with no Gateway and no Langfuse, writing each harness a config for the services that are actually there,
So that the container starts instead of stopping at `configure`, and `doctor` tells me what is off rather than that something is broken.

## Scope

**In:** `scripts/harness/_common.sh` (two enabled tests, the guard's branches, `doctor_gateway`), and the `configure`/`doctor` bodies of `claude.sh`, `codex.sh`, `opencode.sh`.
**Out:** `backend-api/docker-entrypoint.sh`, which is already correct: it configures all three harnesses and then serves, and needs no change. No new variable (AD-20): the switch is the blank base URL 9-1 defined.

## Binding rules (inlined)

- **Unset still refuses; blank disables.** The guard keeps its four literal refusals — `${LITELLM_BASE_URL:?…}`, `${LANGFUSE_BASE_URL:?…}`, `${LANGFUSE_PUBLIC_KEY:?…}`, `${LANGFUSE_SECRET_KEY:?…}` — and wraps each service's in a test that distinguishes *declared* from *non-blank*:

      require_harness_env() {
        if [ -z "${LITELLM_BASE_URL+declared}" ] || [ -n "${LITELLM_BASE_URL}" ]; then
          : "${LITELLM_BASE_URL:?set it in .env, copied from .env.example (blank disables the Gateway)}"
        fi
        if [ -z "${LANGFUSE_BASE_URL+declared}" ] || [ -n "${LANGFUSE_BASE_URL}" ]; then
          : "${LANGFUSE_BASE_URL:?…}" ; : "${LANGFUSE_PUBLIC_KEY:?…}" ; : "${LANGFUSE_SECRET_KEY:?…}"
        fi
      }

  Unset enters the branch and the `:?` fires, naming the variable; blank skips it. This is not decoration: `tests/unit/test_harness_scripts.py::test_configure_refuses_with_nothing_configured` runs `configure` with only `PATH` and `HOME` and requires a non-zero exit naming one of those four, and `test_the_guard_names_every_variable_configure_needs` greps the guard's text for each `${NAME:?`. Both must stay green untouched.
- **Two helpers, used everywhere else:** `litellm_enabled() { [ -n "${LITELLM_BASE_URL:-}" ]; }` and `langfuse_enabled() { [ -n "${LANGFUSE_BASE_URL:-}" ]; }`. Every conditional below is one of these two; no script re-derives the rule.
- **`require_harness_env` stays in the `configure|doctor` dispatch line and stays out of `install`** — two more anchors (`test_configure_and_doctor_check_the_environment_first`, `test_install_does_not_check_the_gateway_environment`).
- **Config files carry names, not values.** No script may expand `${LITELLM_API_KEY` (anchor: `test_a_config_file_is_written_with_variable_names_not_values`), and `GITHUB_TOKEN` / `LITELLM_SPEND_KEY` appear in no script (AD-5, anchor). Every file is still written `chmod 600` (`test_harness_config_permissions.py`).
- **What each `configure` writes when a service is off:**
  - `claude.sh` — Gateway off: no `ANTHROPIC_BASE_URL` entry, so Claude Code uses its own endpoint and the login in `AGENT_HOME/.claude`. Tracing off: no `CLAUDE_CODE_ENABLE_TELEMETRY`, no `OTEL_*` entries, and `DISABLE_AUTOUPDATER` and the rest stay. The file must remain valid JSON in all four combinations — assemble the `env` entries as a list and join them, so no branch can leave a trailing comma.
  - `codex.sh` — Gateway off: no `model_provider` line and no `[model_providers.litellm]` table, so Codex uses its own provider and the login in `CODEX_HOME`; `approval_policy` and `sandbox_mode` are unconditional. Tracing off: no `[otel]` and no `[otel.span_attributes]` tables.
  - `opencode.sh` — Gateway off: no `provider` block at all (the `local` harness is disabled in that mode, 9-4) and a log line saying so; the `permission` block and `$schema` stay. Tracing off: no `plugin` entry and no `experimental.openTelemetry`.
- **`doctor` probes only what exists.** `doctor_gateway` returns success with `log "gateway disabled"` when `litellm_enabled` is false; the version check and `doctor_skill_present` are unconditional. A doctor that reported a disabled service as unreachable would be a false alarm, and one that reported it as reachable would be a lie.
- **The mode is stated, once per script, at `configure`:** `log "gateway disabled"` / `log "tracing disabled"` on the same `[harness:<name>]` stream everything else uses.

## Acceptance criteria

**Given** an environment with only `PATH` and `HOME`
**When** each of the three scripts runs `configure`
**Then** it exits non-zero naming one of the four guard variables — unchanged behaviour, asserted by the existing anchor.

**Given** `LITELLM_BASE_URL=""` and the Langfuse variables set
**When** each script runs `configure`
**Then** it exits 0; `claude`'s `settings.json` parses as JSON and has no `ANTHROPIC_BASE_URL`; `codex`'s `config.toml` parses and has no `model_provider` and no `[model_providers.litellm]`; `opencode`'s `opencode.json` parses and has no `provider`; and all three still contain their OTLP/Langfuse configuration.

**Given** `LANGFUSE_BASE_URL=""` and the Gateway variables set
**When** each script runs `configure`
**Then** it exits 0; no file contains an `OTEL_EXPORTER_OTLP_ENDPOINT`, an `[otel]` table or the Langfuse plugin; and all three still contain their Gateway route.

**Given** both blank
**When** each script runs `configure`
**Then** it exits 0, every file parses, each contains neither the Gateway route nor the tracing configuration, and each is `600`.

**Given** both set to the committed `.env.example` values
**When** each script runs `configure`
**Then** the file it writes is byte-for-byte what it writes today.

**Given** `LITELLM_BASE_URL=""`
**When** `doctor` runs
**Then** it exits 0, prints the version and the skill line, and logs `gateway disabled` without making a request.

## Implementation notes

- New test file: `backend-api/tests/unit/test_harness_scripts_off_mode.py`, running the real scripts with `bash` against a temporary `AGENT_HOME`/`CODEX_HOME` the way `test_harness_scripts.py` already shells out. Parse the written files with `json.loads` and `tomllib` rather than substring-matching whatever is easy to grep.
- The byte-for-byte case above is the guard against a refactor that "cleans up" the enabled path; write it first.
- Keep `_common.sh`'s normative `HARNESS_ENV_CONTRACT` array untouched (9-4 depends on it, and a test compares it to the Python tuple in both directions).

## Verification

```bash
make lint && make test
```

## Sources for detail only

Spine AD-10 (the script is the only place a harness's config is defined), AD-5 (never `GITHUB_TOKEN`, never `LITELLM_SPEND_KEY`), AD-20. `scripts/harness/_common.sh` — the guard's own comment on why `install` is exempt. `backend-api/docker-entrypoint.sh` — the start-up order that makes a refusal here stop the container.
