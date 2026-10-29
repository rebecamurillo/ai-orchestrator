#!/usr/bin/env bash
# Shared helpers for scripts/harness/<name>.sh. Sourced, never executed.
# Contract (AD-10, AD-20): each harness script implements
#   install    — image build: install the CLI at the pinned version, copy BMAD skill stubs to the global dirs
#   ensure     — container start, before configure: reinstall the CLI only when it is not at its pin
#   configure  — container start: (re)generate the harness config from environment variables
#   doctor     — readiness: print version, confirm skill discovery and gateway reachability; exit ≠ 0 on failure
set -euo pipefail

: "${AGENT_HOME:=/home/agent}"
: "${BMAD_VERSION:=6.11.0}"

# `install` runs during `docker build`, where the Gateway and Langfuse values do not exist
# and must never be baked into an image layer or passed as a build argument. Only the two
# verbs that read those values require them, so the guard is a function the dispatcher in
# <harness>.sh calls for `configure` and `doctor` and not for `install`.
require_harness_env() {
  # Blank (declared as "") means the service is disabled — skip the check.
  # Unset means the operator forgot — fire :? and refuse.
  if [ -z "${LITELLM_BASE_URL+declared}" ] || [ -n "${LITELLM_BASE_URL}" ]; then
    : "${LITELLM_BASE_URL:?set it in .env, copied from .env.example}"
  fi
  if [ -z "${LANGFUSE_BASE_URL+declared}" ] || [ -n "${LANGFUSE_BASE_URL}" ]; then
    : "${LANGFUSE_BASE_URL:?set it in .env, copied from .env.example}"
    : "${LANGFUSE_PUBLIC_KEY:?set it in .env, copied from .env.example}"
    : "${LANGFUSE_SECRET_KEY:?set it in .env, copied from .env.example}"
  fi
}

# Service-state predicates — the sole conditionals for gateway/tracing decisions.
# ${VAR:-} is safe under set -u: unset expands to empty → [ -n "" ] = false = disabled.
litellm_enabled() { [ -n "${LITELLM_BASE_URL:-}" ]; }
langfuse_enabled() { [ -n "${LANGFUSE_BASE_URL:-}" ]; }

# AD-10: this list is NORMATIVE. It is exactly what env_for(attempt) exports to every harness, plus the harness's own
# HARNESS_ENV_ALIASES (declared in <harness>.sh, derived from these) and the Project's env vars. Config files reference
# these NAMES, never values. Never LITELLM_SPEND_KEY, never GITHUB_TOKEN (AD-5).
HARNESS_ENV_CONTRACT=(ORCH_RUN_ID ORCH_ATTEMPT_ID ORCH_STORY_ID ORCH_HARNESS ORCH_PROJECT ORCH_TAGS ORCH_LANGFUSE_TAGS TRACEPARENT
  LITELLM_BASE_URL LITELLM_API_KEY LANGFUSE_BASE_URL LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_ENVIRONMENT ORCH_LOG_CONTENT)
# Header values the adapter derives from the contract (same for every harness):
#   ORCH_TAGS = run:$ORCH_RUN_ID,attempt:$ORCH_ATTEMPT_ID,story:$ORCH_STORY_ID,harness:$ORCH_HARNESS,project:$ORCH_PROJECT
#   langfuse_session_id=$ORCH_RUN_ID  langfuse_tags=[json of ORCH_TAGS]
#     — each harness carries that JSON array through its own header mechanism: claude in an
#       ANTHROPIC_CUSTOM_HEADERS line, codex as an env NAME in TOML, opencode through the alias
#       OPENCODE_LANGFUSE_TAGS, escaped, because opencode.json is substituted before it is parsed
#   x-litellm-end-user-id=$ORCH_RUN_ID  x-litellm-session-id=$ORCH_ATTEMPT_ID  x-litellm-tags=$ORCH_TAGS   (spend logs: GET /spend/logs/v2?end_user=&session_id=)

log() { printf '[harness:%s] %s\n' "${HARNESS_NAME:-?}" "$*" >&2; }

# The harness CLIs' own npm prefix, the mount point of the `harness-bin` volume, and the
# image-only prefix `install` writes at build time (never mounted, so a volume never hides
# it). Both kept apart from NPM_CONFIG_PREFIX (/opt/npm-global), which holds the image's
# corepack shims and whatever an agent installs during a Run. Overridable only so a test can
# point them at scratch directories.
: "${HARNESS_PREFIX:=/opt/harness-cli}"
: "${HARNESS_IMAGE_PREFIX:=/opt/harness-image}"

# The pin shape every reader of a harness pin accepts. A test keeps its four copies identical:
# scripts/harness/_common.sh, deploy/install.sh, scripts/push-images.sh, release.yml.
PLAIN_VERSION='^[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}([-+][0-9A-Za-z.-]+)?$'

require_plain_pin() {  # $1 pin variable name, $2 value
  [[ "$2" =~ $PLAIN_VERSION ]] && return 0
  log "$1='$2' is not a plain version (x.y.z)"
  return 1
}

# The one npm line `install` (image build) and `ensure` (container start) both run. npm's own
# fetch retries are off (hard rule 7) and the whole call is bounded, so a stalled registry
# cannot outlast the container's healthcheck.
npm_install_cli() {  # $1 prefix, $2 npm package, $3 version
  timeout 120 npm install -g --prefix "$1" --fetch-retries=0 --fetch-timeout=60000 "$2@$3"
}

# The first stdout line of `<executable> --version`, field $2 of it; empty when absent.
cli_version_at() {  # $1 executable path, $2 awk field ($1 or $NF)
  [ -x "$1" ] || return 0
  { timeout 30 "$1" --version 2>/dev/null || true; } | head -1 | awk "{print $2}"
}

# Leftovers of a start interrupted inside `_place_cli`: a half-staged `.next` is dropped; a
# `.prev` is put back when the live copy is missing, and dropped when the live copy landed.
_recover_cli() {  # $1 npm package, $2 cli
  local live="${HARNESS_PREFIX}/lib/node_modules/$1" link="${HARNESS_PREFIX}/bin/$2"
  rm -rf "${live}.next"
  rm -f "${link}.next"
  if [ -e "${live}.prev" ]; then
    if [ -e "$live" ]; then rm -rf "${live}.prev"; else mv "${live}.prev" "$live"; fi
  fi
  if [ -L "${link}.prev" ] || [ -e "${link}.prev" ]; then
    if [ -L "$link" ] || [ -e "$link" ]; then rm -f "${link}.prev"; else mv "${link}.prev" "$link"; fi
  fi
}

# A failed swap: the new copy is removed and the one set aside is put back.
_undo_place() {  # $1 npm package, $2 cli
  local live="${HARNESS_PREFIX}/lib/node_modules/$1" link="${HARNESS_PREFIX}/bin/$2"
  if [ -e "${live}.prev" ]; then rm -rf "$live"; mv "${live}.prev" "$live"; fi
  if [ -L "${link}.prev" ] || [ -e "${link}.prev" ]; then rm -f "$link"; mv "${link}.prev" "$link"; fi
  rm -rf "${live}.next"
  rm -f "${link}.next"
}

# Replace the volume's copy of one package and its bin link with $1's. The new copy is staged
# as `.next`, the old one renamed to `.prev`, `.next` renamed into place, and only then is
# `.prev` removed. A failed step puts `.prev` back; a start interrupted between the renames
# leaves no live copy for a moment, and the next start's `_recover_cli` restores it.
_place_cli() {  # $1 source prefix, $2 npm package, $3 cli, $4 cp|mv
  local live="${HARNESS_PREFIX}/lib/node_modules/$2" link="${HARNESS_PREFIX}/bin/$3"
  mkdir -p "$(dirname "$live")" "${HARNESS_PREFIX}/bin" || return 1
  _recover_cli "$2" "$3"
  if [ "$4" = cp ]; then
    cp -a "$1/lib/node_modules/$2" "${live}.next" || { rm -rf "${live}.next"; return 1; }
  else
    mv "$1/lib/node_modules/$2" "${live}.next" || return 1
  fi
  cp -a "$1/bin/$3" "${link}.next" || { _undo_place "$2" "$3"; return 1; }
  if [ -e "$live" ]; then mv "$live" "${live}.prev" || { _undo_place "$2" "$3"; return 1; }; fi
  if [ -L "$link" ] || [ -e "$link" ]; then
    mv "$link" "${link}.prev" || { _undo_place "$2" "$3"; return 1; }
  fi
  if ! { mv "${live}.next" "$live" && mv "${link}.next" "$link"; }; then
    _undo_place "$2" "$3"
    return 1
  fi
  rm -rf "${live}.prev"
  rm -f "${link}.prev"
}

# `ensure`: the CLI on the `harness-bin` volume reconciled against the pin `.env` sets, in
# this order: the image's own copy when it is at the pin (copied over the volume's on every
# start, no network, so a changed volume copy is restored); else the volume's copy when it is
# at the pin; else exactly one npm install into a staging prefix, moved in only when it
# reports the pin, never retried (hard rule 7). Versions are read from those absolute paths,
# never the first match on PATH. A non-zero exit refuses that harness only: ensure-all.sh
# continues, and the probe reports `cli not at pinned version` until the next start.
ensure_cli_at_pin() {  # $1 harness, $2 cli, $3 npm package, $4 pin variable name, $5 pin, $6 version-reading function
  local name="$1" cli="$2" pkg="$3" pin="$5" reader="$6" have staging staged
  require_plain_pin "$4" "$pin" || { log "${name} refused"; return 1; }
  if [ "$("$reader" "${HARNESS_IMAGE_PREFIX}/bin/${cli}")" = "$pin" ]; then
    if _place_cli "${HARNESS_IMAGE_PREFIX}" "$pkg" "$cli" cp; then
      log "${name} ${pin} from image"
      return 0
    fi
    log "${name}: copying ${pin} from ${HARNESS_IMAGE_PREFIX} failed"
  fi
  _recover_cli "$pkg" "$cli"
  have="$("$reader" "${HARNESS_PREFIX}/bin/${cli}")"
  if [ "$have" = "$pin" ]; then log "${name} ${pin} at pin"; return 0; fi
  log "${name} ${have:-absent} → ${pin}"
  staging="${HARNESS_PREFIX}/.staging/${name}"
  rm -rf "$staging"
  if ! mkdir -p "$staging" 2>/dev/null; then
    log "${name}: cannot create ${staging}"
    return 1
  fi
  if ! npm_install_cli "$staging" "$pkg" "$pin"; then
    rm -rf "$staging"
    log "${name}: npm install ${pkg}@${pin} failed (installed: $(_now "$reader" "$cli"), pin: ${pin})"
    return 1
  fi
  staged="$("$reader" "${staging}/bin/${cli}")"
  if [ "$staged" != "$pin" ]; then
    rm -rf "$staging"
    log "${name}: after install the cli reports ${staged:-absent}, not the pin ${pin} (installed: $(_now "$reader" "$cli"))"
    return 1
  fi
  if ! _place_cli "$staging" "$pkg" "$cli" mv; then
    rm -rf "$staging"
    log "${name}: moving ${pin} into ${HARNESS_PREFIX} failed (installed: $(_now "$reader" "$cli"), pin: ${pin})"
    return 1
  fi
  rm -rf "$staging"
  log "${name} ${pin} at pin"
}

# What the volume's CLI reports now, for a failure line.
_now() {  # $1 version-reading function, $2 cli
  local v
  v="$("$1" "${HARNESS_PREFIX}/bin/$2")"
  printf '%s' "${v:-absent}"
}

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

# Where the operator skills are read from. `/app/ia-agents-skills` in the image and
# `<repo>/ia-agents-skills` in a non-image run (`make local`) are the same expression: both
# are the grandparent of this file's own directory. Overridable so a test can point it at a
# scratch tree without reaching into any harness script.
_harness_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${OPERATOR_SKILLS_SRC:=$(dirname "$(dirname "$_harness_scripts_dir")")/ia-agents-skills}"

# One JSON array of the arguments, escaped. Printed, not returned.
_json_array() {
  local json='[' i=0 name escaped
  for name in "$@"; do
    escaped="${name//\\/\\\\}"     # \ → \\
    escaped="${escaped//\"/\\\"}"  # " → \"
    [ "$i" -gt 0 ] && json="${json},"
    json="${json}\"${escaped}\""
    i=$((i+1))
  done
  printf '%s]' "$json"
}

# A digest of a directory's file names and contents, so two skill trees can be compared
# without diffutils. python3 is already this file's dependency (probe_gateway_models).
_dir_digest() {
  python3 - "$1" <<'PY'
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob("*")):
    digest.update(path.relative_to(root).as_posix().encode() + b"\0")
    if path.is_file():
        digest.update(path.read_bytes())
print(digest.hexdigest())
PY
}

# Write the sorted skills-manifest.json one level above $1 (the dest skills dir), naming
# every skill directory now present in it. This file is the instance's skill catalog: the
# installed-skill pre-flight check reads it (infrastructure/skill_catalog.py), and a run
# time that cannot read it can only report "catalog unavailable".
# Sets SKILLS_MANIFEST_PATH and SKILLS_MANIFEST_COUNT for the caller.
write_skills_manifest() {
  local dest="$1" manifest d
  manifest="$(dirname "$dest")/skills-manifest.json"
  local skill_names=()
  if [ -d "$dest" ]; then
    while IFS= read -r d; do
      skill_names+=("$(basename "$d")")
    done < <(find "$dest" -mindepth 1 -maxdepth 1 -type d | sort)
  fi
  printf '{"skills":%s}\n' "$(_json_array "${skill_names[@]+"${skill_names[@]}"}")" > "$manifest"
  SKILLS_MANIFEST_PATH="$manifest"
  SKILLS_MANIFEST_COUNT="${#skill_names[@]}"
  log "skills manifest → $manifest (${#skill_names[@]} skills)"
}

# Operator skills at container start (hub-Run operations, skills install fix, 2026-09-24).
# `install_operator_skills` below runs during `docker build` and refuses a name that already
# exists, because at build time that can only be a collision with a BMAD stub. This one runs
# on every boot, against a dest that already holds whatever an earlier boot installed, and is
# therefore idempotent rather than refusing: `${AGENT_HOME}` is the mount point of the
# `agent-home` volume, and Docker seeds a named volume from the image only while the volume
# is empty — so a skill added to the image after the volume was created is invisible at run
# time, silently, for the life of the volume, and so is the manifest that names it.
#
# Copies a skill the dest lacks, replaces one whose image copy differs (the image is the
# source of truth — an instance must not run a skill nobody shipped), leaves an identical one
# alone, never removes anything, and always rewrites the manifest. Prints one JSON line on
# stdout naming what changed, which is what the backend logs.
sync_operator_skills() {
  local src="$1" dest="$2" d name
  local installed=() updated=()
  mkdir -p "$dest"
  if [ -d "$src" ]; then
    while IFS= read -r d; do
      name="$(basename "$d")"
      if [ ! -d "$dest/$name" ]; then
        cp -R "$d" "$dest/"
        installed+=("$name")
      elif [ "$(_dir_digest "$d")" != "$(_dir_digest "$dest/$name")" ]; then
        rm -rf "${dest:?}/${name:?}"
        cp -R "$d" "$dest/"
        updated+=("$name")
      fi
    done < <(find "$src" -mindepth 1 -maxdepth 1 -type d | sort)
  else
    log "operator skills source not found, nothing to copy: $src"
  fi
  write_skills_manifest "$dest"
  log "operator skills → $dest (installed ${#installed[@]}, updated ${#updated[@]})"
  printf '{"dest":"%s","installed":%s,"updated":%s,"skills":%s}\n' \
    "$dest" \
    "$(_json_array "${installed[@]+"${installed[@]}"}")" \
    "$(_json_array "${updated[@]+"${updated[@]}"}")" \
    "$SKILLS_MANIFEST_COUNT"
}

# Operator skills: copy every subdirectory from $1 (ia-agents-skills source) into $2 (dest
# skills dir), detect name collisions against already-installed stubs, and write a sorted
# skills-manifest.json one level above $2. Called after bmad_install_global_skills so
# stubs are already present when collision detection runs. AD-16. Build time only — a boot
# runs `sync_operator_skills` above, which is idempotent where this one refuses.
install_operator_skills() {
  local src="$1" dest="$2"

  # Collect ALL collision names before deciding to exit (operator sees every problem at once).
  local collisions=()
  if [ -d "$src" ]; then
    local d
    while IFS= read -r d; do
      local name
      name="$(basename "$d")"
      [ -d "$dest/$name" ] && collisions+=("$name")
    done < <(find "$src" -mindepth 1 -maxdepth 1 -type d | sort)
  fi
  if [ "${#collisions[@]}" -gt 0 ]; then
    log "operator skill name collision(s) with installed stubs: ${collisions[*]}"
    exit 1
  fi

  # Copy operator skill subdirectories to dest.
  if [ -d "$src" ]; then
    mkdir -p "$dest"
    while IFS= read -r d; do
      cp -R "$d" "$dest/"
    done < <(find "$src" -mindepth 1 -maxdepth 1 -type d | sort)
  fi

  # Write sorted skills-manifest.json enumerating every skill dir now present in dest.
  write_skills_manifest "$dest"
}

doctor_skill_present() {  # $1 = skills dir
  [ -f "$1/bmad-build-auto/SKILL.md" ] || { log "bmad-build-auto not found in $1"; return 1; }
  log "bmad-build-auto discoverable in $1"
}

doctor_gateway() {
  if ! litellm_enabled; then log "gateway disabled"; return 0; fi
  curl -fsS -H "Authorization: Bearer ${LITELLM_API_KEY:?}" "${LITELLM_BASE_URL%/}/v1/models" >/dev/null \
    && log "gateway reachable at ${LITELLM_BASE_URL}" || { log "gateway unreachable"; return 1; }
}

# Emit one JSON line to stdout: {"ok":<bool>,"failing_reason":<null|string>,"version":"<ver>","models":<array>}.
# $1 = ok (true|false), $2 = reason (literal "null" for null, else the reason string),
# $3 = version string, $4 = models JSON array (e.g. "[]" or '["m1","m2"]').
probe_output() {
  local ok="$1" reason="$2" version="$3" models_json="$4"
  if [ "$reason" = "null" ]; then
    printf '{"ok":%s,"failing_reason":null,"version":"%s","models":%s}\n' \
      "$ok" "$version" "$models_json"
  else
    printf '{"ok":%s,"failing_reason":"%s","version":"%s","models":%s}\n' \
      "$ok" "$reason" "$version" "$models_json"
  fi
}

# Check gateway reachability for probe(). Sets PROBE_MODELS_OK (true/false),
# PROBE_MODELS_REASON (failing reason or empty), and PROBE_MODELS_JSON (array or "[]").
# When gateway is disabled, sets ok=true with an empty models list (Design Notes, 2-1).
probe_gateway_models() {
  if ! litellm_enabled; then
    PROBE_MODELS_OK=true; PROBE_MODELS_REASON=""; PROBE_MODELS_JSON="[]"; return 0
  fi
  local tmpfile http_code
  tmpfile=$(mktemp)
  if ! http_code=$(curl -s -w '%{http_code}' -o "$tmpfile" \
      -H "Authorization: Bearer ${LITELLM_API_KEY:?}" \
      "${LITELLM_BASE_URL%/}/v1/models" 2>/dev/null); then
    rm -f "$tmpfile"
    PROBE_MODELS_OK=false; PROBE_MODELS_REASON="gateway unreachable"; PROBE_MODELS_JSON="[]"
    return 0
  fi
  if [ "$http_code" = "401" ]; then
    rm -f "$tmpfile"
    PROBE_MODELS_OK=false; PROBE_MODELS_REASON="not logged in"; PROBE_MODELS_JSON="[]"
    return 0
  fi
  if [ "${http_code:-000}" -lt 200 ] 2>/dev/null || [ "${http_code:-000}" -ge 300 ] 2>/dev/null; then
    rm -f "$tmpfile"
    PROBE_MODELS_OK=false; PROBE_MODELS_REASON="gateway unreachable"; PROBE_MODELS_JSON="[]"
    return 0
  fi
  PROBE_MODELS_JSON=$(python3 -c "import json;d=json.load(open('${tmpfile}'));print(json.dumps([m['id'] for m in d.get('data',[])]))" 2>/dev/null) || PROBE_MODELS_JSON="[]"
  rm -f "$tmpfile"
  PROBE_MODELS_OK=true; PROBE_MODELS_REASON=""
}
