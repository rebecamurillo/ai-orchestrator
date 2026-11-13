#!/usr/bin/env bash
# kit/install.sh — render the orchestrator bootstrap into a project or a harness home and
# configure the agent connection (MCP) to a running ai-orchestrator instance.
#
#   install.sh [--harness claude|codex|opencode|all] [--base-url URL] [--web-url URL]
#              [--token-var NAME] [--project DIR | --home]
#
# The documented call, from inside the project:
#
#   curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
#     "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness claude
#
# Beside the script, `bootstrap/` and `mcp/` are used; piped, they come from the instance's
# kit archive. The token value is read only to fetch that archive and to probe the version:
# it is passed in a curl header, never printed, never written anywhere.
#
# Portable bash 3.2 (a stock macOS): no associative arrays, no `sed -i`, no `mapfile`.
set -euo pipefail
# bash >= 5.2 treats `&` in a replacement as the match unless this is off
shopt -u patsub_replacement 2>/dev/null || true

self="${BASH_SOURCE[0]:-}"
here=""
# read from a pipe, `$BASH_SOURCE` names no readable file
if [[ -n "$self" && -f "$self" ]]; then here="$(cd "$(dirname "$self")" && pwd)"; fi

harness="all"
base_url_arg=""
web_url_arg=""
token_var="ORCHESTRATOR_TOKEN"
project_arg=""
use_home=0

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

# A heredoc: read from a pipe there is no file to re-read, and `--help` must work piped.
usage() {
	cat <<'TEXT'
install.sh [--harness claude|codex|opencode|all] [--base-url URL] [--web-url URL]
           [--token-var NAME] [--project DIR | --home]

  --harness    which agent CLI is configured, default `all`:
               claude → .claude/skills/ and .mcp.json ; codex → .agents/skills/ and
               ${CODEX_HOME:-~/.codex}/config.toml ; opencode → .agents/skills/ and opencode.json
  --base-url   the instance; default $ORCHESTRATOR_BASE_URL, else http://127.0.0.1:8000
  --web-url    the instance's web address, so the agent can link Run pages; default none
  --token-var  the NAME of the environment variable holding the token, default
               ORCHESTRATOR_TOKEN (^[A-Z_][A-Z0-9_]*$). The installer never takes a token value
  --project    where to install; default the current directory
  --home       install into $HOME (and the harnesses' own config homes) instead

Writes the rendered `orchestrator` bootstrap skill, the harness's MCP configuration (a file
that already declares `orchestrator` is left as it is) and <root>/.orchestrator/bootstrap.json.
TEXT
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--harness) [[ $# -ge 2 ]] || die "--harness needs a value"; harness="$2"; shift ;;
		--harness=*) harness="${1#--harness=}" ;;
		--base-url) [[ $# -ge 2 ]] || die "--base-url needs a value"; base_url_arg="$2"; shift ;;
		--base-url=*) base_url_arg="${1#--base-url=}" ;;
		--web-url) [[ $# -ge 2 ]] || die "--web-url needs a value"; web_url_arg="$2"; shift ;;
		--web-url=*) web_url_arg="${1#--web-url=}" ;;
		--token-var) [[ $# -ge 2 ]] || die "--token-var needs a value"; token_var="$2"; shift ;;
		--token-var=*) token_var="${1#--token-var=}" ;;
		--token|--token=*) die "pass the variable's name with --token-var; the installer never takes a token value" ;;
		--project) [[ $# -ge 2 ]] || die "--project needs a value"; project_arg="$2"; shift ;;
		--project=*) project_arg="${1#--project=}" ;;
		--home) use_home=1 ;;
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
[[ "$token_var" =~ ^[A-Z_][A-Z0-9_]*$ ]] || die "--token-var '${token_var}' is not a variable name (^[A-Z_][A-Z0-9_]*\$)"
if [[ "$use_home" -eq 1 && -n "$project_arg" ]]; then die "--project and --home exclude each other"; fi

if [[ "$use_home" -eq 1 ]]; then
	[[ -n "${HOME:-}" && -d "$HOME" ]] || die "--home needs HOME to be set to a directory"
	root="$HOME"
else
	project="${project_arg:-$PWD}"
	[[ -d "$project" ]] || die "${project}: not a directory — pass --project /path/to/your/repo"
	root="$(cd "$project" && pwd)"
fi

base_url="${base_url_arg:-${ORCHESTRATOR_BASE_URL:-http://127.0.0.1:8000}}"
base_url="${base_url%/}"
web_url="${web_url_arg%/}"
# a newline or other control character could open a new key in the TOML or JSON written below
[[ "$base_url" != *[[:cntrl:]]* ]] || die "--base-url holds a control character"
[[ "$web_url" != *[[:cntrl:]]* ]] || die "--web-url holds a control character"
# JSON and TOML basic strings share these two escapes
base_url_lit="${base_url//\\/\\\\}"
base_url_lit="${base_url_lit//\"/\\\"}"
token_value="${!token_var:-}"

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "$1 is not installed — $2"; }

scratch=""
trap '[[ -z "$scratch" ]] || rm -rf "$scratch"' EXIT
mkscratch() { [[ -n "$scratch" ]] || scratch="$(mktemp -d)"; }

# ── where the template and the MCP files come from ───────────────────────────
kit_dir=""
resolve_kit() {
	if [[ -n "$here" && -f "${here}/bootstrap/SKILL.md.tmpl" && -d "${here}/mcp" ]]; then
		kit_dir="$here"
		return 0
	fi
	need_cmd curl "install curl — it fetches the kit from the instance"
	need_cmd tar "install tar — it unpacks the kit"
	[[ -n "$token_value" ]] ||
		die "no bootstrap/ beside this script, so the kit comes from ${base_url} — export ${token_var} (the instance's token) and run again"
	mkscratch
	curl -fsSL -H "Authorization: Bearer ${token_value}" -o "${scratch}/kit.tar.gz" \
		"${base_url}/api/v1/kit/archive" ||
		die "${base_url}/api/v1/kit/archive did not answer — is the instance up, and is ${token_var} right?"
	tar -xzf "${scratch}/kit.tar.gz" -C "$scratch" ||
		die "what ${base_url}/api/v1/kit/archive returned is not a readable tar.gz"
	[[ -f "${scratch}/bootstrap/SKILL.md.tmpl" && -d "${scratch}/mcp" ]] ||
		die "the archive from ${base_url}/api/v1/kit/archive carries no bootstrap/ and mcp/"
	kit_dir="$scratch"
	say "kit      fetched from ${base_url}/api/v1/kit/archive"
}

# ── rendering: parameter expansion, so `&`, `|` and `\` in a value stay literal ──
web_text=""
render() {   # render TEMPLATE_FILE HARNESS_TEXT [BASE_URL_TEXT] → stdout
	local text base="${3-$base_url}"
	text="$(cat "$1"; printf x)"
	text="${text%x}"
	text="${text//@@WEB_URL@@/$web_text}"
	text="${text//@@BASE_URL@@/$base}"
	text="${text//@@TOKEN_VAR@@/$token_var}"
	text="${text//@@HARNESS@@/$2}"
	printf '%s' "$text"
}

# ── the JSON merge: stdlib json, paths as arguments ──────────────────────────
# exit 0 merged · 3 `orchestrator` already declared (its url on stdout, nothing written)
# · 2 not valid JSON or not an object · 4 KEY is not an object. `check` only validates.
MERGE_PY='
import json, os, sys
mode, target, block, key = sys.argv[1:5]
try:
    with open(target) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("not an object")
except Exception:
    sys.exit(2)
servers = data.get(key)
if servers is not None and not isinstance(servers, dict):
    sys.exit(4)
if mode == "check":
    sys.exit(0)
if isinstance(servers, dict) and "orchestrator" in servers:
    entry = servers["orchestrator"]
    print(entry.get("url", "") if isinstance(entry, dict) else "")
    sys.exit(3)
with open(block) as f:
    new = json.load(f)[key]["orchestrator"]
if servers is None:
    servers = data[key] = {}
servers["orchestrator"] = new
tmp = target + ".orchestrator-tmp"
with open(tmp, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
os.replace(tmp, target)
'

# ── plan every MCP target before any write ───────────────────────────────────
claude_target=""
codex_target=""
opencode_target=""
want_claude=0; want_codex=0; want_opencode=0
case "$harness" in
	claude) want_claude=1 ;;
	codex) want_codex=1 ;;
	opencode) want_opencode=1 ;;
	all) want_claude=1; want_codex=1; want_opencode=1 ;;
esac

plan_json_target() {   # plan_json_target FILE TEMPLATE KEY
	local target="$1" tmpl="$2"
	[[ -f "$target" ]] || return 0
	if ! command -v python3 >/dev/null 2>&1; then
		say "python3 is not installed, so ${target} cannot be merged. Add this block to it by hand:" >&2
		render "${kit_dir}/mcp/${tmpl}" "" "$base_url_lit" >&2
		exit 1
	fi
	local key="$3" rc=0
	python3 -I -c "$MERGE_PY" check "$target" /dev/null "$key" || rc=$?
	case "$rc" in
		0) ;;
		4) die "${target}: its \"${key}\" is not an object; fix it and run again. Nothing was written" ;;
		*) die "${target} is not valid JSON; fix it and run again. Nothing was written" ;;
	esac
}

plan() {
	if [[ "$want_claude" -eq 1 ]]; then
		if [[ "$use_home" -eq 1 ]]; then claude_target="${HOME}/.claude.json"; else claude_target="${root}/.mcp.json"; fi
		plan_json_target "$claude_target" claude.json mcpServers
	fi
	if [[ "$want_codex" -eq 1 ]]; then
		codex_target="${CODEX_HOME:-$HOME/.codex}/config.toml"
	fi
	if [[ "$want_opencode" -eq 1 ]]; then
		local dir
		if [[ "$use_home" -eq 1 ]]; then dir="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"; else dir="$root"; fi
		opencode_target="${dir}/opencode.json"
		if [[ -f "${dir}/opencode.jsonc" ]]; then
			say "${dir}/opencode.jsonc exists, so no opencode.json is written. Add this block to it by hand:" >&2
			render "${kit_dir}/mcp/opencode.json" "" "$base_url_lit" >&2
			exit 1
		fi
		plan_json_target "$opencode_target" opencode.json mcp
	fi
}

# ── the beta.4 move ──────────────────────────────────────────────────────────
remove_old_kit() {
	local rel name path
	[[ -f "${root}/.orchestrator/kit.json" ]] || return 0
	for rel in .claude/skills .agents/skills; do
		for name in orchestrator orchestrator-admin initiative-spec initiative-run; do
			path="${root}/${rel}/${name}"
			if [[ -e "$path" ]]; then rm -rf "$path"; say "removed  ${path}"; fi
		done
	done
	if [[ -e "${root}/.orchestrator/bin" ]]; then
		rm -rf "${root}/.orchestrator/bin"; say "removed  ${root}/.orchestrator/bin"
	fi
	rm -f "${root}/.orchestrator/kit.json"; say "removed  ${root}/.orchestrator/kit.json"
	say "note     .env was not touched; a token the old kit wrote there is not read by the bootstrap — export it in the shell or the harness environment instead"
}

# ── the skill ────────────────────────────────────────────────────────────────
written=""
install_skill() {   # install_skill REL HARNESS_TEXT
	local target="${root}/${1}/orchestrator"
	rm -rf "$target"
	mkdir -p "$target"
	render "${kit_dir}/bootstrap/SKILL.md.tmpl" "$2" > "${target}/SKILL.md"
	say "skill    ${target}/SKILL.md"
	written="${written}${target}/SKILL.md"$'\n'
}

install_skills() {
	case "$harness" in
		claude) install_skill .claude/skills claude ;;
		codex) install_skill .agents/skills codex ;;
		opencode) install_skill .agents/skills opencode ;;
		all)
			install_skill .claude/skills claude
			install_skill .agents/skills "codex and opencode"
			;;
	esac
}

# ── the MCP configuration ────────────────────────────────────────────────────
differs() {   # differs FILE EXISTING_URL
	if [[ "$2" != "${base_url}/mcp" ]]; then
		say "         it points at ${2:-no url}; the base URL given is ${base_url}/mcp — edit ${1} by hand if that is wrong"
	fi
}

install_json_mcp() {   # install_json_mcp TARGET TEMPLATE KEY
	local target="$1" tmpl="$2" key="$3" block url rc=0
	mkscratch
	block="${scratch}/${tmpl}"
	render "${kit_dir}/mcp/${tmpl}" "" "$base_url_lit" > "$block"
	if [[ ! -f "$target" ]]; then
		mkdir -p "$(dirname "$target")"
		cp "$block" "$target"
		say "mcp      ${target} written"
		written="${written}${target}"$'\n'
		return 0
	fi
	url="$(python3 -I -c "$MERGE_PY" merge "$target" "$block" "$key")" || rc=$?
	case "$rc" in
		0) say "mcp      ${target} merged (every other key kept)"; written="${written}${target}"$'\n' ;;
		3) say "mcp      ${target} already declares orchestrator — kept as it is"; differs "$target" "$url"; written="${written}${target} (kept)"$'\n' ;;
		*) die "${target} could not be merged" ;;
	esac
}

install_codex_mcp() {
	local target="$codex_target" block url="" in_table=0 line found=0
	mkscratch
	block="${scratch}/codex.toml"
	render "${kit_dir}/mcp/codex.toml" "" "$base_url_lit" > "$block"
	say "note     ${target} is per-user: it configures codex for every project on this machine"
	if [[ ! -f "$target" ]]; then
		mkdir -p "$(dirname "$target")"
		cp "$block" "$target"
		say "mcp      ${target} written"
		written="${written}${target}"$'\n'
		return 0
	fi
	# Every TOML spelling of the key: a header (indented, spaced, quoted, or a sub-table), an
	# `orchestrator = {…}` inside `[mcp_servers]`, or a dotted key. Missing one appends a
	# second table and codex refuses the whole file.
	local ws='[[:space:]]*' name="[\"']?orchestrator[\"']?" in_servers=0
	local hdr="^${ws}\\[${ws}mcp_servers${ws}\\.${ws}${name}${ws}[].]"
	local dotted="^${ws}mcp_servers${ws}\\.${ws}${name}${ws}[.=]"
	local inline="^${ws}${name}${ws}[.=]"
	local urlre="^${ws}url${ws}=${ws}[\"']([^\"']*)[\"']"
	while IFS= read -r line || [[ -n "$line" ]]; do
		line="${line%$'\r'}"
		if [[ "$line" =~ $hdr ]]; then in_table=1; in_servers=0; found=1; continue; fi
		if [[ "$line" =~ ^${ws}\[ ]]; then
			in_table=0; in_servers=0
			[[ "$line" =~ ^${ws}\[${ws}mcp_servers${ws}\] ]] && in_servers=1
			continue
		fi
		if [[ "$line" =~ $dotted || ( "$in_servers" -eq 1 && "$line" =~ $inline ) ]]; then found=1; fi
		if [[ "$in_table" -eq 1 && "$line" =~ $urlre ]]; then url="${BASH_REMATCH[1]}"; fi
	done < "$target"
	if [[ "$found" -eq 1 ]]; then
		say "mcp      ${target} already declares orchestrator — kept as it is"
		differs "$target" "$url"
		written="${written}${target} (kept)"$'\n'
		return 0
	fi
	if [[ -s "$target" && -n "$(tail -c 1 "$target")" ]]; then printf '\n' >> "$target"; fi
	[[ -s "$target" ]] && printf '\n' >> "$target"
	cat "$block" >> "$target"
	say "mcp      ${target} table appended"
	written="${written}${target}"$'\n'
}

install_mcp() {
	[[ "$want_claude" -eq 0 ]] || install_json_mcp "$claude_target" claude.json mcpServers
	[[ "$want_codex" -eq 0 ]] || install_codex_mcp
	[[ "$want_opencode" -eq 0 ]] || install_json_mcp "$opencode_target" opencode.json mcp
}

# ── the marker ───────────────────────────────────────────────────────────────
marker=""
install_marker() {
	marker="${root}/.orchestrator/bootstrap.json"
	mkdir -p "${root}/.orchestrator"
	printf '{\n  "bootstrap_contract": 1,\n  "harness": "%s",\n  "base_url": "%s",\n  "installed_at": "%s"\n}\n' \
		"$harness" "$base_url_lit" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$marker"
	say "marker   ${marker} (no credential — commit it)"
	written="${written}${marker}"$'\n'
}

# ── the probe ────────────────────────────────────────────────────────────────
json_string() { tr -d ' \t\n' < "$1" | tr ',' '\n' | sed -n 's/^{*"'"$2"'":"\([^"]*\)".*/\1/p' | head -1; }
json_int() { tr -d ' \t\n' < "$1" | tr ',' '\n' | sed -n 's/^{*"'"$2"'":\([0-9][0-9]*\).*/\1/p' | head -1; }

probe() {
	local body code app contract
	if [[ -z "$token_value" ]]; then
		say "version  skipped — ${token_var} is not set. Export it and run again to verify the instance."
		return 0
	fi
	need_cmd curl "install curl — it proves the instance and the token"
	mkscratch
	body="${scratch}/version.json"
	code="$(curl -sS -H "Authorization: Bearer ${token_value}" -o "$body" -w '%{http_code}' "${base_url}/api/v1/version" || true)"
	code="${code:-000}"
	case "$code" in
		200)
			app="$(json_string "$body" app_version)"
			contract="$(json_int "$body" bootstrap_contract)"
			say "version  ${base_url} runs ${app:-an unnamed release}; bootstrap_contract ${contract:-unreported}"
			if [[ -n "$contract" && "$contract" -gt 1 ]]; then
				say "refusal-bootstrap-contract: the instance reports bootstrap_contract ${contract}; this bootstrap is 1. A difference, not an error — read the guide."
			fi
			;;
		401|403) die "${base_url}/api/v1/version refused the token (${code}) — check the value of ${token_var}" ;;
		*) die "${base_url}/api/v1/version answered ${code} — is the instance up, and is the base URL right?" ;;
	esac
}

# ── go ───────────────────────────────────────────────────────────────────────
if [[ -n "$web_url" ]]; then
	web_text="The web address is ${web_url}; link Run pages there."
else
	web_text="No web address was given."
fi

step "ai-orchestrator bootstrap → ${root} (harness: ${harness})"
resolve_kit
plan
remove_old_kit
install_skills
install_mcp
install_marker
probe

say
say "Written or kept:"
printf '%s' "$written" | while IFS= read -r p; do say "  ${p}"; done
say
say "Open your agent CLI in ${root} and have it use the 'orchestrator' skill."
