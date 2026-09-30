#!/usr/bin/env bash
# deploy/llm-platform/sync-env.sh — point the repository-root `.env` at the running llm-platform stack.
#
# Six values in the orchestrator's contract describe where the Gateway and Langfuse are and
# how to authenticate to them. Five come straight out of `deploy/llm-platform/.env`; the sixth,
# `LITELLM_API_KEY`, has to be minted from the running proxy, because a `key_type: llm_api`
# virtual key is what AD-5 gives a harness — a key that reaches the model routes and cannot
# read another Run's spend.
#
# This is the only script that writes to the root `.env`. It rewrites exactly those six
# assignments in place, keeps every other line byte for byte, and takes a timestamped backup
# first. It never adds a variable: a name absent from `.env.example` is not part of the
# contract (AD-20), so an unknown name here is an error rather than an insertion.
#
# An optional argument names a different target — the release bundle's `deploy/.env`,
# which carries the same contract lines this script rewrites.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
host_env="${here}/.env"
# the repository-root .env, two levels up from deploy/llm-platform/; install.sh passes its own
root_env="${1:-${here}/../../.env}"

[[ -f "$host_env" ]] || { echo "deploy/llm-platform/.env is missing — run 'make platform-up' first" >&2; exit 1; }
[[ -f "$root_env" ]] || { echo "${root_env} is missing — cp .env.example .env first" >&2; exit 1; }

set -a
# shellcheck disable=SC1090
. "$host_env"
set +a

litellm="http://127.0.0.1:${LITELLM_PORT:-4000}"

# `key_type: llm_api` restricts the key to the model routes (AD-5, deploy/llm-platform/README.md).
echo "minting a harness key from ${litellm}/key/generate"
response="$(curl -fsS -X POST "${litellm}/key/generate" \
	-H "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
	-H 'Content-Type: application/json' \
	-d '{"key_type": "llm_api", "key_alias": "orchestrator-harnesses"}')" || {
	echo "the proxy did not answer — is 'make platform-up' finished?" >&2
	exit 1
}

api_key="$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["key"])')"
[[ -n "$api_key" ]] || { echo "no key in the proxy's answer" >&2; exit 1; }

backup="${root_env}.backup-$(date -u +%Y%m%dT%H%M%SZ)"
cp "$root_env" "$backup"

python3 - "$root_env" <<PY
import sys

path = sys.argv[1]

# the spend key is the master key here: a single-operator machine, and deploy/llm-platform/README.md records
# that as an accepted exposure rather than the intended production split
values = {
    "LITELLM_BASE_URL": "http://host.docker.internal:${LITELLM_PORT:-4000}",
    "LITELLM_API_KEY": "${api_key}",
    "LITELLM_SPEND_KEY": "${LITELLM_MASTER_KEY}",
    "LANGFUSE_BASE_URL": "http://host.docker.internal:${LANGFUSE_PORT:-3000}",
    "LANGFUSE_PUBLIC_KEY": "${LANGFUSE_INIT_PROJECT_PUBLIC_KEY}",
    "LANGFUSE_SECRET_KEY": "${LANGFUSE_INIT_PROJECT_SECRET_KEY}",
}

lines = open(path).read().splitlines()
written = set()
out = []
for line in lines:
    name = line.partition("=")[0]
    if name in values:
        comment = line.split("#", 1)
        trailing = "   #" + comment[1] if len(comment) > 1 else ""
        out.append(f"{name}={values[name]}{trailing}")
        written.add(name)
    else:
        out.append(line)

missing = set(values) - written
if missing:
    raise SystemExit(f".env does not declare {sorted(missing)} — it is not the current contract")

open(path, "w").write("\n".join(out) + "\n")
print("rewrote " + ", ".join(sorted(written)))
PY

echo "backup: ${backup#"$root"/}"
echo
echo "Langfuse  http://localhost:${LANGFUSE_PORT:-3000}  (${LANGFUSE_INIT_USER_EMAIL} / see LANGFUSE_INIT_USER_PASSWORD in deploy/llm-platform/.env)"
echo "LiteLLM   ${litellm}"
