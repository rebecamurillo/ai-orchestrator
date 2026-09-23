#!/usr/bin/env bash
# Claude Code harness — the only place its environment and config are defined (AD-10).
# Verified against Claude Code docs 2026-09-02 (research/tracing.md, research/backend.md). Re-verify flags when CLAUDE_CODE_VERSION changes.
# `claude auth status --json` (probe_claude_login, below) verified live against the pinned
# CLI in-container 2026-09-23 — output shape {"loggedIn": bool, ...}; re-verify alongside the
# rest of this file's flags when CLAUDE_CODE_VERSION changes.
HARNESS_NAME=claude
source "$(dirname "$0")/_common.sh"

# AD-10: harness-native names env_for(attempt) derives from HARNESS_ENV_CONTRACT for claude (name=source).
HARNESS_ENV_ALIASES=(ANTHROPIC_AUTH_TOKEN=LITELLM_API_KEY ANTHROPIC_CUSTOM_HEADERS=derived)
# The array above is API-key mode, which is the default (CLAUDE_SUBSCRIPTION_AUTH=false).
# With CLAUDE_SUBSCRIPTION_AUTH=true the adapter builds a different set for this one harness:
# ANTHROPIC_AUTH_TOKEN is NOT exported — Claude Code is logged in against the operator's own
# Claude subscription and that OAuth token must hold Authorization — and the virtual key
# moves into ANTHROPIC_CUSTOM_HEADERS as `x-litellm-api-key: Bearer $LITELLM_API_KEY`.
# That mode also needs `forward_client_headers_to_llm_api: true` on the Gateway and one
# `claude login` inside the container; both are host-side and documented in host/README.md.
: "${CLAUDE_CODE_VERSION:=2.1.258}"

install() {
  npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"
  bmad_install_global_skills claude-code "${AGENT_HOME}/.claude/skills"     # Claude reads ~/.claude/skills, not ~/.agents/skills
  install_operator_skills /app/ia-agents-skills "${AGENT_HOME}/.claude/skills"
}

configure() {
  mkdir -p "${AGENT_HOME}/.claude"
  # Static settings only. Per-attempt values (TRACEPARENT, langfuse_session_id, tags, model, budget) are
  # injected by infrastructure/harness/claude/adapter.py env_for(attempt). Nothing here is per Run.
  # Build env entries conditionally so the file is valid JSON for every service combination.
  local env_entries=()
  if litellm_enabled; then
    env_entries+=("\"ANTHROPIC_BASE_URL\": \"${LITELLM_BASE_URL%/}\"")
  else
    log "gateway disabled"
  fi
  if langfuse_enabled; then
    env_entries+=(
      "\"CLAUDE_CODE_ENABLE_TELEMETRY\": \"1\""
      "\"CLAUDE_CODE_ENHANCED_TELEMETRY_BETA\": \"1\""
      "\"CLAUDE_CODE_PROPAGATE_TRACEPARENT\": \"1\""
      "\"OTEL_TRACES_EXPORTER\": \"otlp\""
      "\"OTEL_METRICS_EXPORTER\": \"none\""
      "\"OTEL_LOGS_EXPORTER\": \"none\""
      "\"OTEL_EXPORTER_OTLP_PROTOCOL\": \"http/protobuf\""
      "\"OTEL_EXPORTER_OTLP_ENDPOINT\": \"$(langfuse_otlp_endpoint)\""
      "\"OTEL_EXPORTER_OTLP_HEADERS\": \"Authorization=Basic $(langfuse_basic_auth),x-langfuse-ingestion-version=4\""
      "\"OTEL_RESOURCE_ATTRIBUTES\": \"service.name=claude-code,deployment.environment=${LANGFUSE_ENVIRONMENT:-mvp}\""
    )
  else
    log "tracing disabled"
  fi
  env_entries+=("\"DISABLE_AUTOUPDATER\": \"1\"")
  # Join entries with ",\n    " — first entry has no leading separator; no trailing comma.
  local env_json="" i
  for i in "${!env_entries[@]}"; do
    if [ "$i" -eq 0 ]; then
      env_json="${env_entries[$i]}"
    else
      env_json="${env_json},
    ${env_entries[$i]}"
    fi
  done
  cat > "${AGENT_HOME}/.claude/settings.json" <<JSON
{
  "env": {
    ${env_json}
  }
}
JSON
  # Langfuse OTLP authenticates with HTTP Basic, so this file necessarily carries
  # LANGFUSE_SECRET_KEY in reversible base64, and `agent-home` outlives `make down`.
  chmod 600 "${AGENT_HOME}/.claude/settings.json"
  log "wrote ${AGENT_HOME}/.claude/settings.json"
}

# Per-attempt env the adapter adds on top (documented here so the contract is in one file):
#   ANTHROPIC_AUTH_TOKEN=$LITELLM_API_KEY                      (Bearer to the gateway; never ANTHROPIC_API_KEY)
#                                                              (absent when CLAUDE_SUBSCRIPTION_AUTH=true)
#   ANTHROPIC_CUSTOM_HEADERS="langfuse_session_id: $ORCH_RUN_ID\nlangfuse_tags: <json ORCH_TAGS>\nx-litellm-end-user-id: $ORCH_RUN_ID\nx-litellm-session-id: $ORCH_ATTEMPT_ID\nx-litellm-tags: $ORCH_TAGS"
#                                        (plus "x-litellm-api-key: Bearer $LITELLM_API_KEY" when CLAUDE_SUBSCRIPTION_AUTH=true)
#   TRACEPARENT=00-<run trace id>-<attempt span id>-01           (read by `claude -p`; parents claude_code.* spans under the Run)
#   OTEL_LOG_USER_PROMPTS=1 / OTEL_LOG_TOOL_CONTENT=1            only when Project.log_prompt_content is true
# Invocation shape (PRD FR-14; --bare is unusable): claude -p --session-id <uuid> --permission-mode dontAsk
#   --allowedTools $CLAUDE_ALLOWED_TOOLS --disallowedTools "mcp__*" --output-format json --max-budget-usd <remaining> "<prompt>"

doctor() {
  claude --version
  doctor_skill_present "${AGENT_HOME}/.claude/skills"
  doctor_gateway
  doctor_claude_login
}

# In subscription mode `claude -p` authenticates via `claude login`'s own OAuth session,
# never `LITELLM_API_KEY` (AD-10) — `probe_gateway_models` tests the Gateway key only, so it
# cannot see a missing or expired login. This is a fast, no-spend check against that same
# session — `--json` is `claude auth status`'s own flag, distinct from the `--output-format
# json` the per-attempt `claude -p` invocation uses (two different subcommands, two different
# flag surfaces) — timeout-bounded at 10s (worst case; the happy path is sub-second) so a
# stalled CLI can never slow `probe()` down. Exit codes distinguish *why* it failed:
# 0 = logged in, 1 = logged out, 2 = timed out, 3 = cli/parse error (missing binary, renamed
# subcommand, non-JSON stdout) — `probe()` turns each into its own `failing_reason` rather
# than reporting every cause as "not logged in".
# The Python is embedded in a single-quoted bash string: it must never itself contain a `'`.
probe_claude_login() {
  python3 -c '
import json, subprocess, sys
try:
    result = subprocess.run(
        ["claude", "auth", "status", "--json"],
        capture_output=True, text=True, timeout=10, check=False,
    )
except subprocess.TimeoutExpired:
    sys.exit(2)
except OSError:
    sys.exit(3)
try:
    data = json.loads(result.stdout)
except json.JSONDecodeError:
    sys.exit(3)
sys.exit(0 if data.get("loggedIn") else 1)
'
}

doctor_claude_login() {
  [ "${CLAUDE_SUBSCRIPTION_AUTH:-false}" = "true" ] || return 0
  probe_claude_login && { log "claude auth: logged in"; return 0; }
  log "claude auth: not logged in (claude auth status)"
  return 1
}

probe() {
  local version_str login_rc
  if ! command -v claude >/dev/null 2>&1; then
    probe_output false "cli not installed" "" "[]"; exit 1
  fi
  # Unlike codex/opencode, `claude --version` prints "<version> (Claude Code)" — the
  # version is the first field, not the last.
  version_str=$(claude --version 2>&1 | awk '{print $1}')
  if [ "$version_str" != "${CLAUDE_CODE_VERSION}" ]; then
    probe_output false "cli not at pinned version ${CLAUDE_CODE_VERSION}" "${version_str}" "[]"
    exit 1
  fi
  if [ "${CLAUDE_SUBSCRIPTION_AUTH:-false}" = "true" ]; then
    login_rc=0
    probe_claude_login || login_rc=$?
    case "$login_rc" in
      0) : ;;
      2) probe_output false "claude auth status timed out" "${version_str}" "[]"; exit 1 ;;
      3) probe_output false "claude auth status failed (cli error)" "${version_str}" "[]"; exit 1 ;;
      *) probe_output false "not logged in (claude auth status)" "${version_str}" "[]"; exit 1 ;;
    esac
  fi
  probe_gateway_models
  if [ "${PROBE_MODELS_OK}" = "true" ]; then
    probe_output true "null" "${version_str}" "${PROBE_MODELS_JSON}"; exit 0
  fi
  probe_output false "${PROBE_MODELS_REASON}" "${version_str}" "[]"; exit 1
}

case "${1:-}" in
  install)                install ;;
  configure|doctor)       require_harness_env; "$1" ;;
  probe)                  require_harness_env; probe ;;
  *)                      echo "usage: $0 install|configure|doctor|probe" >&2; exit 2 ;;
esac
