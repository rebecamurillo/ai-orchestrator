#!/usr/bin/env bash
# install.sh — ai-orchestrator, from an empty machine to http://127.0.0.1:4321 in one command.
#
#   ./install.sh                                  # interactive: asks for the GitHub token and,
#                                                 #   optionally, the gateway and tracing addresses
#   GHCR_TOKEN=ghp_… ./install.sh --yes           # unattended; nothing optional is asked
#   LITELLM_BASE_URL=… LANGFUSE_BASE_URL=… ./install.sh --yes   # gateway and tracing given
#
#   ./install.sh start | stop | status | logs     # day-2 operations on this stack
#   ./install.sh start --with-docker              # add the Docker daemon for Runs (VERIFY_DOCKER)
#   ./install.sh install --no-bmad                # skip the BMAD skills (setup/bmad.choice → removed)
#   ./install.sh setup [--reset]                  # run setup/*.sh and BMAD under the hold; --reset first empties the harness asset folders (logins kept)
#   ./install.sh bmad remove                      # setup/bmad.choice → removed, then setup (BMAD's skills deleted)
#   ./install.sh bmad install                     # setup/bmad.choice → installed, then setup
#   ./install.sh doctor                           # read-only checks; non-zero on any `fail`
#   ./install.sh diagnose                         # a redacted report to attach to a bug report
#   ./install.sh harness claude --subscription    # Claude Max/Pro auth instead of an API key
#   ./install.sh harness claude --api-key         # back to the gateway's own API key
#   ./install.sh harness claude --version 2.1.260 # pin a harness CLI (claude|codex|opencode), recreate
#   ./install.sh upgrade --tag v0.2.0             # replace product files under the hold, run setup, restart (exit 3/4/5 = refused)
#   ./install.sh uninstall                        # stop and DELETE the data, after confirmation
#   ./install.sh env --tag v0.1.0                 # only write .env (what `install` does first)
#   ./install.sh --no-pull                        # images built on this machine: no registry login, no pull
#
# What `install` does, in order:
#   1. checks docker, docker compose v2, curl and openssl are here, and the daemon answers
#   2. logs the docker daemon in to ghcr.io with the token — the images are private
#   3. writes `.env` from `.env.example` with generated secrets, once; never overwrites it. The
#      six optional values LITELLM_BASE_URL, LITELLM_API_KEY, LITELLM_SPEND_KEY,
#      LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY come from the environment or
#      are asked; blank keeps the gateway or tracing off
#   4. writes the seed files `product-files.json` names that are absent; a present file is never changed;
#      `--with-docker` also sets VERIFY_DOCKER=true, which starts the `docker` service
#   5. pulls the two images the compose file pins and starts the stack
#   6. proves /healthz and the login token
#   7. runs the setup service under the instance hold, then prints the setup record
#
# Inputs (environment, all optional unless the step needs them):
#   GHCR_TOKEN          GitHub token that can read the packages; GITHUB_TOKEN is the fallback
#   GITHUB_TOKEN        the git credential written to .env (clone/push of your repositories);
#                       defaults to the token above when images are pulled; --no-pull skips that
#                       fallback, so .env gets only a GITHUB_TOKEN set here, else the placeholder
#   GITHUB_USER         registry login name; resolved from the token when unset
#   LITELLM_BASE_URL, LITELLM_API_KEY, LITELLM_SPEND_KEY, LANGFUSE_BASE_URL,
#   LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY   the gateway and tracing, written to a new .env
#
# Portable bash 3.2 (a stock macOS): no associative arrays, no `sed -i`, no `mapfile`.
# Nothing here stops a service it did not start, and nothing rebinds a port that is taken:
# a port in use is reported with the variable that moves this stack off it.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_file="${here}/.env"
example_file="${here}/.env.example"
compose_file="${here}/docker-compose.yml"
release_file="${here}/release.env"
manifest_file="${here}/product-files.json"

yes=0
no_bmad=0            # 1: install writes `removed` into setup/bmad.choice when that file is absent
with_docker=""       # "" keep .env's VERIFY_DOCKER, 1 --with-docker, 0 --no-docker
pull=1               # 0: the images are already on this machine (built from a checkout)
tag_arg=""
command=""
harness_arg=""       # the harness `harness` acts on
reset=0              # 1: `setup --reset`
bmad_arg=""          # install|remove, the word after `bmad`
subscription=""      # "" neither flag, 1 --subscription, 0 --api-key
version_arg=""       # the harness CLI version `harness --version` pins
version_given=0      # 1 once --version appeared, so an empty value is refused rather than ignored
scratch=""           # where an API answer is parked while it is read; removed on exit
work=""              # .upgrade/{ts}: what an upgrade staged and what it replaced; a refusal removes it
held=0               # 1 while this run holds the instance
hold_code=""
plan=""              # $scratch/plan: the lists an upgrade computes before it writes anything
upgrade_stage=""     # the step an upgrade has reached once it replaced its first file
upgrade_old=""
upgrade_backup=""
upgrade_new=""
dump_partial=""      # a pg_dump being written; an exit before it completes removes it
on_exit() {
	local rc=$?
	set +e
	# A set -e failure or a signal before the first replaced file is a refusal too: the folder is
	# left as found and the hold released.
	if [[ "$rc" -ne 0 && -z "$upgrade_stage" && -n "$work" ]]; then
		[[ "$held" -eq 0 ]] || release_hold 30
		[[ -z "$dump_partial" ]] || rm -f "$dump_partial"
		rm -rf "$work"
		rmdir "${here}/.upgrade" 2>/dev/null
	fi
	# a hold taken by setup, bmad or install's setup run, still held at a set -e or signal exit
	[[ "$held" -eq 0 || -n "$work" ]] || release_hold 15
	[[ -z "$scratch" ]] || rm -rf "$scratch"
	if [[ "$rc" -ne 0 && -n "$upgrade_stage" ]]; then
		{
			printf 'error: upgrade stopped at %s, after product files were replaced\n' "$upgrade_stage"
			printf '  the previous copies are in .upgrade/%s/previous/\n' "${work##*/}"
			[[ -z "$upgrade_backup" ]] || printf '  the database backup is %s\n' "$upgrade_backup"
			printf '  roll back with ./install.sh upgrade --tag %s\n' "$upgrade_old"
			# the old backend still answers until the start step, and an upgrade to the version
			# that answers is refused — so before it, finishing is the way forward
			[[ "$upgrade_stage" == "start" ]] ||
				printf '  or, while the old release still runs, finish with ./install.sh upgrade --tag %s\n' "$upgrade_new"
		} >&2
		exit 1
	fi
}
trap on_exit EXIT

# ── output ───────────────────────────────────────────────────────────────────
say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
	sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ── arguments ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
	# `bmad install` is not the `install` command
	if [[ "$command" == "bmad" && -z "$bmad_arg" && ( "$1" == "install" || "$1" == "remove" ) ]]; then
		bmad_arg="$1"; shift; continue
	fi
	case "$1" in
		install|start|stop|status|logs|upgrade|uninstall|env) command="$1" ;;
		doctor|diagnose|harness|setup|bmad) command="$1" ;;
		--reset) reset=1 ;;
		--tag) [[ $# -ge 2 ]] || die "--tag needs a value"; tag_arg="$2"; shift ;;
		--tag=*) tag_arg="${1#--tag=}" ;;
		--yes|-y) yes=1 ;;
		--no-pull) pull=0 ;;
		--no-bmad) no_bmad=1 ;;
		--with-docker) with_docker=1 ;;
		--no-docker) with_docker=0 ;;
		--subscription) subscription=1 ;;
		--api-key) subscription=0 ;;
		--version|--version=*)
			[[ "$version_given" -eq 0 ]] ||
				die "--version given twice: ./install.sh harness <claude|codex|opencode> --version X"
			version_given=1
			if [[ "$1" == --version=* ]]; then
				version_arg="${1#--version=}"
			else
				[[ $# -ge 2 && "$2" != -* ]] ||
					die "--version needs a value: ./install.sh harness <claude|codex|opencode> --version X"
				version_arg="$2"; shift
			fi ;;
		-h|--help) usage; exit 0 ;;
		# `harness` takes the harness name as a bare word; nothing else here does
		*) [[ "$command" != "bmad" || -n "$bmad_arg" ]] ||
		   	die "bmad needs install or remove, not $1: ./install.sh bmad remove | ./install.sh bmad install"
		   [[ "$command" == "harness" && -z "$harness_arg" ]] || die "unknown argument: $1 (try --help)"
		   harness_arg="$1" ;;
	esac
	shift
done
command="${command:-install}"
[[ "$reset" -eq 0 || "$command" == "setup" ]] ||
	die "--reset is for setup: ./install.sh setup --reset"
[[ "$command" != "bmad" || -n "$bmad_arg" ]] ||
	die "bmad needs install or remove: ./install.sh bmad remove | ./install.sh bmad install"
# `bmad remove install` would otherwise run the install command
[[ -z "$bmad_arg" || "$command" == "bmad" ]] ||
	die "bmad takes one word and no other command: ./install.sh bmad remove | ./install.sh bmad install"
[[ "$no_bmad" -eq 0 || "$command" == "install" ]] ||
	die "--no-bmad is for install: ./install.sh install --no-bmad"
[[ -z "$with_docker" || "$command" == "install" || "$command" == "start" ]] ||
	die "--with-docker / --no-docker are for install and start: ./install.sh start --with-docker"
[[ "$version_given" -eq 0 || "$command" == "harness" ]] ||
	die "--version is only for: ./install.sh harness <claude|codex|opencode> --version X"

# ── small helpers ────────────────────────────────────────────────────────────
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "$1 is not installed — $2"; }

# NAME=value from a dotenv file, minus a trailing `  # comment` and surrounding quotes
get_var() {
	local file="$1" name="$2" line value
	# an absent file answers from its `.example`, so a check can run before `.env` exists
	[[ -f "$file" ]] || file="${file}.example"
	line="$(grep "^${name}=" "$file" 2>/dev/null | head -1 || true)"
	value="${line#*=}"
	value="${value%%  #*}"
	value="${value%"${value##*[! ]}"}"   # trim trailing spaces
	value="${value#\'}"; value="${value%\'}"
	value="${value#\"}"; value="${value%\"}"
	printf '%s' "$value"
}

# 0 when FILE has an uncommented `NAME=` line
env_sets() { grep -q "^${2}=" "$1" 2>/dev/null; }

# Rewrite `NAME=…` in place, keeping the line's trailing comment when the new value is not
# empty. An empty value drops the comment: compose reads `NAME=  # text` as the value `# text`.
set_var() {
	local file="$1" name="$2" value="$3" tmp
	grep -q "^${name}=" "$file" || die "${file##*/} does not declare ${name} — not the current contract"
	tmp="$(mktemp)"
	awk -v name="$name" -v value="$value" '
		index($0, name "=") == 1 {
			rest = substr($0, length(name) + 2)
			pos = index(rest, "  #")
			if (value != "" && pos > 0) print name "=" value substr(rest, pos)
			else print name "=" value
			next
		}
		{ print }
	' "$file" > "$tmp"
	cat "$tmp" > "$file"
	rm -f "$tmp"
}

# The pin shape every reader of a harness pin accepts. A test keeps its four copies identical:
# scripts/harness/_common.sh, deploy/install.sh, scripts/push-images.sh, release.yml.
PLAIN_VERSION='^[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}([-+][0-9A-Za-z.-]+)?$'
is_plain_version() { [[ "$1" =~ $PLAIN_VERSION ]]; }

# 0 when plain version $1 is older than plain version $2. `+build` is ignored; a pre-release
# sorts below its release; two pre-releases of one x.y.z compare as text.
version_older() {
	local a="${1%%+*}" b="${2%%+*}" pa="" pb="" i
	local -a x y
	[[ "$a" != *-* ]] || pa="${a#*-}"
	[[ "$b" != *-* ]] || pb="${b#*-}"
	IFS=. read -r -a x <<< "${a%%-*}"
	IFS=. read -r -a y <<< "${b%%-*}"
	for i in 0 1 2; do
		(( 10#${x[$i]} < 10#${y[$i]} )) && return 0
		(( 10#${x[$i]} > 10#${y[$i]} )) && return 1
	done
	[[ -n "$pa" ]] || return 1
	[[ -n "$pb" ]] || return 0
	[[ "$pa" < "$pb" ]]
}

# set_var, or append the line when an `.env` written by an older release lacks it — for an
# optional variable only, whose absence already means its default.
put_var() {
	local file="$1" name="$2" value="$3"
	if grep -q "^${name}=" "$file"; then set_var "$file" "$name" "$value"
	else printf '%s=%s\n' "$name" "$value" >> "$file"; fi
}

is_placeholder() { case "$1" in ""|*change-me*) return 0 ;; *) return 1 ;; esac; }

port_in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# ensure_ports_free "4321 WEB_CLIENT_PORT .env" "8000 BACKEND_API_PORT .env" …
ensure_ports_free() {
	local spec port var file busy=""
	for spec in "$@"; do
		set -- $spec; port="$1"; var="$2"; file="$3"
		if port_in_use "$port"; then busy="${busy}  ${port}  → set ${var} in ${file} to a free port"$'\n'; fi
	done
	[[ -z "$busy" ]] || die "a port this stack needs is already taken on this machine; nothing was started:"$'\n'"${busy}Move this stack off it — do not stop what is listening there."
}

prompt() {   # prompt VAR "question" [secret]
	local var="$1" question="$2" secret="${3:-}" answer
	if [[ "$yes" -eq 1 ]]; then return 0; fi
	if [[ -n "$secret" ]]; then read -r -s -p "$question" answer; printf '\n'; else read -r -p "$question" answer; fi
	printf -v "$var" '%s' "$answer"
}

confirm() {   # confirm "question" → 0 on yes; --yes answers yes
	local answer
	[[ "$yes" -eq 0 ]] || return 0
	read -r -p "$1 [y/N] " answer
	[[ "$answer" == "y" || "$answer" == "Y" || "$answer" == "yes" ]]
}

# The `docker` service is in the compose profile `docker`, which `.env`'s VERIFY_DOCKER turns
# on for every command here; `compose_all` names it regardless, for the commands that must
# reach a sidecar left from when it was on (remove it, `down -v`).
docker_enabled() {
	case "$(get_var "$env_file" VERIFY_DOCKER | tr '[:upper:]' '[:lower:]')" in
		true|1|yes|on) return 0 ;;
		*) return 1 ;;
	esac
}
compose() {
	if docker_enabled; then compose_all "$@"
	else docker compose --project-directory "$here" -f "$compose_file" "$@"; fi
}
compose_all()  { docker compose --project-directory "$here" -f "$compose_file" --profile docker "$@"; }
# The tag the compose file pins for backend-api; the folder's own VERSION is what `resolve_tag` reads.
compose_tag() { sed -n 's/^ *image: *.*\/backend-api:\(.*\)$/\1/p' "$compose_file" | head -1; }
compose_setup() { compose --profile setup "$@"; }

# ── reading the API, and reading JSON without jq ─────────────────────────────
# A client machine has curl and nothing else; every answer below is parsed with sed over a
# flattened copy of the body. Nothing here prints the bearer: `api_get` passes it to curl and
# the value never reaches stdout, a log line or a report.

api_base() { printf 'http://127.0.0.1:%s' "$(get_var "$env_file" BACKEND_API_PORT)"; }

api_get() {   # api_get PATH OUTFILE → the status code, `000` when nothing answered
	local code bearer
	bearer="$(get_var "$env_file" ORCHESTRATOR_TOKEN)"
	code="$(curl -sS -m 10 -H "Authorization: Bearer ${bearer}" -o "$2" -w '%{http_code}' \
		"$(api_base)$1" 2>/dev/null || true)"
	printf '%s' "${code:-000}"
}

api_send() {   # api_send METHOD PATH OUTFILE [JSON] → the status code, `000` when nothing answered
	local code bearer
	local -a body=()
	bearer="$(get_var "$env_file" ORCHESTRATOR_TOKEN)"
	if [[ $# -ge 4 ]]; then body=(-H 'Content-Type: application/json' -d "$4"); fi
	code="$(curl -sS -m 30 -X "$1" -H "Authorization: Bearer ${bearer}" ${body[@]+"${body[@]}"} \
		-o "$3" -w '%{http_code}' "$(api_base)$2" 2>/dev/null || true)"
	printf '%s' "${code:-000}"
}

# Newlines and tabs go; spaces stay, because a `failing_check` is a sentence a human reads.
# Every pattern below therefore tolerates the whitespace a pretty-printing server would add.
json_flat() { tr -d '\n\t' < "$1"; }

# the string value of a top-level key, quotes stripped; empty for a `null` or an absent key
json_string() {
	json_flat "$1" | tr ',' '\n' |
		sed -n 's/^{* *"'"$2"'" *: *"\([^"]*\)".*/\1/p' | head -1
}

# `{"harness_versions":{…}}` rendered `claude:1.2.3 codex:…` — one nested object, read whole
json_object() {
	json_flat "$1" | sed -n 's/.*"'"$2"'" *: *{\([^}]*\)}.*/\1/p' | tr -d '" ' | tr ',' ' '
}

# One item of `{"items":[{…},{…}]}` per line. Split on each item's first key rather than on
# `},{`: the rows carry nested objects of their own (`lines[]`), and `},{` is inside them too.
json_items() {   # json_items FILE FIRSTKEY
	json_flat "$1" | awk -v key="$2" '{ gsub("\\{ *\"" key "\" *: *\"", "\n&"); print }' |
		grep "^{ *\"$2\""
}

# One field out of one such line: item_string "$row" enabled. The keys read below are
# single-valued within a row, so the greedy match cannot reach past the row it was given.
item_string() { printf '%s' "$1" | sed -n 's/.*"'"$2"'" *: *"\([^"]*\)".*/\1/p' | head -1; }
item_word()   { printf '%s' "$1" | sed -n 's/.*"'"$2"'" *: *\([A-Za-z0-9.]*\).*/\1/p' | head -1; }

# The text inside `"KEY": [ … ]`. The rows are flat objects, so the first `]` outside a string
# closes the array; one inside a string is a step path's (`epics[1].stories[3].build`). `working[]` and `in_engine[]` rows both begin with `run_id`: only the
# array they sit in says which they are.
json_array() {
	json_flat "$1" | sed -n 's/.*"'"$2"'" *: *\[//p' | head -1 | awk '{
		q = 0; e = 0
		for (i = 1; i <= length($0); i++) {
			c = substr($0, i, 1)
			if (q) { if (e) e = 0; else if (c == "\\") e = 1; else if (c == "\"") q = 0 }
			else if (c == "\"") q = 1
			else if (c == "]") { print substr($0, 1, i - 1); exit }
		}
	}'
}

# One row per line of the array ARRAYKEY, split on each row's first key
json_array_items() {   # json_array_items FILE ARRAYKEY FIRSTKEY
	json_array "$1" "$2" | awk -v key="$3" '{ gsub("\\{ *\"" key "\" *: *\"", "\n&"); print }' |
		grep "^{ *\"$3\"" || true
}

# openssl is a required host tool; sha256sum and shasum differ across Linux and macOS
sha256_of() { openssl dgst -sha256 -r "$1" | cut -d' ' -f1; }

# ── the product manifest ─────────────────────────────────────────────────────
# manifest_table FILE → `path<TAB>sha256<TAB>role` per row, so a lookup is an exact match on the
# whole path rather than a pattern over JSON text.
manifest_table() {
	local row
	while IFS= read -r row; do
		[[ -n "$row" ]] || continue
		printf '%s\t%s\t%s\n' "$(item_string "$row" path)" "$(item_string "$row" sha256)" "$(item_string "$row" role)"
	done <<EOF
$(json_items "$1" path)
EOF
}

# table_field TABLE PATH COLUMN (2 sha256, 3 role) → empty when the path is not in the table
table_field() { WANT="$2" awk -F'\t' -v c="$3" '$1 == ENVIRON["WANT"] { print $c; exit }' "$1"; }

# ── refusing, and the instance hold ──────────────────────────────────────────
# Every refusal leaves the folder as it found it: the hold is released when this run took one,
# and `.upgrade/{ts}` goes.
refuse() {   # refuse CODE LINE…
	local code="$1" line
	shift
	[[ "$held" -eq 0 ]] || release_hold 30
	printf 'refused: nothing was changed\n' >&2
	for line in "$@"; do printf '%s\n' "$line" >&2; done
	if [[ -n "$work" ]]; then
		rm -rf "$work"
		rmdir "${here}/.upgrade" 2>/dev/null || true
	fi
	exit "$code"
}

# Sets hold_code to the answer; the body (a 409's `errors[]`) stays in $scratch/hold.json
take_hold() {   # take_hold TTL REASON
	hold_code="$(api_send POST /api/v1/instance/hold "${scratch}/hold.json" \
		"{\"ttl_seconds\": ${1}, \"reason\": \"${2}\"}")"
	case "$hold_code" in 2??) held=1 ;; esac
}

release_hold() {   # release_hold TTL_MINUTES
	local code
	code="$(api_send DELETE /api/v1/instance/hold "${scratch}/release.json")"
	held=0
	case "$code" in
		2??) ;;
		*) warn "the hold release answered ${code} — the hold expires on its own in ${1} minutes" ;;
	esac
}

# One line per working step: the rows of ARRAYKEY in FILE (activity `working`, a 409's `errors`)
working_lines() {   # working_lines FILE ARRAYKEY
	local row since
	while IFS= read -r row; do
		[[ -n "$row" ]] || continue
		since="$(item_string "$row" started_at)"
		printf 'run %s (%s) step %s (%s) working since %s\n' "$(item_string "$row" run_id)" \
			"$(item_string "$row" run_label)" "$(item_string "$row" path)" "$(item_string "$row" kind)" \
			"${since:-an unknown time}"
	done <<EOF
$(json_array_items "$1" "$2" run_id)
EOF
}

# ── 1. prerequisites ─────────────────────────────────────────────────────────
check_tools() {
	need_cmd docker "install Docker Desktop or Docker Engine: https://docs.docker.com/get-docker/"
	need_cmd curl "install curl"
	need_cmd openssl "install openssl (it generates the secrets)"
	docker compose version >/dev/null 2>&1 || die "docker compose v2 is missing — it ships with Docker Desktop; on Engine install the docker-compose-plugin package"
	docker info >/dev/null 2>&1 || die "the docker daemon is not answering — start Docker and re-run"
	[[ -f "$example_file" ]] || die "${example_file} is missing — run this script from the extracted bundle"
	[[ -f "$compose_file" ]] || die "${compose_file} is missing — run this script from the extracted bundle"
}

# ── the release tag ──────────────────────────────────────────────────────────
resolve_tag() {
	local tag=""
	if [[ -n "$tag_arg" ]]; then tag="$tag_arg"
	elif [[ -f "${here}/VERSION" ]]; then tag="$(tr -d '[:space:]' < "${here}/VERSION")"
	fi
	[[ -n "$tag" ]] || die "no release tag: pass --tag vX.Y.Z (a release bundle carries it in VERSION)"
	printf '%s' "$tag"
}

# ── 2. registry login ────────────────────────────────────────────────────────
token=""
resolve_token() {
	token="${GHCR_TOKEN:-${GITHUB_TOKEN:-}}"
	if [[ -z "$token" ]]; then
		say "The images are published to ghcr.io as private packages. A GitHub personal access"
		say "token that can read them is needed (classic token, scope read:packages; add repo"
		say "when the same token will clone and push your repositories)."
		prompt token "GitHub token: " secret
	fi
	[[ -n "$token" ]] || die "no GitHub token — set GHCR_TOKEN (or GITHUB_TOKEN) or run without --yes"
}

ghcr_login() {
	local user="${GITHUB_USER:-}"
	if [[ -z "$user" ]]; then
		user="$(curl -fsS -H "Authorization: Bearer ${token}" https://api.github.com/user 2>/dev/null |
			sed -n 's/^ *"login": *"\([^"]*\)".*/\1/p' | head -1 || true)"
	fi
	user="${user:-token}"
	printf '%s' "$token" | docker login ghcr.io -u "$user" --password-stdin >/dev/null ||
		die "ghcr.io refused the token for user ${user} — it needs read:packages and access to the packages"
	say "logged in to ghcr.io as ${user} (credential kept by docker, never by a container)"
}

# ── 3. the environment file ──────────────────────────────────────────────────
GATEWAY_NAMES="LITELLM_BASE_URL LITELLM_API_KEY LITELLM_SPEND_KEY LANGFUSE_BASE_URL LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY"

# Each of the six comes from the environment, else is asked (enter leaves it blank; a key is read
# without echo). Blank is the off switch: a base URL with a placeholder key is refused at start-up.
gateway_values() {
	local name value kind what
	for name in $GATEWAY_NAMES; do
		value="${!name:-}"
		if [[ -z "$value" ]]; then
			kind=""; what="tracing"
			case "$name" in *_KEY) kind=secret ;; esac
			case "$name" in LITELLM_*) what="the gateway" ;; esac
			prompt value "${name} (enter leaves it blank; ${what} stays off without it): " "$kind"
		fi
		set_var "$env_file" "$name" "$value"
	done
	if [[ -n "$(get_var "$env_file" LITELLM_BASE_URL)" && -z "$(get_var "$env_file" LITELLM_API_KEY)" ]]; then
		warn "LITELLM_BASE_URL is set but LITELLM_API_KEY is blank — backend-api refuses to start; set the key in .env or blank the URL"
	fi
	if [[ -n "$(get_var "$env_file" LANGFUSE_BASE_URL)" && ( -z "$(get_var "$env_file" LANGFUSE_PUBLIC_KEY)" || -z "$(get_var "$env_file" LANGFUSE_SECRET_KEY)" ) ]]; then
		warn "LANGFUSE_BASE_URL is set but a Langfuse key is blank — backend-api refuses to start; set both keys in .env or blank the URL"
	fi
}

render_env() {
	local password fernet
	if [[ -f "$env_file" ]]; then
		say ".env already exists — leaving it alone"
		return 0
	fi
	cp "$example_file" "$env_file"
	chmod 600 "$env_file"

	password="$(openssl rand -hex 24)"
	# a Fernet key is 32 random bytes in URL-safe base64 — the `+/` of standard base64 become `-_`
	fernet="$(openssl rand -base64 32 | tr '+/' '-_')"

	set_var "$env_file" ORCHESTRATOR_TOKEN "$(openssl rand -hex 32)"
	set_var "$env_file" ORCHESTRATOR_SESSION_SECRET "$(openssl rand -base64 32 | tr -d '\n')"
	set_var "$env_file" ORCHESTRATOR_SECRET_KEY "$fernet"
	set_var "$env_file" POSTGRES_PASSWORD "$password"
	set_var "$env_file" DATABASE_URL "postgresql+psycopg://orchestrator:${password}@postgres:5432/orchestrator"
	if [[ -n "${GITHUB_TOKEN:-$token}" ]]; then
		set_var "$env_file" GITHUB_TOKEN "${GITHUB_TOKEN:-$token}"
	else
		warn "GITHUB_TOKEN left as a placeholder in .env — fill it in before registering a repository"
	fi
	gateway_values
	say "wrote .env (mode 600): generated ORCHESTRATOR_TOKEN, session secret, Fernet key, database password; gateway $(onoff LITELLM_BASE_URL), tracing $(onoff LANGFUSE_BASE_URL)"
}

onoff() { if [[ -n "$(get_var "$env_file" "$1")" ]]; then printf on; else printf off; fi; }

# ── 3b. the files the product writes once ────────────────────────────────────
seed_write() {   # seed_write PATH — only when absent; a present file is never opened for writing
	local rel="$1" target="${here}/$1"
	[[ ! -e "$target" ]] || return 0
	case "$rel" in
		compose.override.yml)
			cat > "$target" <<'SEED_EOF'
# This file is yours. The product writes it only when it is absent and never replaces it;
# compose changes of your own go here.
services: {}
SEED_EOF
			;;
		setup/bmad.choice)
			mkdir -p "${here}/setup"
			if [[ "$no_bmad" -eq 1 ]]; then printf 'removed\n' > "$target"; else printf 'installed\n' > "$target"; fi
			;;
		*) warn "product-files.json names the seed ${rel}, which this installer does not know how to write — skipped"; return 0 ;;
	esac
	say "wrote ${rel}"
}

write_seeds() {
	local row
	if [[ -f "$manifest_file" ]]; then
		while IFS= read -r row; do
			[[ -n "$row" ]] || continue
			[[ "$(item_string "$row" role)" == "seed" ]] || continue
			seed_write "$(item_string "$row" path)"
		done <<EOF
$(json_items "$manifest_file" path)
EOF
	fi
	if [[ "$no_bmad" -eq 1 ]]; then seed_write setup/bmad.choice; fi
}

# ── 4b. Docker for Runs (the optional `docker` service) ──────────────────────
# `--with-docker` / `--no-docker` write VERIFY_DOCKER; `.env` is what every later command reads.
docker_choice() {
	[[ -n "$with_docker" ]] || return 0
	if [[ "$with_docker" -eq 1 ]]; then
		put_var "$env_file" VERIFY_DOCKER true
		say "VERIFY_DOCKER=true: a privileged Docker-in-Docker sidecar gives Runs a Docker daemon (README.md § Trust)"
	else
		put_var "$env_file" VERIFY_DOCKER false
		say "VERIFY_DOCKER=false"
	fi
}

# The daemon version as the agent user's docker CLI sees it, through the context
# `scripts/docker_context.sh` wrote — the path a Run's command takes. Empty on failure.
docker_reachable() {
	compose exec -T backend-api docker version --format '{{.Server.Version}}' 2>/dev/null
}

# On: backend-api must reach the daemon. A sidecar left in the network namespace of a
# backend-api that has since restarted answers nothing there, so it is recreated once and
# then the start refuses. Off: a sidecar left from when it was on is removed; `docker-data`
# is kept.
docker_reconcile() {
	local version
	if ! docker_enabled; then
		if compose_all ps -a --services 2>/dev/null | grep -qx docker; then
			say "VERIFY_DOCKER is off: removing the docker service's container (the docker-data volume is kept)"
			compose_all rm -sf docker
		fi
		return 0
	fi
	if version="$(docker_reachable)" && [[ -n "$version" ]]; then
		say "docker for Runs: daemon ${version} answers backend-api on tcp://127.0.0.1:2375"
		return 0
	fi
	say "backend-api cannot reach the docker service — recreating it in backend-api's network namespace"
	compose up -d --no-deps --force-recreate --wait --wait-timeout 300 docker
	version="$(docker_reachable)" && [[ -n "$version" ]] ||
		die "backend-api still cannot reach the docker service — ./install.sh logs, and read the docker service's dockerd lines"
	say "docker for Runs: daemon ${version} answers backend-api on tcp://127.0.0.1:2375"
}

# ── 5. the stack ─────────────────────────────────────────────────────────────
stack_up() {
	step "ai-orchestrator ($(compose_tag))"
	if ! compose ps --status running --services 2>/dev/null | grep -q .; then
		ensure_ports_free "$(get_var "$env_file" WEB_CLIENT_PORT) WEB_CLIENT_PORT .env" \
			"$(get_var "$env_file" BACKEND_API_PORT) BACKEND_API_PORT .env"
	fi
	if [[ "$pull" -eq 1 ]]; then compose pull; else say "--no-pull: using the images already on this machine"; fi
	compose up -d --wait --wait-timeout 1800
	docker_reconcile
}

# ── 5b. setup, under the instance hold ───────────────────────────────────────
# The text after a row's `"setup"` key: `null`, or the object whose own `ok` is the one to read —
# the row's `lines[]` carry `ok` fields of their own.
setup_part() { printf '%s' "$1" | sed -n 's/.*"setup" *: *//p'; }

# Every failed script of a setup object, one `script (reason)` per line
setup_failures() {
	local part row
	part="$(printf '%s' "$1" | awk '{ gsub("\\{ *\"script\" *: *\"", "\n&"); print }' | grep '^{ *"script"' || true)"
	while IFS= read -r row; do
		[[ -n "$row" ]] || continue
		printf '%s (%s)\n' "$(item_string "$row" script)" "$(item_string "$row" reason)"
	done <<EOF
$part
EOF
}

# One line per harness from the last setup record, one `failed:` line per failed script.
# 0 when every harness has an ok record; $1 is the setup run's exit code, when there was one.
print_setup_record() {
	local rc="${1:-0}" body code row name setup bad=0 any="" named=0 failure
	body="${scratch}/harnesses.json"
	code="$(api_get /api/v1/harnesses "$body")"
	if [[ "$code" != "200" ]]; then
		say "setup record not read: /api/v1/harnesses answered ${code} — ./install.sh logs"
		return 1
	fi
	while IFS= read -r row; do
		[[ -n "$row" ]] || continue
		any=1
		name="$(item_string "$row" name)"
		setup="$(setup_part "$row")"
		case "$setup" in
			null*|"") say "setup ${name}: no record"; bad=1 ;;
			*)
				if [[ "$(item_word "$setup" ok)" == "true" ]]; then
					say "setup ${name}: ok · trigger $(item_string "$setup" trigger) · $(item_string "$setup" at) · $(item_word "$setup" skills) skills"
				else
					bad=1
					say "setup ${name}: not ok · trigger $(item_string "$setup" trigger) · $(item_string "$setup" at)"
				fi
				while IFS= read -r failure; do
					[[ -n "$failure" ]] || continue
					named=1
					say "  failed: ${failure}"
				done <<EOF
$(setup_failures "$setup")
EOF
				;;
		esac
	done <<EOF
$(json_items "$body" name)
EOF
	[[ -n "$any" ]] || { say "setup record: /api/v1/harnesses returned no rows — ./install.sh logs"; bad=1; }
	if [[ "$rc" -ne 0 && "$named" -eq 0 ]]; then say "setup exited ${rc}; logs in logs/setup/"; fi
	[[ "$bad" -eq 0 ]]
}

# The setup service itself: its logs directory, a one-shot prepare.sh that creates the mounted agent-home
# folders (no running backend-api needed), the BMAD pin, one `run --rm`.
# Returns the run's exit code; the hold around it is the caller's.
setup_service_run() {   # setup_service_run TRIGGER RELEASE [RUNNER_ARG…]
	local pin h rc=0 trigger="$1" release="$2"
	shift 2
	local -a pins=()
	pin="$(env_pin BMAD_VERSION)"
	[[ -n "$pin" || ! -f "$release_file" ]] || pin="$(get_var "$release_file" BMAD_VERSION)"
	# the service's `environment: - BMAD_VERSION` is filled from the shell only
	if [[ -n "$pin" ]]; then pins=(-e "BMAD_VERSION=${pin}"); fi
	# a bind source the daemon creates is root-owned, and a volume subpath must exist before it is mounted;
	# 1777 lets uid 1000 in the setup container write the folder whoever owns it on the host
	mkdir -p "${here}/logs/setup"
	chmod 1777 "${here}/logs/setup" ||
		warn "logs/setup: could not chmod 1777 (owned by another user) — run: sudo chmod 1777 logs/setup"
	compose run --rm --no-deps --user agent --entrypoint /app/scripts/setup/prepare.sh backend-api </dev/null ||
		warn "scripts/setup/prepare.sh failed — the agent home's folders may be missing"
	compose_setup run --rm -e "ORCH_SETUP_TRIGGER=${trigger}" -e "ORCH_RELEASE=${release}" \
		${pins[@]+"${pins[@]}"} setup ${1+"$@"} || rc=$?
	# backend-api writes the skill catalog; a failed run can still have changed the folders. An upgrade's
	# stack_up recreates backend-api, and a stopped backend-api writes it at its next start.
	if [[ "$trigger" != upgrade ]] && compose ps --status running --services 2>/dev/null | grep -q '^backend-api$'; then
		for h in claude codex opencode; do
			compose exec -T backend-api "/app/scripts/harness/${h}.sh" catalog </dev/null ||
				warn "catalog: ${h}.sh catalog failed in backend-api — pre-flight reads the previous catalog until the next start"
		done
	fi
	return "$rc"
}

# The instance is held so no Run starts while the harness trees change, and released whatever
# the run did; an unreleased hold only expires at its ttl. 0 when the run and the record are ok.
run_setup() {   # run_setup TRIGGER
	local trigger="$1" release rc=0 rec=0 step
	release="$(resolve_tag)"
	take_hold 900 "install setup"
	case "$hold_code" in
		2??) ;;
		*)
			say "setup not run: the hold answered ${hold_code}"
			if [[ "$hold_code" == "409" ]]; then
				while IFS= read -r step; do
					[[ -n "$step" ]] || continue
					say "  a Run is working: $(item_string "$step" run_label) · $(item_string "$step" path)"
				done <<EOF
$(json_items "${scratch}/hold.json" run_id)
EOF
			fi
			return 1 ;;
	esac
	setup_service_run "$trigger" "$release" || rc=$?
	release_hold 15
	print_setup_record "$rc" || rec=1
	[[ "$rc" -eq 0 && "$rec" -eq 0 ]]
}

# ── 6. proof, and where to go ────────────────────────────────────────────────
verify() {
	local api="http://127.0.0.1:$(get_var "$env_file" BACKEND_API_PORT)" bearer
	bearer="$(get_var "$env_file" ORCHESTRATOR_TOKEN)"
	curl -fsS "${api}/healthz" >/dev/null || die "${api}/healthz does not answer — ./install.sh logs"
	curl -fsS -H "Authorization: Bearer ${bearer}" "${api}/api/v1/ping" >/dev/null ||
		die "${api}/api/v1/ping refused the token in .env — ./install.sh logs"
	say "healthz ok, token accepted"
}

print_access() {
	local web="http://127.0.0.1:$(get_var "$env_file" WEB_CLIENT_PORT)"
	local api="http://127.0.0.1:$(get_var "$env_file" BACKEND_API_PORT)"
	say
	say "──────────────────────────────────────────────────────────────"
	say "  Web UI     ${web}"
	say "  API        ${api}   (Authorization: Bearer <token>)"
	say "  Login      $(get_var "$env_file" ORCHESTRATOR_TOKEN)"
	say "             (ORCHESTRATOR_TOKEN in ${env_file})"
	say "  Gateway    $(get_var "$env_file" LITELLM_BASE_URL | sed 's/^$/off/')"
	say "  Tracing    $(get_var "$env_file" LANGFUSE_BASE_URL | sed 's/^$/off/')"
	say "──────────────────────────────────────────────────────────────"
	say "  ./install.sh status | logs | stop | start | upgrade --tag vX.Y.Z"
	say "  Next: log in, create a Project, register a Repository (README.md)."
}

# ── doctor: questions only ───────────────────────────────────────────────────
# Nothing here starts, stops, pulls or edits anything (hard rule 9) — every check is a read.
# Each `fail`/`warn` line ends with the command or the variable that fixes it, and no check
# ever prints a value `.env` keeps secret.

doctor_fails=0
doctor_warns=0

report() {   # report ok|warn|fail NAME TEXT
	case "$1" in
		fail) doctor_fails=$((doctor_fails + 1)) ;;
		warn) doctor_warns=$((doctor_warns + 1)) ;;
	esac
	printf '%-4s  %-9s  %s\n' "$1" "$2" "$3"
}

file_mode() {   # GNU `stat -c` first; BSD rejects it and answers `-f %Lp` instead
	stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1" 2>/dev/null || printf '?'
}

doctor_docker() {
	local engine major
	if ! command -v docker >/dev/null 2>&1; then
		report fail docker "not installed — https://docs.docker.com/get-docker/"
		return 1
	fi
	if ! docker compose version >/dev/null 2>&1; then
		report fail docker "compose v2 is missing — install the docker-compose-plugin package"
		return 1
	fi
	if ! docker info >/dev/null 2>&1; then
		report fail docker "the daemon is not answering — start Docker, then ./install.sh doctor"
		return 1
	fi
	engine="$(docker version --format '{{.Server.Version}}' 2>/dev/null || true)"
	report ok docker "${engine:-?}, compose $(docker compose version --short)"
	major="${engine%%.*}"
	if [[ "$major" =~ ^[0-9]+$ && "$major" -lt 26 ]]; then
		report fail "docker engine" "${engine} — the setup service's volume subpaths need Docker Engine 26 or later — upgrade Docker"
	else
		report ok "docker engine" "${engine:-unknown} (26 or later is needed for volume subpaths)"
	fi
}

doctor_env() {
	local mode missing="" name
	if [[ ! -f "$env_file" ]]; then
		report fail env ".env is missing beside this script — run ./install.sh"
		return 1
	fi
	mode="$(file_mode "$env_file")"
	if [[ "$mode" == "600" ]]; then
		report ok env ".env present, mode 600"
	else
		report warn env ".env is mode ${mode}; it holds every secret of this stack — chmod 600 ${env_file}"
	fi
	for name in ORCHESTRATOR_TOKEN ORCHESTRATOR_SESSION_SECRET \
		ORCHESTRATOR_SECRET_KEY POSTGRES_PASSWORD DATABASE_URL GITHUB_TOKEN; do
		if is_placeholder "$(get_var "$env_file" "$name")"; then missing="${missing}${name} "; fi
	done
	if [[ -n "$missing" ]]; then
		report fail env "still blank or change-me: ${missing}— set each in ${env_file}"
	else
		report ok env "every REQUIRED variable is set"
	fi
}

doctor_images() {
	local tag image missing="" config
	tag="$(compose_tag)"
	if is_placeholder "$tag"; then
		report fail image "no backend-api image tag in ${compose_file##*/} — the folder is incomplete; re-extract it"
	else
		for image in backend-api web-client; do
			if ! docker image inspect "ghcr.io/rebecamurillo/ai-orchestrator/${image}:${tag}" \
				>/dev/null 2>&1; then missing="${missing}${image} "; fi
		done
		if [[ -n "$missing" ]]; then
			report warn image "${tag} not pulled yet (${missing}) — ./install.sh start"
		else
			report ok image "both images present locally at ${tag}"
		fi
	fi
	# `docker login` cannot be probed without a pull, so this reports only whether an entry
	# exists. The file holds the credential: it is grepped, never read out or copied.
	config="${DOCKER_CONFIG:-${HOME}/.docker}/config.json"
	if [[ -f "$config" ]] && grep -q 'ghcr.io' "$config" 2>/dev/null; then
		report ok registry "ghcr.io has an entry in ${config} (only a pull proves it still works)"
	else
		report warn registry "no ghcr.io entry in ${config} — docker login ghcr.io -u <your-github-user>"
	fi
}

doctor_ports() {
	local running var port
	running="$(compose ps --status running --services 2>/dev/null || true)"
	for var in WEB_CLIENT_PORT BACKEND_API_PORT; do
		port="$(get_var "$env_file" "$var")"
		if [[ -z "$port" ]]; then
			report fail port "${var} is blank in .env — compose publishes no port without it; copy the line from .env.example"
		elif [[ -n "$running" ]]; then
			report ok port "${port} (${var}) is this stack's own"
		elif port_in_use "$port"; then
			report fail port "${port} (${var}) is taken by something else and this stack is not running — move this stack with ${var} in .env; do not stop what is listening"
		else
			report ok port "${port} (${var}) free"
		fi
	done
}

doctor_api() {
	local code body
	body="${scratch}/ping.json"
	code="$(curl -sS -m 10 -o /dev/null -w '%{http_code}' "$(api_base)/healthz" 2>/dev/null || true)"
	if [[ "${code:-000}" != "200" ]]; then
		report fail api "$(api_base)/healthz answered ${code:-000} — ./install.sh start, then ./install.sh logs"
		return 1
	fi
	report ok api "$(api_base)/healthz answers"
	code="$(api_get /api/v1/ping "$body")"
	case "$code" in
		200) report ok token "/api/v1/ping accepts the ORCHESTRATOR_TOKEN in .env" ;;
		401|403) report fail token "/api/v1/ping refused the token in .env (${code}) — the running containers hold an older one; ./install.sh start re-reads .env" ;;
		*) report fail token "/api/v1/ping answered ${code} — ./install.sh logs" ;;
	esac
}

doctor_version() {
	local body code app shipped
	body="${scratch}/version.json"
	code="$(api_get /api/v1/version "$body")"
	if [[ "$code" != "200" ]]; then
		report warn version "/api/v1/version answered ${code} — an instance older than the route; ./install.sh upgrade --tag <newer>"
		return 0
	fi
	app="$(json_string "$body" app_version)"
	shipped="absent"
	if [[ -f "${here}/VERSION" ]]; then shipped="$(tr -d '[:space:]' < "${here}/VERSION")"; fi
	report ok version "running ${app:-unnamed}; VERSION ${shipped}"
	if [[ "$shipped" != "absent" && -n "$app" && "$shipped" != "$app" ]]; then
		report warn version "these files are ${shipped} and the instance is ${app} — ./install.sh upgrade --tag ${shipped}, or re-extract the bundle for ${app}"
	fi
	report ok pinned "bmad $(json_string "$body" bmad_version); harness CLIs $(json_object "$body" harness_versions)"
}

doctor_harnesses() {
	local body code row name enabled failing any=""
	body="${scratch}/harnesses.json"
	code="$(api_get /api/v1/harnesses "$body")"
	if [[ "$code" != "200" ]]; then
		report warn harness "/api/v1/harnesses answered ${code} — ./install.sh logs"
		return 0
	fi
	while IFS= read -r row; do
		[[ -n "$row" ]] || continue
		any=1
		name="$(item_string "$row" name)"
		enabled="$(item_word "$row" enabled)"
		failing="$(item_string "$row" failing_check)"
		if [[ "$enabled" == "true" ]]; then
			report ok harness "${name}: enabled"
		else
			report warn harness "${name}: disabled — ${failing:-no readiness run yet}; re-run readiness from the web UI's Fleet page, or POST /api/v1/harnesses/${name}/readiness"
		fi
	done <<EOF
$(json_items "$body" name)
EOF
	[[ -n "$any" ]] || report warn harness "/api/v1/harnesses returned no rows — ./install.sh logs"
}

doctor_image_tag() {
	if env_sets "$env_file" IMAGE_TAG; then
		report warn IMAGE_TAG ".env still sets IMAGE_TAG, which nothing reads now — delete the line from ${env_file}"
	fi
}

doctor_pins() {
	local line name n=0
	if [[ ! -f "$release_file" ]]; then
		report warn "release pins" "release.env missing beside this script — re-extract the folder"
		return 0
	fi
	while IFS= read -r line; do
		case "$line" in ""|"#"*) continue ;; esac
		name="${line%%=*}"
		env_sets "$env_file" "$name" || continue
		n=1
		report warn "release pins" "${name}: .env sets $(env_pin "$name") but release.env pins $(get_var "$release_file" "$name") — delete the line from .env to follow the release"
	done < "$release_file"
	[[ "$n" -eq 1 ]] || report ok "release pins" "no pin of release.env is overridden in .env"
}

doctor_bmad() {
	local choice="installed" pin installed body code
	body="${scratch}/bmad-version.json"
	if [[ -f "${here}/setup/bmad.choice" ]]; then choice="$(tr -d '[:space:]' < "${here}/setup/bmad.choice")"; fi
	if [[ "$choice" == "removed" ]]; then
		report ok bmad "removed by choice"
		return 0
	fi
	if [[ ! -f "$release_file" ]]; then
		report warn bmad "release.env missing beside this script — the installed version cannot be compared"
		return 0
	fi
	pin="$(get_var "$release_file" BMAD_VERSION)"
	code="$(api_get /api/v1/version "$body")"
	if [[ "$code" != "200" ]]; then
		report warn bmad "/api/v1/version answered ${code} — ./install.sh logs"
		return 0
	fi
	installed="$(json_string "$body" bmad_installed)"
	if [[ "$installed" == "$pin" ]]; then
		report ok bmad "installed ${installed}"
	else
		report fail bmad "installed ${installed:-none} but release.env pins ${pin} — ./install.sh install re-runs setup"
	fi
}

doctor_setup() {
	local body code row name setup failures any=""
	body="${scratch}/setup-harnesses.json"
	code="$(api_get /api/v1/harnesses "$body")"
	if [[ "$code" != "200" ]]; then
		report warn setup "/api/v1/harnesses answered ${code} — ./install.sh logs"
		return 0
	fi
	while IFS= read -r row; do
		[[ -n "$row" ]] || continue
		any=1
		name="$(item_string "$row" name)"
		setup="$(setup_part "$row")"
		case "$setup" in
			null*|"") report fail setup "${name}: no setup record — ./install.sh install runs it" ;;
			*)
				if [[ "$(item_word "$setup" ok)" == "true" ]]; then
					report ok setup "${name}: $(item_string "$setup" trigger) at $(item_string "$setup" at)"
				else
					failures="$(setup_failures "$setup" | tr '\n' ' ')"
					report fail setup "${name}: failed ${failures:-with no script named }— ./install.sh install runs it again; logs/setup/ holds the output"
				fi ;;
		esac
	done <<EOF
$(json_items "$body" name)
EOF
	[[ -n "$any" ]] || report warn setup "/api/v1/harnesses returned no rows — ./install.sh logs"
}

doctor_verify_docker() {
	local running backend sidecar health b_started s_started
	running="$(compose_all ps --status running --services 2>/dev/null || true)"
	if ! docker_enabled; then
		if printf '%s\n' "$running" | grep -qx docker; then
			report warn dind "VERIFY_DOCKER is off but the docker service still runs — ./install.sh start removes it"
		else
			report ok dind "off — a repository whose commands run docker or docker compose fails its verify rows with 'Cannot connect to the Docker daemon'; ./install.sh start --with-docker adds the daemon (README.md § Trust first)"
		fi
		return 0
	fi
	if ! printf '%s\n' "$running" | grep -qx docker; then
		report fail dind "VERIFY_DOCKER=true but the docker service is not running — ./install.sh start"
		return 0
	fi
	sidecar="$(compose_all ps -q docker 2>/dev/null | head -1)"
	backend="$(compose_all ps -q backend-api 2>/dev/null | head -1)"
	health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$sidecar" 2>/dev/null || true)"
	if [[ "$health" != "healthy" ]]; then
		report fail dind "the docker service's daemon is ${health:-not answering} — ./install.sh logs, then ./install.sh start"
		return 0
	fi
	# The sidecar joins backend-api's network namespace when it starts; a backend-api started
	# after it has a new namespace, and Runs then reach nothing on 127.0.0.1:2375.
	b_started="$(docker inspect --format '{{.State.StartedAt}}' "$backend" 2>/dev/null || true)"
	s_started="$(docker inspect --format '{{.State.StartedAt}}' "$sidecar" 2>/dev/null || true)"
	# whole seconds: RFC 3339 nanoseconds drop trailing zeros, which breaks a string compare
	if [[ -n "$b_started" && -n "$s_started" && "${b_started:0:19}" > "${s_started:0:19}" ]]; then
		report fail dind "backend-api restarted after the docker service, which is left in the old network namespace — ./install.sh start recreates it"
		return 0
	fi
	report ok dind "VERIFY_DOCKER=true: the docker service is healthy in backend-api's network namespace (tcp://127.0.0.1:2375)"
}

doctor_disk() {
	local summary root used avail
	summary="$(docker system df --format '{{.Type}} {{.Size}} reclaimable {{.Reclaimable}}' 2>/dev/null | tr '\n' ';' | sed 's/;$//' || true)"
	root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
	if [[ -n "$root" && -d "$root" ]]; then
		used="$(df -P "$root" 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%')"
		avail="$(df -h "$root" 2>/dev/null | awk 'NR==2 {print $4}')"
		if [[ -n "$used" && "$used" -ge 90 ]]; then
			report warn disk "${root} is ${used}% full, ${avail} free — the work volume grows unbounded; docker image prune on superseded tags, and check WORKTREE_RETENTION_DAYS"
		else
			report ok disk "${root}: ${avail} free; ${summary}"
		fi
	else
		report ok disk "the daemon's data root (${root:-unknown}) is inside its own VM, not a path on this machine; ${summary}"
	fi
}

doctor_gc() {
	local missing="" name
	for name in WORKTREE_RETENTION_DAYS WORKTREE_GC_CRON CLONE_CHECK_CRON TERMINAL_POLL_CRON; do
		if [[ -z "$(get_var "$env_file" "$name")" ]]; then missing="${missing}${name} "; fi
	done
	if [[ -n "$missing" ]]; then
		report fail gc "blank in .env: ${missing}— backend-api refuses to start without them; copy each line from .env.example"
	else
		report ok gc "retention $(get_var "$env_file" WORKTREE_RETENTION_DAYS) days; worktree_gc $(get_var "$env_file" WORKTREE_GC_CRON); clone_check $(get_var "$env_file" CLONE_CHECK_CRON); terminal_poll $(get_var "$env_file" TERMINAL_POLL_CRON)"
	fi
}

# ── diagnose: the report a bug report attaches ───────────────────────────────
# Secrets are masked by default: a value is printed only when its NAME is one of the
# non-secret kinds below, so a credential added to the contract later is masked without this
# script changing. The logs go through a sed program built from this machine's own `.env`,
# plus the shapes a provider token has wherever it came from.

env_name_is_secret() {
	case "$1" in
		*TOKEN*|*KEY*|*SECRET*|*PASSWORD*|DATABASE_URL) return 0 ;;
		*) return 1 ;;
	esac
}

env_name_is_public() {
	case "$1" in
		*PORT|*CRON|*VERSION|*_DAYS|*_SECONDS|*_DIR|*MODELS|*TEMPLATE|*TEMPLATES) return 0 ;;
		IMAGE_TAG|COMPOSE_PROJECT_NAME|BIND_ADDRESS|BACKEND_API_URL|LOG_LEVEL) return 0 ;;
		POSTGRES_USER|POSTGRES_DB|MAX_ACTIVE_RUNS|ORCH_TEST_MODE|AGENT_HOME) return 0 ;;
		LITELLM_BASE_URL|LANGFUSE_BASE_URL|LANGFUSE_ENVIRONMENT|LITELLM_SPEND_MATCH) return 0 ;;
		READINESS_BUDGET_USD|LOG_PROMPT_CONTENT_DEFAULT|CLAUDE_SUBSCRIPTION_AUTH) return 0 ;;
		CLAUDE_ALLOWED_TOOLS|VERIFY_DOCKER) return 0 ;;
		*) return 1 ;;
	esac
}

masked_env() {
	local line name value
	while IFS= read -r line; do
		case "$line" in *=*) name="${line%%=*}" ;; *) continue ;; esac
		case "$name" in '#'*|*' '*) continue ;; esac
		value="$(get_var "$env_file" "$name")"
		if env_name_is_secret "$name"; then
			if [[ -n "$value" ]]; then printf '%s=<redacted>\n' "$name"
			else printf '%s=<empty>\n' "$name"; fi
		elif env_name_is_public "$name"; then
			printf '%s=%s\n' "$name" "$value"
		elif [[ -n "$value" ]]; then printf '%s=<masked>\n' "$name"
		else printf '%s=<empty>\n' "$name"; fi
	done < "$env_file"
}

redaction_script() {
	local line name value
	printf '%s\n' 's|ghp_[A-Za-z0-9_]\{8,\}|<redacted>|g' \
		's|github_pat_[A-Za-z0-9_]\{8,\}|<redacted>|g' \
		's|sk-[A-Za-z0-9_.-]\{8,\}|<redacted>|g' \
		's|pk-lf-[A-Za-z0-9_.-]\{8,\}|<redacted>|g' \
		's|://[^:/@ ]\{1,\}:[^@ ]\{1,\}@|://<redacted>@|g'
	[[ -f "$env_file" ]] || return 0
	while IFS= read -r line; do
		case "$line" in *=*) name="${line%%=*}" ;; *) continue ;; esac
		case "$name" in '#'*|*' '*) continue ;; esac
		env_name_is_secret "$name" || continue
		value="$(get_var "$env_file" "$name")"
		[[ "${#value}" -ge 8 ]] || continue
		# a value carrying the delimiter or a sed escape would break the program, not redact
		case "$value" in *'|'*|*'&'*|*'\'*|*change-me*) continue ;; esac
		printf 's|%s|<redacted>|g\n' "$value"
	done < "$env_file"
}

# ── commands ─────────────────────────────────────────────────────────────────
cmd_env() {
	resolve_tag >/dev/null
	token="${GHCR_TOKEN:-${GITHUB_TOKEN:-}}"
	render_env
}

cmd_install() {
	local tag
	step "checking prerequisites"
	check_tools
	tag="$(resolve_tag)"
	say "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?'), compose $(docker compose version --short), release ${tag}"

	if [[ "$pull" -eq 1 ]]; then
		step "registry login"
		resolve_token
		ghcr_login
	fi

	step "environment"
	render_env
	docker_choice
	write_seeds

	stack_up
	step "verifying"
	verify

	step "setup"
	[[ -n "$scratch" ]] || scratch="$(mktemp -d)"
	run_setup install ||
		warn "setup did not finish cleanly — the instance is up; read the lines above, then re-run ./install.sh install"
	print_access
}

cmd_start() {
	check_tools
	[[ -f "$env_file" ]] || die ".env is missing — run ./install.sh first"
	docker_choice
	stack_up
	verify
	print_access
}

cmd_stop() {
	[[ -f "$env_file" ]] || die ".env is missing — nothing was installed here"
	step "stopping ai-orchestrator (data kept)"
	compose stop
}

cmd_status() {
	[[ -f "$env_file" ]] || die ".env is missing — nothing was installed here"
	say "ai-orchestrator ($(compose_tag)):"
	compose ps
}

cmd_logs() {
	[[ -f "$env_file" ]] || die ".env is missing — nothing was installed here"
	compose logs -f --tail 200
}

count_lines() { awk 'END { print NR }' "$1"; }

# The engine's Runs, one per line: `run {id} ({label}) {status}[ {park_kind}][ — {queue_reason}]`
engine_lines() {   # engine_lines ACTIVITY_FILE
	local row park reason
	while IFS= read -r row; do
		[[ -n "$row" ]] || continue
		park="$(item_string "$row" park_kind)"
		reason="$(item_string "$row" queue_reason)"
		printf 'run %s (%s) %s%s%s\n' "$(item_string "$row" run_id)" "$(item_string "$row" run_label)" \
			"$(item_string "$row" status)" "${park:+ ${park}}" "${reason:+ — ${reason}}"
	done <<EOF
$(json_array_items "$1" in_engine run_id)
EOF
}

# place FROM TO — a new inode, never a write through the old one: `install.sh` is a product
# path, and the bash running it reads the open file.
place_file() {
	local target="${here}/${1}"
	mkdir -p "$(dirname "$target")"
	cp -p "${work}/staged/${1}" "${target}.upgrade-new"
	mv "${target}.upgrade-new" "$target"
}

keep_previous() {   # keep_previous PATH — the folder's copy moves under .upgrade/{ts}/previous/
	mkdir -p "$(dirname "${work}/previous/${1}")"
	mv "${here}/${1}" "${work}/previous/${1}"
}

# Everything below only reads: the lists land in $plan, the folder is untouched.
plan_files() {   # plan_files OLD_TABLE NEW_TABLE
	local p h r oh nm
	: > "${plan}/replace"; : > "${plan}/add"; : > "${plan}/remove"; : > "${plan}/edited"
	: > "${plan}/seed"; : > "${plan}/examples"
	while IFS=$'\t' read -r p h r; do
		[[ -n "$p" ]] || continue
		unsafe_path "$p"
		case "$r" in
			product)
				if [[ -e "${here}/${p}" ]]; then
					printf '%s\n' "$p" >> "${plan}/replace"
					oh="$(table_field "$1" "$p" 2)"
					if [[ -z "$oh" || "$(sha256_of "${here}/${p}")" != "$oh" ]]; then
						printf '%s\n' "$p" >> "${plan}/edited"
					fi
				else
					printf '%s\n' "$p" >> "${plan}/add"
				fi
				case "$p" in
					templates/shipped/*.yaml)
						nm="${p#templates/shipped/}"; nm="${nm%.yaml}"
						if [[ "$nm" == */* ]]; then :
						elif [[ -z "$(table_field "$1" "$p" 3)" ]]; then
							printf 'new: %s\n' "$p" >> "${plan}/examples"
						elif [[ "$(table_field "$1" "$p" 2)" != "$h" && -e "${here}/templates/${nm}.yaml" ]]; then
							printf 'improved: %s (your copy: templates/%s.yaml)\n' "$p" "$nm" >> "${plan}/examples"
						fi ;;
				esac ;;
			seed)
				[[ -e "${here}/${p}" ]] || printf '%s\n' "$p" >> "${plan}/seed" ;;
		esac
	done < "$2"
	while IFS=$'\t' read -r p h r; do
		[[ -n "$p" && "$r" == "product" ]] || continue
		unsafe_path "$p"
		[[ -z "$(table_field "$2" "$p" 3)" && -e "${here}/${p}" ]] || continue
		printf '%s\n' "$p" >> "${plan}/remove"
	done < "$1"
}

# A manifest names paths inside this folder and nowhere else
unsafe_path() {
	case "$1" in
		/*|..|../*|*/..|*/../*) refuse 1 "product-files.json names ${1}, which is outside this folder" ;;
	esac
}

# Refuses (exit 1 or 3) before anything is written when backend-api runs but cannot be asked, or a
# step is working. Sets api_up.
setup_preflight() {
	local services health activity working
	api_up=0
	services="$(compose ps --status running --services 2>/dev/null || true)"
	if printf '%s\n' "$services" | grep -qx backend-api; then api_up=1; fi
	[[ "$api_up" -eq 1 ]] || return 0
	health="$(api_get /healthz "${scratch}/healthz.out")"
	activity="$(api_get /api/v1/instance/activity "${scratch}/activity.json")"
	if [[ "$health" != "200" || "$activity" != "200" ]]; then
		refuse 1 "backend-api is running but its API did not answer (/healthz ${health}, /api/v1/instance/activity ${activity}) — ./install.sh logs"
	fi
	working="$(working_lines "${scratch}/activity.json" working)"
	[[ -z "$working" ]] || refuse 3 "$working"
}

# `setup`, `setup --reset`, `bmad remove`, `bmad install`: one setup run under the hold; no restart.
cmd_setup() {
	local release trigger word working rc=0 rec=0 api_up=0
	local -a runner_args=()
	check_tools
	[[ -f "$env_file" ]] || die ".env is missing — run ./install.sh first"
	scratch="$(mktemp -d)"
	release="$(resolve_tag)"
	setup_preflight
	if [[ "$api_up" -eq 1 ]]; then
		take_hold 900 setup
		case "$hold_code" in
			2??) ;;
			409)
				working="$(working_lines "${scratch}/hold.json" errors)"
				refuse 3 "${working:-the instance hold answered 409: a step is working}" ;;
			*) refuse 1 "the instance hold answered ${hold_code} — ./install.sh logs" ;;
		esac
	fi
	if [[ "$command" == "bmad" ]]; then
		word="installed"
		[[ "$bmad_arg" != "remove" ]] || word="removed"
		mkdir -p "${here}/setup"
		printf '%s\n' "$word" > "${here}/setup/bmad.choice.tmp"
		mv "${here}/setup/bmad.choice.tmp" "${here}/setup/bmad.choice"
		say "setup/bmad.choice: ${word}"
	fi
	trigger="on-demand"
	if [[ "$reset" -eq 1 ]]; then trigger="reset"; runner_args=(--reset); fi
	step "setup (${trigger})"
	setup_service_run "$trigger" "$release" ${runner_args[@]+"${runner_args[@]}"} || rc=$?
	[[ "$held" -eq 0 ]] || release_hold 15
	if [[ "$api_up" -eq 1 ]]; then
		print_setup_record "$rc" || rec=1
	else
		say "setup record not read: backend-api is not running — ./install.sh start, then ./install.sh doctor"
	fi
	[[ "$rc" -eq 0 && "$rec" -eq 0 ]] || exit 2
}

cmd_upgrade() {
	local old new running_version code image ts services api_up=0 staged new_dbos old_dbos line p backup
	local working engine postgres_up=0 setup_rc=0 made_backups=0
	local -a run_flags=(--rm)
	check_tools
	[[ -f "$env_file" ]] || die ".env is missing — run ./install.sh first"
	[[ -n "$tag_arg" ]] || die "upgrade needs --tag vX.Y.Z"
	new="$tag_arg"
	[[ "$new" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]] || die "--tag ${new} is not a release tag"
	old=""
	if [[ -f "${here}/VERSION" ]]; then old="$(tr -d '[:space:]' < "${here}/VERSION")"; fi
	step "upgrade ${old} → ${new}"
	# What the instance answers is the version actually running; VERSION is only what this folder
	# holds, and the two disagree whenever a refresh never reached a restart.
	running_version="$old"
	scratch="$(mktemp -d)"
	code="$(api_get /api/v1/version "${scratch}/version.json")"
	if [[ "$code" == "200" ]]; then
		running_version="$(json_string "${scratch}/version.json" app_version)"
		say "running ${running_version} → target ${new}"
	else
		say "running ${running_version} (from VERSION; /api/v1/version answered ${code}) → target ${new}"
	fi
	[[ "$new" != "$running_version" ]] ||
		die "${new} is already what is running — nothing to upgrade; pass the newer tag"
	upgrade_old="${old:-$running_version}"
	upgrade_new="$new"
	[[ -f "$manifest_file" ]] ||
		refuse 5 "this folder has no product-files.json: it was installed before release manifests — follow \"Migrating an existing folder\" in README.md; never run an older install.sh upgrade across this release"

	# ── stage the release: nothing in the folder changes until the replace step ──
	image="$(backend_image)"
	[[ -n "$image" ]] || die "no backend-api image in ${compose_file##*/} — nothing was changed"
	image="${image}:${new}"
	if [[ "$pull" -eq 1 ]]; then
		resolve_token
		ghcr_login
	fi
	ts="$(date -u +%Y%m%dT%H%M%SZ)"
	work="${here}/.upgrade/${ts}"
	staged="${work}/staged"
	mkdir -p "$staged" "${work}/previous"
	if [[ "$pull" -eq 1 ]]; then
		docker pull "$image" > "${scratch}/pull.out" 2>&1 ||
			refuse 1 "docker pull ${image} failed:" "$(cat "${scratch}/pull.out")"
	else
		run_flags+=(--pull never)
	fi
	docker run "${run_flags[@]}" "$image" kit bootstrap > "${work}/staged.tar" 2> "${scratch}/extract.err" ||
		refuse 1 "cannot read ${image} (kit bootstrap):" "$(cat "${scratch}/extract.err")"
	tar -x -C "$staged" --strip-components 1 -f "${work}/staged.tar" 2> "${scratch}/tar.err" ||
		refuse 1 "cannot unpack ${image}:" "$(cat "${scratch}/tar.err")"
	rm -f "${work}/staged.tar"
	[[ -f "${staged}/product-files.json" && -f "${staged}/release.env" ]] ||
		refuse 1 "${image} carries no product-files.json and release.env — a release before the manifest cannot be upgraded to; restore the backup by hand"

	# ── plan: pure reads ──
	plan="${scratch}/plan"
	mkdir -p "$plan"
	manifest_table "$manifest_file" > "${plan}/old.tsv"
	manifest_table "${staged}/product-files.json" > "${plan}/new.tsv"
	[[ -s "${plan}/new.tsv" ]] || refuse 1 "${image}'s product-files.json lists no file"
	plan_files "${plan}/old.tsv" "${plan}/new.tsv"
	plan_release_pins "${staged}/release.env" "$new"

	# ── refusals ──
	services="$(compose ps --status running --services 2>/dev/null || true)"
	if printf '%s\n' "$services" | grep -qx backend-api; then api_up=1; fi
	if printf '%s\n' "$services" | grep -qx postgres; then postgres_up=1; fi
	new_dbos="$(env_pin DBOS_APPLICATION_VERSION)"
	[[ -n "$new_dbos" ]] || new_dbos="$(get_var "${staged}/release.env" DBOS_APPLICATION_VERSION)"
	if [[ "$api_up" -eq 1 ]]; then
		local health activity
		health="$(api_get /healthz "${scratch}/healthz.out")"
		activity="$(api_get /api/v1/instance/activity "${scratch}/activity.json")"
		if [[ "$health" != "200" || "$activity" != "200" ]]; then
			refuse 1 "backend-api is running but its API did not answer (/healthz ${health}, /api/v1/instance/activity ${activity}) — ./install.sh logs"
		fi
		working="$(working_lines "${scratch}/activity.json" working)"
		[[ -z "$working" ]] || refuse 3 "$working"
		old_dbos="$(json_string "${scratch}/activity.json" dbos_application_version)"
		engine="$(engine_lines "${scratch}/activity.json")"
		if [[ "$old_dbos" != "$new_dbos" && -n "$engine" ]]; then
			refuse 4 "release ${new} changes DBOS_APPLICATION_VERSION ${old_dbos} → ${new_dbos}; these Runs are in the engine and would not resume — finish or cancel them first:" "$engine"
		fi
	else
		old_dbos="$(env_pin DBOS_APPLICATION_VERSION)"
		[[ -n "$old_dbos" ]] || old_dbos="$(get_var "$release_file" DBOS_APPLICATION_VERSION)"
		[[ "$old_dbos" == "$new_dbos" ]] ||
			refuse 4 "release ${new} changes DBOS_APPLICATION_VERSION ${old_dbos} → ${new_dbos} and backend-api is stopped, so the Runs in the engine cannot be listed — ./install.sh start, then upgrade again"
	fi

	print_upgrade_plan "$new"
	say "Read the release notes first. Migrations run forward only; the backup below is what a rollback"
	say "restores from. A release that changes DBOS_APPLICATION_VERSION is refused while Runs are in the engine."
	confirm "Continue?" || refuse 1 "upgrade cancelled"

	# ── the hold, the backup ──
	if [[ "$api_up" -eq 1 ]]; then
		take_hold 1800 "upgrade to ${new}"
		case "$hold_code" in
			2??) ;;
			409)
				working="$(working_lines "${scratch}/hold.json" errors)"
				refuse 3 "${working:-the instance hold answered 409: a step is working}" ;;
			*) refuse 1 "the instance hold answered ${hold_code} — ./install.sh logs" ;;
		esac
	fi
	backup=""
	if [[ "$postgres_up" -eq 1 ]]; then
		[[ -d "${here}/backups" ]] || made_backups=1
		mkdir -p "${here}/backups"
		backup="${here}/backups/orchestrator-${old}-${ts}.dump"
		dump_partial="$backup"
		if ! compose exec -T postgres pg_dump -U "$(get_var "$env_file" POSTGRES_USER)" -Fc \
			"$(get_var "$env_file" POSTGRES_DB)" > "$backup"; then
			rm -f "$backup"
			[[ "$made_backups" -eq 0 ]] || rmdir "${here}/backups" 2>/dev/null || true
			refuse 1 "database backup failed — ./install.sh logs"
		fi
		dump_partial=""
		say "database backup: ${backup}"
	else
		warn "postgres is not running — no backup taken"
	fi
	upgrade_backup="$backup"

	# ── replace: the first write ──
	upgrade_stage="replace"
	# one file at a time, so an interruption leaves at most one product path absent
	while IFS= read -r p; do keep_previous "$p"; place_file "$p"; done < "${plan}/replace"
	while IFS= read -r p; do place_file "$p"; done < "${plan}/add"
	while IFS= read -r p; do keep_previous "$p"; done < "${plan}/remove"
	while IFS= read -r p; do place_file "$p"; say "wrote ${p}"; done < "${plan}/seed"
	keep_previous product-files.json
	place_file product-files.json

	upgrade_stage="setup"
	setup_service_run upgrade "$new" || setup_rc=$?
	[[ "$setup_rc" -eq 0 ]] || warn "setup exited ${setup_rc} — the record below names what failed"

	upgrade_stage="start"
	stack_up
	verify
	upgrade_stage=""

	print_upgrade_report "$old" "$new" "$ts" "$setup_rc"
	print_access
}

# What the upgrade will do, from the lists plan_files and plan_release_pins wrote
print_upgrade_plan() {
	local line
	say "replace $(count_lines "${plan}/replace") files, add $(count_lines "${plan}/add"), remove $(count_lines "${plan}/remove"); your files are not touched"
	while IFS= read -r line; do say "  edited here, kept in .upgrade/${work##*/}/previous/: ${line}"; done < "${plan}/edited"
	while IFS= read -r line; do say "  removed by this release: ${line}"; done < "${plan}/remove"
	while IFS= read -r line; do say "  written (absent here): ${line}"; done < "${plan}/seed"
	while IFS= read -r line; do say "  ${line}"; done < "${plan}/examples"
	print_pin_lines
}

print_pin_lines() {
	local line
	if [[ -s "${plan}/pins" ]]; then
		say "release pins this upgrade changes:"
		while IFS= read -r line; do say "  ${line}"; done < "${plan}/pins"
	else
		say "release pins: unchanged"
	fi
	if [[ -s "${plan}/overrides" ]]; then
		say ".env overrides of release.env, which keep their value:"
		while IFS= read -r line; do say "  ${line}"; done < "${plan}/overrides"
	else
		say "no pin of release.env is overridden in .env"
	fi
}

print_upgrade_report() {   # print_upgrade_report OLD NEW TS SETUP_RC
	local line rows
	step "upgraded ${1} → ${2}"
	say "replaced: $(count_lines "${plan}/replace") files"
	while IFS= read -r line; do say "added: ${line}"; done < "${plan}/add"
	while IFS= read -r line; do say "removed: ${line} (kept at .upgrade/${3}/previous/${line})"; done < "${plan}/remove"
	while IFS= read -r line; do say "edited: ${line} (your copy: .upgrade/${3}/previous/${line})"; done < "${plan}/edited"
	while IFS= read -r line; do say "seed written: ${line}"; done < "${plan}/seed"
	while IFS= read -r line; do say "$line"; done < "${plan}/examples"
	print_pin_lines
	print_setup_record "$4" || say "the setup record above is not ok — ./install.sh logs"
	say "Runs that continue:"
	rows=""
	[[ ! -f "${scratch}/activity.json" ]] || rows="$(engine_lines "${scratch}/activity.json")"
	if [[ -n "$rows" ]]; then printf '%s\n' "$rows" | sed 's/^/  /'; else say "  none"; fi
}

# A harness pin from .env, a `#` comment after any whitespace dropped (get_var drops only `  #`).
env_pin() {
	get_var "$env_file" "$1" | sed -E 's/[[:space:]]+#.*$//'
}

# The NAME=value lines of a release.env
read_release_pins() { grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$1" || true; }

# The release.env this folder holds against the release's: each changed pin as `NAME old → new`,
# and each pin `.env` overrides with a different value. Writes $plan/pins and $plan/overrides.
plan_release_pins() {   # plan_release_pins STAGED_RELEASE_ENV TARGET
	local line name old new note pinned
	: > "${plan}/pins"; : > "${plan}/overrides"
	while IFS= read -r line; do
		[[ -n "$line" ]] || continue
		name="${line%%=*}"
		new="$(get_var "$1" "$name")"
		old="$(get_var "$release_file" "$name")"
		if [[ "$old" != "$new" ]]; then
			note=""
			if is_plain_version "$old" && is_plain_version "$new" && version_older "$new" "$old"; then
				note="   (downgrade)"
			fi
			printf '%s %s → %s%s\n' "$name" "${old:-unset}" "$new" "$note" >> "${plan}/pins"
		fi
		if env_sets "$env_file" "$name"; then
			pinned="$(env_pin "$name")"
			if [[ "$pinned" != "$new" ]]; then
				printf '%s: .env sets %s, release %s pins %s\n' "$name" "$pinned" "$2" "$new" >> "${plan}/overrides"
			fi
		fi
	done <<EOF
$(read_release_pins "$1")
EOF
}

backend_image() {
	sed -n 's/^ *image: *\(.*\/backend-api\):.*/\1/p' "$compose_file" | head -1
}

cmd_doctor() {
	local docker_ok=0 env_ok=0
	scratch="$(mktemp -d)"
	step "doctor"
	if doctor_docker; then docker_ok=1; fi
	if doctor_env; then env_ok=1; fi
	if [[ "$env_ok" -eq 1 && "$docker_ok" -eq 1 ]]; then
		doctor_images
		doctor_ports
	fi
	if [[ "$env_ok" -eq 1 ]]; then
		doctor_image_tag
		doctor_pins
		if doctor_api; then
			doctor_version
			doctor_harnesses
			doctor_setup
			doctor_bmad
		fi
		if [[ "$docker_ok" -eq 1 ]]; then doctor_verify_docker; fi
		doctor_gc
	fi
	if [[ "$docker_ok" -eq 1 ]]; then doctor_disk; fi
	say
	say "${doctor_fails} fail, ${doctor_warns} warn"
	[[ "$doctor_fails" -eq 0 ]] || die "fix each fail line above — every one ends with the command to run or the variable to set"
}

cmd_diagnose() {
	local dir out stamp redact code
	[[ -f "$env_file" ]] || die ".env is missing — nothing was installed here"
	scratch="$(mktemp -d)"
	redact="${scratch}/redact.sed"
	redaction_script > "$redact"
	dir="${here}/diagnostics"
	mkdir -p "$dir"
	stamp="$(date -u +%Y%m%dT%H%M%SZ)"
	out="${dir}/${stamp}.md"
	code="$(api_get /api/v1/version "${scratch}/version.json")"
	{
		printf '# ai-orchestrator diagnostics %s\n\n' "$stamp"
		printf '## Versions\n\n```\n'
		printf 'compose    %s\n' "$(compose_tag)"
		printf 'VERSION    %s\n' \
			"$( [[ -f "${here}/VERSION" ]] && tr -d '[:space:]' < "${here}/VERSION" || printf absent )"
		if [[ "$code" == "200" ]]; then
			printf '/version   app %s · kit %s · bmad %s\n' \
				"$(json_string "${scratch}/version.json" app_version)" \
				"$(json_string "${scratch}/version.json" kit_version)" \
				"$(json_string "${scratch}/version.json" bmad_version)"
			printf 'harnesses  %s\n' "$(json_object "${scratch}/version.json" harness_versions)"
		else
			printf '/version   answered %s — the stack is down, or older than the route\n' "$code"
		fi
		printf '```\n\n## docker compose ps\n\n```\n'
		compose ps 2>&1 || true
		printf '```\n\n## docker compose logs, last 200 lines, redacted\n\n```\n'
		compose logs --tail 200 --no-color 2>&1 | sed -f "$redact" || true
		printf '```\n\n## .env, values masked\n\n```\n'
		masked_env | sed -f "$redact"
		printf '```\n'
	} > "$out"
	chmod 600 "$out"
	say "wrote ${out}"
	say
	say "Every value in it is masked unless it is a port, a cron, a version, a directory or a"
	say "flag, and the logs are filtered for token-shaped strings. Read it before you send it:"
	say "a log line can carry anything a target repository printed."
}

# ── harness: a CLI pin, or which credential the claude harness authenticates with ──
# The row a harness has in /api/v1/harnesses, printed as one line.
print_harness_row() {   # print_harness_row NAME → 0 enabled, 1 disabled, 2 no row to read
	local name="$1" body code row
	body="${scratch}/harnesses.json"
	code="$(api_get /api/v1/harnesses "$body")"
	if [[ "$code" != "200" ]]; then
		say "/api/v1/harnesses answered ${code} — ./install.sh logs"
		return 2
	fi
	row="$(json_items "$body" name | grep -E '"name" *: *"'"$name"'"' | head -1 || true)"
	if [[ -z "$row" ]]; then
		say "${name} is not in /api/v1/harnesses — ./install.sh logs"
		return 2
	fi
	if [[ "$(item_word "$row" enabled)" == "true" ]]; then
		say "${name}: enabled"
		return 0
	fi
	say "${name}: disabled — $(item_string "$row" failing_check)"
	return 1
}

# Recreated, never `compose restart`: a restart keeps the environment the container was
# created with, so a changed `.env` value would never reach it.
recreate_backend() {   # recreate_backend WHAT → WHAT is what .env now holds, said on failure
	if compose up -d --no-deps --wait --wait-timeout 1800 backend-api; then
		docker_reconcile
		return 0
	fi
	say "$1 is written to .env; backend-api did not come back healthy with it."
	warn "backend-api did not become healthy after the recreate — ./install.sh logs"
	return 1
}

# `harness <name> --version X`: the pin is `.env`'s, and the container's entrypoint (`ensure`)
# installs it at the next start onto the `harness-bin` volume — no new image needed.
cmd_harness_version() {
	local variable="$1" since lines current tmp
	current="$(env_pin "$variable")"
	[[ -n "$current" || ! -f "$release_file" ]] || current="$(get_var "$release_file" "$variable")"
	if [[ "$current" == "$version_arg" ]]; then
		say "${harness_arg} is already pinned at ${version_arg} — nothing to do."
		return 0
	fi
	# the pin is release.env's; .env holds only a commented `# NAME=` override line until one is set
	if ! env_sets "$env_file" "$variable"; then
		tmp="$(mktemp)"
		awk -v name="$variable" '!done && index($0, "# " name "=") == 1 { print name "="; done = 1; next } { print }' \
			"$env_file" > "$tmp"
		cat "$tmp" > "$env_file"
		rm -f "$tmp"
		env_sets "$env_file" "$variable" || printf '%s=\n' "$variable" >> "$env_file"
	fi
	set_var "$env_file" "$variable" "$version_arg"
	step "${harness_arg} → ${version_arg}"
	say "${variable}=${version_arg} in .env now. backend-api installs it when it is recreated"
	say "(from the image when it ships that version, else one npm install onto harness-bin). A pin"
	say "that cannot be installed refuses ${harness_arg} alone until the next start."
	if compose ps --status running --services 2>/dev/null | grep -q '^backend-api$'; then
		if confirm "Recreate backend-api so it installs ${harness_arg} ${version_arg}?"; then
			since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
			recreate_backend "${variable}=${version_arg}" || return 1
			step "verifying"
			lines="$(compose logs --no-log-prefix --since "$since" backend-api 2>/dev/null |
				grep -F "[harness:${harness_arg}]" || true)"
			[[ -z "$lines" ]] || say "$lines"
			if grep -q 'refused' <<< "$lines"; then
				warn "backend-api refused ${harness_arg} at ${version_arg} — the lines above say why; ./install.sh logs"
				return 1
			fi
			say "The row reads disabled until readiness is re-run:"
			print_harness_row "$harness_arg" || true
		else
			say "Not recreated: ./install.sh start applies the pin."
		fi
	else
		say
		say "backend-api is not running: ./install.sh start applies the pin."
	fi
	say
	say "The pin change resets ${harness_arg}'s readiness. Re-run it from the web UI's Fleet page,"
	say "or POST /api/v1/harnesses/${harness_arg}/readiness."
}

cmd_harness() {
	local rc
	[[ -f "$env_file" ]] || die ".env is missing — run ./install.sh first"
	[[ -n "$harness_arg" ]] ||
		die "harness needs a name: ./install.sh harness claude --subscription (or --api-key, or --version X)"
	if [[ "$version_given" -eq 1 ]]; then
		local variable
		case "$harness_arg" in
			claude)   variable=CLAUDE_CODE_VERSION ;;
			codex)    variable=CODEX_VERSION ;;
			opencode) variable=OPENCODE_VERSION ;;
			*) die "unknown harness '${harness_arg}' — one of claude, codex, opencode" ;;
		esac
		[[ -z "$subscription" ]] ||
			die "--version cannot be combined with --subscription or --api-key: ./install.sh harness <claude|codex|opencode> --version X"
		is_plain_version "$version_arg" ||
			die "--version needs a version like 2.1.260, not '${version_arg}': ./install.sh harness <claude|codex|opencode> --version X"
		scratch="$(mktemp -d)"
		cmd_harness_version "$variable"
		return
	fi
	[[ "$harness_arg" == "claude" ]] ||
		die "only claude has a subscription login; ${harness_arg} authenticates with an API key alone — set it in your gateway's environment and restart the gateway"
	[[ -n "$subscription" ]] || die "harness claude needs --subscription, --api-key or --version X"
	scratch="$(mktemp -d)"

	if [[ "$subscription" -eq 1 ]]; then
		set_var "$env_file" CLAUDE_SUBSCRIPTION_AUTH true
		step "claude → Claude Max/Pro subscription"
		say "CLAUDE_SUBSCRIPTION_AUTH is true in .env now. The adapter stops exporting"
		say "ANTHROPIC_AUTH_TOKEN — set, it would override the login — and moves the gateway's"
		say "virtual key into the x-litellm-api-key header instead."
		say
		say "One edit stays yours, because this script does not rewrite YAML. In"
		say "your gateway's litellm.config.yaml uncomment both:"
		say
		say "  general_settings:"
		say "    forward_client_headers_to_llm_api: true   # EVERY route on this proxy, not"
		say "                                             # only the Claude one"
		say "  model_list:"
		say "    - model_name: claude-subscription        # the entry and its litellm_params"
		say
		say "Then restart your gateway and bind the Run to"
		say "the model name claude-subscription: Claude Code's own default model is not in"
		say "model_list, and a Run on it answers 400."
	else
		set_var "$env_file" CLAUDE_SUBSCRIPTION_AUTH false
		step "claude → the gateway's own API key"
		say "CLAUDE_SUBSCRIPTION_AUTH is false in .env now: the virtual key reaches the harness"
		say "as ANTHROPIC_AUTH_TOKEN again."
		say "Comment forward_client_headers_to_llm_api back out in"
		say "your gateway's litellm.config.yaml, make sure ANTHROPIC_API_KEY is set in"
		say "your gateway's environment, and restart the gateway."
	fi

	if compose ps --status running --services 2>/dev/null | grep -q '^backend-api$'; then
		if [[ "$subscription" -eq 1 ]]; then
			step "logging Claude Code in, inside the container"
			say "It prints a URL. Open it, finish the login there, then come back here. The"
			say "credentials land under AGENT_HOME, a named volume that survives a restart."
			compose exec backend-api claude login ||
				warn "claude login did not finish — re-run ./install.sh harness claude --subscription"
		fi
		if confirm "Recreate backend-api so it re-reads .env?"; then
			recreate_backend "CLAUDE_SUBSCRIPTION_AUTH" || return 1
			step "verifying"
			rc=0
			print_harness_row claude || rc=$?
			if [[ "$rc" -eq 1 ]]; then
				say "In this mode the probe runs 'claude auth status' and refuses there first,"
				say "so an expired login shows up as that line."
			fi
		else
			say "Not recreated: backend-api keeps the old setting until ./install.sh start."
		fi
	else
		say
		say "backend-api is not running, so the login cannot happen yet. Start the stack"
		say "(./install.sh start) and re-run this command to log in and verify."
	fi
	say
	say "What is proven, and what is not: the container half is unit-tested; the gateway half"
	say "above is written from LiteLLM's own guide and has never been run against a live"
	say "subscription (deploy/llm-platform/README.md of github.com/rebecamurillo/ai-orchestrator). A subscription is not metered per"
	say "request, so the dollar figures a Run shows come from LiteLLM's price table rather"
	say "than from anything you are billed — the budget still stops the Run."
}

cmd_uninstall() {
	local answer
	[[ -f "$env_file" ]] || die ".env is missing — nothing was installed here"
	step "uninstall"
	say "This stops ai-orchestrator and DELETES its volumes: the database, every clone and"
	say "worktree, the agent home and the harness CLIs (harness-bin). .env is kept so the token"
	say "survives; delete it yourself."
	if [[ "$yes" -eq 0 ]]; then
		read -r -p "Type 'delete' to confirm: " answer
		[[ "$answer" == "delete" ]] || die "uninstall cancelled"
	fi
	compose_all down -v --remove-orphans
	say "removed. ${env_file} was kept."
}

case "$command" in
	install)   cmd_install ;;
	start)     cmd_start ;;
	stop)      cmd_stop ;;
	status)    cmd_status ;;
	logs)      cmd_logs ;;
	upgrade)   cmd_upgrade ;;
	uninstall) cmd_uninstall ;;
	env)       cmd_env ;;
	doctor)    cmd_doctor ;;
	diagnose)  cmd_diagnose ;;
	harness)   cmd_harness ;;
	setup|bmad) cmd_setup ;;
esac
