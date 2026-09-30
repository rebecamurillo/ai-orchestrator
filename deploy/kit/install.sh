#!/usr/bin/env bash
# kit/install.sh — wire a consumer project up to an ai-orchestrator instance.
#
# Copies the `orchestrator` skill (SKILL.md + references/) into the project's
# `.claude/skills/` so its agents know the API protocol, and makes sure the two
# connection values exist in the project's `.env`. Idempotent: re-running refreshes the
# skill and never overwrites an existing value.
#
#   ./install.sh /path/to/project                       # skill + .env placeholders
#   ORCHESTRATOR_TOKEN=... ./install.sh /path/to/project  # also fills the token and pings
#
# The alternative to this script is the plugin route inside Claude Code:
#   /plugin marketplace add OptimAI-labs/ai-orchestrator && /plugin install orchestrator@optimai
# Both deliver the same skill; this script exists for projects that vendor skills directly.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project="${1:?usage: install.sh /path/to/project}"
project="$(cd "$project" && pwd)"

base_url="${ORCHESTRATOR_BASE_URL:-http://127.0.0.1:8000}"
token="${ORCHESTRATOR_TOKEN:-}"

[[ -d "$project" ]] || { echo "$project: not a directory" >&2; exit 1; }
[[ -f "$here/skills/orchestrator/SKILL.md" ]] || {
  echo "run this script from a checkout or an extracted release bundle — skills/orchestrator is missing beside it" >&2
  exit 1
}

# ── the skill ────────────────────────────────────────────────────────────────
skills_dir="$project/.claude/skills"
mkdir -p "$skills_dir"
rm -rf "$skills_dir/orchestrator"
cp -R "$here/skills/orchestrator" "$skills_dir/orchestrator"
echo "skill    $skills_dir/orchestrator (SKILL.md + $(find "$skills_dir/orchestrator/references" -name '*.md' | wc -l | tr -d ' ') references)"

# ── the connection values ────────────────────────────────────────────────────
env_file="$project/.env"
touch "$env_file"

ensure() {
  local name="$1" value="$2"
  if grep -q "^${name}=" "$env_file"; then
    echo "env      ${name} already set in .env — left alone"
  else
    printf '%s=%s\n' "$name" "$value" >> "$env_file"
    if [[ -n "$value" ]]; then echo "env      ${name} written to .env"
    else echo "env      ${name}= added to .env — FILL IT IN"; fi
  fi
}

ensure ORCHESTRATOR_BASE_URL "$base_url"
ensure ORCHESTRATOR_TOKEN "$token"

# ── prove the pair works, when we have both ──────────────────────────────────
# read back from .env so a pre-existing value is what gets tested
read_env() { grep "^${1}=" "$env_file" | head -1 | cut -d= -f2-; }
base_url="$(read_env ORCHESTRATOR_BASE_URL)"
token="$(read_env ORCHESTRATOR_TOKEN)"

if [[ -n "$token" ]]; then
  if curl -fsS -H "Authorization: Bearer ${token}" "${base_url}/api/v1/ping" >/dev/null 2>&1; then
    echo "ping     ${base_url}/api/v1/ping — token accepted"
  else
    echo "ping     ${base_url}/api/v1/ping FAILED — is the stack up, and is the token right?" >&2
    exit 1
  fi
else
  echo "ping     skipped — set ORCHESTRATOR_TOKEN in ${env_file} and re-run to verify"
fi

echo
echo "Done. Open Claude Code in ${project} — the 'orchestrator' skill covers connection,"
echo "project/repository setup, launching runs, polling, and signals. The spec-folder"
echo "format (epics.yaml / stories.yaml / SPEC.md) is references/spec-folder.md."
