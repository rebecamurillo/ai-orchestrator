#!/usr/bin/env bash
# Seed the readiness fixture's origin (SPEC CAP-8, AD-16): a bare git repository under
# $WORK_DIR/readiness/origin.git, holding one `main` branch built from
# fixtures/readiness-repo/ with _bmad/ installed at BMAD_VERSION — the same
# `bmad-method@{version} install --yes --modules bmm --tools claude-code,codex,opencode`
# command `application/steps/bmad_install.py::INSTALL_COMMAND` runs for a real Run, and the
# same three tool-folder lines its own `IGNORED` tuple appends afterwards.
#
# Idempotent and cheap: run at every container start (`docker-entrypoint.sh`), this script
# always leaves the origin at the same state for the image's current `BMAD_VERSION`, so a
# readiness Run never clones a stale fixture or one pinned to a version this image no
# longer runs. `fixtures/readiness-repo/` is copied into a scratch working tree and never
# edited in place.
set -euo pipefail

: "${WORK_DIR:=/work}"
: "${BMAD_VERSION:=6.11.0}"

FIXTURE_SRC="${READINESS_FIXTURE_SRC:-/app/fixtures/readiness-repo}"
READINESS_DIR="${WORK_DIR}/readiness"
ORIGIN="${READINESS_DIR}/origin.git"
SCRATCH="${READINESS_DIR}/scratch"

log() { printf '[readiness-fixture] %s\n' "$*" >&2; }

mkdir -p "${READINESS_DIR}"
rm -rf "${SCRATCH}" "${ORIGIN}"

log "bare origin at ${ORIGIN}"
# `-b main`, not the default: `git init --bare` leaves HEAD a symbolic ref to whatever
# `init.defaultBranch` says — `master` in this image — which this fixture never creates, and
# `git ls-remote -- <url> HEAD`, the clone check's own first line, answers nothing for an
# unborn HEAD (`use_cases/clone_check.py::_reachable` then reports `the remote answered no refs`).
git init --bare -q -b main "${ORIGIN}"

log "building main from ${FIXTURE_SRC} (BMAD_VERSION=${BMAD_VERSION})"
cp -r "${FIXTURE_SRC}" "${SCRATCH}"
cd "${SCRATCH}"
git init -q -b main
git config user.email "orchestrator@localhost"
git config user.name "orchestrator"

npx --yes "bmad-method@${BMAD_VERSION}" install --yes --modules bmm \
  --tools claude-code,codex,opencode --directory "${SCRATCH}"

# the same three lines `application/steps/bmad_install.py::IGNORED` appends after every
# real repo-init install (AD-16) — this fixture must ignore the same tool folders, so a
# readiness Run's own commit never carries them either
for line in ".claude/skills/bmad-*" ".agents/skills/bmad-*" ".opencode/commands/bmad-*"; do
  grep -qxF "${line}" .gitignore 2>/dev/null || echo "${line}" >> .gitignore
done

git add -A
git commit -q -m "readiness fixture: seed (orchestrator)"
git remote add origin "${ORIGIN}"
git push -q -f origin main

cd /
rm -rf "${SCRATCH}"

log "done"
