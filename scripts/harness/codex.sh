#!/usr/bin/env bash
# Codex CLI harness — the only place its environment and config are defined (AD-10).
# Verified against Codex docs 2026-09-02 (research/tracing.md, research/backend.md). TRACEPARENT honouring is source-verified only: day-1 check.
HARNESS_NAME=codex
source "$(dirname "$0")/_common.sh"

# AD-10: codex reads the contract names directly through env_http_headers and env_key; no aliases.
HARNESS_ENV_ALIASES=()
: "${CODEX_VERSION:=0.152.1}"
export CODEX_HOME="${CODEX_HOME:-${AGENT_HOME}/.codex}"

install() {
  npm install -g "@openai/codex@${CODEX_VERSION}"
  bmad_install_global_skills codex "${AGENT_HOME}/.agents/skills"           # Codex reads $HOME/.agents/skills (+ $CWD/.agents/skills)
}

configure() {
  mkdir -p "${CODEX_HOME}"
  # Provider + auth cannot be overridden by a project .codex/config.toml, so they live here.
  # wire_api "responses" is the only supported value; LiteLLM serves /v1/responses.
  cat > "${CODEX_HOME}/config.toml" <<TOML
model_provider = "litellm"
approval_policy = "never"
sandbox_mode = "danger-full-access"      # the container is the sandbox (AD-10); bwrap/seccomp may not work under cap_drop ALL

[model_providers.litellm]
name = "LiteLLM"
base_url = "${LITELLM_BASE_URL%/}/v1"
env_key = "LITELLM_API_KEY"
wire_api = "responses"
# Per-attempt headers by environment variable NAME (AD-10): values come from env_for(attempt), never from this file.
env_http_headers = { langfuse_session_id = "ORCH_RUN_ID", langfuse_tags = "ORCH_LANGFUSE_TAGS", x-litellm-end-user-id = "ORCH_RUN_ID", x-litellm-session-id = "ORCH_ATTEMPT_ID", x-litellm-tags = "ORCH_TAGS" }

[otel]
environment = "${LANGFUSE_ENVIRONMENT:-mvp}"
log_user_prompt = false
trace_exporter = { otlp-http = { endpoint = "$(langfuse_otlp_endpoint)/v1/traces", protocol = "binary", headers = { Authorization = "Basic $(langfuse_basic_auth)", x-langfuse-ingestion-version = "4" } } }
metrics_exporter = "none"

[otel.span_attributes]
"service.name" = "codex-cli"
TOML
  # No key material today; held to the same mode so the three cannot drift apart.
  chmod 600 "${CODEX_HOME}/config.toml"
  log "wrote ${CODEX_HOME}/config.toml"
}

# Per-attempt values arrive ONLY through the environment (HARNESS_ENV_CONTRACT in _common.sh): ORCH_RUN_ID, ORCH_TAGS,
# ORCH_LANGFUSE_TAGS (JSON string), TRACEPARENT, LITELLM_API_KEY. If a `-c key=value` override is ever needed, quote the value
# as a TOML string: -c 'otel.span_attributes.run_id="<run_id>"' — an unquoted [..] parses as a TOML array and is rejected.
# Invocation shape (PRD FR-14, provisional): codex exec --json -C <worktree> -m <model> -o <last.md> "<prompt>"; session id from the thread.started event.

doctor() {
  codex --version
  doctor_skill_present "${AGENT_HOME}/.agents/skills"
  doctor_gateway
}

case "${1:-}" in
  install)          install ;;
  configure|doctor) require_harness_env; "$1" ;;
  *)                echo "usage: $0 install|configure|doctor" >&2; exit 2 ;;
esac
