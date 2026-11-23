# Developing ai-orchestrator

How to run the orchestrator from a source checkout, build its images, keep the gates green
and publish a version. Operators who only run a released instance want `INSTALL.md`; the
rules an agent must not bend are `AGENTS.md`; the deploy folder's reference is
`deploy/README.md`.

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

## Boot a development machine

Every step is a no-op when it is already done.

### 1. Prerequisites

Install these yourself; `make install` checks for them and names the exact fix for each one
it finds missing, but deliberately installs none of them:

- **Docker** (Docker Desktop on macOS) — runs the stack
- **uv** — `brew install uv` (backend tooling and gates)
- **Node 24** with corepack — `nvm install 24` (web-client tooling; pnpm comes from corepack)
- **git**, with access to this repository and to the target repositories

### 2. Install and check

```bash
git clone https://github.com/rebecamurillo/ai-orchestrator && cd ai-orchestrator
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
| `ROOT_TEMPLATES` | optional — the workflow templates `/workflows/new` offers, comma-separated, in the order you write them. `.env.example` sets the four shipped roots, `staged-initiative-hub,staged-initiative-repo,repo-init,agent-smoke`; blank or unset offers every stored template a Run can start from (everything but the ones only another template calls). Name a template you authored in `templates/` here to make it startable; a name nothing stores is ignored. Read at start-up, so a change needs a restart |

```bash
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

In **gateway / full** mode you also need `LITELLM_API_KEY` (the harness key),
`LITELLM_SPEND_KEY` (backend only), and in full mode the `LANGFUSE_*` keys — step 5 mints
and writes all of them for you.

### 5. (Gateway / full mode only) start the host services

```bash
make platform-up          # generate deploy/llm-platform/.env, start LiteLLM + Langfuse, wait for health
make platform-env-sync    # mint the harness key and write the six values into the root .env
```

Two things `platform-up` cannot do for you, both in `deploy/llm-platform/.env`:

- **A real provider key** (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or a running oMLX). The
  proxy starts and answers `/health` without one, but every completion fails 401 — enough
  to bring the stack up, not enough to run a harness.
- Or use a **Claude subscription instead of an API key**: set
  `CLAUDE_SUBSCRIPTION_AUTH=true` in `.env` and follow `deploy/llm-platform/README.md` →
  "authenticate on a Claude subscription".

Details, key separation, and verification commands: `deploy/llm-platform/README.md`.

### 6. Start the app — pick a mode

There are two ways to launch, publishing the same ports — so run one at a time (each
refuses a port the other holds; `make down` switches back from mode A).

**Mode A — containers (recommended for demos and client machines):**

```bash
make up          # docker compose up -d --build: web-client, backend-api, postgres
```

Everything runs in compose, and the harness CLIs (claude, codex, opencode) ship inside the
backend image at the `*_VERSION` pins in `.env` (passed as build arguments). They run from
the `harness-bin` volume, and each start reconciles them against those pins: the image's own
copy when it is at the pin, else one `npm install` of the pin (registry needed then). Raise a
pin in `.env` and `docker compose up -d backend-api` (a recreate; `restart` keeps the old
environment) installs it, with no rebuild. A pin that cannot be installed refuses that
harness alone. `harness-bin` is not backed up. To re-seed it from the image, stop the stack
and `docker volume rm <project>_harness-bin` — both take the stack down, so only with the
Operator's go-ahead (hard rule 9).
The first run builds both images (minutes). The backend
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
`ANTHROPIC_API_KEY` as a Project env var in the UI. Mode B uses your own `claude` login — if
`claude` works in your terminal, the harness works.

Both ports are published on `127.0.0.1` only — one operator at one machine. Use the IP, not
`localhost` (which also resolves to `::1`, where nothing listens). Reaching the stack from
another host is a host-level decision (a tunnel), not a compose one.

```bash
make logs        # follow every service
make down        # stop the stack; pgdata, work and agent-home volumes survive
```

From here the operator flow is the same as for a released instance: `INSTALL.md` § 5
onwards (Project, Repository, clone check, `repo-init`, `agent-smoke`, the first-run demo).

## Build the images yourself

Releases publish the images; from a checkout you can build the same two on this machine —
to test a change before it is tagged, to publish a pre-release by hand, or to run the
deploy package without registry access.

```bash
make images                              # both images, native arch, compose's dev tags; starts nothing
PUSH=0 scripts/push-images.sh            # both images, native arch, tagged ghcr.io/…:<VERSION> — no registry
GHCR_TOKEN=ghp_… make push               # linux/amd64 + linux/arm64, pushed to GHCR as :<VERSION> and :sha-<commit>
GHCR_TOKEN=ghp_… make push TAG=1.0.0-rc.2   # one-off tag instead of VERSION's
```

`make push` needs a classic GitHub token with `write:packages` (`GITHUB_TOKEN` is the
fallback; `GITHUB_USER` names the login, otherwise it is resolved from the token). With no
token in the environment it expects a prior `docker login ghcr.io`. The token is read from
the environment only, never from an argument: argv is visible in `ps` and lands in shell
history. It reaches the docker daemon's credential store and nothing else — never a build
argument, never an image layer (hard rule 5). The foreign architecture builds under
emulation, which is slow for backend-api (three npm CLIs and Chromium's system libraries)
but finishes; `release.yml` is the same build with one native runner per architecture.

To run the deploy package from images built here instead of pulled:
`PUSH=0 scripts/push-images.sh`, then `docker run --rm ghcr.io/rebecamurillo/ai-orchestrator/backend-api:$(cat VERSION) kit bootstrap | tar x`
and `cd ai-orchestrator && ./install.sh --no-pull` — no GitHub token is asked for and nothing
is pulled. `make bundle TAG=<tag>` packs the same directory as a tarball for an offline client.

## Publish a new version

A release is a version bump merged on `main`, then a `v<VERSION>` tag; `release.yml` does the
building and pushing. `DEPLOY.md` §4 holds the reasons, this is the checklist.

1. **Bump, on a branch** (`chore/release-<version>`). The version lives in seven places, nine with the compose
   image tags; `make lint` (`scripts/check_version.py`) fails when the first five
   disagree, and the compose tags' agreement is a deployment test (`make test-deploy`):
   - `VERSION` — the number itself (`1.0.0-beta.3`, never a `v` prefix)
   - `backend-api/pyproject.toml`, `web-client/package.json`,
     `deploy/kit/.claude-plugin/plugin.json`, `deploy/kit/manifest.json`
   - `contracts/openapi.json` (`info.version`; `make openapi` regenerates it)
   - `backend-api/uv.lock` — the `orchestrator` package entry, in PEP 440 form
     (`1.0.0b3`); `cd backend-api && uv lock --check` proves it
   - the two `image:` tags in `deploy/docker-compose.yml`, set to `VERSION`
   - `deploy/release.env` — its pins reviewed
2. **Pull request, CI green, merge.** The merge commit on `main` gets its own `ci.yml` run;
   wait for it to succeed. `release.yml` refuses a tag on a commit with no successful
   `ci.yml` run for that exact SHA. Run `make test-deploy` locally before tagging (its
   workflow is on manual dispatch for now).
3. **Tag the merge commit and push the tag:**

   ```bash
   git switch main && git pull --ff-only
   git tag -a "v$(cat VERSION)" -m "v$(cat VERSION)" && git push origin "v$(cat VERSION)"
   gh run watch "$(gh run list -w release.yml -L1 --json databaseId -q '.[0].databaseId')"
   ```

   A build job that fails with `denied: permission_denied` means the workflow cannot write
   the GHCR packages (a package first created by a hand `make push` is not linked to the
   repository). Once per package, in GitHub → the package → Package settings → *Manage
   Actions access*, add `rebecamurillo/ai-orchestrator` with **Write**, then
   `gh run rerun <run-id> --failed` — the tag stays where it is.

4. **Check what landed.** `release.yml` pushes
   `ghcr.io/rebecamurillo/ai-orchestrator/{backend-api,web-client}:<VERSION>` (and
   `:sha-<commit>`, multi-arch, no `latest`) and creates the GitHub Release.
   `docker buildx imagetools inspect ghcr.io/rebecamurillo/ai-orchestrator/backend-api:<VERSION>`
   lists both platforms.
5. **Upgrade a host** — a separate act, never automatic. From the deploy package directory:
   read the cautions in `deploy/README.md` § Upgrading (a `DBOS_APPLICATION_VERSION` bump
   needs a drain; hand-patched compose services), then `./install.sh upgrade --tag <VERSION>`
   and `./install.sh doctor`.

`make push` (above) stays for a pre-release that goes out before there is a tag.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Every `POST /api/v1/projects` answers 500 | `ORCHESTRATOR_SECRET_KEY` is still the placeholder — mint a real Fernet key (step 4), restart |
| A gate is red on a fresh machine | Run `make doctor` first: missing uv/Node/pnpm reads as a test failure |
| `/login` or `/healthz` unreachable on `localhost` | Use `127.0.0.1` — nothing listens on `::1` |
| Harness readiness fails 401 on every model | The Gateway has no real upstream provider key in `deploy/llm-platform/.env` — see `deploy/llm-platform/README.md` |
| Claude Code fails with `Invalid model name … claude-opus-5` | Its own default model is not in the Gateway's `model_list`: bind a model on the Run, or add the name in `deploy/llm-platform/litellm.config.yaml` |
| `make e2e-ui` refuses: `127.0.0.1:4321 is already used` | It binds the same port `make up` publishes — `make down` first, or change `WEB_CLIENT_PORT` |
| Cost shows "provisional" | Gateway is disabled (`LITELLM_BASE_URL=` blank) — expected in bare mode |
| No trace link on Runs | Tracing is disabled (`LANGFUSE_BASE_URL=` blank) — expected outside full mode |
| Second clone / renamed checkout sees empty data | Compose project name changed — `make env` pins `COMPOSE_PROJECT_NAME=aio-dev` in `.env` |
| A story parks `misconfigured: no story file` | The target repository has no `_bmad/` at the instance's `bmad_version` — run `repo-init` on it and merge the PR |
| A harness is not `enabled` | `GET /api/v1/harnesses` names the `failing_check`; `cli not at pinned version` means backend-api was not recreated since the pin changed |

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

**MCP** is a route on backend-api (`api/mcp_mount.py`), behind the same bearer as every
other call; each tool calls the API's own REST operation in process
(`infrastructure/mcp/`). There is nothing MCP can do that the API cannot.

## Quality: TDD and the gates

The project is built test-first (AD-18): a story's tests exist and fail before its
implementation exists, and test files are protected — a revision must trace to a declared
behaviour change (the rules are `AGENTS.md` hard rule 1). Unit tests run with no Postgres
and no network, against shared in-memory fakes (one per port); e2e tests run in a
disposable compose stack (`aio-e2e`) with its own database, volumes and ports, so the
suite's leftovers never land in the stack you develop against. `make e2e-api` alone
attaches to whatever stack is configured and refuses any database whose name does not end
in `_e2e`. The gate commands and the enforced coverage numbers are in `README.md` §
Contributing; the summary:

- **Coverage.** `orchestrator.domain` and `orchestrator.application` hold 100 % branch
  coverage (`make test` fails under it); `web-client/src/lib/**` and `src/stores/**` hold
  90 % lines; changed lines must be 90 % covered (`make coverage`). Raise a number by
  writing a test — a lowered threshold, an excluded file, or a `pragma: no cover` is the
  failure the gate exists to catch.
- **Test pairs.** Every module under `backend-api/src/` and `web-client/src/` is named by a
  test module, or `make lint` fails with the path of the one that is not.
- **No test pins shipped template content** (step ids, ordering, counts, YAML text):
  shipped templates are exemplars that evolve freely; template behaviour is covered on
  fixture copies the test owns.

`make test-deploy` (`-unit`, `-stack`) is the deployment gate: it runs `deploy-tests/` — the
deploy folder, `install.sh`, the setup runner, the release files and throwaway stacks. Its
workflow (`.github/workflows/deploy.yml`) is on manual dispatch for now; run it locally
before a release. The unit lane needs bash ≥ 4 and GNU `stat` (on macOS, run it in a Linux
container).

## The BMAD method on a new machine

The repository commits the method itself (`_bmad/`, version **6.12.4**); the skill stubs
and your personal install answers are per machine and git-ignored. Once per machine:

```bash
npx --yes bmad-method@6.12.4 install --directory . --modules bmm --tools claude-code,codex --yes --user-name OptimAI-team
git status                                   # must be clean
ls .claude/skills | grep -c '^bmad-'         # 49 skills
```

Pin the version exactly — a different one rewrites installer-managed files and shows up as
a diff. Team overrides: `_bmad/custom/config.toml` (committed); personal:
`_bmad/custom/config.user.toml` (ignored). Then open Claude Code here and type
`/bmad-help`.

## More

- **Production deploys** (GHCR images, upgrades, rollback, drain): `DEPLOY.md`
- **The deploy folder** (every file's role, every `install.sh` verb, refusals, migration):
  `deploy/README.md`
- **Host stack in depth** (LiteLLM keys, Langfuse, oMLX, egress, backups): `deploy/llm-platform/README.md`
- **Workflow templates** (the single-file format, three working examples): `templates/README.md`
- **The served guide** (what a connected agent reads): `guide/`, served at `/llms.txt` and `/guide/{id}.md`
- **Project brain template** (the planning-hub template repo for client products):
  [OptimAI-labs/project-brain-template](https://github.com/OptimAI-labs/project-brain-template),
  source under `templates/project-brain/`
- **Architecture spine**: `_bmad-output/architecture/ARCHITECTURE-SPINE.md` (`AD-1..AD-20`);
  the design baseline and pending specs are indexed by `_bmad-output/README.md`
