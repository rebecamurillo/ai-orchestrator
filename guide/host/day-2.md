---
title: Day 2
kind: procedure
audience: host
readme: day-2
---

Local agent on the host or the user only.

```bash
./install.sh status              # docker compose ps, for this stack
./install.sh logs                # follow the orchestrator's output
./install.sh doctor              # read-only health checks; non-zero on any `fail`
./install.sh diagnose            # a redacted report to attach to a bug report
./install.sh harness claude --subscription   # Claude Max/Pro login instead of an API key
./install.sh stop                # stop, keeping every volume
./install.sh start               # start again
./install.sh start --with-docker     # add a Docker daemon for Runs' commands (§ Docker for Runs)
./install.sh setup               # run setup/*.sh and BMAD now
./install.sh setup --reset       # empty the harness asset folders first (logins kept)
./install.sh bmad remove         # delete BMAD's skills and keep them out
./install.sh bmad install        # put BMAD's skills back
./install.sh upgrade --tag <newer>   # § Upgrading
./install.sh uninstall           # stop and DELETE the volumes, after typing `delete`
```

`doctor` changes nothing. It prints one `ok` / `warn` / `fail` line per check — docker and the
daemon, `docker engine` (26 or later), `.env` and its mode, `release pins` (each pin `.env`
overrides), `IMAGE_TAG` (a leftover line in `.env`, which nothing reads now), the version the
instance reports, the two ports, `/healthz` and the token, each harness's readiness,
`setup` (the last run's record and its failures), `bmad` (the installed version against the
release pin, or removed by choice), free disk, the retention and cron
settings — and every `fail` and `warn` line ends with the command to run or the variable to
set. No secret is printed, so its output is safe to paste.

`diagnose` writes `diagnostics/<timestamp>.md`: versions, `compose ps`, the last 200 lines of
the logs, and `.env` with every value masked except ports, crons, versions, directories and
flags. That file is what a bug report attaches. Read it before you send it — a log line
carries whatever a target repository printed.

`harness claude --subscription` sets `CLAUDE_SUBSCRIPTION_AUTH`, prints the two lines to
uncomment in your gateway's `litellm.config.yaml`, runs `claude login` inside the container,
and reads `GET /api/v1/harnesses` back after the restart. `--api-key` goes the other way. The
starter's README (§ Getting an LLM platform) has the whole picture, including what a
subscription does to the cost figures on screen and which half of that path has never been
run live.

`uninstall` keeps `.env`, so the token survives a reinstall; remove it yourself when you
mean it.

### If something is wrong

Start with `./install.sh doctor`. It is the whole checklist, it is useful even when the
instance does not answer at all, and the line that fails names its own fix. If that is not
enough, `./install.sh diagnose` collects everything a maintainer will ask for, already
redacted.

The `orchestrator-admin` skill in `kit/` is the same ground for an agent: install it into this
directory and Claude Code, Codex or OpenCode will walk install, upgrade, backup, rollback,
harness and subscription setup, secret rotation, garbage collection and filing the bug report
— running these commands and reading their output rather than improvising around them.

Ports: everything publishes on `127.0.0.1` — 4321 (web) and 8000 (API). If one is already
taken on your machine the script stops before starting anything and names the variable
that moves this stack off it (`WEB_CLIENT_PORT`, `BACKEND_API_PORT` in `.env`). It never
stops what is listening there.

### For the host agent

`./install.sh doctor` is your first move, every time, before diagnosing anything by hand. Besides
the checks listed above it covers: whether both images are actually pulled; `.env` with no
`change-me` left in a REQUIRED variable; whether `~/.docker/config.json` has a ghcr.io entry at
all (only a pull proves the credential still works); `/api/v1/version` against `VERSION`, with
the pinned BMAD and harness CLI versions; each harness's `enabled` and `failing_check`; and
Docker for Runs (`dind`).

How to read it:

- **`fail` on `.env`** — nothing else is meaningful yet. Fix it first and re-run.
- **`fail` on `token`** — the containers are running an older `ORCHESTRATOR_TOKEN` than the
  file says. `./install.sh start` re-reads `.env`.
- **`fail` on `setup`** — a setup script failed or no record exists: `./install.sh setup`
  runs it again; `logs/setup/` holds each script's output. **`fail` on `bmad`** — the
  installed version differs from the release pin: `./install.sh setup`. **`fail` on
  `docker engine`** — upgrade Docker Engine to 26 or later. **`warn` on `release pins`** —
  `.env` overrides a pin of `release.env`; delete the line to follow the release.
  **`warn` on `IMAGE_TAG`** — delete the line from `.env`.
- **`warn` on `version`** — the instance was never restarted after a refresh, or these files came
  from a different release than the instance runs. The line names the `upgrade --tag` that
  reconciles them. Decide which number is the intended one before running it.
- **`warn` on a harness** — the `failing_check` is the first failing readiness line
  verbatim. `cli not at pinned version` means the CLI in the container is not the
  `*_VERSION` `.env` pins — `backend-api` was not recreated since the pin changed, or the
  start-up install of that pin failed (`./install.sh logs` names both versions);
  `./install.sh harness <name> --version <pin>` applies it (see `host/harness-setup`);
  `not logged in (claude auth status)` means the subscription login expired (see
  `host/harness-setup`). Re-run the diagnostic with
  `POST /api/v1/harnesses/{name}/readiness`, or from the web UI's Fleet page.
- **The gateway is blank** — `LITELLM_BASE_URL` blank is the gateway's off switch. Set the
  six values in `.env` (README.md § The gateway and tracing values), then
  `./install.sh start`.
- **`dind`** — Docker for Runs. `ok … off` is the default: a repository whose commands run
  `docker compose` fails those rows with `Cannot connect to the Docker daemon`.
  `./install.sh start --with-docker` turns it on — a privileged sidecar, so put README.md
  § Trust to the user first; it is their decision. `fail` while on names the case (not
  running, unhealthy, left in an old network namespace after backend-api restarted), and
  `./install.sh start` repairs each.
