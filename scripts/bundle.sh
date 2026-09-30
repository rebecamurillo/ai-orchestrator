#!/usr/bin/env bash
# scripts/bundle.sh — assemble the client package for one release tag.
#
#   scripts/bundle.sh                   # the tag in VERSION → dist/ai-orchestrator-deploy-<tag>.tar.gz
#   scripts/bundle.sh 1.0.0-beta        # an explicit tag
#   scripts/bundle.sh 1.0.0-beta /dir   # … into that directory instead
#
# The archive extracts to one directory, `ai-orchestrator-deploy-<tag>/`, laid out so the
# first thing a client sees is `install.sh`:
#
#   install.sh  get.sh  docker-compose.yml  .env.example  README.md  VERSION
#   host/       the optional LiteLLM + Langfuse stack
#   plugin/     the Claude Code skill that teaches a project's agents the API
#
# `deploy/` in the repository is the bundle root, so `deploy/install.sh` finds `host/`
# beside it in a bundle and one level up in a checkout — the same script serves both.
# `VERSION` carries the tag, which is how `install.sh` knows which images to pull without
# being told. Files are taken from the working tree through `git ls-files` (tracked plus
# untracked-but-not-ignored), so a filled `.env` or `host/.env` can never end up inside a
# package handed to a client (hard rule 5), and neither can `host/backups/`.
#
# `release.yml` runs this on a tag; `make bundle TAG=…` runs it on the operator's machine
# to hand a package out ahead of, or beside, a GitHub Release.
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

copy_tree() {   # copy_tree <repo dir> <bundle dir>
	local from="$1" to="$2" path
	while IFS= read -r -d '' path; do
		[[ -f "${root}/${path}" ]] || continue     # in the index but deleted from the tree
		mkdir -p "${to}/$(dirname "${path#"${from}"/}")"
		cp -p "${root}/${path}" "${to}/${path#"${from}"/}"
	done < <(git -C "$root" ls-files -z --cached --others --exclude-standard -- "$from")
}

copy_tree deploy "$target"
copy_tree host "${target}/host"
copy_tree plugin "${target}/plugin"
printf '%s\n' "$tag" > "${target}/VERSION"

# what must be there for install.sh to work at all
for required in install.sh docker-compose.yml .env.example README.md host/docker-compose.yml \
	host/generate-env.sh host/sync-env.sh host/.env.example plugin/skills/orchestrator/SKILL.md; do
	[[ -f "${target}/${required}" ]] || { echo "bundle is missing ${required}" >&2; exit 1; }
done
# and what must never be
for forbidden in .env host/.env; do
	[[ ! -e "${target}/${forbidden}" ]] || { echo "bundle contains ${forbidden}" >&2; exit 1; }
done

mkdir -p "$out"
archive="${out}/${name}.tar.gz"
tar -czf "$archive" -C "$stage" "$name"
echo "$archive"
(cd "$out" && shasum -a 256 "${name}.tar.gz" 2>/dev/null || sha256sum "${name}.tar.gz")
