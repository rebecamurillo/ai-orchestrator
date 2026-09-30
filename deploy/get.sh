#!/usr/bin/env bash
# get.sh — download a release bundle of ai-orchestrator and extract it.
#
# The repository and its packages are private, so the GitHub Release asset is fetched through
# the API with a token (classic PAT: `repo` to read the release, `read:packages` for the
# images `install.sh` pulls next).
#
#   GITHUB_TOKEN=ghp_… bash get.sh            # the latest release
#   GITHUB_TOKEN=ghp_… bash get.sh v0.1.0     # one release
#
# Without a checkout, fetch this script the same way and pipe it to bash:
#
#   curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
#     https://raw.githubusercontent.com/OptimAI-labs/ai-orchestrator/main/deploy/get.sh \
#     | GITHUB_TOKEN=$GITHUB_TOKEN bash -s -- v0.1.0
#
# Then: cd ai-orchestrator-deploy-<tag> && ./install.sh
set -euo pipefail

repo="${ORCHESTRATOR_REPO:-OptimAI-labs/ai-orchestrator}"
tag="${1:-}"
token="${GITHUB_TOKEN:-${GHCR_TOKEN:-}}"

[[ -n "$token" ]] || { echo "set GITHUB_TOKEN to a token that can read ${repo}" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required" >&2; exit 1; }
command -v tar >/dev/null || { echo "tar is required" >&2; exit 1; }

api="https://api.github.com/repos/${repo}/releases"
if [[ -n "$tag" ]]; then api="${api}/tags/${tag}"; else api="${api}/latest"; fi

release="$(curl -fsS -H "Authorization: Bearer ${token}" -H "Accept: application/vnd.github+json" "$api")" ||
	{ echo "no release at ${api} — check the tag and that the token can read ${repo}" >&2; exit 1; }

tag="$(printf '%s' "$release" | sed -n 's/^ *"tag_name": *"\([^"]*\)".*/\1/p' | head -1)"
name="ai-orchestrator-deploy-${tag}"
asset="$(printf '%s' "$release" | grep -o '"url": *"[^"]*/releases/assets/[0-9]*"' | head -1 | sed 's/.*"\(https[^"]*\)"/\1/')"
[[ -n "$asset" ]] || { echo "release ${tag} has no attached bundle" >&2; exit 1; }

echo "downloading ${name}.tar.gz"
# `Accept: application/octet-stream` makes the API answer with the file (via a redirect to
# storage, where curl correctly drops the Authorization header)
curl -fsSL -H "Authorization: Bearer ${token}" -H "Accept: application/octet-stream" \
	-o "${name}.tar.gz" "$asset"
tar -xzf "${name}.tar.gz"
rm -f "${name}.tar.gz"

echo
echo "extracted ./${name}/"
echo "next:  cd ${name} && GHCR_TOKEN=\$GITHUB_TOKEN ./install.sh"
