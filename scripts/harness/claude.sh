#!/usr/bin/env bash
# Claude Code harness — the only place its environment and config are defined (AD-10).
# Verified against Claude Code docs 2026-09-02 (research/tracing.md, research/backend.md). Re-verify flags when CLAUDE_CODE_VERSION changes.
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
}

configure() {
  mkdir -p "${AGENT_HOME}/.claude"
  # Static settings only. Per-attempt values (TRACEPARENT, langfuse_session_id, tags, model, budget) are
  # injected by infrastructure/harness/claude/adapter.py env_for(attempt). Nothing here is per Run.
  cat > "${AGENT_HOME}/.claude/settings.json" <<JSON
{
  "env": {
    "ANTHROPIC_BASE_URL": "${LITELLM_BASE_URL%/}",
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    "CLAUDE_CODE_PROPAGATE_TRACEPARENT": "1",
    "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_METRICS_EXPORTER": "none",
    "OTEL_LOGS_EXPORTER": "none",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "$(langfuse_otlp_endpoint)",
    "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Basic $(langfuse_basic_auth),x-langfuse-ingestion-version=4",
    "OTEL_RESOURCE_ATTRIBUTES": "service.name=claude-code,deployment.environment=${LANGFUSE_ENVIRONMENT:-mvp}",
    "DISABLE_AUTOUPDATER": "1"
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
}

case "${1:-}" in
  install)          install ;;
  configure|doctor) require_harness_env; "$1" ;;
  *)                echo "usage: $0 install|configure|doctor" >&2; exit 2 ;;
esac
