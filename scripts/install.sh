#!/usr/bin/env bash
# scripts/install.sh — bring a fresh checkout to the state the gates assume.
#
# `make lint`, `make test`, `make e2e` and `make e2e-ui` each assume three things that a
# `git clone` does not give you: a synced backend virtualenv, an installed web-client
# `node_modules`, and an environment file. Every one of them fails with a tooling error
# rather than a test failure when one is missing, and a tooling error is the one failure a
# coding agent cannot act on — it looks like a broken story. So the setup is a command:
#
#   ./scripts/install.sh            everything the unit gates need (make install)
#   ./scripts/install.sh --e2e      that, plus the Playwright browser (make install-e2e)
#   ./scripts/install.sh --check    report only; installs nothing, mutates nothing
#
# Idempotent: `uv sync`, `pnpm install` and `generate-env.sh` are all no-ops on a machine
# that is already set up, so this is safe to run at the top of every session.
#
# It reports every problem it finds before exiting, rather than stopping at the first: a
# machine missing both Node and Docker should learn that once, not twice.
#
# Versions are read from the files that pin them — `web-client/package.json` for Node and
# pnpm, `backend-api/pyproject.toml` for Python — so this script never becomes a second
# copy of a pin to drift.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here"

mode=install
want_browsers=0
for arg in "$@"; do
	case "$arg" in
	--check) mode=check ;;
	--e2e) want_browsers=1 ;;
	*)
		echo "usage: $(basename "$0") [--check] [--e2e]" >&2
		exit 2
		;;
	esac
done

# corepack asks before downloading the pinned pnpm; there is no one to answer in an agent
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

problems=()
note() { printf '  %s\n' "$1"; }
problem() { problems+=("$1"); }

# ── what the pins say ───────────────────────────────────────────────────────
# Read with grep/sed rather than node: Node is one of the things that may be missing.
pnpm_pin="$(sed -n 's/.*"packageManager": *"pnpm@\([^"]*\)".*/\1/p' web-client/package.json)"
node_pin="$(sed -n 's/.*"node": *">=\([0-9]*\)".*/\1/p' web-client/package.json)"
python_pin="$(sed -n 's/^requires-python *= *"==\([0-9]*\.[0-9]*\)\..*/\1/p' backend-api/pyproject.toml)"

echo "ai-orchestrator setup — node >=${node_pin}, pnpm ${pnpm_pin}, python ${python_pin}"

# ── prerequisites this script installs nothing for ──────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }

if have git; then note "git      $(git --version | awk '{print $3}')"; else
	problem "git is missing — install Xcode command line tools, or your distribution's git"
fi

if have uv; then
	note "uv       $(uv --version | awk '{print $2}')"
else
	problem "uv is missing — 'brew install uv', or see https://docs.astral.sh/uv/"
fi

if have node; then
	node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
	note "node     $(node --version)"
	if [ "$node_major" -lt "$node_pin" ]; then
		problem "node $(node --version) is older than the pinned >=${node_pin} (web-client/package.json). 'nvm install ${node_pin} && nvm use ${node_pin}'"
	fi
else
	problem "node is missing — install Node ${node_pin} or newer ('nvm install ${node_pin}')"
fi

if have corepack; then note "corepack $(corepack --version)"; else
	problem "corepack is missing — it ships with Node ${node_pin}; 'npm install -g corepack' otherwise"
fi

# Docker is needed by `make up`, `make e2e` and `make images` — not by lint or unit tests,
# so a missing daemon is reported and never fatal to the parts that do not use it.
if have docker; then
	if docker info >/dev/null 2>&1; then
		note "docker   $(docker --version | awk '{print $3}' | tr -d ,) (daemon up)"
	else
		note "docker   installed, daemon not running — needed by 'make up', 'make e2e', 'make images'"
	fi
else
	note "docker   missing — needed by 'make up', 'make e2e', 'make images'; lint and unit tests do not use it"
fi

# ── the three things a checkout is missing ──────────────────────────────────
if [ "$mode" = check ]; then
	[ -d backend-api/.venv ] && note "backend  .venv present" || problem "backend-api/.venv is missing — run 'make install'"
	[ -d web-client/node_modules ] && note "web      node_modules present" || problem "web-client/node_modules is missing — run 'make install'"
	[ -f .env ] && note "env      .env present" || problem ".env is missing — run 'make install' (or ./scripts/generate-env.sh dev)"
	if [ -f .env ]; then
		# The contract is two-tier (Operator decision 2026-09-20, two-tier configuration
		# contract; reaffirmed 2026-09-30): a name in .env.example but not in .env is a
		# default, not a failure — unless it is one of the six the stack refuses to start
		# without. So the report says which, and only the second kind is a problem. The
		# comparison is DEPLOY.md § 3.3's `comm -13`, inline.
		absent="$(comm -13 <(grep -oE '^[A-Z_]+=' .env | tr -d '=' | sort) \
			<(grep -oE '^[A-Z_]+=' .env.example | tr -d '=' | sort))"
		optional=""
		for name in $absent; do
			case "$name" in
			ORCHESTRATOR_TOKEN | ORCHESTRATOR_SESSION_SECRET | ORCHESTRATOR_SECRET_KEY | POSTGRES_PASSWORD | DATABASE_URL | GITHUB_TOKEN)
				problem "$name is required and missing from .env — copy its line from .env.example, or write a fresh one with './scripts/generate-env.sh dev'"
				;;
			*) optional="$optional $name" ;;
			esac
		done
		if [ -n "${optional// /}" ]; then
			note "env      $(echo $optional | wc -w | tr -d ' ') optional names are absent from .env; each uses its code default"
			echo "$optional" | fold -s -w 84 | sed 's/^ */           /'
		fi
	fi
	if [ "$want_browsers" = 1 ]; then
		if have node && [ -d web-client/node_modules ] &&
			pnpm --dir web-client exec playwright install --dry-run chromium >/dev/null 2>&1; then
			note "browser  chromium ready"
		else
			problem "the Playwright chromium build is missing — run 'make install-e2e'"
		fi
	fi
else
	# Each step is guarded by its own prerequisite rather than by the whole report: a machine
	# with the wrong Node can still have its backend virtualenv synced, and an agent doing
	# backend work should get that rather than nothing. The exit code still reflects the
	# report, so a half-installed machine never passes for a ready one.
	if have uv; then
		# `--locked`: a setup step must never re-resolve the committed lockfiles, for the
		# same reason the gates pass `--locked` and `--frozen-lockfile`.
		echo "syncing backend-api (uv sync --locked) …"
		uv sync --locked --directory backend-api
	else
		echo "skipping backend-api: uv is missing"
	fi

	if have node && have corepack && [ "${node_major:-0}" -ge "$node_pin" ]; then
		echo "activating pnpm ${pnpm_pin} …"
		# corepack resolves `packageManager` from the working directory and this repository
		# has no root package.json, so the pinned version is activated explicitly.
		corepack enable || note "corepack could not write its shims here; using the ones on PATH"
		corepack prepare "pnpm@${pnpm_pin}" --activate
		have pnpm || problem "pnpm is missing — corepack enabled no shim this user can run"

		echo "installing web-client (pnpm install --frozen-lockfile) …"
		pnpm --dir web-client install --frozen-lockfile

		if [ "$want_browsers" = 1 ]; then
			echo "installing the Playwright chromium build (~95 MB) …"
			pnpm --dir web-client exec playwright install chromium
		fi
	else
		echo "skipping web-client: it needs node >=${node_pin} and corepack"
	fi

	echo "writing the environment files …"
	./scripts/generate-env.sh
fi

# ── the report ──────────────────────────────────────────────────────────────
if [ ${#problems[@]} -gt 0 ]; then
	echo
	echo "setup incomplete:" >&2
	for p in "${problems[@]}"; do echo "  - $p" >&2; done
	exit 1
fi

echo
if [ "$mode" = check ]; then
	echo "ready: make lint · make test"
else
	if [ "$want_browsers" = 1 ]; then
		echo "ready: make lint · make test · make e2e · make e2e-ui"
	else
		echo "ready: make lint · make test   ('make install-e2e' adds the Playwright browser)"
	fi
	echo "note: .env holds placeholders. 'make up' and 'make e2e-api' need the tokens filled in."
fi
