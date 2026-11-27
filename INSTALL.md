# Install ai-orchestrator and connect it to a project

This is the operator's guide, start to finish: run an instance on one machine, register the
first repository, prove the pipeline with one trivial Run, then connect a project's own
coding agents to the instance over MCP or plain HTTP. Every command here is the one the
product ships; the deeper references are linked where they apply.

Three documents share the work. This file is the path. `deploy/README.md` is the reference
for the deploy folder (every file's role, every `install.sh` verb, upgrade refusals,
migration). `DEVELOPMENT.md` is for running the orchestrator from a source checkout.

| Step | What you end with | Time |
| --- | --- | --- |
| [1. Prerequisites](#1-prerequisites) | Docker, a GitHub token, 8 GB of RAM | 5 min |
| [2. Install the instance](#2-install-the-instance) | the web UI on `http://127.0.0.1:4321`, the API on `:8000` | 10 min, mostly image pulls |
| [3. Authenticate a harness](#3-authenticate-a-coding-agent-harness) | `claude` (or `codex`, `opencode`) can call its model from inside the container | 5 min |
| [4. Optional: the LLM gateway and tracing](#4-optional-the-llm-gateway-and-tracing) | real cost figures, budget enforcement, a trace per Run | 20 min |
| [5. Register a project and a repository](#5-register-a-project-and-a-repository) | a Project, a Repository with its own verify commands, a green clone check | 10 min |
| [6. Prove the pipeline](#6-prove-the-pipeline) | `agent-smoke` and the first-run demo at `done` | 15 min |
| [7. Connect a project's agents](#7-connect-a-projects-agents-mcp-and-http) | Claude Code / Codex / OpenCode in your project drive the instance | 5 min |
| [8. The hub pattern](#8-the-hub-pattern-a-planning-repository-with-submodules) | one planning repository whose submodules are the code repositories | — |
| [9. Day 2](#9-day-2) | doctor, logs, backup, upgrade, rollback, uninstall | — |
| [10. Exposure and trust](#10-exposure-and-trust) | what the one token can do, before you open a port | — |

## 1. Prerequisites

- **Docker** with Compose v2. Docker Desktop on macOS or Windows (WSL 2), or Docker Engine 26
  or later with the compose plugin on Linux. 8 GB of RAM for the stack; 16 GB with the
  optional LLM platform beside it.
- **A GitHub personal access token (classic)** with:
  - `read:packages` — the two images are private on GitHub Container Registry; your GitHub
    user needs read access to the packages (ask the person who gave you the link);
  - `repo` — when the same token is the credential the orchestrator uses to clone and push
    the repositories you register. This is the usual setup: there are no per-repository
    credentials, so every repository you register must be reachable by this one token.
- `curl`, `tar` and `openssl` (macOS and every mainstream Linux ship them).
- **An account with a model provider** for the coding agent you will dispatch: an Anthropic
  API key or a Claude subscription for `claude`; the equivalent for `codex` or `opencode`.
  Step 3 covers it.

The two published ports are `4321` (web UI) and `8000` (API), both bound to `127.0.0.1`.
If either is taken, the installer stops before starting anything and names the variable to
change (`WEB_CLIENT_PORT`, `BACKEND_API_PORT` in `.env`). Use `127.0.0.1` in the browser,
not `localhost`: nothing listens on `::1`.

## 2. Install the instance

### 2a. From the published images (recommended)

The deploy folder comes out of the image you are about to run, so it can never describe a
different version than the one it starts.

```bash
docker login ghcr.io -u <your-github-user>        # the token is the password
docker run --rm ghcr.io/rebecamurillo/ai-orchestrator/backend-api:1.0.0-beta.6 kit bootstrap | tar x
cd ai-orchestrator
./install.sh
```

`kit bootstrap` writes the folder `ai-orchestrator/`: `install.sh`, `docker-compose.yml`,
`release.env` (the release's pins), `.env.example` (the configuration contract), `README.md`
(the deploy reference), `product-files.json`, `kit/` (the bootstrap and MCP templates the
instance serves), `setup/`, `bmad/`, `templates/shipped/` and a `VERSION`.

`./install.sh` asks two things — the GitHub token, and optionally the gateway and tracing
values (blank keeps both off) — then logs Docker in, writes `.env` with generated secrets,
pulls the two images, starts the stack (web-client, backend-api, postgres), proves the API
answers and the token works, runs the setup phase (BMAD skills into the harness home), and
prints:

```
  Web UI     http://127.0.0.1:4321
  API        http://127.0.0.1:8000   (Authorization: Bearer <token>)
  Login      <ORCHESTRATOR_TOKEN>
```

That token is the one credential of the whole system: the web login and the API bearer. It
lives in `.env` (mode 600) next to `install.sh`. Open `http://127.0.0.1:4321/login` and
paste it.

Unattended, from a provisioning script:

```bash
GHCR_TOKEN=ghp_… ./install.sh --yes                    # no gateway, no tracing
GHCR_TOKEN=ghp_… ./install.sh --yes --no-bmad          # without the BMAD skills
```

Re-running `./install.sh` after a failure is safe: it creates only what is missing and
changes no byte of a file that exists (`.env`, `compose.override.yml`, `setup/bmad.choice`).
Delete a file deliberately to start over.

**What `.env` holds.** The REQUIRED section, generated for you: `ORCHESTRATOR_TOKEN`,
`ORCHESTRATOR_SESSION_SECRET`, `ORCHESTRATOR_SECRET_KEY` (a Fernet key: Project env vars are
encrypted at rest with it), `POSTGRES_PASSWORD` and `DATABASE_URL`, and `GITHUB_TOKEN` set to
the token you gave. Everything under OPTIONAL keeps its code default; the file explains each
line. The handful an operator changes:

| Variable | Why you would change it |
| --- | --- |
| `WEB_CLIENT_PORT`, `BACKEND_API_PORT` | 4321 or 8000 already taken |
| `BIND_ADDRESS` | `0.0.0.0` exposes the UI and API on every interface — read [§10](#10-exposure-and-trust) first |
| `MAX_ACTIVE_RUNS` | how many Runs the engine holds at once; a parked Run keeps its slot |
| `ROOT_TEMPLATES` | the templates `/workflows/new` offers; blank offers every stored root template |
| `READINESS_MODELS` | the default model per harness; with a gateway, every name must exist in its `model_list` |
| `WORKTREE_RETENTION_DAYS` | how long a finished Run's worktrees and logs survive |
| `HUMAN_WAIT_SECONDS` | how long a parked Run waits for you (30 days by default) |
| `CLAUDE_ALLOWED_TOOLS` | which tools a dispatched Claude Code may use; the shipped value allows `Bash` whole — the container is the sandbox and `git push` is denied by the adapter regardless |

A change to `.env` is applied by `./install.sh start`.

### 2b. Offline, or from a tarball

Ask for the release bundle (`ai-orchestrator-deploy-<tag>.tar.gz`, produced by `make bundle`
from a checkout), extract it, and run `./install.sh` inside. The two images move with
`docker save` / `docker load`; `./install.sh --no-pull` then pulls nothing.

### 2c. From a source checkout

For developing the orchestrator itself, or for building the images on this machine:
`DEVELOPMENT.md`. The running instance is the same stack; only how it is built differs.

### Verify

```bash
./install.sh doctor                     # one ok / warn / fail line per check; every fail ends with its fix
./install.sh status                     # docker compose ps for this stack
curl -fs http://127.0.0.1:8000/healthz  # {"status":"ok","version":"1.0.0-beta.6"}
```

`doctor` changes nothing and prints no secret, so its output is safe to paste into a bug
report. The checks: Docker and its version, `.env` and its mode, the release pins, the two
ports, `/healthz`, the token, each harness's readiness, the setup record, the BMAD version,
free disk, retention.

## 3. Authenticate a coding-agent harness

The three harness CLIs (`claude`, `codex`, `opencode`) ship inside the backend image at
pinned versions and run as the non-root user `agent`, in git worktrees under the `work`
volume, with an environment built from an explicit contract — never the backend's own
environment, never `GITHUB_TOKEN`. A harness still has to reach its model provider. Two
ways, per harness:

**An API key, as a Project environment variable.** Create the Project (step 5), open it,
and add `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, …) under its env
vars. Project env vars are encrypted at rest, returned masked, and reach the dispatched
agent and nothing else. This is the setup with no host login to maintain.

**A subscription login, stored in the `agent-home` volume.** For Claude Max/Pro:

```bash
./install.sh harness claude --subscription   # sets CLAUDE_SUBSCRIPTION_AUTH, runs `claude login` in the container
```

The login survives `./install.sh stop` and `start`; it needs a terminal (the command runs
`claude login` interactively). `--api-key` goes back the other way. With a subscription the
provider meters no dollars, so the cost columns in the UI read from the gateway if one is
configured (step 4), else "provisional".

**Prove it.** The Fleet section of the web UI, or `POST /api/v1/harnesses/{name}/readiness`,
runs a one-story fixture the instance ships through the harness end to end and reports the
first failing line. `GET /api/v1/harnesses` shows each harness's `enabled` flag and its
`failing_check`. A harness that is not `enabled` cannot be chosen for a Run — fix the
readiness before step 6, and do not try to prove a harness with a project Run.

## 4. Optional: the LLM gateway and tracing

The product ships no model gateway and no tracing; both are optional, and the stack runs
without them. What each one adds:

| Service | What it gives you | Without it |
| --- | --- | --- |
| **LiteLLM** (model gateway) | metered spend per Run, so the budget gate acts on real numbers; per-harness virtual keys; local or open models behind one endpoint; the `local` harness | each harness authenticates on its own; cost figures are "provisional"; no `local` harness |
| **Langfuse** (tracing) | one trace link per Run, every agent session and tool call inside it | no trace links |

A starter stack for both is in this repository at `deploy/llm-platform/` (its README has
the keys, the pitfalls and the oMLX local-model path). Run it as its own compose project —
from a checkout, `make platform-up` then `make platform-env-sync`. Any other LiteLLM or
Langfuse works the same way: point the instance at it with six values in `.env`, then
`./install.sh start`:

```dotenv
LITELLM_BASE_URL=http://host.docker.internal:4000
LITELLM_API_KEY=…        # a model-routes-only virtual key, the one a harness receives
LITELLM_SPEND_KEY=…      # admin-scoped, reads spend, read by backend-api only, never by a harness
LANGFUSE_BASE_URL=http://host.docker.internal:3000
LANGFUSE_PUBLIC_KEY=…
LANGFUSE_SECRET_KEY=…
```

Blank disables a service; so does deleting the line. Every model named in `READINESS_MODELS`
must exist in the gateway's `model_list`, or backend-api refuses to start. A Claude Code
whose default model is not in that list fails with `Invalid model name`: bind a model on the
Run, or add the name to the gateway's config.

## 5. Register a project and a repository

Everything below is in the web UI; everything the UI does is also the API under `/api/v1`
with `Authorization: Bearer $ORCHESTRATOR_TOKEN`, and the MCP tools of step 7
(`create_project`, `add_repository`, `check_clone`, `init_repository`).

1. **Log in** at `/login` with `ORCHESTRATOR_TOKEN`.
2. **Create a Project** (`/projects/new`): a name, free context text the agents read, and
   env vars (step 3). A Project is the container; it holds repositories and Runs.
3. **Register a Repository** under the Project (`/projects/{id}/edit`): the HTTPS clone URL
   (reachable by `GITHUB_TOKEN`), the default branch, and the repository's own commands:
   - `install_command` — what makes a fresh clone buildable (`pnpm install`, `uv sync`, …);
   - `unit_test_command` — the tests a story must keep green;
   - `quality_gate_command` — lint, typecheck, build, e2e: the gate a human PR would pass.
   The orchestrator runs these, verbatim, in the Run's worktree after every story; a story
   whose verify fails parks the Run. Get them right: run each one yourself in a clean clone
   first. `test_globs` lists test files to freeze (an agent that touches one parks the Run
   `protected_path`); an empty list freezes nothing.
4. **Run the clone check** (button on the same page, or `POST /api/v1/repositories/{id}/clone-check`):
   proves the URL and the token resolve and reports whether the repository holds the BMAD
   method.
5. **Initialise the repository** if it has never run BMAD: "Initialise repository" runs the
   `repo-init` template, which installs the method (`_bmad/`), generates the repository's
   `AGENTS.md`, and opens a pull request. Merge it. A dispatched agent reads its skills out of
   the repository's own `_bmad/`; without them every story parks `misconfigured`.

Field by field, with what to confirm before saving: the guide page `projects`
(`http://127.0.0.1:8000/guide/projects.md`).

## 6. Prove the pipeline

Two checks, in this order, before any real work.

**`agent-smoke`** — five minutes, one agent dispatch: the agent creates one file, the Run
verifies, commits and pushes it. At `/workflows/new` pick the template `agent-smoke`, the
Project, the Repository, a base branch, the harness, and a budget in USD (a Run cannot start
without one). The page shows the pre-flight and the planned step graph before you commit.
Run it on a new install, after a harness or template change, and before any real initiative.

**The first-run demo** — the smallest real story: an initiative folder with one spec folder
and one story (`create ORCHESTRATOR-DEMO.md containing hello`), committed on its own branch,
launched on `staged-initiative-repo` (plain repository) or `staged-initiative-hub` (a hub
with submodules), watched to `done`. It exercises the clone, the dispatch into the harness,
the agent's commit, the protected-path check, your registered verify commands, the push and
the compare link, with no product change in the way. The procedure and the spec-folder
format: guide pages `runs/first-run` and `spec-folder`.

When a demo Run parks, the park names the one piece of the setup that is not right. Fix
that, not the demo.

## 7. Connect a project's agents (MCP and HTTP)

A coding agent working inside one of your project repositories — Claude Code, Codex,
OpenCode — can drive the instance: register repositories, validate a spec folder, preflight
and create Runs, read a parked Run and answer it, read the instance's guide. It does so over
the Model Context Protocol, served by the instance at `$ORCHESTRATOR_BASE_URL/mcp`, or over
plain HTTP; the two are the same operations behind the same token.

### 7a. What the project needs

Two values in the agent's environment, never in a file the project commits:

```bash
export ORCHESTRATOR_BASE_URL=http://127.0.0.1:8000    # the API address
export ORCHESTRATOR_TOKEN=…                           # the instance's token, from its .env
```

A project `.env` is not read by the harness: export the token in the shell that starts the
agent, or set it in the harness's own environment.

### 7b. Run the bootstrap installer

From inside the project repository, with the two values exported:

```bash
curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
  "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness claude --base-url "$ORCHESTRATOR_BASE_URL"
```

The installer comes out of the instance that answered, so the bootstrap it writes always
matches the API it will call. Flags:

| Flag | Meaning |
| --- | --- |
| `--harness claude\|codex\|opencode\|all` | which agent CLI to configure (default `all`) |
| `--base-url URL` | the instance address (overrides `ORCHESTRATOR_BASE_URL`) |
| `--web-url URL` | the web UI address, so the agent can hand you `/workflows/{run_id}` links |
| `--token-var NAME` | the environment variable that holds the token, when it is not `ORCHESTRATOR_TOKEN` |
| `--project DIR` or `--home` | install into a project (default: the current directory) or into your home |
| `--token` | refused — the installer never takes a token value and never writes one |

It writes:

- a skill, `.claude/skills/orchestrator/SKILL.md` and/or `.agents/skills/orchestrator/SKILL.md`
  — the bootstrap: the instance address, the token variable's name, four rules, and the
  instruction to call `version` then `read_guide` first in every session;
- the MCP configuration of each harness (next section);
- `.orchestrator/bootstrap.json`, the record of what was installed;

then probes `GET /api/v1/version`. An existing `orchestrator` MCP entry is left as it is.
Restart the harness afterwards; `/mcp` in a Claude Code session and `codex mcp list` show
the server.

From a deploy folder or a checkout, `kit/install.sh --project <dir>` does the same with the
files beside it and downloads nothing — this is how the instance's own host agent gets its
skill (`kit/install.sh --project .` in the deploy folder).

### 7c. The MCP configuration per harness

The installer merges one block into the harness's own file and keeps every other server and
key. The base URL is written as a literal, the token as a reference to the variable, never as
a value.

**Claude Code** — `.mcp.json` in the project (`~/.claude.json` with `--home`):

```json
{
  "mcpServers": {
    "orchestrator": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": { "Authorization": "Bearer ${ORCHESTRATOR_TOKEN}" }
    }
  }
}
```

**Codex** — `${CODEX_HOME:-~/.codex}/config.toml`, per user:

```toml
[mcp_servers.orchestrator]
url = "http://127.0.0.1:8000/mcp"
bearer_token_env_var = "ORCHESTRATOR_TOKEN"
```

**OpenCode** — `opencode.json` in the project (when the project has `opencode.jsonc`, the
installer prints this block for you to add by hand):

```json
{
  "mcp": {
    "orchestrator": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp",
      "enabled": true,
      "headers": { "Authorization": "Bearer {env:ORCHESTRATOR_TOKEN}" }
    }
  }
}
```

Remote (streamable-HTTP) MCP support varies by CLI version; a build without it does not list
the server, and the guide over `/llms.txt` needs nothing. What each pinned CLI was observed
to support is the guide page `harness-support`.

### 7d. The MCP tools

Each tool is one REST operation of the published contract — nothing MCP can do that the API
cannot, and nothing it does differently.

| Group | Tools | REST equivalent |
| --- | --- | --- |
| Instance | `version`, `list_templates`, `get_template`, `list_projects`, `list_queue`, `list_models` | `GET /api/v1/version`, `/templates`, `/templates/{name}/{version}`, `/projects`, `/queue`, `/harnesses/{name}/models` |
| Guide | `read_guide` (no id: the index; a page id: that page) | `GET /llms.txt`, `GET /guide/{id}.md` |
| Setup | `create_project`, `update_project`, `add_repository`, `check_clone`, `init_repository` | `POST /projects`, `PUT /projects/{id}`, `POST /projects/{id}/repositories`, `POST /repositories/{id}/clone-check`, `POST /repositories/{id}/init` |
| Workflows | `validate_template`, `save_template`, `reload_templates`, `validate_spec_folder` | `POST /templates/{name}/validate`, `POST /templates/{name}/versions`, `POST /templates/reload`, `POST /spec-folders/validate` |
| Dispatch | `preflight_run`, `create_run`, `send_signal` | `POST /runs/preflight`, `POST /runs`, `POST /runs/{id}/signals` |
| Watch | `get_run`, `get_run_detail`, `wait_run_events` (long-poll) | `GET /runs/{id}`, `GET /runs/{id}/detail`, `GET /runs/{id}/events?wait=30` |
| Initiatives | `list_initiatives`, `get_initiative`, `create_initiative`, `cancel_initiative`, `start_next`, `get_session`, `post_session_message`, `retry_session`, `wait_initiative` (polls up to 120 s) | `GET /initiatives`, `GET /initiatives/{id}`, `POST /initiatives`, `POST /initiatives/{id}/cancel`, `POST /initiatives/{id}/start-next`, `GET /runs/{id}/session`, `POST /runs/{id}/session/messages`, `POST /runs/{id}/session/retry` |

A harness that supports MCP resources also lists each guide page as `guide://{id}`, and each
procedure page as a prompt named by its id with `/` replaced by `.` (`runs/launch` is
`runs.launch`). The exact request fields are the guide page `api` and
`contracts/openapi.json`.

### 7e. Without MCP: plain HTTP

Every call carries `Authorization: Bearer $ORCHESTRATOR_TOKEN`. `GET /healthz` needs no
token (liveness only). Errors are RFC 9457 `application/problem+json` — read `detail` and
`errors[]` before retrying anything. Lists are `{items, next_cursor}`; ids are UUIDs; money
is a decimal string in USD.

```bash
curl -fs -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" $ORCHESTRATOR_BASE_URL/api/v1/version
curl -fs $ORCHESTRATOR_BASE_URL/llms.txt                # the guide's index, open
curl -fs $ORCHESTRATOR_BASE_URL/guide/runs/launch.md    # one page
```

### 7f. What the agent does in every session

1. **Handshake**: `version` → `{app_version, bootstrap_contract, guide, bmad_version,
   harness_versions}`. A release difference between the project's bootstrap and the instance
   is reported, never a stop; re-running the installer moves the bootstrap to the newer
   contract.
2. **Read the guide**: `read_guide` with no id, then the pages the task needs — `projects`
   before saving a Project or Repository, `spec-folder` before authoring `epics.yaml`,
   `stories.yaml` or a `SPEC.md`, `workflows/customize` before editing a template,
   `runs/launch`, `runs/monitor` and `runs/parks` around a Run.
3. **The four rules of the bootstrap**: a Run's budget is the owner's decision, never
   invented or raised by the agent; preflight comes before every launch; a park is answered
   only with the signals the Run offers; a remote agent never maintains the installation
   (upgrades, `.env`, restarts and the gateway's model list are the host's, by hand or by the
   local agent in the deploy folder).

**The one-token risk.** There is one token, and every tool added over MCP widens what it can
do: an agent holding it can register repositories, start Runs that spend money and push
branches, and answer parks. This is accepted for the owner's own projects.

## 8. The hub pattern: a planning repository with submodules

The way the owner runs it, and what the `staged-initiative-hub` template is for: one
**hub** repository holds the planning (product context, decisions, one folder per
initiative with its `epics.yaml` and spec folders) and the code repositories as `repos/*`
git submodules. The hub is registered as the Repository; one Run builds every epic of an
initiative, each epic in the member its `workdir` names, on one branch name shared by the hub
and every member. The planning stays in one place, the code lands in each member behind its
own gate, and the agents read the hub's context files on every story.

A template for such a hub, with the two scripts that install and connect an instance, is
[OptimAI-labs/project-brain-template](https://github.com/OptimAI-labs/project-brain-template)
(source in `templates/project-brain/`): `scripts/orchestrator.sh install` bootstraps the
deploy folder next to the hub and runs its `install.sh`; `scripts/connect.sh` runs the
bootstrap installer of §7, pins BMAD to the instance's `bmad_version`, and links the hub's
personas and skills into the harness. The hub's `AGENTS.md` then routes every session: new
work starts at intake, an initiative goes through the planning chain (guide page
`initiatives/chain`), and the Run is launched when the gate passes.

A plain repository without submodules uses `staged-initiative-repo` with the same initiative
folder layout; nothing else changes.

## 9. Day 2

From the deploy folder:

```bash
./install.sh status              # docker compose ps, for this stack
./install.sh logs                # follow the orchestrator's output
./install.sh doctor              # read-only health checks; non-zero on any `fail`
./install.sh diagnose            # a redacted report (diagnostics/<timestamp>.md) to attach to a bug report
./install.sh stop                # stop, keeping every volume
./install.sh start               # start again; also applies a changed .env
./install.sh start --with-docker # add a Docker daemon for Runs whose commands run `docker compose` (privileged sidecar — read guide host/docker-for-runs first)
./install.sh setup               # re-run setup/*.sh and the BMAD install now
./install.sh bmad remove|install # take the BMAD skills out of the harness home, or put them back
./install.sh harness claude --version 2.1.332   # apply a harness CLI pin and recreate backend-api
./install.sh upgrade --tag <newer>
./install.sh uninstall           # stop and DELETE the volumes, after typing `delete`; keeps .env
```

**Data.** Five named volumes: `pgdata` (the database: Runs, projects, templates, metrics),
`work` (git worktrees and logs of Runs, pruned after `WORKTREE_RETENTION_DAYS`), `agent-home`
(harness logins, settings and the BMAD skills), `harness-bin` (the CLIs at their pins,
re-seeded from the image; not backed up) and, with Docker for Runs on, `docker-data`. The
volumes are named after `COMPOSE_PROJECT_NAME` in `.env`: a renamed project starts an empty
database.

**Backup.** `docker compose exec postgres pg_dump -U orchestrator -Fc orchestrator > backup.dump`
from the deploy folder. `upgrade` takes one into `backups/` by itself before it changes
anything. PostgreSQL publishes no port; reach it with `docker compose exec postgres psql -U orchestrator orchestrator`.

**Upgrade.** `./install.sh upgrade --tag <newer>` extracts the target release's folder from
its own image, refuses while a step is working (exit 3) or, when the release changes the
engine's step sequence (`DBOS_APPLICATION_VERSION`), while any Run is in the engine (exit 4:
answer or cancel every parked Run first, or do not upgrade yet), asks to continue, takes the
instance hold and a `pg_dump`, replaces each product file (the previous copy goes to
`.upgrade/{ts}/previous/`), runs setup, restarts and proves the API. Your own files — `.env`,
`templates/*.yaml`, `setup/*.sh`, `compose.override.yml` — are never touched. A project with
the bootstrap of §7 needs nothing after an upgrade.

**Rollback.** `./install.sh upgrade --tag <older>`, plus restoring the `backups/` dump when
the newer release migrated the schema: migrations run forward only.

**Templates.** Your own workflow files live in `./templates` beside `docker-compose.yml`,
mounted read-only; the folder is read at start-up and on `POST /api/v1/templates/reload`,
and a changed file becomes the next version of its name. The web UI at `/templates` edits
and saves versions too; a folder file of the same name wins at the next reload. Format and
examples: `templates/README.md` in this repository and the guide page `workflows/customize`.

**If something is wrong.** `./install.sh doctor` first, every time. Then `./install.sh diagnose`
and read the file before you send it — a log line carries whatever a target repository
printed. The symptom table in `DEVELOPMENT.md` § Troubleshooting covers the usual causes.

## 10. Exposure and trust

Every published port binds `BIND_ADDRESS`, default `127.0.0.1`: the stack is reachable only
from its own machine. Setting `BIND_ADDRESS=0.0.0.0` publishes the web UI and the API on
every interface. Before doing that, know what it means: one bearer token is the entire
authentication, the API dispatches coding agents with write access to your repositories, and
nothing rate-limits login attempts. On any network you do not fully trust, keep loopback and
put a reverse proxy with TLS, an SSH tunnel or a VPN in front.

What runs with which rights:

- The harness CLIs run as the non-root user `agent` inside the backend container, in a
  worktree, with an environment built from a contract plus the Project's env vars. They
  never receive `GITHUB_TOKEN`, `LITELLM_SPEND_KEY` or the backend's environment; `git push`
  is done by the orchestrator, not by the agent.
- A Run's budget is enforced from the gateway's metered spend when a gateway is configured,
  from the harness's own figures otherwise (marked provisional).
- Protected paths — `AGENTS.md`, `epics.yaml`, `SPEC.md`, `stories.yaml`, and the test files
  `test_globs` freezes — park the Run when an agent touches them; nothing proceeds past a
  park without a human signal.
- Docker for Runs (`--with-docker`) adds a privileged sidecar; it is off by default and is
  your decision.

The full statement is the guide page `trust` (`http://127.0.0.1:8000/guide/trust.md`).
