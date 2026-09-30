# ai-orchestrator — install and run

This directory is the client package: everything a machine needs to run a released
ai-orchestrator without the source repository. One script installs it, runs it in Docker,
and opens it on `http://127.0.0.1:4321`.

The stack is three containers — the web UI, the API, and PostgreSQL — pulling the images a
release publishes to GitHub Container Registry
(`ghcr.io/optimai-labs/ai-orchestrator/{backend-api,web-client}`, `linux/amd64` and
`linux/arm64`). The images are private: a GitHub token that can read them is the one
thing you have to bring.

If you are developing the orchestrator itself, this is not your file: use the repository
root's `README.md`. If you are deploying the operator's own host from a checkout, that
procedure is `DEPLOY.md`.

## What you need

- **Docker** with Compose v2 — Docker Desktop (macOS, Windows with WSL 2) or Docker Engine
  plus the compose plugin (Linux). 8 GB of RAM for the orchestrator alone; 16 GB with the
  optional host stack.
- **A GitHub personal access token** (classic) with:
  - `read:packages` — pulls the two images. Your GitHub user must have been granted read
    access to the packages, or be a member of the organisation that owns them; ask the
    person who sent you this package if a pull answers `denied`.
  - `repo` — if the same token will be the credential the orchestrator uses to clone and
    push the repositories you register (the usual setup; see `GITHUB_TOKEN` below). Every
    repository you register must be reachable by this one token.
- `curl` and `openssl` (both ship with macOS and every mainstream Linux).

## Install

```bash
tar -xzf ai-orchestrator-deploy-1.0.0-beta.tar.gz
cd ai-orchestrator-deploy-1.0.0-beta
./install.sh
```

The script asks for the token, then asks whether to install the optional host stack (see
below), and does the rest: it logs Docker in to the registry, writes `.env` with generated
secrets, pulls the images pinned by the bundle's `VERSION`, starts the stack, proves the API
answers and the token works, and prints:

```
  Web UI     http://127.0.0.1:4321
  API        http://127.0.0.1:8000   (Authorization: Bearer <token>)
  Login      <ORCHESTRATOR_TOKEN>
```

Log in with that token. It is the one credential — the web login and the API bearer — and
it lives in `.env` beside the script. Then follow the operator flow: create a Project,
register a Repository, run its clone check, run `repo-init` if the target repository is new
to BMAD, then start a Run from `/workflows/new` with a budget.

Unattended, from a shell or a provisioning script:

```bash
GHCR_TOKEN=ghp_… ./install.sh --yes                    # orchestrator only
GHCR_TOKEN=ghp_… ANTHROPIC_API_KEY=sk-ant-… ./install.sh --yes --with-host
```

Without the tarball in hand, `get.sh` fetches it from the GitHub Release with the same
token (the repository is private too):

```bash
curl -fsSL -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://raw.githubusercontent.com/OptimAI-labs/ai-orchestrator/main/deploy/get.sh \
  | GITHUB_TOKEN=$GITHUB_TOKEN bash -s -- v1.0.0-beta
```

### What the script wrote

`.env` (mode 600) is the release contract `.env.example` with the **REQUIRED** section
filled in: `IMAGE_TAG` from `VERSION`, a generated `ORCHESTRATOR_TOKEN`, session secret,
Fernet key and database password, and `GITHUB_TOKEN` set to the token you gave (override
by exporting a different `GITHUB_TOKEN` before running). Everything under **OPTIONAL**
keeps its default; the file explains each line. `LITELLM_BASE_URL` and
`LANGFUSE_BASE_URL` are blanked, which is the off switch for the gateway and for tracing,
until the host stack is installed.

The script never overwrites an existing `.env` or `host/.env`: re-running it after a
failure picks up where it stopped without rotating the token you already use. Delete a
file deliberately to start over.

The registry credential goes to `docker login` only. It is held by the Docker daemon's own
config, never by a container: the one credential a *process* in this stack holds is
`ORCHESTRATOR_TOKEN`.

## Day 2

```bash
./install.sh status              # docker compose ps, for both stacks
./install.sh logs                # follow the orchestrator's output
./install.sh stop                # stop, keeping every volume
./install.sh start               # start again (and the host stack, if it was installed)
./install.sh start --with-host   # add the host stack to an existing install
./install.sh upgrade --tag 1.0.0
./install.sh uninstall           # stop and DELETE the volumes, after typing `delete`
```

`upgrade` reads the release notes for you only in the sense of printing the two cautions
below; then it takes a `pg_dump` into `backups/`, rewrites `IMAGE_TAG`, pulls, and
restarts. `uninstall` keeps `.env` and `host/.env`, so the token and the Langfuse keys
survive a reinstall; remove them yourself when you mean it.

Ports: everything publishes on `127.0.0.1` — 4321 (web), 8000 (API), and for the host
stack 3000 (Langfuse), 4000 (LiteLLM), 5433, 9000, 9091 (its stores). If one is already
taken on your machine the script stops before starting anything and names the variable
that moves this stack off it (`WEB_CLIENT_PORT`, `BACKEND_API_PORT` in `.env`;
`LANGFUSE_PORT`, `LITELLM_PORT`, … in `host/.env`). It never stops what is listening there.

## The optional host stack (LiteLLM + Langfuse)

`host/` is the model gateway and the tracing server: LiteLLM (routes every model call,
mints per-harness keys, records spend so a Run's budget is real) and Langfuse (traces), with
their stores (PostgreSQL, ClickHouse, Redis, MinIO) — seven more containers, as their own
compose project so they survive this stack's restarts. Without it each coding agent
authenticates on its own, cost figures are provisional, trace links are absent, and the
`local` harness is unavailable.

`./install.sh` offers it; `--with-host` / `--no-host` decide it unattended. The script
generates `host/.env` with random credentials (`host/generate-env.sh`), writes the provider
keys you give it (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` — prompted,
or from the environment; at least one is needed before a model answers anything), starts
the stack, waits for it (the first start runs migrations — a few minutes), mints the
harness's virtual key and writes the six connection values into `.env`
(`host/sync-env.sh`), then starts the orchestrator against it. It prints the Langfuse
login at the end; it is also in `host/.env`.

`host/README.md` documents the key separation (`LITELLM_API_KEY` is a model-routes-only
virtual key; `LITELLM_SPEND_KEY` reads spend and never reaches a harness), the model routes
in `host/litellm.config.yaml`, and `CLAUDE_SUBSCRIPTION_AUTH`. Pointing at your own
existing LiteLLM/Langfuse instead works the same way: set the `*_BASE_URL` and key
variables in `.env` by hand and skip the host stack.

Every model named in `READINESS_MODELS` must exist in the gateway's `model_list`, or
backend-api refuses to start.

## Agents in your projects

The package carries a Claude Code skill that teaches a project's agents to drive this API —
create projects, launch runs, poll progress, answer checkpoints:

```bash
plugin/install.sh /path/to/your/project
```

copies it into the project's `.claude/skills/`, adds `ORCHESTRATOR_BASE_URL` (default
`http://127.0.0.1:8000`) and `ORCHESTRATOR_TOKEN` to its `.env`, and pings the API to prove
the pair works. The skill's `references/spec-folder.md` documents the `epics.yaml` /
`stories.yaml` / `SPEC.md` format the templates read.

## Exposure

Every published port binds `BIND_ADDRESS`, default `127.0.0.1` — the stack is reachable
only from its own machine. Setting `BIND_ADDRESS=0.0.0.0` in `.env` publishes the web UI
and the API on every interface. Before doing that, know what it means: one bearer token is
the entire authentication, the API dispatches coding agents with write access to your
repositories, and nothing rate-limits login attempts. On any network you do not fully
trust, keep loopback and put a reverse proxy with TLS (or an SSH tunnel / VPN) in front.
PostgreSQL publishes no port in any case; reach it with
`docker compose exec postgres psql -U orchestrator orchestrator` from this directory.

## Trust

The backend container runs harness CLIs as the user `agent` with passwordless sudo, and
without `cap_drop` — deliberately, so an agent can `apt-get install` what a target
repository's install script needs. A Run executes code from the repositories you
register. Register only repositories you trust as much as this machine.

## Upgrading — the two cautions

- **`DBOS_APPLICATION_VERSION`** is pinned in `.env` and versions the engine's durable
  step sequence. A release whose notes say to bump it makes every in-flight Run
  unrecoverable under the old value — drain or cancel Runs first (a parked `needs_you`
  Run holds its slot for up to `HUMAN_WAIT_SECONDS`, 30 days by default, and does not
  time out on its own). Never bump it as routine.
- **Migrations run forward only.** Rolling `IMAGE_TAG` back across a release that
  migrated the schema is expected to fail closed. `./install.sh upgrade` takes the backup
  a rollback restores from; by hand it is
  `docker compose exec postgres pg_dump -U orchestrator -Fc orchestrator > backup.dump`.
- **Harness CLI versions are baked into the image.** The `*_VERSION` variables in `.env`
  exist for the runtime probe check; changing one without pulling an image built with it
  makes every probe fail `cli not at pinned version`.
- `POSTGRES_DB` is fixed after first boot, and the stack supports exactly one
  `backend-api` replica.

## Known limits of this package

- No push notifications: agents and dashboards poll the API (the UI polls every 5 s
  while a Run is active, 30 s idle).
- The backend image is large (~1.1 GB compressed): it carries Python, Node, three
  harness CLIs, and Chromium system libraries for in-worktree browser tests.
- The manual path still works: `cp .env.example .env`, fill in the REQUIRED section,
  `docker compose pull && docker compose up -d --wait`. The contract file is the reference;
  `install.sh` is that procedure with the secrets generated for you.
