#!/usr/bin/env bash
# Point the agent user's docker CLI at the optional `docker` service, or away from it.
#
# A `shell` row and a harness process both get `PATH`, `HOME` and `LANG` from this process and
# nothing else of its environment (`infrastructure/process/runner.py`), so a `DOCKER_HOST` set
# on the container never reaches them. What does reach them is `$HOME/.docker`: this script
# writes the context `orchestrator-dind` there and makes it current, so every `docker` and
# `docker compose` a Run executes talks to the sidecar's daemon.
#
# Run at every container start (`docker-entrypoint.sh`). `agent-home` is a volume, so a context
# written by an earlier start survives; the script therefore reconciles both ways — with
# VERIFY_DOCKER off it removes the context and leaves the CLI on `default`, whose socket does
# not exist here, and a command needing docker fails with `Cannot connect to the Docker daemon`
# instead of reaching a daemon the operator turned off.
#
# Context commands are local file writes; none of them contacts a daemon.
set -euo pipefail

CONTEXT="orchestrator-dind"
# Where dockerd listens inside backend-api's network namespace: the `docker` service's
# `--host` in both compose files says the same.
ENDPOINT="tcp://127.0.0.1:2375"

log() { printf '[docker-context] %s\n' "$*" >&2; }

enabled() {
  case "$(printf '%s' "${VERIFY_DOCKER:-false}" | tr '[:upper:]' '[:lower:]')" in
    true | 1 | yes | on) return 0 ;;
    *) return 1 ;;
  esac
}

if ! command -v docker >/dev/null 2>&1; then
  log "no docker CLI in this image; nothing to point"
  exit 0
fi

# `default` first: the CLI refuses to remove the context that is current.
docker context use default >/dev/null
docker context rm --force "${CONTEXT}" >/dev/null 2>&1 || true

if enabled; then
  docker context create "${CONTEXT}" \
    --description "the docker service (VERIFY_DOCKER=true)" \
    --docker "host=${ENDPOINT}" >/dev/null
  docker context use "${CONTEXT}" >/dev/null
  log "VERIFY_DOCKER=true: docker talks to ${ENDPOINT}"
else
  log "VERIFY_DOCKER is off: no daemon for Runs' docker commands"
fi
