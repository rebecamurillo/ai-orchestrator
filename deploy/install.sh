#!/usr/bin/env bash
# install.sh — ai-orchestrator, from an empty machine to http://127.0.0.1:4321 in one command.
#
#   ./install.sh                                  # interactive: asks for the GitHub token,
#                                                 #   offers the optional llm-platform stack
#   GHCR_TOKEN=ghp_… ./install.sh --yes           # unattended, orchestrator only
#   GHCR_TOKEN=ghp_… ANTHROPIC_API_KEY=sk-ant-… ./install.sh --yes --with-platform
#
#   ./install.sh start | stop | status | logs     # day-2 operations on this stack
#   ./install.sh upgrade --tag v0.2.0             # backup, retag, pull, restart
#   ./install.sh uninstall                        # stop and DELETE the data, after confirmation
#   ./install.sh env --tag v0.1.0                 # only write .env (what `install` does first)
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
tag_arg=""
command=""

# ── output ───────────────────────────────────────────────────────────────────
say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
	sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ── arguments ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
	case "$1" in
		install|start|stop|status|logs|upgrade|uninstall|env) command="$1" ;;
		--tag) [[ $# -ge 2 ]] || die "--tag needs a value"; tag_arg="$2"; shift ;;
		--tag=*) tag_arg="${1#--tag=}" ;;
		--yes|-y) yes=1 ;;
		--with-platform) with_platform=1 ;;
		--no-platform) with_platform=0 ;;
		-h|--help) usage; exit 0 ;;
		*) die "unknown argument: $1 (try --help)" ;;
	esac
	shift
done
command="${command:-install}"

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
	compose pull
	compose up -d --wait --wait-timeout 300
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

	step "registry login"
	resolve_token
	ghcr_login

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
	local old new backup
	check_tools
	[[ -f "$env_file" ]] || die ".env is missing — run ./install.sh first"
	[[ -n "$tag_arg" ]] || die "upgrade needs --tag vX.Y.Z"
	old="$(get_var "$env_file" IMAGE_TAG)"; new="$tag_arg"
	step "upgrade ${old} → ${new}"
	say "Read the release notes first. A release that bumps DBOS_APPLICATION_VERSION makes"
	say "every in-flight Run unrecoverable — drain or cancel Runs before such an upgrade."
	say "Migrations run forward only; the backup below is what a rollback restores from."
	confirm "Continue?" || die "upgrade cancelled"
	resolve_token
	ghcr_login
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
	stack_up
	verify
	print_access
}

cmd_uninstall() {
	local answer
	[[ -f "$env_file" ]] || die ".env is missing — nothing was installed here"
	step "uninstall"
	say "This stops ai-orchestrator and DELETES its volumes: the database, every clone and"
	say "worktree, and the agent home. .env is kept so the token survives; delete it yourself."
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
esac
