# ai-orchestrator

An orchestrator that runs BMAD dev-loop workflows against other repositories: a Run is planned up front, executed durably, dispatches stories to a coding-agent harness (Claude Code, Codex, OpenCode), verifies with the target repository's own commands, and stops for the operator only at declared checkpoints or when an agent is blocked.

The product is specified, not yet built. Everything that decides what gets built lives under `_bmad-output/planning-artifacts/mvp/`:

| Document | Path |
| --- | --- |
| PRD (build contract, FR-1..FR-33) | `mvp/prd.md` + `mvp/addendum.md` |
| Architecture spine (binding, AD-1..AD-20) | `mvp/architecture/ARCHITECTURE-SPINE.md` |
| Epics and stories (8 epics, 66 stories) | `mvp/epics/epics.md`, `mvp/epics/epics.yaml`, one folder per epic |
| UX experience and visual system | `ux-designs/ux-v1-dev-loop-2026-08-26/`, `ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md` |

## Running it

Configuration is the environment (AD-20): `.env.example` is the contract, `make lint` fails when a
setting exists in one place and not the other. Copy it once, fill it in, and never commit the result.

```bash
make env                    # write .env (and .env.e2e), then fill in the tokens and keys
make up                     # build the images and start web-client, backend-api, postgres
```

`make env` is `cp .env.example .env` plus the one line that is not an application setting:
`COMPOSE_PROJECT_NAME=aio-dev`, which names this stack's containers and volumes. There are two
local environments and they share nothing — `aio-dev` is the one you develop in, `aio-e2e` is
the one `make e2e` builds and destroys around the gate. Without the name compose falls back to
the checkout's directory name, so a second clone would silently be a third project with empty
volumes.

One of those values is not a placeholder you can leave alone. `ORCHESTRATOR_SECRET_KEY` must be
a real Fernet key — `change-me-fernet-key` is not one, and `cryptography` refuses it with
`Fernet key must be 32 url-safe base64-encoded bytes`. The backend builds a Fernet per request,
so with the committed value the stack starts, `/healthz` answers, and every write to
`/api/v1/projects` answers 500 with the reason only in `docker compose logs backend-api`. Mint
one before you use the Projects API (`.env.e2e` gets one of its own, generated):

```bash
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

`make up` is `docker compose up -d --build`. The first run builds both images, which takes
minutes: the backend image installs Node 24, the three harness CLIs at their pinned versions,
and the BMAD skill stubs. When it returns, `docker compose ps` shows three services and every
one of them reaches `healthy` — the backend after `alembic upgrade head`, the web-client after
`/login` answers.

```bash
curl -fs http://127.0.0.1:8000/healthz     # {"status":"ok", …}
open http://127.0.0.1:4321/login           # the token from .env logs in
```

Both ports are published on `127.0.0.1` only, like the database: one operator at one machine.
Reaching the stack from another host is a host-level decision (a tunnel), not a compose one.
The addresses are written as `127.0.0.1` rather than `localhost` for the same reason
`astro.config.mjs` pins it: `localhost` also resolves to `::1`, which nothing here listens on.

The model gateway (LiteLLM), the tracing server (Langfuse) and the model server run on the host
rather than in compose, and `backend-api` reaches them through `host.docker.internal`. Setting
them up — the two Gateway keys, the `langfuse_otel` callback, the egress allowlist and the
nightly `pg_dump` — is `host/README.md`, with `host/litellm.config.yaml` as the starting config.

```bash
make logs                                # follow every service
make down                                # stop the stack; pgdata, work and agent-home survive
docker compose down -v                   # the deliberate act that also deletes them
```

Inside the backend container everything an agent needs is already there, as the non-root user
`agent`:

```bash
docker compose exec backend-api sh -c 'id -un; claude --version; codex --version; opencode --version'
docker compose exec backend-api scripts/harness/claude.sh doctor   # version · skills · gateway
```

### Running backend-api from a shell instead

`DATABASE_URL` in the contract names the compose service (`@postgres:5432`), because that is
what the containers use. It does not resolve from a shell on this machine, so a host run
overrides it — without that line the process dies in the migration step:

```bash
set -a; . ./.env; set +a                       # the contract both components read
docker compose up -d postgres                  # postgres:18, published on 127.0.0.1:5432

export DATABASE_URL="postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:5432/$POSTGRES_DB"
uv run --locked --directory backend-api python -m orchestrator.main
```

The process logs one `migrations applied` line carrying the Alembic revision and then binds —
it never serves a half-migrated schema. Check the schema with:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'select * from alembic_version'
```

The gates that decide whether work is done. Every one of them runs; a target whose tooling a
later story still brings would exit non-zero with `not available until story <id>` rather than
pass silently, and none is in that state:

```bash
make lint        # ruff · mypy · import-linter · env-contract · eslint · prettier · tsc · astro check
make test        # backend unit tests (pytest) + web-client unit tests (vitest)
make e2e-api     # httpx scenarios + schemathesis against the stack   (story 1.2)
make openapi     # export contracts/openapi.json, regenerate types    (story 1.3)
make e2e-ui      # playwright against the built web-client            (story 1.3)
make durability  # kill the backend mid-Run, restart it, count what is left (story 4.17)
make up / down   # docker compose: web-client, backend-api, postgres  (story 1.6)
```

`make e2e` is the whole gate, and the target to type:

```bash
make e2e        # build the aio-e2e stack, run the suite in it, destroy it — dev stack untouched
```

The suite writes and cleans up nothing. `tests/e2e/test_projects.py` says so in its own
docstring — there is no `DELETE` in the API yet, so it makes its names unique per run instead —
`test_schemathesis.py` drives every published operation with generated input while
authenticated, and `test_clone_check.py` leaves bare fixture repositories and base clones under
`WORK_DIR`. That is right for a suite that has to pass twice against the same stack, and ruinous
against the stack you develop in: a few runs and the Projects list is mostly generated noise.

So the gate gets a stack of its own. `make e2e` brings up compose project `aio-e2e` from
`docker-compose.yml` plus `docker-compose.e2e.yml`, with its own database (`orchestrator_e2e`),
its own `pgdata`, `work` and `agent-home` volumes, its own ports (`55432`, `8020`, `4341`) so it
runs beside `make up` rather than instead of it, and `down -v` in a trap so a failed run cleans
up as thoroughly as a green one. `.env.e2e` is generated on first use and holds no real
credential: the git and gateway values are the committed placeholders, exactly as CI runs them.

`make e2e-api` is the gate itself — what CI invokes, and what `make e2e` invokes once the stack
is up. Run directly it attaches to whatever `DATABASE_URL` names, so
`scripts/check_e2e_target.sh` refuses any database whose name does not end in `_e2e`, before
pytest opens a connection. To point it at a stack you keep anyway, say so:

```bash
set -a; . ./.env; set +a
export DATABASE_URL="${DATABASE_URL/@postgres:/@127.0.0.1:}" BACKEND_API_URL=http://127.0.0.1:8000
E2E_ALLOW_SHARED_STACK=1 make e2e-api                   # and keep what it leaves behind
```

### The web-client half

`make lint`, `make test`, `make openapi` and `make e2e-ui` all run web-client tooling, so they
need Node 24 and pnpm 11.25.0 (pnpm comes from corepack; the first call downloads it). Two
one-time steps per machine:

```bash
pnpm --dir web-client install --frozen-lockfile
pnpm --dir web-client exec playwright install chromium     # ~95 MB, for make e2e-ui only
```

`make openapi` needs neither `.env` nor the database: it builds the application with dummy
settings, writes `contracts/openapi.json`, and regenerates `web-client/src/api/schema.d.ts`
from it. Both files are committed, and `make lint` fails when either is out of date — the
TypeScript types for an API payload are generated, never written by hand (AD-3).

`make e2e-ui` builds web-client and runs Playwright against the built server on
`127.0.0.1:4321`, with a stub backend-api on `127.0.0.1:8788`. It needs no database and no
running backend; `E2E_BACKEND=real` points the same specs at a real one instead.

That is the same address `make up` publishes the web-client on, so the two cannot run at
once: with the stack up, Playwright refuses with `127.0.0.1:4321 is already used`. Run
`make down` first, or give the container a different `WEB_CLIENT_PORT` in `.env`.

## Contributing

The five gates decide whether work is done, and they run in one order — `lint`, then `test`,
then `e2e-api`, then `e2e-ui`, then `images`. A failing gate stops the ones after it, locally
and in CI:

```bash
make lint        # ruff · mypy · import-linter · env contract · test pairs · contract drift · eslint · prettier · tsc · astro check
make test        # backend unit tests + web-client unit tests, both with coverage
make coverage    # changed lines >= 90 %, against the branch this work forks from
make e2e         # the e2e-api gate in a stack of its own, created and destroyed around it
make e2e-api     # httpx scenarios + schemathesis against a running stack
make e2e-ui      # playwright against the built web-client and a stubbed backend
make durability  # the restart-and-orphan proof: kill the backend mid-Run and count what is left
make openapi     # re-export the contract; CI then fails on any diff (AD-3)
make images      # build both container images without starting anything
```

`.github/workflows/ci.yml` runs those same targets as five jobs chained by `needs:`, one run
per ref. The lint job also re-exports the contract and refuses any diff, so a hand-edited
`contracts/openapi.json` fails there rather than reaching the browser as a type that lies. It calls no command the Makefile does not hold, and it carries no credential: the
e2e job copies `.env.example` to `.env` and runs on the committed placeholders, with two
exceptions it writes itself — `ORCHESTRATOR_SECRET_KEY`, because the committed placeholder is
not a valid Fernet key and every write would answer 500 without it, and `POSTGRES_DB`, which it
names `orchestrator_e2e` so the same guard that protects a developer's stack also passes there.
The key is generated on the runner, read from no repository secret, and dies with the job.

`make e2e-api` is the one gate that needs more than the Makefile gives it: it constructs
`Settings` in the test process, so the *whole* contract must be exported, and `DATABASE_URL`
must name an address this machine can reach rather than the compose hostname `postgres`. `make
e2e` does all of that around it, against a stack built for the purpose:

```bash
make e2e
```

Two rules are enforced rather than asked for:

- **Coverage.** `orchestrator.domain` and `orchestrator.application` are at 100 % branch
  coverage — `make test` re-reports over those two packages with `--fail-under=100` after the
  suite runs — and `web-client/src/lib/**` and `src/stores/**` at 90 % lines. Changed lines
  must be 90 % covered (`make coverage`). Raise a number by writing a test; a threshold that
  is lowered, a file that is excluded, or a `pragma: no cover` added to reach it is the
  failure the gate exists to catch.
- **Test pairs.** Every module under `backend-api/src/` is imported by a module under
  `tests/unit/`, and every module under `web-client/src/` is named by one, or `make lint`
  fails with the path of the module that is not. `__init__.py`, `main.py`, generated and
  ambient declarations, and `.astro` page routes are exempt — everything else has a test
  module of its own.

`make durability` is the proof that "a Run survives a restart" is measured rather than
promised (FR-12, SM-4). It builds the same disposable stack `make e2e` builds and then, inside
it, starts a Run, `docker compose kill`s `backend-api` in the middle of a step, brings the
container back and reads what the database and the container's process table say: the row that
was running gets a second Attempt and the one that had already finished does not, the Run reaches
`done`, and exactly one process group for that Run exists afterwards. A second scenario kills the
backend while a Run waits on a `checkpoint` row and then continues it. Both print the Run's
attempt table.

It is a target of its own rather than part of `make e2e-api` because it needs a backend it may
kill and restart, which means a container. `make e2e-api` attaches to whatever stack is
configured — in CI that is a backend-api process started from source on the runner — so the
`durability` marker is deselected there and CI runs `make durability` as its own step of the
`e2e-api` job instead, against a compose stack of its own:

```bash
make durability   # builds and destroys its own stack; the two scenarios take ~75 seconds
```

`make images` is last because it is the slowest and the only one that needs a Docker
daemon. It is also the only gate that proves a Dockerfile still builds: every gate before it
runs from source, so without it `backend-api/Dockerfile` or `web-client/Dockerfile` could
break and no pipeline would notice until someone ran `make up`.

Before opening a change: `make lint && make test && make coverage`, then `make e2e` and
`make e2e-ui`. `make e2e` runs beside `make up` — it publishes its own ports. `make e2e-ui`
still does not: it binds `127.0.0.1:4321`, which is where `make up` publishes the web-client,
so run `make down` first or give the dev container a different `WEB_CLIENT_PORT`.

## Setting up the BMAD method on a new machine

The repository commits the method itself (`_bmad/`: config, scripts, manifests, modules) so every clone carries the same version, **6.11.0**. Two things are per machine and git-ignored: the skill stubs Claude Code loads (`.claude/skills/bmad-*`, `.agents/skills/bmad-*`) and your personal install answers (`_bmad/config.user.toml`). Reinstall them once per machine with the steps below.

### 1. Prerequisites

- **git** with access to this repository.
- **Node.js 22 or newer** (the installer runs through `npx`). With nvm: `nvm install 22 && nvm use 22`.
- **uv** (the BMAD scripts run with `uv run`): `brew install uv` on macOS, or see https://docs.astral.sh/uv/.
- **Claude Code** CLI, logged in: https://docs.anthropic.com/en/docs/claude-code — `npm install -g @anthropic-ai/claude-code`, then `claude` and `/login` once.

### 2. Clone and install the skill stubs

```bash
git clone <this repository> ai-orchestrator
cd ai-orchestrator
npx --yes bmad-method@6.11.0 install --directory . --modules bmm --tools claude-code,codex --yes --user-name OptimAI-team
```

The installer writes the skill stubs into `.claude/skills/` (read by Claude Code) and `.agents/skills/` (read by Codex and OpenCode), and regenerates `_bmad/config.user.toml` with your answers. Pin the version exactly: a different `bmad-method` version rewrites the installer-managed files under `_bmad/` and shows up as a diff.

### 3. Check

```bash
git status                                   # must be clean: the committed _bmad/ files match 6.11.0
ls .claude/skills | grep -c '^bmad-'         # 49 skills
uv run _bmad/scripts/resolve_config.py --project-root .   # prints the merged config as JSON
```

Then open Claude Code in the repository and type `/bmad-help`. It reads the planning artifacts and tells you where the project stands and which skill comes next.

### Notes

- Team-wide overrides go in `_bmad/custom/config.toml` (committed). Personal ones go in `_bmad/custom/config.user.toml` (ignored). Never edit `_bmad/config.toml` or `_bmad/config.user.toml` by hand: the installer regenerates them.
- To change an install answer (name, language), re-run the same `install` command with the new flags; prior answers are the defaults.
- Copies of the skills under `~/.claude/skills/` are optional. This repository relies on the project-level ones in `.claude/skills/`.

## Where the work stands

Epics and stories are complete (`mvp/epics/`). Next: `bmad-sprint-planning` to generate the tracking file, then build Epic 1 (repository foundation and quality gates) with `bmad-build`; Epics 2 to 8 are written for unattended `bmad-build-auto` dispatch, one brief per story.
