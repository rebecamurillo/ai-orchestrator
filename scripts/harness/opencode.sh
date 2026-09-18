#!/usr/bin/env bash
# OpenCode harness (`local`) — the only place its environment and config are defined (AD-10).
# Verified against OpenCode + Langfuse docs 2026-09-02 (research/tracing.md, research/backend.md).
# No inbound TRACEPARENT exists: correlation is by Langfuse session/user id only (AD-11).
HARNESS_NAME=opencode
source "$(dirname "$0")/_common.sh"

# AD-10: harness-native names env_for(attempt) derives from HARNESS_ENV_CONTRACT for opencode (name=source).
HARNESS_ENV_ALIASES=(LANGFUSE_BASEURL=LANGFUSE_BASE_URL LANGFUSE_USER_ID=ORCH_RUN_ID)
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
  # Build top-level JSON entries conditionally so the file is valid JSON for every service
  # combination. Entries are joined with ",\n" — no leading or trailing comma.
  # @ai-sdk/openai-compatible against LiteLLM (the anthropic provider + baseURL drops the key — open bug). Auto-approval is config-driven (`permission`); `opencode run --auto` also exists.
  local entries=()
  entries+=('  "$schema": "https://opencode.ai/config.json"')
  if langfuse_enabled; then
    entries+=("  \"plugin\": [\"@langfuse/opencode-observability-plugin@${LANGFUSE_OPENCODE_PLUGIN_VERSION}\"]")
    entries+=('  "experimental": { "openTelemetry": true }')
  else
    log "tracing disabled"
  fi
  if litellm_enabled; then
    local models="" m provider_entry
    IFS=',' read -ra arr <<< "${LOCAL_MODELS}"
    for m in "${arr[@]}"; do models+="\"${m}\": {\"name\": \"${m}\"},"; done
    models="${models%,}"
    provider_entry=$(cat <<ENTRY
  "provider": {
    "litellm": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LiteLLM",
      "options": { "baseURL": "${LITELLM_BASE_URL%/}/v1", "apiKey": "{env:LITELLM_API_KEY}",
                   "headers": { "langfuse_session_id": "{env:ORCH_RUN_ID}", "langfuse_tags": "{env:ORCH_LANGFUSE_TAGS}", "x-litellm-end-user-id": "{env:ORCH_RUN_ID}", "x-litellm-session-id": "{env:ORCH_ATTEMPT_ID}", "x-litellm-tags": "{env:ORCH_TAGS}" } },
      "models": { ${models} }
    }
  }
ENTRY
)
    entries+=("${provider_entry}")
  else
    log "gateway disabled"
  fi
  entries+=('  "permission": { "edit": "allow", "bash": "allow", "webfetch": "deny" }')
  # Join entries: open brace, first entry bare, subsequent entries with leading ",\n", close brace.
  local json="{" i
  for i in "${!entries[@]}"; do
    if [ "$i" -eq 0 ]; then
      json="${json}"$'\n'"${entries[$i]}"
    else
      json="${json}"$',\n'"${entries[$i]}"
    fi
  done
  json="${json}"$'\n}'
  printf '%s\n' "${json}" | cat > "${OPENCODE_CONFIG_DIR}/opencode.json"
  # No key material today; held to the same mode so the three cannot drift apart.
  chmod 600 "${OPENCODE_CONFIG_DIR}/opencode.json"
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

probe() {
  local version_str
  if ! command -v opencode >/dev/null 2>&1; then
    probe_output false "cli not installed" "" "[]"; exit 1
  fi
  version_str=$(opencode --version 2>&1 | awk '{print $NF}')
  if [ "$version_str" != "${OPENCODE_VERSION}" ]; then
    probe_output false "cli not at pinned version ${OPENCODE_VERSION}" "${version_str}" "[]"
    exit 1
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
