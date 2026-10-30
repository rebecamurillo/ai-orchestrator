#!/usr/bin/env bash
# Codex CLI harness — the only place its environment and config are defined (AD-10).
# Verified against Codex docs 2026-09-02 (research/tracing.md, research/backend.md). TRACEPARENT honouring is source-verified only: day-1 check.
HARNESS_NAME=codex
source "$(dirname "$0")/_common.sh"

# AD-10: codex reads the contract names directly through env_http_headers and env_key; no aliases.
HARNESS_ENV_ALIASES=()
: "${CODEX_VERSION:=0.152.1}"
CODEX_PACKAGE="@openai/codex"
export CODEX_HOME="${CODEX_HOME:-${AGENT_HOME}/.codex}"

# Codex reads $HOME/.agents/skills (+ $CWD/.agents/skills). Named once so `install` and
# `skills` cannot drift; `skills-manifest.json` is written one level above it.
SKILLS_DIR="${AGENT_HOME}/.agents/skills"

install() {
  require_plain_pin CODEX_VERSION "${CODEX_VERSION}"
  npm_install_cli "${HARNESS_IMAGE_PREFIX}" "${CODEX_PACKAGE}" "${CODEX_VERSION}"
  bmad_install_global_skills codex "${SKILLS_DIR}"
  install_operator_skills "${OPERATOR_SKILLS_SRC}" "${SKILLS_DIR}"
}

# Container start, not image build: the operator skills alone, idempotently, because the
# `agent-home` volume shadows the image (`_common.sh::sync_operator_skills`).
skills() {
  sync_operator_skills "${OPERATOR_SKILLS_SRC}" "${SKILLS_DIR}"
}

installed_version() { cli_version_at "$1" '$NF'; }

ensure() {
  ensure_cli_at_pin codex codex "${CODEX_PACKAGE}" CODEX_VERSION "${CODEX_VERSION}" installed_version
}

configure() {
  mkdir -p "${CODEX_HOME}"
  # Provider + auth cannot be overridden by a project .codex/config.toml, so they live here.
  # Sections are conditional: omitted entirely when the service is disabled so the file is
  # valid TOML in all four service combinations. Piped through cat to write the file so the
  # redirect pattern satisfies test_harness_config_permissions.py's grep for `cat > "${`.
  {
    if litellm_enabled; then
      printf 'model_provider = "litellm"\n'
    else
      log "gateway disabled"
    fi
    # wire_api "responses" is the only supported value; LiteLLM serves /v1/responses.
    cat <<'STATIC'
approval_policy = "never"
sandbox_mode = "danger-full-access"      # the container is the sandbox (AD-10); bwrap/seccomp may not work under cap_drop ALL
STATIC
    if litellm_enabled; then
      cat <<LITELLM

[model_providers.litellm]
name = "LiteLLM"
base_url = "${LITELLM_BASE_URL%/}/v1"
env_key = "LITELLM_API_KEY"
wire_api = "responses"
# A BMAD turn is a long single stream — planning, edits, a gate run — and the default idle
# timeout is far shorter than one. LiteLLM's own Codex guide sets this; without it a turn
# that thinks for a while is cut off as idle. Not a retry (hard rule 7): the two retry knobs
# that guide also sets are deliberately left at their defaults, because a silently repeated
# dispatch is exactly what that rule forbids.
stream_idle_timeout_ms = 7200000
# Per-attempt headers by environment variable NAME (AD-10): values come from env_for(attempt), never from this file.
env_http_headers = { langfuse_session_id = "ORCH_RUN_ID", langfuse_tags = "ORCH_LANGFUSE_TAGS", x-litellm-end-user-id = "ORCH_RUN_ID", x-litellm-session-id = "ORCH_ATTEMPT_ID", x-litellm-tags = "ORCH_TAGS" }
LITELLM
    fi
    if langfuse_enabled; then
      cat <<OTEL

[otel]
environment = "${LANGFUSE_ENVIRONMENT:-mvp}"
log_user_prompt = false
trace_exporter = { otlp-http = { endpoint = "$(langfuse_otlp_endpoint)/v1/traces", protocol = "binary", headers = { Authorization = "Basic $(langfuse_basic_auth)", x-langfuse-ingestion-version = "4" } } }
metrics_exporter = "none"

[otel.span_attributes]
"service.name" = "codex-cli"
OTEL
    else
      log "tracing disabled"
    fi
  } | cat > "${CODEX_HOME}/config.toml"
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
  doctor_skill_present "${SKILLS_DIR}"
  doctor_gateway
}

probe() {
  local version_str
  if ! command -v codex >/dev/null 2>&1; then
    probe_output false "cli not installed" "" "[]"; exit 1
  fi
  version_str=$(codex --version 2>&1 | awk '{print $NF}')
  if [ "$version_str" != "${CODEX_VERSION}" ]; then
    probe_output false "cli not at pinned version ${CODEX_VERSION}" "${version_str}" "[]"
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
  # `ensure` reads only the pin: no Gateway or Langfuse value, exactly as `install` does not
  ensure)                 ensure ;;
  # `skills` reads no Gateway or Langfuse value, exactly as `install` does not
  skills)                 skills ;;
  configure|doctor)       require_harness_env; "$1" ;;
  probe)                  require_harness_env; probe ;;
  *)                      echo "usage: $0 install|ensure|skills|configure|doctor|probe" >&2; exit 2 ;;
esac
