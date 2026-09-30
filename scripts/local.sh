#!/usr/bin/env bash
# scripts/local.sh — run the app on this machine instead of in containers (mode B).
#
# Postgres stays in compose (the one piece with no local-install story); backend-api and
# web-client run from source as host processes. The contract in `.env` is written for the
# containers — service hostnames and container paths — so this script rewrites exactly the
# values that only make sense inside the compose network, exports the rest untouched, and
# never edits the file itself:
#
#   DATABASE_URL        @postgres:5432        → @127.0.0.1:5432 (the published port)
#   LITELLM_BASE_URL    host.docker.internal  → 127.0.0.1 (when non-blank)
#   LANGFUSE_BASE_URL   host.docker.internal  → 127.0.0.1 (when non-blank)
#   BACKEND_API_URL     http://backend-api:…  → http://127.0.0.1:$BACKEND_API_PORT
#   WORK_DIR            /work                 → .local/work under the checkout
#   AGENT_HOME          /home/agent           → $HOME — your own harness logins apply
#   TEMPLATES_DIR       /app/templates        → templates/ in the checkout
#   HARNESS_SCRIPTS_DIR /app/scripts/harness  → scripts/harness/ in the checkout
#
# `.env` need not be complete: under the two-tier contract (Operator decision 2026-09-20;
# reaffirmed 2026-09-30) every optional line may be absent, so the values this script reads
# before exporting them take the contract's own default when the file does not say.
#
# Dispatching a Run in this mode uses the harness CLIs on YOUR PATH (claude, codex,
# opencode) — the container mode ships them in the image; here they are the machine's.
#
#   scripts/local.sh backend    postgres in compose, then backend-api in the foreground
#   scripts/local.sh web        web-client (astro dev) in the foreground
#   scripts/local.sh up         both: backend in the background, web in the foreground,
#                               both stopped together on Ctrl-C
#
# The published ports are the same ones `make up` publishes, so the two modes cannot run
# at once: each command refuses a port that is already bound rather than racing for it.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

what="${1:-up}"
case "$what" in
backend | web | up) ;;
*)
	echo "usage: $(basename "$0") [backend|web|up]" >&2
	exit 2
	;;
esac

[[ -f .env ]] || {
	echo "no .env — run \`make env\` and fill it in first (README: Boot a new machine)" >&2
	exit 1
}
set -a
# shellcheck disable=SC1091
. ./.env
set +a

# ── the values this script rewrites, defaulted so an incomplete .env still runs ──
# `set -u` is on, and an absent optional line is now legal, so each of these is bound to the
# contract's own default before it is read. The pattern is the harness scripts' `:=`.
: "${BACKEND_API_PORT:=8000}"
: "${WEB_CLIENT_PORT:=4321}"
: "${DATABASE_URL:=}"
: "${LITELLM_BASE_URL:=}"
: "${LANGFUSE_BASE_URL:=}"
export BACKEND_API_PORT WEB_CLIENT_PORT

# ── the local overrides ──────────────────────────────────────────────────────
export DATABASE_URL="${DATABASE_URL/@postgres:/@127.0.0.1:}"
export LITELLM_BASE_URL="${LITELLM_BASE_URL/host.docker.internal/127.0.0.1}"
export LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL/host.docker.internal/127.0.0.1}"
export BACKEND_API_URL="http://127.0.0.1:${BACKEND_API_PORT}"
export WORK_DIR="${LOCAL_WORK_DIR:-$root/.local/work}"
export AGENT_HOME="${LOCAL_AGENT_HOME:-$HOME}"
export TEMPLATES_DIR="$root/templates"
# the probe adapters shell `<HARNESS_SCRIPTS_DIR>/<name>.sh probe`; without this they would
# point at the image's `/app/scripts/harness`, which a host process does not have
export HARNESS_SCRIPTS_DIR="$root/scripts/harness"
export KIT_DIR="$root/deploy/kit"
mkdir -p "$WORK_DIR"

refuse_if_bound() {
	local port="$1" name="$2"
	if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
		exec 3>&- || true
		echo "127.0.0.1:$port is already bound — $name cannot start." >&2
		echo "If the container stack is up, stop it first: make down" >&2
		exit 1
	fi
}

start_postgres() {
	docker compose up -d --wait postgres
}

run_backend() {
	# main.py migrates before it binds and logs one `migrations applied` line
	exec uv run --locked --directory backend-api python -m orchestrator.main
}

run_web() {
	# astro dev reads BACKEND_API_URL, ORCHESTRATOR_TOKEN, ORCHESTRATOR_SESSION_SECRET,
	# WEB_CLIENT_PORT and ROOT_TEMPLATES from the environment exported above
	exec pnpm --dir web-client dev
}

case "$what" in
backend)
	refuse_if_bound "$BACKEND_API_PORT" backend-api
	start_postgres
	run_backend
	;;
web)
	refuse_if_bound "$WEB_CLIENT_PORT" web-client
	run_web
	;;
up)
	refuse_if_bound "$BACKEND_API_PORT" backend-api
	refuse_if_bound "$WEB_CLIENT_PORT" web-client
	start_postgres

	uv run --locked --directory backend-api python -m orchestrator.main &
	backend_pid=$!
	# stop the backend when the web process (the foreground one) exits, however it exits
	trap 'kill "$backend_pid" 2>/dev/null || true; wait "$backend_pid" 2>/dev/null || true' EXIT
	trap 'exit 130' INT TERM

	printf 'waiting for backend-api on 127.0.0.1:%s ' "$BACKEND_API_PORT"
	for _ in $(seq 1 120); do
		if curl -fs "http://127.0.0.1:${BACKEND_API_PORT}/healthz" >/dev/null 2>&1; then
			echo ' ok'
			# no `exec` here: the EXIT trap above is what stops the backend when
			# the web process ends, and an exec would discard it
			pnpm --dir web-client dev
			exit 0
		fi
		kill -0 "$backend_pid" 2>/dev/null || {
			echo ' backend-api exited before becoming healthy — its output is above' >&2
			exit 1
		}
		printf '.'
		sleep 1
	done
	echo ' backend-api never answered /healthz — stopping' >&2
	exit 1
	;;
esac
