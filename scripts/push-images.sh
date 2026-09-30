#!/usr/bin/env bash
# scripts/push-images.sh — build both images for linux/amd64 + linux/arm64 and push them to
# GHCR under one tag, from a workstation.
#
#   scripts/push-images.sh                 # the tag in VERSION
#   scripts/push-images.sh 1.0.0-beta      # an explicit tag
#   PUSH=0 scripts/push-images.sh          # build only (loads the native arch, no registry)
#
# `release.yml` is the same build on CI, one native runner per architecture. This script is
# the manual route for a pre-release a client tests before a tag exists: buildx cross-builds
# the foreign architecture under emulation, which is slow for backend-api (it installs three
# npm CLIs and Chromium's system libraries) but finishes. Both platforms in one manifest, so
# a client's `docker compose pull` picks its own.
#
# Needs a prior `docker login ghcr.io` with a token that can write the packages; the token
# stays in the docker daemon's own credential store (never a build argument, never a layer —
# hard rule 5). Each image is labelled with the commit it was built from, so `docker inspect`
# on a client machine answers "what is this" without the registry.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tag="${1:-$(tr -d '[:space:]' < "${root}/VERSION")}"
namespace="${IMAGE_NAMESPACE:-ghcr.io/optimai-labs/ai-orchestrator}"
platforms="${PLATFORMS:-linux/amd64,linux/arm64}"
push="${PUSH:-1}"
revision="$(git -C "$root" rev-parse HEAD)"

case "$tag" in
	[0-9]*.[0-9]*.[0-9]*|v[0-9]*.[0-9]*.[0-9]*) ;;
	*) echo "tag must be a version like 1.0.0-beta (got '${tag}')" >&2; exit 1 ;;
esac

docker buildx version >/dev/null 2>&1 || { echo "docker buildx is missing" >&2; exit 1; }

if [[ "$push" == "1" ]]; then
	output="--push"
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
		--file "$dockerfile" \
		--tag "${namespace}/${component}:${tag}" \
		--tag "${namespace}/${component}:sha-${revision}" \
		--label "org.opencontainers.image.source=https://github.com/OptimAI-labs/ai-orchestrator" \
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
