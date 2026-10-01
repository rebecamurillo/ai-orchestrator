#!/usr/bin/env bash
# kit/install.sh — plug one project repository into a running ai-orchestrator instance.
#
#   install.sh [--harness claude|codex|opencode|all] [--base-url URL] [--token TOKEN] [--project DIR]
#
#   --harness    which agent CLI reads the skills, default `all`:
#                claude → <project>/.claude/skills/ ; codex, opencode → <project>/.agents/skills/
#   --base-url   the instance; default $ORCHESTRATOR_BASE_URL, else http://127.0.0.1:8000
#   --token      its bearer; default $ORCHESTRATOR_TOKEN. Without one the version probe is
#                skipped and the script says how to set it
#   --project    where to install; default the current directory. A bare path argument works too
#
# The documented call, from inside the project, against a running instance — the kit comes
# out of the instance that answers, so the skills can never be a different version than it:
#
#   curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
#     "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness claude
#
# In a checkout or an extracted bundle, `skills/` beside this script is used instead and
# nothing is downloaded.
#
# What it writes, all of it idempotent: each skill under the per-harness directory (an
# existing copy is replaced), the kit's commands in <project>/.orchestrator/bin/ (executable;
# the PATH line is printed), ORCHESTRATOR_BASE_URL and ORCHESTRATOR_TOKEN in <project>/.env
# (an existing value is left alone), and <project>/.orchestrator/kit.json — the version
# marker the skill's handshake reads. kit.json carries no credential and is meant to be
# committed.
#
# Portable bash 3.2 (a stock macOS): no associative arrays, no `sed -i`, no `mapfile`.
# The token is never printed, never logged, and never written outside .env.
set -euo pipefail

self="${BASH_SOURCE[0]:-}"
here=""
# read from a pipe, `$BASH_SOURCE` names no readable file — every use of it is guarded
if [[ -n "$self" && -f "$self" ]]; then here="$(cd "$(dirname "$self")" && pwd)"; fi

harness="all"
base_url_arg=""
token_arg=""
project_arg=""

# ── output ───────────────────────────────────────────────────────────────────
say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

# A heredoc, not `sed -n` over this file the way deploy/install.sh does it: read from a pipe
# there is no file to re-read, and `--help` has to work on the documented call.
usage() {
	cat <<'TEXT'
install.sh [--harness claude|codex|opencode|all] [--base-url URL] [--token TOKEN] [--project DIR]

  --harness    which agent CLI reads the skills, default `all`:
               claude → <project>/.claude/skills/ ; codex, opencode → <project>/.agents/skills/
  --base-url   the instance; default $ORCHESTRATOR_BASE_URL, else http://127.0.0.1:8000
  --token      its bearer; default $ORCHESTRATOR_TOKEN. Without one the version probe is
               skipped and the script says how to set it
  --project    where to install; default the current directory. A bare path argument works too

Writes the skills into the per-harness directory, the kit's commands into
<project>/.orchestrator/bin/, ORCHESTRATOR_BASE_URL and ORCHESTRATOR_TOKEN into
<project>/.env (never overwriting a value), and <project>/.orchestrator/kit.json.
TEXT
}

# ── arguments ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
	case "$1" in
		--harness) [[ $# -ge 2 ]] || die "--harness needs a value"; harness="$2"; shift ;;
		--harness=*) harness="${1#--harness=}" ;;
		--base-url) [[ $# -ge 2 ]] || die "--base-url needs a value"; base_url_arg="$2"; shift ;;
		--base-url=*) base_url_arg="${1#--base-url=}" ;;
		--token) [[ $# -ge 2 ]] || die "--token needs a value"; token_arg="$2"; shift ;;
		--token=*) token_arg="${1#--token=}" ;;
		--project) [[ $# -ge 2 ]] || die "--project needs a value"; project_arg="$2"; shift ;;
		--project=*) project_arg="${1#--project=}" ;;
		-h|--help) usage; exit 0 ;;
		-*) die "unknown argument: $1 (try --help)" ;;
		# the pre-2026-09-30 call was `install.sh /path/to/project`
		*) project_arg="$1" ;;
	esac
	shift
done

case "$harness" in
	claude|codex|opencode|all) ;;
	*) die "--harness takes claude, codex, opencode or all (got '${harness}')" ;;
esac

project="${project_arg:-$PWD}"
[[ -d "$project" ]] || die "${project}: not a directory — pass --project /path/to/your/repo"
project="$(cd "$project" && pwd)"

base_url="${base_url_arg:-${ORCHESTRATOR_BASE_URL:-http://127.0.0.1:8000}}"
base_url="${base_url%/}"
token="${token_arg:-${ORCHESTRATOR_TOKEN:-}}"

# ── small helpers ────────────────────────────────────────────────────────────
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "$1 is not installed — $2"; }

scratch=""
trap '[[ -z "$scratch" ]] || rm -rf "$scratch"' EXIT

# the string value of a top-level key, without python: one key per line, quotes stripped
json_string() {
	tr -d ' \t\n' < "$1" | tr ',' '\n' |
		sed -n 's/^{*"'"$2"'":"\([^"]*\)".*/\1/p' | head -1
}

# The one-liner that replaces a stale kit. `$ORCHESTRATOR_TOKEN` stays a variable name here:
# the credential is not in the line the user reads, copies, or pastes into a bug report.
reinstall_line() {
	printf 'curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness %s' "$harness"
}

# ── where the skills come from ───────────────────────────────────────────────
kit_dir=""
resolve_kit() {
	if [[ -n "$here" && -d "${here}/skills" ]]; then
		kit_dir="$here"
		return 0
	fi
	need_cmd curl "install curl — it fetches the kit from the instance"
	need_cmd tar "install tar — it unpacks the kit"
	[[ -n "$token" ]] ||
		die "no skills/ beside this script, so the kit comes from ${base_url} — pass --token or export ORCHESTRATOR_TOKEN"
	scratch="$(mktemp -d)"
	curl -fsSL -H "Authorization: Bearer ${token}" -o "${scratch}/kit.tar.gz" \
		"${base_url}/api/v1/kit/archive" ||
		die "${base_url}/api/v1/kit/archive did not answer — is the instance up, and is the token right?"
	tar -xzf "${scratch}/kit.tar.gz" -C "$scratch" ||
		die "what ${base_url}/api/v1/kit/archive returned is not a readable tar.gz"
	[[ -d "${scratch}/skills" ]] || die "the archive from ${base_url}/api/v1/kit/archive carries no skills/"
	kit_dir="$scratch"
	say "kit      fetched from ${base_url}/api/v1/kit/archive"
}

# ── the skills ───────────────────────────────────────────────────────────────
written=""
install_skills() {
	local dirs rel target src name count
	case "$harness" in
		claude) dirs=".claude/skills" ;;
		codex|opencode) dirs=".agents/skills" ;;
		all) dirs=".claude/skills .agents/skills" ;;
	esac
	for rel in $dirs; do
		target="${project}/${rel}"
		mkdir -p "$target"
		count=0
		for src in "${kit_dir}"/skills/*/; do
			src="${src%/}"
			[[ -f "${src}/SKILL.md" ]] || continue
			name="${src##*/}"
			rm -rf "${target}/${name}"
			cp -R "$src" "${target}/${name}"
			count=$((count + 1))
		done
		[[ "$count" -gt 0 ]] || die "${kit_dir}/skills holds no skill with a SKILL.md"
		say "skills   ${target} (${count})"
		written="${written}${target}"$'\n'
	done
}

# ── the commands ─────────────────────────────────────────────────────────────
bin_target=""
install_bin() {
	local src name count
	[[ -d "${kit_dir}/bin" ]] || return 0
	bin_target="${project}/.orchestrator/bin"
	mkdir -p "$bin_target"
	count=0
	for src in "${kit_dir}"/bin/*; do
		[[ -f "$src" ]] || continue
		name="${src##*/}"
		cp "$src" "${bin_target}/${name}"
		# the archive's mode survives tar, a checkout's does not survive every filesystem
		chmod +x "${bin_target}/${name}"
		count=$((count + 1))
	done
	if [[ "$count" -eq 0 ]]; then bin_target=""; return 0; fi
	say "bin      ${bin_target} (${count})"
	say "         on PATH: export PATH=\"${bin_target}:\$PATH\""
}

# ── the connection values ────────────────────────────────────────────────────
env_file=""

ensure() {
	local name="$1" value="$2"
	if grep -q "^${name}=" "$env_file"; then
		say "env      ${name} already set in .env — left alone"
	else
		printf '%s=%s\n' "$name" "$value" >> "$env_file"
		if [[ -n "$value" ]]; then say "env      ${name} written to .env"
		else say "env      ${name}= added to .env — FILL IT IN"; fi
	fi
}

install_env() {
	env_file="${project}/.env"
	touch "$env_file"
	# an appended line must not land on the tail of an unterminated one
	if [[ -s "$env_file" && -n "$(tail -c 1 "$env_file")" ]]; then printf '\n' >> "$env_file"; fi
	ensure ORCHESTRATOR_BASE_URL "$base_url"
	ensure ORCHESTRATOR_TOKEN "$token"
}

# read back from .env, so a pre-existing value is what the marker records and the probe tests
read_env() { grep "^${1}=" "$env_file" | head -1 | cut -d= -f2-; }

# ── the version marker ───────────────────────────────────────────────────────
kit_version=""
marker=""
install_marker() {
	local manifest="${kit_dir}/manifest.json"
	marker="${project}/.orchestrator/kit.json"
	[[ -f "$manifest" ]] || die "manifest.json is missing beside the skills — the kit is incomplete"
	kit_version="$(json_string "$manifest" kit_version)"
	[[ -n "$kit_version" ]] || die "${manifest} declares no kit_version"
	mkdir -p "${project}/.orchestrator"
	printf '{\n  "kit_version": "%s",\n  "base_url": "%s",\n  "installed_at": "%s",\n  "harness": "%s"\n}\n' \
		"$kit_version" "$base_url" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$harness" > "$marker"
	say "marker   ${marker} (kit ${kit_version}; no credential — commit it)"
}

# ── prove the pair, and name a skew ──────────────────────────────────────────
http_code() {   # http_code URL OUTFILE → the status code, `000` when nothing answered
	local code
	code="$(curl -sS -H "Authorization: Bearer ${token}" -o "$2" -w '%{http_code}' "$1" || true)"
	printf '%s' "${code:-000}"
}

probe() {
	local body code app
	if [[ -z "$token" ]]; then
		say "version  skipped — no token. Put ORCHESTRATOR_TOKEN in ${env_file} (or pass --token) and re-run to verify."
		return 0
	fi
	need_cmd curl "install curl — it proves the instance and the token"
	[[ -n "$scratch" ]] || scratch="$(mktemp -d)"
	body="${scratch}/version.json"
	code="$(http_code "${base_url}/api/v1/version" "$body")"
	case "$code" in
		200)
			app="$(json_string "$body" app_version)"
			say "version  ${base_url} runs ${app:-an unnamed version}; this kit is ${kit_version}"
			if [[ -n "$app" && "$app" != "$kit_version" ]]; then
				warn "the instance runs ${app} and this kit is ${kit_version} — the skills are stale. Re-install:"$'\n'"  $(reinstall_line)"
			fi
			;;
		404)
			say "version  ${base_url}/api/v1/version answered 404 — an instance older than this route; falling back to /api/v1/ping"
			code="$(http_code "${base_url}/api/v1/ping" "$body")"
			[[ "$code" == "200" ]] ||
				die "${base_url}/api/v1/ping answered ${code} — is the instance up, and is the token the one in its own .env?"
			say "ping     ${base_url}/api/v1/ping — token accepted"
			;;
		401|403)
			die "${base_url}/api/v1/version refused the token (${code}) — it is ORCHESTRATOR_TOKEN in the instance's own .env"
			;;
		*)
			die "${base_url}/api/v1/version answered ${code} — is the instance up, and is the base URL right?"
			;;
	esac
}

# ── go ───────────────────────────────────────────────────────────────────────
step "ai-orchestrator kit → ${project} (harness: ${harness})"
resolve_kit
install_skills
install_bin
install_env
base_url="$(read_env ORCHESTRATOR_BASE_URL)"
base_url="${base_url%/}"
token="$(read_env ORCHESTRATOR_TOKEN)"
install_marker
probe

say
say "Written:"
printf '%s' "$written" | sed 's/^/  /'
[[ -z "$bin_target" ]] || say "  ${bin_target}"
say "  ${env_file}"
say "  ${marker}"
say
say "Open your agent CLI in ${project} and have it use the 'orchestrator' skill: it covers the"
say "version handshake, project and repository setup, launching Runs, polling, and signals."
say "The spec-folder format (epics.yaml / stories.yaml / SPEC.md) is references/spec-folder.md"
say "beside it."
