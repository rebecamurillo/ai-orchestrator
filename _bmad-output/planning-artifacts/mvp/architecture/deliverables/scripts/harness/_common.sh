#!/usr/bin/env bash
# Shared helpers for scripts/harness/<name>.sh. Sourced, never executed.
# Contract (AD-10, AD-20): each harness script implements
#   install    — image build: install the CLI at the pinned version, copy BMAD skill stubs to the global dirs
#   configure  — container start: (re)generate the harness config from environment variables
#   doctor     — readiness: print version, confirm skill discovery and gateway reachability; exit ≠ 0 on failure
set -euo pipefail

: "${AGENT_HOME:=/home/agent}"
: "${BMAD_VERSION:=6.11.0}"
: "${LITELLM_BASE_URL:?}"
: "${LANGFUSE_BASE_URL:?}"
: "${LANGFUSE_PUBLIC_KEY:?}"
: "${LANGFUSE_SECRET_KEY:?}"

# AD-10: the only per-attempt values a harness process receives. Config files reference these NAMES, never values.
HARNESS_ENV_CONTRACT=(ORCH_RUN_ID ORCH_ATTEMPT_ID ORCH_STORY_ID ORCH_HARNESS ORCH_PROJECT TRACEPARENT
  LITELLM_BASE_URL LITELLM_API_KEY LANGFUSE_BASE_URL LANGFUSE_BASEURL LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_ENVIRONMENT LANGFUSE_USER_ID ORCH_LOG_CONTENT)
# Header values the adapter derives from the contract (same for every harness):
#   ORCH_TAGS = run:$ORCH_RUN_ID,attempt:$ORCH_ATTEMPT_ID,story:$ORCH_STORY_ID,harness:$ORCH_HARNESS,project:$ORCH_PROJECT
#   langfuse_session_id=$ORCH_RUN_ID  langfuse_tags=[json of ORCH_TAGS]
#   x-litellm-end-user-id=$ORCH_RUN_ID  x-litellm-session-id=$ORCH_ATTEMPT_ID  x-litellm-tags=$ORCH_TAGS   (spend logs: GET /spend/logs/v2?end_user=&session_id=)

log() { printf '[harness:%s] %s\n' "${HARNESS_NAME:-?}" "$*" >&2; }

# Langfuse OTLP endpoint + Basic auth header (research/tracing.md)
langfuse_otlp_endpoint() { printf '%s/api/public/otel' "${LANGFUSE_BASE_URL%/}"; }
langfuse_basic_auth()    { printf '%s' "${LANGFUSE_PUBLIC_KEY}:${LANGFUSE_SECRET_KEY}" | base64 | tr -d '\n'; }

# BMAD skill stubs: installed once into a scratch project, then copied to the global skill dirs.
# BMAD has no global mode (research/backend.md); the target repo still needs its own _bmad/ (AD-16).
bmad_install_global_skills() {
  local tools="$1" dest="$2" tmp
  tmp="$(mktemp -d)"
  ( cd "$tmp" && git init -q . && npx --yes "bmad-method@${BMAD_VERSION}" install --yes --modules bmm --tools "$tools" --directory "$tmp" )
  mkdir -p "$dest"
  case "$tools" in
    claude-code) cp -R "$tmp/.claude/skills/." "$dest/" ;;
    *)           cp -R "$tmp/.agents/skills/." "$dest/" ;;
  esac
  rm -rf "$tmp"
  log "BMAD ${BMAD_VERSION} skill stubs → $dest ($(ls "$dest" | wc -l | tr -d ' ') skills)"
}

doctor_skill_present() {  # $1 = skills dir
  [ -f "$1/bmad-build-auto/SKILL.md" ] || { log "bmad-build-auto not found in $1"; return 1; }
  log "bmad-build-auto discoverable in $1"
}

doctor_gateway() {
  curl -fsS -H "Authorization: Bearer ${LITELLM_API_KEY:?}" "${LITELLM_BASE_URL%/}/v1/models" >/dev/null \
    && log "gateway reachable at ${LITELLM_BASE_URL}" || { log "gateway unreachable"; return 1; }
}
