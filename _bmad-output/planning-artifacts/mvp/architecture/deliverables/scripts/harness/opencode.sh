#!/usr/bin/env bash
# OpenCode harness (`local`) — the only place its environment and config are defined (AD-10).
# Verified against OpenCode + Langfuse docs 2026-09-02 (research/tracing.md, research/backend.md).
# No inbound TRACEPARENT exists: correlation is by Langfuse session/user id only (AD-11).
HARNESS_NAME=opencode
source "$(dirname "$0")/_common.sh"
: "${OPENCODE_VERSION:=1.18.26}"
: "${LOCAL_MODELS:=local-coder,local-general}"
: "${LANGFUSE_OPENCODE_PLUGIN_VERSION:=0.3.0}"
OPENCODE_CONFIG_DIR="${AGENT_HOME}/.config/opencode"

install() {
  npm install -g "opencode-ai@${OPENCODE_VERSION}"
  # OpenCode reads ~/.claude/skills and ~/.agents/skills too; the codex.sh stubs suffice. Install its own dir anyway so it stands alone.
  bmad_install_global_skills opencode "${OPENCODE_CONFIG_DIR}/skills"
}

configure() {
  mkdir -p "${OPENCODE_CONFIG_DIR}"
  local models="" m
  IFS=',' read -ra arr <<< "${LOCAL_MODELS}"
  for m in "${arr[@]}"; do models+="\"${m}\": {\"name\": \"${m}\"},"; done
  models="${models%,}"
  # @ai-sdk/openai-compatible against LiteLLM (the anthropic provider + baseURL drops the key — open bug). Auto-approval is config-driven (`permission`); `opencode run --auto` also exists.
  cat > "${OPENCODE_CONFIG_DIR}/opencode.json" <<JSON
{
  "\$schema": "https://opencode.ai/config.json",
  "plugin": ["@langfuse/opencode-observability-plugin@${LANGFUSE_OPENCODE_PLUGIN_VERSION}"],
  "experimental": { "openTelemetry": true },
  "provider": {
    "litellm": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LiteLLM",
      "options": { "baseURL": "${LITELLM_BASE_URL%/}/v1", "apiKey": "{env:LITELLM_API_KEY}",
                   "headers": { "langfuse_session_id": "{env:ORCH_RUN_ID}", "langfuse_tags": "{env:ORCH_LANGFUSE_TAGS}", "x-litellm-end-user-id": "{env:ORCH_RUN_ID}", "x-litellm-session-id": "{env:ORCH_ATTEMPT_ID}", "x-litellm-tags": "{env:ORCH_TAGS}" } },
      "models": { ${models} }
    }
  },
  "permission": { "edit": "allow", "bash": "allow", "webfetch": "deny" }
}
JSON
  log "wrote ${OPENCODE_CONFIG_DIR}/opencode.json"
}

# Per-attempt env the adapter adds:
#   LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASEURL=$LANGFUSE_BASE_URL   (plugin spells it BASEURL)
#   LANGFUSE_USER_ID=<run_id>  LANGFUSE_ENVIRONMENT
#   ORCH_RUN_ID, ORCH_TAGS, ORCH_LANGFUSE_TAGS — read by the {env:...} references in options.headers above (AD-10: names, not values).
# Invocation shape (PRD FR-14, provisional): opencode run --format json --dir <worktree> -m litellm/<model> "<prompt>";
#   session id from JSON events, fallback ~/.local/share/opencode/opencode.db (session.directory = worktree).

doctor() {
  opencode --version
  doctor_skill_present "${OPENCODE_CONFIG_DIR}/skills"
  doctor_gateway
}

case "${1:-}" in install|configure|doctor) "$1" ;; *) echo "usage: $0 install|configure|doctor" >&2; exit 2 ;; esac
