#!/usr/bin/env bash
# install.sh — ai-orchestrator, from an empty machine to http://127.0.0.1:4321 in one command.
#
#   ./install.sh                                  # interactive: asks for the GitHub token,
#                                                 #   offers the optional llm-platform stack
#   GHCR_TOKEN=ghp_… ./install.sh --yes           # unattended, orchestrator only
#   GHCR_TOKEN=ghp_… ANTHROPIC_API_KEY=sk-ant-… ./install.sh --yes --with-platform
#
#   ./install.sh start | stop | status | logs     # day-2 operations on this stack
#   ./install.sh doctor                           # read-only checks; non-zero on any `fail`
#   ./install.sh diagnose                         # a redacted report to attach to a bug report
#   ./install.sh harness claude --subscription    # Claude Max/Pro auth instead of an API key
#   ./install.sh harness claude --api-key         # back to the gateway's own API key
#   ./install.sh harness claude --version 2.1.260 # pin a harness CLI (claude|codex|opencode), recreate
#   ./install.sh upgrade --tag v0.2.0             # login + pull, show pin changes, ask, backup, retag, restart
#   ./install.sh uninstall                        # stop and DELETE the data, after confirmation
#   ./install.sh env --tag v0.1.0                 # only write .env (what `install` does first)
#   ./install.sh --no-pull                        # images built on this machine: no registry login, no pull
#
# What `install` does, in order:
#   1. checks docker, docker compose v2, curl and openssl are here, and the daemon answers
#   2. logs the docker daemon in to ghcr.io with the token — the images are private
#   3. writes `.env` from `.env.example` with generated secrets, once; never overwrites it
#   4. optionally brings up llm-platform/ (LiteLLM + Langfuse) and points `.env` at it
#   5. pulls the two images pinned by IMAGE_TAG and starts the stack
#   6. proves /healthz and the login token, then prints where to go
#
# Inputs (environment, all optional unless the step needs them):
#   GHCR_TOKEN          GitHub token that can read the packages; GITHUB_TOKEN is the fallback
#   GITHUB_TOKEN        the git credential written to .env (clone/push of your repositories);
#                       defaults to the token above, which is usually the same PAT
#   GITHUB_USER         registry login name; resolved from the token when unset
#   IMAGE_TAG           the release to run; `--tag` wins, then the VERSION file beside this script
#   ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY   provider keys for the llm-platform stack
#
# Portable bash 3.2 (a stock macOS): no associative arrays, no `sed -i`, no `mapfile`.
# Nothing here stops a service it did not start, and nothing rebinds a port that is taken:
# a port in use is reported with the variable that moves this stack off it.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_file="${here}/.env"
example_file="${here}/.env.example"
compose_file="${here}/docker-compose.yml"
# llm-platform/ sits beside this script in the bundle and in the checkout alike (deploy/ is the client install, entire)
platform_dir="${here}/llm-platform"
platform_env="${platform_dir}/.env"

yes=0
with_platform=""     # "" ask, 1 yes, 0 no
pull=1               # 0: the images are already on this machine (built from a checkout)
tag_arg=""
command=""
harness_arg=""       # the harness `harness` acts on
subscription=""      # "" neither flag, 1 --subscription, 0 --api-key
version_arg=""       # the harness CLI version `harness --version` pins
version_given=0      # 1 once --version appeared, so an empty value is refused rather than ignored
scratch=""           # where an API answer is parked while it is read; removed on exit
trap '[[ -z "$scratch" ]] || rm -rf "$scratch"' EXIT

# ── output ───────────────────────────────────────────────────────────────────
say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
	sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ── arguments ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
	case "$1" in
		install|start|stop|status|logs|upgrade|uninstall|env) command="$1" ;;
		doctor|diagnose|harness) command="$1" ;;
		--tag) [[ $# -ge 2 ]] || die "--tag needs a value"; tag_arg="$2"; shift ;;
		--tag=*) tag_arg="${1#--tag=}" ;;
		--yes|-y) yes=1 ;;
		--no-pull) pull=0 ;;
		--with-platform) with_platform=1 ;;
		--no-platform) with_platform=0 ;;
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
		*) [[ "$command" == "harness" && -z "$harness_arg" ]] || die "unknown argument: $1 (try --help)"
		   harness_arg="$1" ;;
	esac
	shift
done
command="${command:-install}"
[[ "$version_given" -eq 0 || "$command" == "harness" ]] ||
	die "--version is only for: ./install.sh harness <claude|codex|opencode> --version X"

# ── small helpers ────────────────────────────────────────────────────────────
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "$1 is not installed — $2"; }

# NAME=value from a dotenv file, minus a trailing `  # comment` and surrounding quotes
get_var() {
	local file="$1" name="$2" line value
	# an absent llm-platform/.env answers from its contract, so the port check can run before it exists
	[[ -f "$file" ]] || file="${file}.example"
	line="$(grep "^${name}=" "$file" 2>/dev/null | head -1 || true)"
	value="${line#*=}"
	value="${value%%  #*}"
	value="${value%"${value##*[! ]}"}"   # trim trailing spaces
	value="${value#\'}"; value="${value%\'}"
	value="${value#\"}"; value="${value%\"}"
	printf '%s' "$value"
}

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

compose()      { docker compose --project-directory "$here" -f "$compose_file" "$@"; }
# The llm-platform stack runs as its own compose project, named after this stack's
# COMPOSE_PROJECT_NAME (`aio` → `aio-host`), never as the host file's own `name:`: a
# repository checkout's dev llm-platform stack is `ai-orchestrator-host`, and sharing that name would
# make `up` here recreate a stack this script did not start (hard rule 9 — learned the hard
# way on 2026-09-30).
platform_project() { printf '%s-host' "$( [[ -f "$env_file" ]] && get_var "$env_file" COMPOSE_PROJECT_NAME || true )"; }
platform_compose() {
	local project; project="$(platform_project)"; [[ "$project" != "-host" ]] || project="aio-host"
	docker compose --project-name "$project" --project-directory "$platform_dir" -f "${platform_dir}/docker-compose.yml" --env-file "$platform_env" "$@"
}

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
	elif [[ -n "${IMAGE_TAG:-}" ]]; then tag="$IMAGE_TAG"
	elif [[ -f "${here}/VERSION" ]]; then tag="$(tr -d '[:space:]' < "${here}/VERSION")"
	elif [[ -f "$env_file" ]]; then tag="$(get_var "$env_file" IMAGE_TAG)"
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
render_env() {
	local tag="$1" password fernet
	if [[ -f "$env_file" ]]; then
		say ".env already exists — leaving it alone"
		return 0
	fi
	cp "$example_file" "$env_file"
	chmod 600 "$env_file"

	password="$(openssl rand -hex 24)"
	# a Fernet key is 32 random bytes in URL-safe base64 — the `+/` of standard base64 become `-_`
	fernet="$(openssl rand -base64 32 | tr '+/' '-_')"

	set_var "$env_file" IMAGE_TAG "$tag"
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
	# the gateway and tracing are off until the llm-platform stack is chosen; a non-blank base URL
	# with a placeholder key is refused at start-up, and blank is the documented off switch
	set_var "$env_file" LITELLM_BASE_URL ""
	set_var "$env_file" LANGFUSE_BASE_URL ""
	say "wrote .env (mode 600): generated ORCHESTRATOR_TOKEN, session secret, Fernet key, database password; IMAGE_TAG=${tag}"
}

# ── 4. the optional llm-platform stack ───────────────────────────────────────────────
want_platform() {
	if [[ -n "$with_platform" ]]; then [[ "$with_platform" -eq 1 ]]; return; fi
	if [[ -f "$platform_env" ]]; then return 0; fi          # already set up on this machine
	[[ "$yes" -eq 0 ]] || return 1
	say
	say "Optional: the llm-platform stack — LiteLLM (model gateway, spend tracking) and Langfuse (traces),"
	say "seven more containers on ports 3000, 4000, 5433, 9000 and 9091. Without it each coding"
	say "agent authenticates on its own and cost figures are provisional. It can be added later"
	say "with: ./install.sh start --with-platform"
	confirm "Install the llm-platform stack now?"
}

platform_up() {
	[[ -f "${platform_dir}/docker-compose.yml" ]] || die "llm-platform/ is missing beside this script — the bundle is incomplete"
	step "llm-platform stack (LiteLLM + Langfuse)"
	# a port check whenever *this* host project is not already running — whatever is listening
	# on 3000 or 4000 then belongs to something else, and this script never takes it over
	if [[ ! -f "$platform_env" ]] || ! platform_compose ps --status running --services 2>/dev/null | grep -q .; then
		ensure_ports_free "$(get_var "$platform_env" LANGFUSE_PORT || true) LANGFUSE_PORT llm-platform/.env" \
			"$(get_var "$platform_env" LITELLM_PORT || true) LITELLM_PORT llm-platform/.env" \
			"$(get_var "$platform_env" HOST_POSTGRES_PORT || true) HOST_POSTGRES_PORT llm-platform/.env" \
			"$(get_var "$platform_env" MINIO_API_PORT || true) MINIO_API_PORT llm-platform/.env" \
			"$(get_var "$platform_env" MINIO_CONSOLE_PORT || true) MINIO_CONSOLE_PORT llm-platform/.env"
	fi
	if [[ ! -f "$platform_env" ]]; then
		"${platform_dir}/generate-env.sh"
		local name value
		for name in ANTHROPIC_API_KEY OPENAI_API_KEY OPENROUTER_API_KEY; do
			eval "value=\${${name}:-}"
			if [[ -z "$value" && "$yes" -eq 0 ]]; then
				prompt value "${name} for the gateway (enter to skip): " secret
			fi
			if [[ -n "$value" ]]; then set_var "$platform_env" "$name" "$value"; say "llm-platform/.env: ${name} set"; fi
		done
		if [[ "$(get_var "$platform_env" ANTHROPIC_API_KEY)" == "not-set" && "$(get_var "$platform_env" OPENAI_API_KEY)" == "not-set" ]]; then
			warn "no provider key in llm-platform/.env — the gateway starts, but every model call answers 401 until one is set"
		fi
	fi
	say "starting the llm-platform stack (the first start runs migrations; a few minutes)…"
	platform_compose up -d --wait --wait-timeout 900
	if [[ -z "$(get_var "$env_file" LITELLM_BASE_URL)" ]]; then
		"${platform_dir}/sync-env.sh" "$env_file"
	else
		say ".env already points at a gateway — not re-minting the harness key"
	fi
}

# ── 5. the stack ─────────────────────────────────────────────────────────────
stack_up() {
	step "ai-orchestrator ($(get_var "$env_file" IMAGE_TAG))"
	if ! compose ps --status running --services 2>/dev/null | grep -q .; then
		ensure_ports_free "$(get_var "$env_file" WEB_CLIENT_PORT) WEB_CLIENT_PORT .env" \
			"$(get_var "$env_file" BACKEND_API_PORT) BACKEND_API_PORT .env"
	fi
	if [[ "$pull" -eq 1 ]]; then compose pull; else say "--no-pull: using the images already on this machine"; fi
	compose up -d --wait --wait-timeout 1800
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
	if [[ -f "$platform_env" ]]; then
		say "  Langfuse   http://127.0.0.1:$(get_var "$platform_env" LANGFUSE_PORT)   $(get_var "$platform_env" LANGFUSE_INIT_USER_EMAIL) / $(get_var "$platform_env" LANGFUSE_INIT_USER_PASSWORD)"
		say "  LiteLLM    http://127.0.0.1:$(get_var "$platform_env" LITELLM_PORT)"
	fi
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
	report ok docker "$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?'), compose $(docker compose version --short)"
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
	for name in IMAGE_TAG ORCHESTRATOR_TOKEN ORCHESTRATOR_SESSION_SECRET \
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
	tag="$(get_var "$env_file" IMAGE_TAG)"
	if is_placeholder "$tag"; then
		report fail image "IMAGE_TAG is not set — put the release tag you mean to run in ${env_file}"
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
	local body code app tag shipped
	body="${scratch}/version.json"
	code="$(api_get /api/v1/version "$body")"
	if [[ "$code" != "200" ]]; then
		report warn version "/api/v1/version answered ${code} — an instance older than the route; ./install.sh upgrade --tag <newer>"
		return 0
	fi
	app="$(json_string "$body" app_version)"
	tag="$(get_var "$env_file" IMAGE_TAG)"
	shipped="absent"
	if [[ -f "${here}/VERSION" ]]; then shipped="$(tr -d '[:space:]' < "${here}/VERSION")"; fi
	report ok version "running ${app:-unnamed}; IMAGE_TAG ${tag}; VERSION ${shipped}"
	if [[ -n "$app" && "$app" != "$tag" ]]; then
		report warn version "the instance runs ${app} but IMAGE_TAG says ${tag} — ./install.sh upgrade --tag ${tag}"
	fi
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

doctor_platform() {
	local running gateway
	if [[ ! -f "$platform_env" ]]; then
		report ok platform "not configured — each agent authenticates on its own, cost figures are provisional, and the local harness is unavailable; ./install.sh start --with-platform adds it"
		return 0
	fi
	running="$(platform_compose ps --status running --services 2>/dev/null || true)"
	if [[ -n "$running" ]]; then
		report ok platform "configured and running: $(printf '%s' "$running" | tr '\n' ' ')"
	else
		report warn platform "configured but not running — ./install.sh start --with-platform"
	fi
	gateway="$(get_var "$env_file" LITELLM_BASE_URL)"
	if [[ -n "$gateway" ]]; then
		report ok gateway ".env points at ${gateway}"
	else
		report warn gateway "llm-platform/ is installed but LITELLM_BASE_URL is blank, which is the gateway's off switch — llm-platform/sync-env.sh ${env_file} fills it in"
	fi
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
		CLAUDE_ALLOWED_TOOLS) return 0 ;;
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
	local tag; tag="$(resolve_tag)"
	token="${GHCR_TOKEN:-${GITHUB_TOKEN:-}}"
	render_env "$tag"
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
	render_env "$tag"

	if want_platform; then platform_up; fi

	stack_up
	step "verifying"
	verify
	print_access
}

cmd_start() {
	check_tools
	[[ -f "$env_file" ]] || die ".env is missing — run ./install.sh first"
	# --no-platform always wins; otherwise an installed llm-platform stack (llm-platform/.env exists) comes up too
	if [[ "$with_platform" != "0" && ( -f "$platform_env" || "$with_platform" == "1" ) ]]; then platform_up; fi
	stack_up
	verify
	print_access
}

cmd_stop() {
	[[ -f "$env_file" ]] || die ".env is missing — nothing was installed here"
	step "stopping ai-orchestrator (data kept)"
	compose stop
	if [[ -f "$platform_env" ]] && confirm "Also stop the llm-platform stack (LiteLLM + Langfuse)?"; then platform_compose stop; fi
}

cmd_status() {
	[[ -f "$env_file" ]] || die ".env is missing — nothing was installed here"
	say "ai-orchestrator ($(get_var "$env_file" IMAGE_TAG)):"
	compose ps
	if [[ -f "$platform_env" ]]; then say; say "llm-platform stack:"; platform_compose ps; fi
}

cmd_logs() {
	[[ -f "$env_file" ]] || die ".env is missing — nothing was installed here"
	compose logs -f --tail 200
}

cmd_upgrade() {
	local old new backup running code
	check_tools
	[[ -f "$env_file" ]] || die ".env is missing — run ./install.sh first"
	[[ -n "$tag_arg" ]] || die "upgrade needs --tag vX.Y.Z"
	old="$(get_var "$env_file" IMAGE_TAG)"; new="$tag_arg"
	step "upgrade ${old} → ${new}"
	# What the instance answers is the version actually running; IMAGE_TAG is only what it was
	# last told to run, and the two disagree whenever a retag never reached a restart.
	running="$old"
	scratch="$(mktemp -d)"
	code="$(api_get /api/v1/version "${scratch}/version.json")"
	if [[ "$code" == "200" ]]; then
		running="$(json_string "${scratch}/version.json" app_version)"
		say "running ${running} → target ${new}"
	else
		say "running ${running} (from IMAGE_TAG; /api/v1/version answered ${code}) → target ${new}"
	fi
	[[ "$new" != "$running" ]] ||
		die "${new} is already what is running — nothing to upgrade; pass the newer tag"
	require_pin_declarations
	resolve_token
	ghcr_login
	read_release_pins "$new"
	plan_release_pins
	say "Read the release notes first. A release that bumps DBOS_APPLICATION_VERSION makes"
	say "every in-flight Run unrecoverable — drain or cancel Runs before such an upgrade."
	say "Migrations run forward only; the backup below is what a rollback restores from."
	confirm "Continue?" || die "upgrade cancelled"
	mkdir -p "${here}/backups"
	backup="${here}/backups/orchestrator-${old}-$(date -u +%Y%m%dT%H%M%SZ).dump"
	if compose ps --status running --services 2>/dev/null | grep -q '^postgres$'; then
		compose exec -T postgres pg_dump -U "$(get_var "$env_file" POSTGRES_USER)" -Fc \
			"$(get_var "$env_file" POSTGRES_DB)" > "$backup"
		say "database backup: ${backup}"
	else
		warn "postgres is not running — no backup taken"
	fi
	set_var "$env_file" IMAGE_TAG "$new"
	write_release_pins
	stack_up
	verify
	print_access
}

HARNESS_PIN_VARIABLES=(CLAUDE_CODE_VERSION CODEX_VERSION OPENCODE_VERSION)
release_pins=()   # empty: the release image carries no contract, and the pins stay as they are

# Every pin is checked before anything is written, so `.env` is never left half-upgraded.
require_pin_declarations() {
	local name
	for name in "${HARNESS_PIN_VARIABLES[@]}"; do
		grep -q "^${name}=" "$env_file" ||
			die ".env does not declare ${name} — add the line from .env.example; nothing was changed"
	done
}

# The harness CLI pins a release ships, read from its own backend image: `harness-bin`
# outlives the image, so a release's CLIs reach this host only through these pins.
read_release_pins() {   # read_release_pins TAG → fills release_pins, or dies having written nothing
	local tag="$1" image file errors name value rc=0
	local -a run_flags=(--rm)
	image="$(backend_image)"
	[[ -n "$image" ]] || die "no backend-api image in ${compose_file##*/} — nothing was changed"
	image="${image}:${tag}"
	file="${scratch}/release.env.example"
	if [[ "$pull" -eq 1 ]]; then
		docker pull "$image" >/dev/null || die "docker pull ${image} failed"
	else
		run_flags+=(--pull never)
	fi
	errors="${scratch}/release.err"
	docker run "${run_flags[@]}" --entrypoint cat "$image" /app/deploy/.env.example \
		> "$file" 2> "$errors" || rc=$?
	release_pins=()
	if [[ "$rc" -ne 0 ]]; then
		# only `cat`'s own answer means a release older than the pins' contract
		if [[ "$rc" -lt 125 ]] && grep -q 'No such file' "$errors"; then
			warn "${image} carries no /app/deploy/.env.example, so the harness pins in .env stay as they are."
			warn "Set ${HARNESS_PIN_VARIABLES[*]} in .env to that release's values by hand."
			return 0
		fi
		die "cannot read /app/deploy/.env.example from ${image} — nothing was changed:"$'\n'"$(cat "$errors")"
	fi
	for name in "${HARNESS_PIN_VARIABLES[@]}"; do
		value="$(get_var "$file" "$name")"
		is_plain_version "$value" ||
			die "${image} carries no usable ${name} in /app/deploy/.env.example — nothing was changed"
		release_pins+=("$value")
	done
}

# A harness pin from .env, a `#` comment after any whitespace dropped (get_var drops only `  #`).
env_pin() {
	get_var "$env_file" "$1" | sed -E 's/[[:space:]]+#.*$//'
}

plan_release_pins() {
	local i name old new note changed=0
	[[ "${#release_pins[@]}" -gt 0 ]] || return 0
	for i in "${!HARNESS_PIN_VARIABLES[@]}"; do
		name="${HARNESS_PIN_VARIABLES[$i]}"; new="${release_pins[$i]}"
		old="$(env_pin "$name")"
		[[ "$old" != "$new" ]] || continue
		[[ "$changed" -eq 1 ]] || say "harness CLI pins this upgrade writes to .env:"
		changed=1
		note=""
		if is_plain_version "$old" && version_older "$new" "$old"; then note="   (downgrade)"; fi
		say "  ${name} ${old:-unset} → ${new}${note}"
	done
	[[ "$changed" -eq 1 ]] || say "harness CLI pins: unchanged"
}

write_release_pins() {
	local i name
	[[ "${#release_pins[@]}" -gt 0 ]] || return 0
	for i in "${!HARNESS_PIN_VARIABLES[@]}"; do
		name="${HARNESS_PIN_VARIABLES[$i]}"
		[[ "$(env_pin "$name")" != "${release_pins[$i]}" ]] || continue
		set_var "$env_file" "$name" "${release_pins[$i]}"
	done
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
		if doctor_api; then
			doctor_version
			doctor_harnesses
		fi
		if [[ "$docker_ok" -eq 1 ]]; then doctor_platform; fi
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
		printf 'IMAGE_TAG  %s\n' "$(get_var "$env_file" IMAGE_TAG)"
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
	compose up -d --no-deps --wait --wait-timeout 1800 backend-api && return 0
	say "$1 is written to .env; backend-api did not come back healthy with it."
	warn "backend-api did not become healthy after the recreate — ./install.sh logs"
	return 1
}

# `harness <name> --version X`: the pin is `.env`'s, and the container's entrypoint (`ensure`)
# installs it at the next start onto the `harness-bin` volume — no new image needed.
cmd_harness_version() {
	local variable="$1" since lines
	if [[ "$(env_pin "$variable")" == "$version_arg" ]]; then
		say "${harness_arg} is already pinned at ${version_arg} — nothing to do."
		return 0
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
		die "only claude has a subscription login; ${harness_arg} authenticates with an API key alone — set it in llm-platform/.env and restart the gateway"
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
		say "${platform_dir}/litellm.config.yaml uncomment both:"
		say
		say "  general_settings:"
		say "    forward_client_headers_to_llm_api: true   # EVERY route on this proxy, not"
		say "                                             # only the Claude one"
		say "  model_list:"
		say "    - model_name: claude-subscription        # the entry and its litellm_params"
		say
		say "Then restart the gateway (./install.sh start --with-platform) and bind the Run to"
		say "the model name claude-subscription: Claude Code's own default model is not in"
		say "model_list, and a Run on it answers 400."
	else
		set_var "$env_file" CLAUDE_SUBSCRIPTION_AUTH false
		step "claude → the gateway's own API key"
		say "CLAUDE_SUBSCRIPTION_AUTH is false in .env now: the virtual key reaches the harness"
		say "as ANTHROPIC_AUTH_TOKEN again."
		say "Comment forward_client_headers_to_llm_api back out in"
		say "${platform_dir}/litellm.config.yaml, make sure ANTHROPIC_API_KEY is set in"
		say "${platform_env}, and restart the gateway."
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
	say "subscription (deploy/llm-platform/README.md). A subscription is not metered per"
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
	compose down -v --remove-orphans
	if [[ -f "$platform_env" ]] && confirm "Also remove the llm-platform stack and its data (traces, spend logs)?"; then
		platform_compose down -v --remove-orphans
	fi
	say "removed. ${env_file} and ${platform_env} were kept."
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
esac
