#!/usr/bin/env bash
# backend-api container start-up, in the order the story fixed.
#
#   1. every harness's static config is regenerated from the environment (AD-10, AD-20).
#      Regenerated, not preserved: `agent-home` is a volume, and a stale config written by
#      an older image would otherwise survive a rebuild. A missing required variable stops
#      the container here, before anything is served.
#   2. the readiness fixture's bare origin is rebuilt (SPEC CAP-8, AD-16) — idempotent,
#      cheap, and must exist before `main.run_migrations` seeds the `readiness` Project's
#      Repository and runs its clone check.
#   3. `alembic upgrade head` — the schema reaches head before the process starts, so a
#      database that cannot be migrated fails the container instead of a request (spine
#      Operations). The application repeats this as its start-up step; the second call
#      finds the schema already at head and applies nothing.
#   4. the application replaces this shell, so PID 1 is uvicorn and SIGTERM reaches it.
#
# No credential is read here. Everything comes from the process environment, which compose
# fills from `.env`.
set -euo pipefail

cd /app

for harness in claude codex opencode; do
  "scripts/harness/${harness}.sh" configure
done

scripts/readiness_fixture.sh

cd /app/backend-api
alembic upgrade head

exec python -m orchestrator.main
