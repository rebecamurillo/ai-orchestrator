#!/usr/bin/env bash
# OpenCode harness (`local`) — the only place its environment and config are defined (AD-10).
# Verified against OpenCode + Langfuse docs 2026-09-02 (research/tracing.md, research/backend.md).
# No inbound TRACEPARENT exists: correlation is by Langfuse session/user id only (AD-11).
HARNESS_NAME=opencode
source "$(dirname "$0")/_common.sh"

# AD-10: harness-native names env_for(attempt) derives from HARNESS_ENV_CONTRACT for opencode (name=source).
# OPENCODE_LANGFUSE_TAGS is ORCH_LANGFUSE_TAGS escaped for the JSON string it is substituted into
# below — OpenCode expands {env:...} textually, before parsing (adapter.py::local_aliases).
HARNESS_ENV_ALIASES=(LANGFUSE_BASEURL=LANGFUSE_BASE_URL LANGFUSE_USER_ID=ORCH_RUN_ID OPENCODE_LANGFUSE_TAGS=ORCH_LANGFUSE_TAGS)
: "${OPENCODE_VERSION:=1.18.26}"
: "${LOCAL_MODELS:=local-coder,local-general}"
: "${LANGFUSE_OPENCODE_PLUGIN_VERSION:=0.3.0}"
OPENCODE_CONFIG_DIR="${AGENT_HOME}/.config/opencode"

# OpenCode's own skills dir. Named once so `install`, `skills` and `doctor` cannot drift;
# `skills-manifest.json` is written one level above it.
SKILLS_DIR="${OPENCODE_CONFIG_DIR}/skills"

install() {
  npm install -g "opencode-ai@${OPENCODE_VERSION}"
  # OpenCode reads ~/.claude/skills and ~/.agents/skills too; the codex.sh stubs suffice. Install its own dir anyway so it stands alone.
  bmad_install_global_skills opencode "${SKILLS_DIR}"
  install_operator_skills "${OPERATOR_SKILLS_SRC}" "${SKILLS_DIR}"
}

# Container start, not image build: the operator skills alone, idempotently, because the
# `agent-home` volume shadows the image (`_common.sh::sync_operator_skills`).
skills() {
  sync_operator_skills "${OPERATOR_SKILLS_SRC}" "${SKILLS_DIR}"
}

configure() {
  mkdir -p "${OPENCODE_CONFIG_DIR}"
  # Build top-level JSON entries conditionally so the file is valid JSON for every service
  # combination. Entries are joined with ",\n" — no leading or trailing comma.
  # @ai-sdk/openai-compatible against LiteLLM (the anthropic provider + baseURL drops the key — open bug). Auto-approval is config-driven (`permission`); `opencode run --auto` also exists.
  # Every {env:NAME} below is substituted TEXTUALLY, before OpenCode parses this file as JSON(C),
  # so a value carrying a `"` would break the document rather than land in it. That is why the
  # tags arrive as OPENCODE_LANGFUSE_TAGS, pre-escaped by adapter.py::local_aliases, and why any
  # future reference to a value that is not plain text needs the same treatment. `probe` runs
  # `opencode models`, which parses this file, so a config this breaks fails readiness.
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
                   "headers": { "langfuse_session_id": "{env:ORCH_RUN_ID}", "langfuse_tags": "{env:OPENCODE_LANGFUSE_TAGS}", "x-litellm-end-user-id": "{env:ORCH_RUN_ID}", "x-litellm-session-id": "{env:ORCH_ATTEMPT_ID}", "x-litellm-tags": "{env:ORCH_TAGS}" } },
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
#   ORCH_RUN_ID, ORCH_ATTEMPT_ID, ORCH_TAGS, OPENCODE_LANGFUSE_TAGS — read by the {env:...} references in options.headers above (AD-10: names, not values).
# Invocation shape (PRD FR-14, provisional): opencode run --format json --dir <worktree> -m litellm/<model> "<prompt>";
#   session id from JSON events, fallback ~/.local/share/opencode/opencode.db (session.directory = worktree).

# `opencode models` is the cheapest thing that makes OpenCode read, substitute and PARSE
# opencode.json: it opens no session and calls no model, it exits 1 on a config it cannot parse
# and 0 on one it can, and it prints the provider/model pairs the file configures. Before this
# existed, `configure` wrote a file nothing validated until a dispatch ran, and a config that
# every dispatch died on left readiness green (defect of 2026-09-20).
#
# The reference values are this check's own, and deliberately shaped like an attempt's rather
# than blank: a `{env:NAME}` whose variable is unset substitutes to nothing, which parses, so a
# blank environment would be a check that cannot fail. They do not prove the escaping is right —
# only Python builds the real values, so `tests/unit/test_opencode_config_substitution.py` is
# what holds that — they prove this file survives a realistic substitution.
config_parses() {
  if ! litellm_enabled; then return 0; fi
  ORCH_RUN_ID="${ORCH_RUN_ID:-probe-run}" \
  ORCH_ATTEMPT_ID="${ORCH_ATTEMPT_ID:-probe-attempt}" \
  ORCH_TAGS="${ORCH_TAGS:-run:probe-run,attempt:probe-attempt,story:,harness:local,project:probe}" \
  OPENCODE_LANGFUSE_TAGS="${OPENCODE_LANGFUSE_TAGS:-[\\\"run:probe-run\\\",\\\"attempt:probe-attempt\\\",\\\"story:\\\",\\\"harness:local\\\",\\\"project:probe\\\"]}" \
    opencode models >/dev/null 2>&1
}

doctor() {
  opencode --version
  doctor_skill_present "${SKILLS_DIR}"
  config_parses \
    && log "config parses: ${OPENCODE_CONFIG_DIR}/opencode.json" \
    || { log "config unparseable: ${OPENCODE_CONFIG_DIR}/opencode.json"; return 1; }
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
  if ! config_parses; then
    probe_output false "config unparseable" "${version_str}" "[]"; exit 1
  fi
  probe_gateway_models
  if [ "${PROBE_MODELS_OK}" = "true" ]; then
    probe_output true "null" "${version_str}" "${PROBE_MODELS_JSON}"; exit 0
  fi
  probe_output false "${PROBE_MODELS_REASON}" "${version_str}" "[]"; exit 1
}

case "${1:-}" in
  install)                install ;;
  # `skills` reads no Gateway or Langfuse value, exactly as `install` does not
  skills)                 skills ;;
  configure|doctor)       require_harness_env; "$1" ;;
  probe)                  require_harness_env; probe ;;
  *)                      echo "usage: $0 install|skills|configure|doctor|probe" >&2; exit 2 ;;
esac
