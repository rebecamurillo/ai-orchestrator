#!/usr/bin/env bash
# scripts/bundle.sh — the offline client package for one release tag.
#
#   scripts/bundle.sh                   # the tag in VERSION → dist/ai-orchestrator-deploy-<tag>.tar.gz
#   scripts/bundle.sh 1.0.0-beta        # an explicit tag
#   scripts/bundle.sh 1.0.0-beta /dir   # … into that directory instead
#
# `deploy/` in the repository IS the client install, entire: `install.sh`, the compose file,
# the env contract, `README.md`, `llm-platform/` (LiteLLM + Langfuse) and `kit/` (the agent
# skills). The archive is that one directory, extracted as `ai-orchestrator-deploy-<tag>/`,
# plus a `VERSION` file carrying the tag so `install.sh` knows which images to pull.
#
# This is the escape hatch for a client who must receive a file — procurement, an air-gapped
# network. The documented path pulls the same directory out of the backend image
# (`deploy/README.md`). Files are taken from the working tree through `git ls-files` (tracked
# plus untracked-but-not-ignored), so a filled `.env` or `llm-platform/.env` can never end up
# inside a package handed to a client (hard rule 5), and neither can `llm-platform/backups/`.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# the tag defaults to the repository's VERSION file — the one place the release number lives
tag="${1:-$(tr -d '[:space:]' < "${root}/VERSION")}"
out="${2:-${root}/dist}"
name="ai-orchestrator-deploy-${tag}"

case "$tag" in
	[0-9]*.[0-9]*.[0-9]*|v[0-9]*.[0-9]*.[0-9]*) ;;
	*) echo "tag must be a version like 1.0.0-beta or v0.1.0 (got '${tag}')" >&2; exit 1 ;;
esac

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
target="${stage}/${name}"
mkdir -p "$target"

while IFS= read -r -d '' path; do
	[[ -f "${root}/${path}" ]] || continue     # in the index but deleted from the tree
	mkdir -p "${target}/$(dirname "${path#deploy/}")"
	cp -p "${root}/${path}" "${target}/${path#deploy/}"
done < <(git -C "$root" ls-files -z --cached --others --exclude-standard -- deploy)
printf '%s\n' "$tag" > "${target}/VERSION"

# what must be there for install.sh to work at all
for required in install.sh docker-compose.yml .env.example README.md llm-platform/docker-compose.yml \
	llm-platform/generate-env.sh llm-platform/sync-env.sh llm-platform/.env.example \
	kit/install.sh kit/skills/orchestrator/SKILL.md; do
	[[ -f "${target}/${required}" ]] || { echo "bundle is missing ${required}" >&2; exit 1; }
done
# and what must never be
for forbidden in .env llm-platform/.env; do
	[[ ! -e "${target}/${forbidden}" ]] || { echo "bundle contains ${forbidden}" >&2; exit 1; }
done

mkdir -p "$out"
archive="${out}/${name}.tar.gz"
tar -czf "$archive" -C "$stage" "$name"
echo "$archive"
(cd "$out" && shasum -a 256 "${name}.tar.gz" 2>/dev/null || sha256sum "${name}.tar.gz")
