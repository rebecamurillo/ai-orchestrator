#!/usr/bin/env bash
# backend-api container start-up, in the order the story fixed.
#
#   1. every harness CLI is reconciled against its `*_VERSION` pin (`ensure-all.sh`):
#      `/opt/harness-cli` is the `harness-bin` volume; the image's copy is laid on it when at
#      the pin, else the pin is installed there once. A pin that cannot be installed refuses that
#      harness alone until the next start; the container continues, so `restart: always`
#      never turns a failed npm install into a retry loop (hard rule 7).
#   2. every harness's static config is regenerated from the environment (AD-10, AD-20).
#      Regenerated, not preserved: `agent-home` is a volume, and a stale config written by
#      an older image would otherwise survive a rebuild. A missing required variable stops
#      the container here, before anything is served.
#   3. the readiness fixture's bare origin is rebuilt (SPEC CAP-8, AD-16) — idempotent,
#      cheap, and must exist before `main.run_migrations` seeds the `readiness` Project's
#      Repository and runs its clone check.
#   4. `alembic upgrade head` — the schema reaches head before the process starts, so a
#      database that cannot be migrated fails the container instead of a request (spine
#      Operations). The application repeats this as its start-up step; the second call
#      finds the schema already at head and applies nothing.
#   5. the application replaces this shell, so PID 1 is uvicorn and SIGTERM reaches it.
#
# No credential is read here. Everything comes from the process environment, which compose
# fills from `.env`.
set -euo pipefail

# `docker run --rm <image> kit bootstrap | tar x` — the client install out of the image, before
# anything that needs an environment or a database (agent-delivery-kit plan §1). The archive
# extracts to `ai-orchestrator/`, the directory `deploy/README.md` tells a client to enter.
if [[ "${1:-}" == "kit" ]]; then
  case "${2:-}" in
    bootstrap) exec tar -C /app --transform 's,^deploy,ai-orchestrator,;s,^VERSION,ai-orchestrator/VERSION,' -cf - deploy VERSION ;;
    *) echo "usage: docker run --rm <image> kit bootstrap | tar x" >&2; exit 64 ;;
  esac
fi

cd /app

scripts/harness/ensure-all.sh

for harness in claude codex opencode; do
  "scripts/harness/${harness}.sh" configure
done

scripts/readiness_fixture.sh

cd /app/backend-api
alembic upgrade head

exec python -m orchestrator.main
