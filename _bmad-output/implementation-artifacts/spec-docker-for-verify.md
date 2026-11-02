---
title: 'Docker for Runs: a daemon for target repositories whose commands run docker compose'
type: 'feature'
created: '2026-11-02'
status: 'in review'
baseline_commit: '4b7e270'
context: []
---

## Intent

**Problem (verified 2026-11-02 on the production instance, release 1.0.0-beta.2).** A `shell`
row — install, test or quality gate from the Repository record or `epics.yaml` — cannot use
Docker: the backend-api image has no `docker` CLI, compose or buildx, and no daemon is
reachable. A target repository whose quality gate runs `docker compose` (adele-demo-simulation:
`scripts/check.sh && scripts/test-e2e.sh`, PostGIS integration tests and a full-stack
Playwright E2E in compose) cannot pass.

Constraints that shaped the design:

- `infrastructure/process/runner.py` gives a `shell` row `env={}` plus `PATH`, `HOME`, `LANG`
  from the backend process; Project `env_vars` are not wired to `shell` rows
  (`application/steps/shell.py`). A `DOCKER_HOST` cannot be passed per Project or per row.
- Worktrees live on the `work` named volume at `WORK_DIR`. A host-socket mount fails: a
  compose file's relative bind mount resolves on the daemon's filesystem, which cannot see
  the volume. The daemon has to mount `work` at the same path.
- Target scripts connect to published ports on `localhost` (`localhost:${DB_PORT:-5432}`), so
  published ports must appear on backend-api's `localhost`.

**Approach.** An optional Docker-in-Docker sidecar in backend-api's network namespace, the
docker client baked into the backend image, and the agent user's CLI pointed at the sidecar
through a docker context in `$HOME/.docker`. The Operator applied the equivalent by hand on
production on 2026-11-02 (a `docker-cli` one-shot filling a volume with the static client and a
`DOCKER_HOST` wrapper on `PATH`, plus the same `docker` service); this change replaces it on
the next upgrade (deploy/README.md § Upgrading).

## Decisions (2026-11-02; each for the Operator to validate in review)

- **D1 — the switch is `VERIFY_DOCKER` in `.env`, the sidecar is the compose profile
  `docker`.** One variable both halves read: install.sh adds `--profile docker` to every
  compose call when it is true, and the container start points the CLI by it.
  `--with-docker` / `--no-docker` on `install` and `start` write it, as `--with-platform`
  decides the llm-platform stack. A Settings field (`verify_docker`), because pre-flight reads
  it and AD-20 puts every `.env.example` line in Settings; not a deploy-only variable.
- **D2 — the CLI finds the daemon through a docker context, not `DOCKER_HOST`.** AD-5/AD-10's
  `HARNESS_ENV_CONTRACT` stays exactly as it is: the runner already passes `HOME`, and
  `$HOME/.docker/config.json`'s `currentContext` reaches every `shell` row and every harness
  process without a new name in any env builder. `scripts/docker_context.sh` runs at each
  start (entrypoint, after `configure`, before migrations) and reconciles both ways, because
  `agent-home` is a volume and a context written by one start outlives the container. The
  production wrapper's `PATH` override is not reproduced.
- **D3 — `dockerd` on `tcp://127.0.0.1:2375`, no TLS, inside backend-api's namespace only.**
  `dockerd` is the first argument because the dind entrypoint, given bare flags, prepends its
  own `--host=tcp://0.0.0.0:2375`, which `postgres` and `web-client` could reach. Bridge
  `10.213.0.1/24`, pools `10.214.0.0/16` size 24. Same values as the production hand edit.
- **D4 — versions.** `docker:29.4.3-dind` (the production pin) and a 29.4.3 client; compose
  5.6.1 and buildx 0.38.1, current stable on 2026-11-02. All three downloads are checked
  against a literal sha256 per architecture in the Dockerfile, because download.docker.com
  publishes no checksum file for the static archive; the compose and buildx values were
  cross-checked against each release's own `checksums.txt`.
- **D5 — readiness.** `./install.sh doctor` gains a `dind` line from `ps` and `inspect` only
  (doctor never `exec`s): off; on and healthy; on and not running, unhealthy, or older than
  backend-api's own start (the stale-namespace case, reproduced in a scratch stack: the
  sidecar's own healthcheck stays green while backend-api reaches nothing). `start`, and every
  command that recreates backend-api, checks the daemon from inside backend-api and
  force-recreates the sidecar once when it does not answer. Pre-flight gains a `docker` line,
  appended after FR-8's twelve: `warn` when off and the Run looks like it needs a daemon (a
  `shell` row naming docker, or a compose file at the repository root at the plan commit),
  `ok` when on, absent otherwise. A guess, so it never blocks a start.
- **D6 — consumer stack only.** The sidecar is in `deploy/docker-compose.yml`. The dev stack
  (`docker-compose.yml`, and `DEPLOY.md`'s prod overlay on it) does not carry it:
  `test_compose.py` pins every image there to `postgres:*`, and changing that is not this
  change's to declare.

## Out of scope (follow-ups)

- A GitHub-Actions-style `services:` field per epic, so a Run declares the containers it
  needs instead of each repository's scripts starting them.
- A step that waits on the pushed branch's GitHub check results as a quality gate.
- Per-Run isolation on the shared daemon (a compose project name per Run, or a daemon per
  Run), so two Runs on one repository with fixed project names or ports do not collide.
- The sidecar in the dev stack, as an overlay, once the Operator rules on `test_compose.py`.
