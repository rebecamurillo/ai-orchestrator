#!/usr/bin/env bash
# The deployment gate (AD-31): never called by another target, CI job or Run.
set -euo pipefail
cd "$(dirname "$0")/.."
lane="${1:-}"
case "$lane" in
  unit) lanes=(unit) ;;
  stack) lanes=(stack) ;;
  "") lanes=(unit stack) ;;
  *) echo "usage: scripts/test-deploy.sh [unit|stack]" >&2; exit 2 ;;
esac
cd backend-api
uv run --locked ruff check ../deploy-tests
uv run --locked ruff format --check ../deploy-tests
for l in "${lanes[@]}"; do
  uv run --locked python -m pytest "../deploy-tests/$l" -q -p no:cacheprovider
done
