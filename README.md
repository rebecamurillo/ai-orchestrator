# ai-orchestrator

An orchestrator that runs BMAD dev-loop workflows against other repositories: a Run is
planned up front, executed durably, dispatches stories to a coding-agent harness (Claude
Code, Codex, OpenCode), verifies with the target repository's own commands, and stops for
the operator only at declared checkpoints or when an agent is blocked.

**Who reads what:**

| Document | Audience | Holds |
| --- | --- | --- |
| `README.md` (this file) | humans | boot a machine, start the stack, run an orchestration, keep the gates green |
| `AGENTS.md` | AI agents | the hard rules, the architecture, the gates |
| `DEPLOY.md` | the operator of the production machine | GHCR images, upgrades, rollback, the drain rule, running without the host services |
| `host/README.md` | whoever sets up LiteLLM / Langfuse / the model server | the optional host stack, its keys, its pitfalls |
| `_bmad-output/` | agents and the operator | BMAD output: the binding architecture spine (`AD-n`), the design baseline, pending specs — `_bmad-output/README.md` is the index |

## The system at a glance

Three containers in one compose stack, plus optional services on the host:

```
 browser ── 127.0.0.1:4321 ──► web-client (Astro SSR + React islands)
                                   │  Bearer ORCHESTRATOR_TOKEN, server side only
                                   ▼
                               backend-api (FastAPI + DBOS durable engine)
                                   │            │              │
                                   ▼            ▼              ▼
                               postgres:18   harness CLIs   git / target repos
                               (schemas:     (claude, codex,  (worktrees under
                                public+dbos)  opencode, in     the `work` volume)
                                              the image)
                                   │
              optional, on the host, reached via host.docker.internal:
                LiteLLM gateway :4000 ── model providers / local oMLX
                Langfuse tracing :3000
```

- **web-client** talks only to backend-api, server side, with the bearer token. The browser
  never holds a credential.
- **backend-api** owns everything else: the database, the durable workflow engine (DBOS),
  git worktrees, and the harness CLIs that are pre-installed in its image at pinned versions.
- **LiteLLM** (model gateway: metered spend, local models) and **Langfuse** (tracing) are
  optional. Each is one variable in `.env`; blank disables it and the stack runs without it.

## Boot a new machine (per-client setup)

Every client machine follows the same steps. Nothing here needs to be done twice — every
step is a no-op when it is already done.

### 1. Prerequisites

Install these yourself; `make install` checks for them and names the exact fix for each one
it finds missing, but deliberately installs none of them:

- **Docker** (Docker Desktop on macOS) — runs the stack
- **uv** — `brew install uv` (backend tooling and gates)
- **Node 24** with corepack — `nvm install 24` (web-client tooling; pnpm comes from corepack)
- **git**, with access to this repository and to the target repositories

### 2. Install and check

```bash
git clone <this repository> ai-orchestrator && cd ai-orchestrator
make install     # backend .venv from uv.lock, web-client from pnpm-lock.yaml, .env files
make doctor      # report only: what is missing and the command that fixes it
```

Run `make doctor` before blaming anything on the code: `uv: command not found` and
`Cannot find module 'astro'` are setup failures wearing a test failure's clothes.

### 3. Choose your environment mode

Decide up front which services this machine runs. Both switches live in `.env`; **blank
disables** the service, and so does deleting the line — both base URLs default to blank.

| Mode | `LITELLM_BASE_URL` | `LANGFUSE_BASE_URL` | You get |
| --- | --- | --- | --- |
| **Bare** (simplest, fine for a demo) | *(blank)* | *(blank)* | Runs work; cost figures are provisional; no trace links; `local` models unavailable; the harness authenticates directly with the provider |
| **Gateway only** | `http://host.docker.internal:4000` | *(blank)* | Metered cost from LiteLLM, local models, budget enforcement on real numbers; no traces |
| **Full** | `http://host.docker.internal:4000` | `http://host.docker.internal:3000` | Everything above plus a Langfuse trace link on every Run |

The full runbook for what each switch changes is `DEPLOY.md` → "Running without the host
services".

### 4. Write the environment

```bash
make env         # writes .env (a copy of .env.example) and .env.e2e; never overwrites
```

`.env.example` is the contract: every setting of both components lives there, commented,
in two sections. **REQUIRED** is what the stack refuses to start without — six lines, and
a `.env` holding only those six boots:

```dotenv
ORCHESTRATOR_TOKEN=…            # a long random string
ORCHESTRATOR_SESSION_SECRET=…   # 32 random bytes
ORCHESTRATOR_SECRET_KEY=…       # a real Fernet key (mint it below)
POSTGRES_PASSWORD=…             # a random string
DATABASE_URL=postgresql+psycopg://orchestrator:<that same password>@postgres:5432/orchestrator
GITHUB_TOKEN=…                  # clones and pushes the target repositories
```

Everything under **OPTIONAL** has a code default equal to the value `.env.example` prints,
so those lines may be edited, left alone, deleted, or left blank — the app boots either
way (Operator decision 2026-09-20, two-tier configuration contract; reaffirmed
2026-09-30). `make env` still writes the whole file, which is the easier thing to read.

Open `.env` and set these — the rest can keep their defaults:

| Variable | Set it to |
| --- | --- |
| `ORCHESTRATOR_TOKEN` | a long random string — the one login for the web UI and the API |
| `ORCHESTRATOR_SESSION_SECRET` | 32 random bytes — signs the browser session cookie |
| `ORCHESTRATOR_SECRET_KEY` | a **real Fernet key** — mint it with the command below. The committed placeholder is not one, and with it every write to `/api/v1/projects` answers 500 |
| `POSTGRES_PASSWORD` | a random string — and the same password inside `DATABASE_URL` |
| `GITHUB_TOKEN` | a token that can clone the client's target repositories (read by git only; a harness never receives it) |
| `LITELLM_BASE_URL`, `LANGFUSE_BASE_URL` | per your mode from step 3 — blank or absent disables |
| `ROOT_TEMPLATES` | optional — the workflow templates `/workflows/new` offers, comma-separated, in the order you write them. `.env.example` sets the two shipped roots, `initiative-hub,repo-init`; blank or unset offers every stored template a Run can start from (everything but the ones only another template calls). Name a template you authored in `templates/` here to make it startable; a name nothing stores is ignored. Read at start-up, so a change needs a restart |

```bash
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

In **gateway / full** mode you also need `LITELLM_API_KEY` (the harness key),
`LITELLM_SPEND_KEY` (backend only), and in full mode the `LANGFUSE_*` keys — step 5 mints
and writes all of them for you.

### 5. (Gateway / full mode only) start the host services

```bash
make host-up          # generate host/.env, start LiteLLM + Langfuse, wait for health
make host-env-sync    # mint the harness key and write the six values into the root .env
```

Two things `host-up` cannot do for you, both in `host/.env`:

- **A real provider key** (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or a running oMLX). The
  proxy starts and answers `/health` without one, but every completion fails 401 — enough
  to bring the stack up, not enough to run a harness.
- Or use a **Claude subscription instead of an API key**: set
  `CLAUDE_SUBSCRIPTION_AUTH=true` in `.env` and follow `host/README.md` →
  "authenticate on a Claude subscription".

Details, key separation, and verification commands: `host/README.md`.

### 6. Start the app — pick a mode

There are two ways to launch, publishing the same ports — so run one at a time (each
refuses a port the other holds; `make down` switches back from mode A).

**Mode A — containers (recommended for demos and client machines):**

```bash
make up          # docker compose up -d --build: web-client, backend-api, postgres
```

Everything runs in compose, and the harness CLIs (claude, codex, opencode) ship inside the
backend image at pinned versions. The first run builds both images (minutes). The backend
runs its migrations before it binds — it never serves a half-migrated schema.

**Mode B — local processes (faster iteration while developing):**

```bash
make local          # postgres in compose; backend-api + web-client from source, one Ctrl-C stops both
make local-backend  # or each half in its own terminal…
make local-web      # …with its logs to itself
```

Postgres still runs in compose (it is the one piece with no local-install story); the
backend and web-client run from source on this machine. `scripts/local.sh` reads the same
`.env` and rewrites only the values that name the compose network — `@postgres:` becomes
`@127.0.0.1:`, `host.docker.internal` becomes `127.0.0.1`, and the container paths become
`.local/work`, your `$HOME` and `templates/` (override with `LOCAL_WORK_DIR` /
`LOCAL_AGENT_HOME`). Two consequences: Runs dispatch to the harness CLIs on **your PATH**
(install and log them in yourself — mode A ships them), and `AGENT_HOME=$HOME` means your
own `claude` login is what a Run uses.

### 7. Verify

```bash
docker compose ps                                    # three services, all `healthy`
curl -fs http://127.0.0.1:8000/healthz               # {"status":"ok", …}
open http://127.0.0.1:4321/login                     # ORCHESTRATOR_TOKEN logs in
docker compose exec backend-api scripts/harness/claude.sh doctor   # version · skills · gateway
```

In bare mode, authenticate the `claude` harness once. Mode A (stored in the `agent-home`
volume, survives `make down`): `docker compose exec -it backend-api claude login`, or set
`ANTHROPIC_API_KEY` as a Project env var in the UI (step "Create a Project" below). Mode B
uses your own `claude` login — if `claude` works in your terminal, the harness works.

Both ports are published on `127.0.0.1` only — one operator at one machine. Use the IP, not
`localhost` (which also resolves to `::1`, where nothing listens). Reaching the stack from
another host is a host-level decision (a tunnel), not a compose one.

```bash
make logs        # follow every service
make down        # stop the stack; pgdata, work and agent-home volumes survive
```

## Start your first orchestration

The whole flow happens in the web UI at `http://127.0.0.1:4321`. Everything the UI does is
also the API under `/api/v1` with `Authorization: Bearer $ORCHESTRATOR_TOKEN`.

1. **Log in** at `/login` with `ORCHESTRATOR_TOKEN`.
2. **Create a Project** (`/projects/new`): a name, free context text for the agents, and
   env vars (encrypted at rest, returned masked). The Project is the container — the repo
   comes next.
3. **Register a Repository** under the Project (`/projects/{id}/edit`): the target repo's
   URL, default branch, and its own commands — `install_command`, `unit_test_command`,
   `quality_gate_command`. Those commands are what the orchestrator verifies each story
   with; get them right.
4. **Run the clone check** (button on the same page): proves the URL and token resolve and
   reports the target's BMAD state.
5. **Initialise the repository** if the target has never run the BMAD method: the
   "Initialise repository" action runs the `repo-init` template — installs the method,
   generates the repo's `AGENTS.md`, and opens it all as a pull request.
6. **Start a Run** at `/workflows/new`: pick a template, the project, the repository, a
   base branch, a **budget in USD** (required — a Run cannot start without one), the
   harness and optionally a model, and the template's declared inputs. The page shows the
   pre-flight result and the planned step graph before you commit.

   | Template | Runs |
   | --- | --- |
   | `initiative-hub` | every epic of one initiative, in one Run, from a hub repository whose `repos/*` submodules are the member repositories |
   | `repo-init` | bootstrap the BMAD method into a repo, as a PR |

   Those two are what `/workflows/new` offers (`ROOT_TEMPLATES` in `.env`; blank offers
   every stored template a Run can start from). `templates/` also ships the hub flow's
   callees, `initiative-hub-epic` and `initiative-hub-story`, and the single-repository
   `epic` and `story`, which only the harness readiness diagnostic dispatches — none of
   those is on the menu. The mono-repo `initiative` and `story-run` workflows are retired
   to `templates/drafts/` (kept, not seeded — Operator decision 2026-09-30).

   The harness page section shows each harness's live probe; the deeper readiness
   diagnostic (`POST /harnesses/{name}/readiness`) runs a trivial story end to end and
   proves the plumbing before you spend a real budget on it.
7. **Watch it**: the Board (`/`) is the kanban of Runs; `/runs` shows the queue and step
   history; `/workflows/{id}` is the step-level detail, `?view=diagram` for the graph.
8. **Answer when it stops.** A Run parks as `needs_you` at a declared checkpoint, when an
   agent is blocked, when verify fails, when the budget or a timeout is hit, or when a
   protected path (SPEC, stories, AGENTS.md, existing tests) was touched. The Run detail
   names the reason and offers exactly the signals that apply: `answer`, `continue`,
   `retry`, `skip_story`, `skip_epic`, `budget_raise`, `cancel`, and the terminal signals.
   Nothing proceeds past a park without you.

Run statuses are `queued → running → needs_you / done / failed / cancelled`. A `done` story
with a green verify also writes one append-only trajectory row — exportable per Project as
JSONL from the Project page.

## Run it from another project

The orchestrator ships as a consumer package, so a machine that never clones this
repository can run it from the published images and a project's own agents can drive it
over HTTP:

- **Run the stack** — each release attaches `ai-orchestrator-deploy-<tag>.tar.gz`
  (`install.sh`, the compose pulling the private GHCR images, the env contract, and the
  optional `host/` stack). A client extracts it and runs `./install.sh` with a GitHub token
  that can read the packages; `make bundle TAG=<tag>` builds the same archive here. The
  procedure is `deploy/README.md`.
- **Let a project's agents use it** — install the Claude Code plugin in the consumer
  project: `/plugin marketplace add OptimAI-labs/ai-orchestrator`, then
  `/plugin install orchestrator@optimai`. The skill (`plugin/skills/orchestrator/`)
  teaches the full API protocol: project and repository setup, template discovery,
  preflight, run creation, polling, and signals. The project needs
  `ORCHESTRATOR_BASE_URL` and `ORCHESTRATOR_TOKEN` in its environment.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Every `POST /api/v1/projects` answers 500 | `ORCHESTRATOR_SECRET_KEY` is still the placeholder — mint a real Fernet key (step 4), restart |
| A gate is red on a fresh machine | Run `make doctor` first: missing uv/Node/pnpm reads as a test failure |
| `/login` or `/healthz` unreachable on `localhost` | Use `127.0.0.1` — nothing listens on `::1` |
| Harness readiness fails 401 on every model | The Gateway has no real upstream provider key in `host/.env` — see `host/README.md` |
| Claude Code fails with `Invalid model name … claude-opus-5` | Its own default model is not in the Gateway's `model_list`: bind a model on the Run, or add the name in `host/litellm.config.yaml` |
| `make e2e-ui` refuses: `127.0.0.1:4321 is already used` | It binds the same port `make up` publishes — `make down` first, or change `WEB_CLIENT_PORT` |
| Cost shows "provisional" | Gateway is disabled (`LITELLM_BASE_URL=` blank) — expected in bare mode |
| No trace link on Runs | Tracing is disabled (`LANGFUSE_BASE_URL=` blank) — expected outside full mode |
| Second clone / renamed checkout sees empty data | Compose project name changed — `make env` pins `COMPOSE_PROJECT_NAME=aio-dev` in `.env` |

## Architecture

**Infrastructure** is the diagram above: postgres 18 holds one database with two schemas —
`public` (the application's, migrated by Alembic) and `dbos` (owned by the durable engine).
**DBOS** is the job runner: every Run is a durable workflow whose steps survive a backend
restart — `make durability` kills the backend mid-Run and proves the Run still completes.
The queue is partitioned per Repository, capped globally by `MAX_ACTIVE_RUNS`. Harness CLIs
run inside the backend container as the non-root user `agent`, in git worktrees under the
`work` volume, with an env built from an explicit contract — never the backend's own env.

**Code** (backend-api) is layered — `domain ◄ application ◄ {api, infrastructure} ◄
main.py` — with the direction enforced by `import-linter` in `make lint`. The web-client is
Astro SSR with React islands; the browser talks only to a same-origin proxy, and every API
payload type is generated from `contracts/openapi.json` (`pnpm gen:api`), never written by
hand. The layer rules and per-component detail live in `AGENTS.md`,
`backend-api/AGENTS.md` and `web-client/AGENTS.md`; the binding architecture decisions
(`AD-1..AD-20`) in `_bmad-output/architecture/ARCHITECTURE-SPINE.md`.

## Quality: TDD and the gates

The project is built test-first (AD-18): a story's tests exist and fail before its
implementation exists, and test files are protected — a revision must trace to a declared
behaviour change (the rules are `AGENTS.md` hard rule 1). Unit tests run with no Postgres
and no network, against shared in-memory fakes (one per port); e2e tests run in a
disposable compose stack (`aio-e2e`) with its own database, volumes and ports, so the
suite's leftovers never land in the stack you develop against. `make e2e-api` alone
attaches to whatever stack is configured and refuses any database whose name does not end
in `_e2e`. The gate commands and the enforced coverage numbers are under "Contributing"
below.

## Contributing

The five gates decide whether work is done, and they run in one order — a failing gate
stops the ones after it, locally and in CI:

```bash
make lint        # static gates, both components
make test        # unit tests, both components
make coverage    # changed lines >= 90 %, against the branch this work forks from
make e2e         # the e2e-api gate (httpx scenarios + schemathesis) in its own stack
make e2e-api     # the gate itself, against a running stack
make e2e-ui      # playwright against the built web-client
make durability  # the restart-and-orphan proof
make openapi     # re-export contracts/openapi.json; CI fails on any diff (AD-3)
make images      # build both container images without starting anything
```

`.github/workflows/ci.yml` runs the same targets as five jobs chained by `needs:` — it
calls no command the Makefile does not hold and carries no credential (it runs on the
committed `.env.example` placeholders, generating only a Fernet key on the runner).

Two rules are enforced rather than asked for:

- **Coverage.** `orchestrator.domain` and `orchestrator.application` hold 100 % branch
  coverage (`make test` fails under it); `web-client/src/lib/**` and `src/stores/**` hold
  90 % lines; changed lines must be 90 % covered (`make coverage`). Raise a number by
  writing a test — a lowered threshold, an excluded file, or a `pragma: no cover` is the
  failure the gate exists to catch.
- **Test pairs.** Every module under `backend-api/src/` and `web-client/src/` is named by a
  test module, or `make lint` fails with the path of the one that is not.

Before opening a change: `make lint && make test && make coverage`, then `make e2e` and
`make e2e-ui` (the latter needs `make down` first — it binds the dev stack's port).

## The BMAD method on a new machine

The repository commits the method itself (`_bmad/`, version **6.11.0**); the skill stubs
and your personal install answers are per machine and git-ignored. Once per machine:

```bash
npx --yes bmad-method@6.11.0 install --directory . --modules bmm --tools claude-code,codex --yes --user-name OptimAI-team
git status                                   # must be clean
ls .claude/skills | grep -c '^bmad-'         # 49 skills
```

Pin the version exactly — a different one rewrites installer-managed files and shows up as
a diff. Team overrides: `_bmad/custom/config.toml` (committed); personal:
`_bmad/custom/config.user.toml` (ignored). Then open Claude Code here and type
`/bmad-help`.

## More

- **Production deploys** (GHCR images, upgrades, rollback, drain): `DEPLOY.md`
- **Consumer package** (run a release without a checkout; agent-integration plugin):
  `deploy/README.md`, `plugin/`
- **Host stack in depth** (LiteLLM keys, Langfuse, oMLX, egress, backups): `host/README.md`
- **Project brain template** (the planning-hub template repo for client products):
  [OptimAI-labs/project-brain-template](https://github.com/OptimAI-labs/project-brain-template),
  source under `templates/project-brain/`
- **Architecture spine**: `_bmad-output/architecture/ARCHITECTURE-SPINE.md` (`AD-1..AD-20`);
  the design baseline and pending specs are indexed by `_bmad-output/README.md`
