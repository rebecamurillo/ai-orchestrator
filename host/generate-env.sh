#!/usr/bin/env bash
# host/generate-env.sh — write `host/.env` with freshly generated secrets.
#
# Why this exists rather than "copy the example and fill it in": Langfuse's ENCRYPTION_KEY has
# to be exactly 64 hex characters or the container exits, and four other values are secrets
# that should never have a committed default. Generating them removes both the placeholder
# that does not work and the temptation to commit one that does (hard rule 5).
#
# Idempotent by refusal: an existing `host/.env` is never overwritten, because doing so would
# invalidate the Langfuse project keys already written into the repository-root `.env` and
# silently detach the orchestrator from its own traces. Delete it deliberately to start over.
#
#   ./host/generate-env.sh            write host/.env if it does not exist
#   ./host/generate-env.sh --print    print the four values the root .env needs
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
example="${here}/.env.example"
target="${here}/.env"

secret() { openssl rand -hex "${1:-24}"; }
b64()    { openssl rand -base64 32 | tr -d '\n'; }
lfkey()  { printf '%s-lf-%s' "$1" "$(uuidgen | tr '[:upper:]' '[:lower:]')"; }

if [[ "${1:-}" == "--print" ]]; then
	[[ -f "$target" ]] || { echo "host/.env does not exist — run ./host/generate-env.sh first" >&2; exit 1; }
	# the four the orchestrator's own .env needs, and nothing else
	grep -E '^(LANGFUSE_INIT_PROJECT_PUBLIC_KEY|LANGFUSE_INIT_PROJECT_SECRET_KEY|LANGFUSE_PORT|LITELLM_PORT)=' "$target"
	exit 0
fi

if [[ -f "$target" ]]; then
	echo "host/.env already exists — leaving it alone" >&2
	exit 0
fi

[[ -f "$example" ]] || { echo "$example is missing" >&2; exit 1; }

# Start from the committed contract so a variable added there is never silently dropped here,
# then fill in only the values that must be generated.
python3 - "$example" "$target" <<'PY'
import subprocess
import sys
import uuid

example, target = sys.argv[1], sys.argv[2]


def sh(*command: str) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


generated = {
    "HOST_POSTGRES_PASSWORD": lambda: sh("openssl", "rand", "-hex", "24"),
    "CLICKHOUSE_PASSWORD": lambda: sh("openssl", "rand", "-hex", "24"),
    "MINIO_ROOT_PASSWORD": lambda: sh("openssl", "rand", "-hex", "24"),
    "NEXTAUTH_SECRET": lambda: sh("openssl", "rand", "-base64", "32"),
    "LANGFUSE_SALT": lambda: sh("openssl", "rand", "-base64", "32"),
    # exactly 64 hex characters, or langfuse-web exits on start
    "LANGFUSE_ENCRYPTION_KEY": lambda: sh("openssl", "rand", "-hex", "32"),
    "LANGFUSE_INIT_USER_PASSWORD": lambda: sh("openssl", "rand", "-hex", "12"),
    "LITELLM_MASTER_KEY": lambda: "sk-" + sh("openssl", "rand", "-hex", "24"),
    "LANGFUSE_INIT_PROJECT_PUBLIC_KEY": lambda: f"pk-lf-{uuid.uuid4()}",
    "LANGFUSE_INIT_PROJECT_SECRET_KEY": lambda: f"sk-lf-{uuid.uuid4()}",
}

out, seen = [], set()
for line in open(example).read().splitlines():
    stripped = line.lstrip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        out.append(line)
        continue
    name, _, rest = line.partition("=")
    if name in generated:
        comment = rest.split("#", 1)
        trailing = f"   #{comment[1]}" if len(comment) > 1 else ""
        out.append(f"{name}={generated[name]()}{trailing}")
        seen.add(name)
    else:
        out.append(line)

missing = set(generated) - seen
if missing:
    raise SystemExit(f"host/.env.example no longer declares: {sorted(missing)}")

with open(target, "w") as handle:
    handle.write("\n".join(out) + "\n")
PY

chmod 600 "$target"
echo "wrote ${target} (mode 600) with generated secrets"
echo
echo "Put these two in the repository-root .env so the orchestrator reaches this stack:"
grep -E '^(LANGFUSE_INIT_PROJECT_PUBLIC_KEY|LANGFUSE_INIT_PROJECT_SECRET_KEY)=' "$target" |
	sed -e 's/^LANGFUSE_INIT_PROJECT_PUBLIC_KEY=/  LANGFUSE_PUBLIC_KEY=/' \
	    -e 's/^LANGFUSE_INIT_PROJECT_SECRET_KEY=/  LANGFUSE_SECRET_KEY=/'
echo "  LANGFUSE_BASE_URL=http://host.docker.internal:3000"
echo "  LITELLM_BASE_URL=http://host.docker.internal:4000"
echo
# a checkout has the Makefile; a release bundle runs the script directly
if [[ -f "${here}/../Makefile" ]]; then
	echo "\`make host-env-sync\` writes all four into the root .env for you."
else
	echo "\`host/sync-env.sh ../.env\` writes all four into the orchestrator's .env for you (install.sh does this)."
fi
