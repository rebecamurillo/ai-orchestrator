# Running ai-orchestrator from the release bundle

This directory is the consumer package: everything a machine needs to run a released
ai-orchestrator without cloning the repository. The stack is three containers — the web
UI, the API, and PostgreSQL — pulling the images a release publishes to GHCR
(`ghcr.io/optimai-labs/ai-orchestrator/{backend-api,web-client}`, `linux/amd64` and
`linux/arm64`).

If you are developing the orchestrator itself, this is not your file: use the repository
root's `README.md` (`make up` / `make local`). If you are deploying the operator's own
host from a checkout, that procedure is `DEPLOY.md`.

## Prerequisites

- Docker Engine with Compose v2.
- A GitHub token the orchestrator will use to clone and push target repositories
  (`GITHUB_TOKEN` below). Every repository you register must be reachable by this one
  token — there are no per-repository credentials.
- Optional: a LiteLLM gateway and a Langfuse server. Each is one variable in `.env`:
  blank disables the integration, and so does leaving the line out — both default to
  blank. The full stack for both ships in the bundle's `host/` directory (see below).
  Without a gateway, each harness uses its own authentication and spend tracking is
  provisional.

## Start

`.env.example` is in two sections. **REQUIRED** is what the stack refuses to start
without; everything under **OPTIONAL** has a code default equal to the value the file
prints, so those lines may be deleted or left blank and the stack still comes up
(Operator decision 2026-09-20, two-tier configuration contract; reaffirmed 2026-09-30).

The minimal `.env` is seven lines:

```dotenv
IMAGE_TAG=v0.1.0
ORCHESTRATOR_TOKEN=…            # long random; the web login and the API bearer
ORCHESTRATOR_SESSION_SECRET=…   # 32 random bytes
ORCHESTRATOR_SECRET_KEY=…       # a real Fernet key; the placeholder is not one, and until
                                # you replace it every project write answers 500:
                                # python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
POSTGRES_PASSWORD=…
DATABASE_URL=postgresql+psycopg://orchestrator:<that same password>@postgres:5432/orchestrator
GITHUB_TOKEN=…                  # the git credential described above
```

Or start from the full reference and edit it, which is the easier thing to read:

```bash
cp .env.example .env
# fill in the REQUIRED section; the OPTIONAL one already holds every default
docker compose pull
docker compose up -d --wait
```

**A minimal `.env` only works from the release that shipped the two-tier contract.** An
older `IMAGE_TAG` runs an image whose settings module requires every variable, so a
seven-line file makes it refuse to start, naming the first field it misses. Pin the tag
first, then trim the file — never the other way round.

Verify:

```bash
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" http://127.0.0.1:8000/api/v1/ping
```

Open `http://127.0.0.1:4321`, log in with `ORCHESTRATOR_TOKEN`, and follow the operator
flow: create a Project, register a Repository, run its clone check, run `repo-init` if
the target repository is new to BMAD, then start a Run from `/workflows/new` with a
budget.

## Agents in your projects

The repository ships a Claude Code plugin that teaches a project's agents to drive this
API — create projects, launch runs, poll progress, answer checkpoints. In a consumer
project:

```
/plugin marketplace add OptimAI-labs/ai-orchestrator
/plugin install orchestrator@optimai
```

The bundle also carries the same skill at `../plugin/skills/orchestrator/`;
`../plugin/install.sh /path/to/project` copies it into a project's `.claude/skills/`,
adds the two variables to its `.env`, and pings the API to prove the pair works. The
skill's `references/spec-folder.md` documents the `epics.yaml` / `stories.yaml` /
`SPEC.md` format the `epic` and `initiative-hub` templates read. Either way, the project needs two values in its environment:
`ORCHESTRATOR_BASE_URL` (default `http://127.0.0.1:8000`) and `ORCHESTRATOR_TOKEN`.

## The optional host stack (LiteLLM + Langfuse)

The bundle's `../host/` directory is the gateway and tracing stack: LiteLLM, Langfuse,
and their stores (PostgreSQL, ClickHouse, Redis, MinIO), as its own compose project so it
survives this stack's restarts.

```bash
cd ../host
./generate-env.sh          # writes host/.env with random credentials
docker compose up -d --wait
./sync-env.sh ../deploy/.env   # mints the harness virtual key, writes the six values back
cd ../deploy && docker compose up -d --wait
```

`host/README.md` documents the key separation (`LITELLM_API_KEY` is a model-routes-only
virtual key; `LITELLM_SPEND_KEY` reads spend and never reaches a harness), model routes,
and `CLAUDE_SUBSCRIPTION_AUTH`. Pointing at your own existing LiteLLM/Langfuse instead
works the same way: set the `*_BASE_URL` and key variables in `.env`.

Every model named in `READINESS_MODELS` must exist in the gateway's `model_list`, or
backend-api refuses to start.

## Exposure

Every published port binds `BIND_ADDRESS`, default `127.0.0.1` — the stack is reachable
only from its own machine. Setting `BIND_ADDRESS=0.0.0.0` publishes the web UI and the
API on every interface. Before doing that, know what it means: one bearer token is the
entire authentication, the API dispatches coding agents with write access to your
repositories, and nothing rate-limits login attempts. On any network you do not fully
trust, keep loopback and put a reverse proxy with TLS (or an SSH tunnel / VPN) in front.
PostgreSQL publishes no port in any case; reach it with
`docker compose exec postgres psql -U orchestrator orchestrator`.

## Trust

The backend container runs harness CLIs as the user `agent` with passwordless sudo, and
without `cap_drop` — deliberately, so an agent can `apt-get install` what a target
repository's install script needs. A Run executes code from the repositories you
register. Register only repositories you trust as much as this machine.

## Upgrading

```bash
# read the release notes first — see the two cautions below
sed -i '' 's/^IMAGE_TAG=.*/IMAGE_TAG=v0.2.0/' .env
docker compose pull && docker compose up -d --wait
```

- **`DBOS_APPLICATION_VERSION`** is pinned in `.env` and versions the engine's durable
  step sequence. A release whose notes say to bump it makes every in-flight Run
  unrecoverable under the old value — drain or cancel Runs first (a parked `needs_you`
  Run holds its slot for up to `HUMAN_WAIT_SECONDS`, 30 days by default, and does not
  time out on its own). Never bump it as routine.
- **Migrations run forward only.** Rolling `IMAGE_TAG` back across a release that
  migrated the schema is expected to fail closed. Take a database backup before
  upgrading: `docker compose exec postgres pg_dump -U orchestrator -Fc orchestrator > backup.dump`.
- **Harness CLI versions are baked into the image.** The `*_VERSION` variables in `.env`
  exist for the runtime probe check; changing one without pulling an image built with it
  makes every probe fail `cli not at pinned version`.
- **A trimmed `.env` is not backward-compatible.** Rolling `IMAGE_TAG` back across the
  release that shipped the two-tier contract, with a `.env` that has been cut down to the
  REQUIRED section, makes the older image refuse to start on the first variable it no
  longer finds. Keep the full file until the rollback window has closed.
- `POSTGRES_DB` is fixed after first boot, and the stack supports exactly one
  `backend-api` replica.

## Known limits of this package

- No push notifications: agents and dashboards poll the API (the UI polls every 5 s
  while a Run is active, 30 s idle).
- The backend image is large (~1.1 GB compressed): it carries Python, Node, three
  harness CLIs, and Chromium system libraries for in-worktree browser tests.
