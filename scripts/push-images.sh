#!/usr/bin/env bash
# scripts/push-images.sh — build both images for linux/amd64 + linux/arm64 and push them to
# GHCR under one tag, from a workstation.
#
#   scripts/push-images.sh                 # the tag in VERSION (after `docker login ghcr.io`)
#   GHCR_TOKEN=ghp_… scripts/push-images.sh 1.0.0-beta   # an explicit tag, logging in itself
#   PUSH=0 scripts/push-images.sh          # build only (loads the native arch, no registry)
#
# `release.yml` is the same build on CI, one native runner per architecture. This script is
# the manual route for a pre-release a client tests before a tag exists: buildx cross-builds
# the foreign architecture under emulation, which is slow for backend-api (it installs three
# npm CLIs and Chromium's system libraries) but finishes. Both platforms in one manifest, so
# a client's `docker compose pull` picks its own.
#
# Needs a `docker login ghcr.io` with a token that can write the packages. Either log in
# beforehand, or set `GHCR_TOKEN` (`GITHUB_TOKEN` is the fallback; `GITHUB_USER` names the
# login, resolved from the token when unset) and this script performs the login itself, the
# same way `deploy/install.sh` does. Environment only, never an argument: argv is visible in
# `ps` and lands in shell history. The token reaches the docker daemon's credential store and
# nothing else — never a build argument, never a layer (hard rule 5). Each image is labelled
# with the commit it was built from, so `docker inspect` on a client machine answers "what is
# this" without the registry.
#
# The harness CLI pins (CLAUDE_CODE_VERSION, CODEX_VERSION, OPENCODE_VERSION) are passed as
# build arguments read from the repository's `.env.example`, because a published image carries
# the contract's pins; `.env` is never read. One also set in this script's environment must
# equal the contract's, or nothing is built. To publish another pin, change `.env.example`.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The pin shape every reader of a harness pin accepts. A test keeps its four copies identical:
# scripts/harness/_common.sh, deploy/install.sh, scripts/push-images.sh, release.yml.
PLAIN_VERSION='^[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}([-+][0-9A-Za-z.-]+)?$'

# NAME's value from the first `NAME=` line of the repository's `.env.example`, read as compose
# reads it: a `#` comment after whitespace dropped, then a matched pair of quotes.
contract_value() {
	local line value
	[[ -f "${root}/.env.example" ]] || return 0
	line="$(grep "^$1=" "${root}/.env.example" | head -1 || true)"
	[[ -n "$line" ]] || return 0
	value="${line#*=}"
	value="$(printf '%s' "$value" | sed -E 's/(^|[[:space:]]+)#.*$//; s/[[:space:]]+$//')"
	case "$value" in \"*\"|\'*\') value="${value:1:${#value}-2}" ;; esac
	printf '%s' "$value"
}

pin_args=()
for name in CLAUDE_CODE_VERSION CODEX_VERSION OPENCODE_VERSION; do
	value="$(contract_value "$name")"
	given="${!name:-}"
	if [[ -n "$given" && -n "$value" && "$given" != "$value" ]]; then
		echo "${name}=${given} in the environment, ${value} in .env.example — the image carries the contract's pin; nothing was built" >&2
		exit 1
	fi
	[[ -n "$value" ]] || value="$given"
	[[ -n "$value" ]] || continue
	if ! [[ "$value" =~ $PLAIN_VERSION ]]; then
		echo "${name}='${value}' is not a plain version (x.y.z) — nothing was built" >&2
		exit 1
	fi
	pin_args+=(--build-arg "${name}=${value}")
done

tag="${1:-$(tr -d '[:space:]' < "${root}/VERSION")}"
namespace="${IMAGE_NAMESPACE:-ghcr.io/rebecamurillo/ai-orchestrator}"
platforms="${PLATFORMS:-linux/amd64,linux/arm64}"
push="${PUSH:-1}"
revision="$(git -C "$root" rev-parse HEAD)"

case "$tag" in
	[0-9]*.[0-9]*.[0-9]*|v[0-9]*.[0-9]*.[0-9]*) ;;
	*) echo "tag must be a version like 1.0.0-beta (got '${tag}')" >&2; exit 1 ;;
esac

docker buildx version >/dev/null 2>&1 || { echo "docker buildx is missing" >&2; exit 1; }

ghcr_login() {   # with GHCR_TOKEN (or GITHUB_TOKEN) set: log the daemon in, as install.sh does
	local token="${GHCR_TOKEN:-${GITHUB_TOKEN:-}}" user="${GITHUB_USER:-}"
	[[ -n "$token" ]] || return 0
	if [[ -z "$user" ]]; then
		user="$(curl -fsS -H "Authorization: Bearer ${token}" https://api.github.com/user 2>/dev/null |
			sed -n 's/^ *"login": *"\([^"]*\)".*/\1/p' | head -1 || true)"
	fi
	user="${user:-token}"
	printf '%s' "$token" | docker login ghcr.io -u "$user" --password-stdin >/dev/null ||
		{ echo "ghcr.io refused the token for user ${user} — it needs write:packages" >&2; exit 1; }
	echo "logged in to ghcr.io as ${user} (credential kept by docker)"
}

if [[ "$push" == "1" ]]; then
	output="--push"
	ghcr_login
	# an early, cheap refusal: a bad or absent credential fails here, not after an hour's build.
	# A private package answers `denied` without a valid credential and `manifest unknown`
	# with one when the tag does not exist yet; only the first is a reason to stop.
	probe="$(docker manifest inspect "${namespace}/web-client:${tag}" 2>&1 >/dev/null || true)"
	if printf '%s' "$probe" | grep -qi 'denied\|unauthorized'; then
		echo "ghcr.io denies access to ${namespace} — 'docker login ghcr.io' with a token that has write:packages" >&2
		exit 1
	fi
else
	output="--load"
	platforms="$(docker version --format 'linux/{{.Server.Arch}}')"
fi

build() {   # build <component> <context> <dockerfile>
	local component="$1" context="$2" dockerfile="$3"
	echo "== ${namespace}/${component}:${tag} (${platforms})"
	docker buildx build \
		--platform "$platforms" \
		${pin_args[@]+"${pin_args[@]}"} \
		--file "$dockerfile" \
		--tag "${namespace}/${component}:${tag}" \
		--tag "${namespace}/${component}:sha-${revision}" \
		--label "org.opencontainers.image.source=https://github.com/rebecamurillo/ai-orchestrator" \
		--label "org.opencontainers.image.revision=${revision}" \
		--label "org.opencontainers.image.version=${tag}" \
		--provenance=false --sbom=false \
		"$output" \
		"$context"
}

# the backend needs the repository root (backend-api/ + scripts/harness/ + templates/);
# the web-client needs nothing outside its own directory — the same contexts release.yml uses
build web-client "${root}/web-client" "${root}/web-client/Dockerfile"
build backend-api "${root}" "${root}/backend-api/Dockerfile"

if [[ "$push" == "1" ]]; then
	echo
	for component in web-client backend-api; do
		docker buildx imagetools inspect "${namespace}/${component}:${tag}" | sed -n '1,3p;/Platform:/p'
	done
	echo
	echo "pushed ${namespace}/{web-client,backend-api}:${tag} (and :sha-${revision})"
fi
