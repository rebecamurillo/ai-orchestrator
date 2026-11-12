---
title: Docker for Runs (optional, off by default)
kind: page
audience: host
---

Local agent on the host or the user only.

# Docker for Runs (optional, off by default)

A Run executes the target repository's own commands — install, tests, quality gate — inside
`backend-api`. The image carries the `docker` CLI with the compose and buildx plugins, but no
daemon: a repository whose commands run `docker compose` (database integration tests, an
end-to-end suite in compose) fails those rows with `Cannot connect to the Docker daemon`.

```bash
./install.sh start --with-docker     # sets VERIFY_DOCKER=true in .env, starts the sidecar
./install.sh start --no-docker       # sets it false, removes the sidecar, keeps its image cache
```

`VERIFY_DOCKER=true` starts the `docker` service (compose profile `docker`): Docker-in-Docker
(`docker:<version>-dind`, privileged), placed in backend-api's network namespace.

- **Where the daemon is.** dockerd listens on `127.0.0.1:2375` inside that namespace only —
  nothing is published on this machine. At each start backend-api writes a docker context
  for the `agent` user (`$HOME/.docker`), so every `docker` a Run's command or a coding agent
  types reaches it; no variable has to be passed to the Run.
- **Ports.** A port a target's compose file publishes appears on backend-api's `localhost`,
  which is where its scripts look (`localhost:5432`). It collides with backend-api's own
  `BACKEND_API_PORT` (8000 by default) if a target publishes that one.
- **Bind mounts.** The sidecar mounts the `work` volume at `WORK_DIR`, the path backend-api
  uses, so a relative bind mount in a target's compose file (`./tests/fixtures:/fixtures`)
  resolves to the worktree.
- **Networks.** The daemon's bridge and its compose networks use `10.213.0.0/24` and
  `10.214.0.0/16`, away from `172.16.0.0/12`, where compose and Docker Desktop put theirs.
- **Image cache.** Pulled images and build cache live on the `docker-data` volume and survive
  restarts; it is not backed up, and `docker volume rm <project>_docker-data` while the
  sidecar is stopped empties it.
- **Concurrency.** One daemon serves every Run. A target whose compose file fixes its
  project name, container names or host ports collides with itself when two Runs on that
  repository verify at once (`MAX_ACTIVE_RUNS` above 1); the second `up` fails or stops the
  first one's containers. Keep such a repository to one Run at a time, or make its scripts
  take the project name and ports from the environment.
- **Cleanup.** Nothing removes what a target starts. A script that exits before its own
  `docker compose down` leaves containers running in the sidecar until the next Run's
  `down`, or until the sidecar is recreated (`./install.sh start --no-docker`, then
  `--with-docker`).
- **Restarts.** If backend-api restarts or is recreated on its own, the sidecar is left in the
  old namespace and Runs reach nothing. `./install.sh doctor` reports it on its `dind` line;
  `./install.sh start` (and every install.sh command that recreates backend-api) checks the
  daemon from inside backend-api and recreates the sidecar when it does not answer.

Pre-flight warns on the New-workflow screen (`docker` line) when VERIFY_DOCKER is off and the
Run looks like it needs a daemon: a `shell` row naming `docker`, or a compose file at the
repository root. It is a guess and never blocks a start. By hand, without install.sh:
`VERIFY_DOCKER=true` in `.env`, then `docker compose --profile docker up -d --wait`.
