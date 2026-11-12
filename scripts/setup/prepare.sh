#!/usr/bin/env bash
# Creates the setup run's mounted folders under the agent home. Runs as `agent` in a one-shot
# container that carries backend-api's env files: read nothing but the two variables below and
# print no environment.
set -euo pipefail

: "${HARNESS_SCRIPTS_DIR:=/app/scripts/harness}"
: "${AGENT_HOME:=/home/agent}"

dirs=()
for h in claude codex opencode; do
  if ! out="$("$HARNESS_SCRIPTS_DIR/$h.sh" asset-dirs 2>/dev/null)"; then
    echo "prepare: $h.sh asset-dirs failed" >&2
    exit 2
  fi
  while IFS= read -r line; do
    case "$line" in
      "" | /* | .. | ../* | */.. | */../*)
        echo "prepare: $h.sh asset-dirs printed a bad path: '$line'" >&2
        exit 2
        ;;
    esac
    dirs+=("$line")
  done <<<"$out"
done
dirs+=(.orchestrator)

for d in "${dirs[@]}"; do
  if [ ! -d "$AGENT_HOME/$d" ]; then
    mkdir -p "$AGENT_HOME/$d"
    echo "created $AGENT_HOME/$d"
  fi
done
