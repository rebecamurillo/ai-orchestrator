#!/usr/bin/env bash
# scripts/generate-env.sh — give each local environment an environment file of its own.
#
# Two environments, two compose projects, nothing shared (AD-20):
#
#   aio-dev   `.env`       the stack you develop against; `make up` / `make down`
#   aio-e2e   `.env.e2e`   the stack `make e2e` creates, runs the gate in, and destroys
#
# Docker namespaces volumes by project, so naming the projects is what separates the two
# databases, the two `work` trees and the two agent homes. The name is read from the
# environment file by compose itself (`COMPOSE_PROJECT_NAME`), which is why it is written
# here rather than in `.env.example`: it configures the docker CLI, not the application, and
# the contract holds application settings only.
#
# `.env.e2e` carries no real credential. Its Gateway, tracing and git placeholders are the
# committed ones, exactly as CI runs them (AD-5); the four values that must be real to work
# at all — the login token, the cookie key, the Fernet key and the database password — are
# generated here, because a placeholder Fernet key answers 500 on every write and a
# committed default is a secret nobody rotates (hard rule 5).
#
# Idempotent by refusal: an existing file is never rewritten. Delete it to start over.
#
#   ./scripts/generate-env.sh            both
#   ./scripts/generate-env.sh dev        .env only
#   ./scripts/generate-env.sh e2e        .env.e2e only
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
example="${here}/.env.example"

[[ -f "$example" ]] || { echo "$example is missing" >&2; exit 1; }

what="${1:-all}"
case "$what" in
dev | e2e | all) ;;
*)
	echo "usage: $(basename "$0") [dev|e2e|all]" >&2
	exit 2
	;;
esac

# ── aio-dev: the operator's own .env, which may already hold real tokens ─────
# Never rewritten, only completed: an existing file gets the project name appended and
# nothing else touched.
if [[ "$what" == "dev" || "$what" == "all" ]]; then
	target="${here}/.env"
	if [[ ! -f "$target" ]]; then
		cp "$example" "$target"
		chmod 600 "$target"
		echo "wrote .env from .env.example — fill in the tokens and keys before \`make up\`"
	fi
	if grep -qE '^COMPOSE_PROJECT_NAME=' "$target"; then
		echo ".env already names its compose project — leaving it alone"
	else
		{
			echo ""
			echo "# ── Compose project (docker CLI, not an application setting) ────────────────"
			echo "# Names this stack's containers and volumes. Without it compose falls back to the"
			echo "# checkout's directory name, so a renamed or second clone would silently become a"
			echo "# different project with empty volumes."
			echo "COMPOSE_PROJECT_NAME=aio-dev"
		} >>"$target"
		echo "appended COMPOSE_PROJECT_NAME=aio-dev to .env"
		echo "  the next \`make up\` starts project aio-dev with fresh volumes; anything the"
		echo "  previous project held is still on disk under its old name (docker volume ls)"
	fi
fi

# ── aio-e2e: generated whole, disposable, and holding no real credential ─────
if [[ "$what" == "e2e" || "$what" == "all" ]]; then
	target="${here}/.env.e2e"
	if [[ -f "$target" ]]; then
		echo ".env.e2e already exists — leaving it alone"
	else
		python3 - "$example" "$target" <<'PY'
import base64
import os
import subprocess
import sys

example, target = sys.argv[1], sys.argv[2]

#: Ports of its own, so the gate's stack runs beside the dev stack rather than instead of it.
BACKEND_PORT = "8020"
WEB_PORT = "4341"
POSTGRES_PORT = "55432"
DATABASE = "orchestrator_e2e"


def hex_secret(length: int = 24) -> str:
    return subprocess.run(  # fixed argv, no shell
        ["openssl", "rand", "-hex", str(length)], capture_output=True, text=True, check=True
    ).stdout.strip()


def fernet_key() -> str:
    """32 random bytes in url-safe base64 — what `Fernet(key)` accepts, unlike `rand -base64`."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


lines = open(example).read().splitlines()
users = (
    line.partition("=")[2].split("#")[0].strip()
    for line in lines
    if line.startswith("POSTGRES_USER=")
)
user = next(users, "orchestrator")
password = hex_secret()

replacements = {
    "ORCHESTRATOR_TOKEN": hex_secret(),
    "ORCHESTRATOR_SESSION_SECRET": hex_secret(32),
    # the committed placeholder is not a valid Fernet key: without a real one every write
    # to /api/v1/projects answers 500 and the suite would test nothing
    "ORCHESTRATOR_SECRET_KEY": fernet_key(),
    "BACKEND_API_URL": f"http://backend-api:{BACKEND_PORT}",
    "WEB_CLIENT_PORT": WEB_PORT,
    "BACKEND_API_PORT": BACKEND_PORT,
    "POSTGRES_PASSWORD": password,
    "POSTGRES_DB": DATABASE,
    "DATABASE_URL": f"postgresql+psycopg://{user}:{password}@postgres:5432/{DATABASE}",
    # traces from a gate run must not read as the dev stack's on the shared host tracing server
    "LANGFUSE_ENVIRONMENT": "e2e",
}

out, seen = [], set()
for line in lines:
    name, sep, rest = line.partition("=")
    if not sep or name.lstrip().startswith("#") or name not in replacements:
        out.append(line)
        continue
    comment = rest.split("  #", 1)
    trailing = f"  #{comment[1]}" if len(comment) > 1 else ""
    out.append(f"{name}={replacements[name]}{trailing}")
    seen.add(name)

missing = set(replacements) - seen
if missing:
    raise SystemExit(f".env.example no longer declares: {sorted(missing)}")

out += [
    "",
    "# ── Compose project (docker CLI, not an application setting) ────────────────",
    "# `make e2e` creates this project, runs the gate in it and destroys it with `down -v`.",
    "# E2E_POSTGRES_PORT is read by docker-compose.e2e.yml: docker-compose.yml publishes",
    "# postgres on 127.0.0.1:5432, which the dev stack already holds.",
    "COMPOSE_PROJECT_NAME=aio-e2e",
    f"E2E_POSTGRES_PORT={POSTGRES_PORT}",
]

with open(target, "w") as handle:
    handle.write("\n".join(out) + "\n")
PY
		chmod 600 "$target"
		echo "wrote .env.e2e (mode 600) — project aio-e2e, database orchestrator_e2e, no real credential"
	fi
fi
