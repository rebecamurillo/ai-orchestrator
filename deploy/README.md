# ai-orchestrator — install and run

This directory is the client package: everything a machine needs to run a released
ai-orchestrator without the source repository. One script installs it, runs it in Docker,
and opens it on `http://127.0.0.1:4321`.

The stack is three containers — the web UI, the API, and PostgreSQL — pulling the images a
release publishes to GitHub Container Registry
(`ghcr.io/rebecamurillo/ai-orchestrator/{backend-api,web-client}`, `linux/amd64` and
`linux/arm64`). The images are private: a GitHub token that can read them is the one
thing you have to bring.

If you are developing the orchestrator itself, this is not your file: use the repository
root's `README.md`. If you are deploying the operator's own host from a checkout, that
procedure is `DEPLOY.md`.

## What you need

- **Docker** with Compose v2 — Docker Desktop (macOS, Windows with WSL 2) or Docker Engine
  plus the compose plugin (Linux). 8 GB of RAM for the orchestrator alone; 16 GB with the
  optional llm-platform stack.
- **A GitHub personal access token** (classic) with:
  - `read:packages` — pulls the two images. Your GitHub user must have been granted read
    access to the packages, or be a member of the organisation that owns them; ask the
    person who sent you this package if a pull answers `denied`.
  - `repo` — if the same token will be the credential the orchestrator uses to clone and
    push the repositories you register (the usual setup; see `GITHUB_TOKEN` below). Every
    repository you register must be reachable by this one token.
- `curl` and `openssl` (both ship with macOS and every mainstream Linux).

## Install

These files come out of the image you are about to run, so they can never describe a
different version than it. Log Docker in first (`docker login ghcr.io -u <your-github-user>`,
the token as the password), then:

```bash
docker run --rm ghcr.io/rebecamurillo/ai-orchestrator/backend-api:1.0.0-beta kit bootstrap | tar x
cd ai-orchestrator
./install.sh
```

`kit bootstrap` writes this whole directory — `install.sh`, the compose file, the `.env`
contract, this README, `llm-platform/`, `kit/`, and a `VERSION` naming the tag — to stdout as
a tar stream. Upgrading is the same two commands with a newer tag, then
`./install.sh upgrade --tag <newer>`.

Offline, or where procurement needs a file to sign for: ask the person who sent you here for
`make bundle`'s tarball (`ai-orchestrator-deploy-<tag>.tar.gz`), extract it, and run
`./install.sh` from inside. `docker save` / `docker load` moves the two images the same way.

The script asks for the token, then asks whether to install the optional llm-platform stack (see
below), and does the rest: it logs Docker in to the registry, writes `.env` with generated
secrets, pulls the images pinned by `VERSION`, starts the stack, proves the API
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
GHCR_TOKEN=ghp_… ANTHROPIC_API_KEY=sk-ant-… ./install.sh --yes --with-platform
```

### What the script wrote

`.env` (mode 600) is the release contract `.env.example` with the **REQUIRED** section
filled in: `IMAGE_TAG` from `VERSION`, a generated `ORCHESTRATOR_TOKEN`, session secret,
Fernet key and database password, and `GITHUB_TOKEN` set to the token you gave (override
by exporting a different `GITHUB_TOKEN` before running). Everything under **OPTIONAL**
keeps its default; the file explains each line. `LITELLM_BASE_URL` and
`LANGFUSE_BASE_URL` are blanked, which is the off switch for the gateway and for tracing,
until the llm-platform stack is installed.

The script never overwrites an existing `.env` or `llm-platform/.env`: re-running it after a
failure picks up where it stopped without rotating the token you already use. Delete a
file deliberately to start over.

The registry credential goes to `docker login` only. It is held by the Docker daemon's own
config, never by a container: the one credential a *process* in this stack holds is
`ORCHESTRATOR_TOKEN`.

## Day 2

```bash
./install.sh status              # docker compose ps, for both stacks
./install.sh logs                # follow the orchestrator's output
./install.sh doctor              # read-only health checks; non-zero on any `fail`
./install.sh diagnose            # a redacted report to attach to a bug report
./install.sh harness claude --subscription   # Claude Max/Pro login instead of an API key
./install.sh stop                # stop, keeping every volume
./install.sh start               # start again (and the llm-platform stack, if it was installed)
./install.sh start --with-platform   # add the llm-platform stack to an existing install
./install.sh upgrade --tag 1.0.0
./install.sh uninstall           # stop and DELETE the volumes, after typing `delete`
```

`doctor` changes nothing. It prints one `ok` / `warn` / `fail` line per check — docker and the
daemon, `.env` and its mode, `IMAGE_TAG` against the images actually pulled and against the
version the instance reports, the two ports, `/healthz` and the token, each harness's
readiness, the llm-platform stack, free disk, the retention and cron settings — and every
`fail` and `warn` line ends with the command to run or the variable to set. No secret is
printed, so its output is safe to paste.

`diagnose` writes `diagnostics/<timestamp>.md`: versions, `compose ps`, the last 200 lines of
the logs, and `.env` with every value masked except ports, crons, versions, directories and
flags. That file is what a bug report attaches. Read it before you send it — a log line
carries whatever a target repository printed.

`harness claude --subscription` sets `CLAUDE_SUBSCRIPTION_AUTH`, prints the two lines to
uncomment in `llm-platform/litellm.config.yaml`, runs `claude login` inside the container, and
reads `GET /api/v1/harnesses` back after the restart. `--api-key` goes the other way.
`llm-platform/README.md` has the whole picture, including what a subscription does to the cost
figures on screen and which half of that path has never been run live.

`upgrade` prints `running <version> → target <tag>` and refuses a target equal to what is
already running; then it takes a `pg_dump` into `backups/`, rewrites `IMAGE_TAG`, pulls, and
restarts. It reads the release notes for you only in the sense of printing the two cautions at
the end of this file. `uninstall` keeps `.env` and `llm-platform/.env`, so the token and the
Langfuse keys survive a reinstall; remove them yourself when you mean it.

### If something is wrong

Start with `./install.sh doctor`. It is the whole checklist, it is useful even when the
instance does not answer at all, and the line that fails names its own fix. If that is not
enough, `./install.sh diagnose` collects everything a maintainer will ask for, already
redacted.

The `orchestrator-admin` skill in `kit/` is the same ground for an agent: install it into this
directory and Claude Code, Codex or OpenCode will walk install, upgrade, backup, rollback,
harness and subscription setup, secret rotation, garbage collection and filing the bug report
— running these commands and reading their output rather than improvising around them.

Ports: everything publishes on `127.0.0.1` — 4321 (web), 8000 (API), and for the host
stack 3000 (Langfuse), 4000 (LiteLLM), 5433, 9000, 9091 (its stores). If one is already
taken on your machine the script stops before starting anything and names the variable
that moves this stack off it (`WEB_CLIENT_PORT`, `BACKEND_API_PORT` in `.env`;
`LANGFUSE_PORT`, `LITELLM_PORT`, … in `llm-platform/.env`). It never stops what is listening there.

## Editing the workflow templates

The shipped templates are a starting point, not a fixed part of the product. Open
`/templates`, pick a template and a version, edit the YAML in place, **Validate**, and
**Save as v{n+1}**. A saved version never changes; the save is a new version beside it, and
the versions column keeps every earlier one.

Two families ship, side by side and never sharing a callee: **staged** (`staged-initiative-hub`
and `staged-initiative-repo` on the menu — three agent sessions per story, plan / implement /
review, each on its own model: the Run's `model` implements, `plan_model` plans and
`review_model` reviews) and **auto** (`initiative-hub` — one `bmad-build-auto` session per
story, kept exactly as it shipped). The first segment of the name is the family; the header
comment under each file's `description:` names its role, its callers and its sibling in the
other family, and what differs. Edit the family you run; a change to a row both share usually
belongs in both.

A template that calls another (`staged-initiative-hub` → `staged-hub-epic` →
`staged-hub-story`) names the callee by `name` and omits `version`, so it resolves to the
callee's latest saved version each time a Run is planned. Editing the story template is
therefore one save: the next hub Run picks it up through the unchanged hub and epic files.
The editor says so above the Save button — which callers *follow* this save and which are
*pinned* to an integer version and will not — and every save `applies to Runs planned after
this save`: a Run that is already planned, queued or running keeps the tree it was planned
from. A save that would break a follower (an input renamed or removed) is refused and names
that caller.

An upgrade that ships a changed template adds a new version of it on first boot and never
overwrites or removes the versions you saved. The shipped version lands above yours, so it
becomes the latest: after an upgrade, re-apply your edit as the next version of each template
you customized.

What you can change — step kinds, inputs, loops, checkpoints, a model or a timeout per step,
the prompts agents are sent — and the same edit loop over the API are in
`kit/skills/orchestrator/references/workflows.md`. That guide is installed into every project
with the kit, so the project's coding agent can propose and validate a template change for
you; it saves only on your go-ahead.

A template does not decide which shell commands an agent may run. That is
`CLAUDE_ALLOWED_TOOLS` in `.env`. The shipped value allows `Bash` whole — the container is
the sandbox, and `git push` stays denied by the harness adapter — so an agent is never
parked on a denied package manager or test runner. An install that narrows it to command
families (`Bash(yarn *)`, `Bash(npx *)`, …) must list every tool its repositories use, and
a change needs `./install.sh start`.

## The optional llm-platform stack (LiteLLM + Langfuse)

`llm-platform/` is the model gateway and the tracing server: LiteLLM (routes every model call,
mints per-harness keys, records spend so a Run's budget is real) and Langfuse (traces), with
their stores (PostgreSQL, ClickHouse, Redis, MinIO) — seven more containers, as their own
compose project so they survive this stack's restarts. Without it each coding agent
authenticates on its own, cost figures are provisional, trace links are absent, and the
`local` harness is unavailable.

`./install.sh` offers it; `--with-platform` / `--no-platform` decide it unattended. The script
generates `llm-platform/.env` with random credentials (`llm-platform/generate-env.sh`), writes the provider
keys you give it (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` — prompted,
or from the environment; at least one is needed before a model answers anything), starts
the stack, waits for it (the first start runs migrations — a few minutes), mints the
harness's virtual key and writes the six connection values into `.env`
(`llm-platform/sync-env.sh`), then starts the orchestrator against it. It prints the Langfuse
login at the end; it is also in `llm-platform/.env`.

`llm-platform/README.md` documents the key separation (`LITELLM_API_KEY` is a model-routes-only
virtual key; `LITELLM_SPEND_KEY` reads spend and never reaches a harness), the model routes
in `llm-platform/litellm.config.yaml`, and `CLAUDE_SUBSCRIPTION_AUTH`. Pointing at your own
existing LiteLLM/Langfuse instead works the same way: set the `*_BASE_URL` and key
variables in `.env` by hand and skip the llm-platform stack.

Every model named in `READINESS_MODELS` must exist in the gateway's `model_list`, or
backend-api refuses to start.

## Agents in your projects

The instance serves the skills that teach a project's agents to drive this API — create
projects, launch runs, poll progress, answer checkpoints. Run this **from inside the project
repository**, with the two connection values exported:

```bash
curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
  "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness claude
```

The kit comes out of the instance that answered, so the skills cannot be a different version
than the API they call. `--harness` picks where they land, because the three agent CLIs read
different directories:

| `--harness` | writes into | read by |
| --- | --- | --- |
| `claude` | `.claude/skills/` | Claude Code |
| `codex`, `opencode` | `.agents/skills/` | Codex, OpenCode |
| `all` (the default) | both | any of them |

It also adds `ORCHESTRATOR_BASE_URL` (default `http://127.0.0.1:8000`) and
`ORCHESTRATOR_TOKEN` to the project's `.env` without ever overwriting a value you already
have, writes `.orchestrator/kit.json` — the version marker the skill checks on every session,
which holds no credential and is meant to be committed — and calls `GET /api/v1/version` to
prove the pair. Re-run it whenever it tells you the kit is stale. `--base-url`, `--token` and
`--project` override the environment; from a checkout or an extracted bundle, `kit/install.sh`
uses the skills beside it and downloads nothing.

The skill's `references/spec-folder.md` documents the `epics.yaml` / `stories.yaml` /
`SPEC.md` format the templates read.

## Notifications

Set `NOTIFY_WEBHOOK_URL` in `.env` to be told when a Run needs you or ends. One POST is sent each time a Run enters `needs_you`, `done`, `failed` or `cancelled`; blank (the default) sends nothing. Delivery is best-effort: a webhook that is down is logged as `notify_failed` and never fails the Run.

- `NOTIFY_WEBHOOK_FORMAT=json` posts the structured event (run, project, repository, template, status, park kind, reason, step path, attempt, spend, time). `slack` posts a one-line `{"text": ...}` that Slack and Mattermost incoming webhooks accept.
- `NOTIFY_WEBHOOK_SECRET`, when set, adds `X-Orchestrator-Signature: sha256=<hex HMAC-SHA256 of the request body>` so the receiver can check the sender.
- `PUBLIC_BASE_URL` (for example `https://orchestrator.example.com`) adds a link to the Run; blank leaves it out.

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
- **Harness CLI versions are `.env`'s `*_VERSION` pins.** The image ships the release's
  pins. At every start `backend-api` copies the image's CLI onto the `harness-bin` volume
  (`/opt/harness-cli`) when the image's is at the pin, and otherwise runs one `npm install`
  of the pin there, kept across a recreate.
- `./install.sh harness <claude|codex|opencode> --version X` edits the pin and recreates
  `backend-api`. `docker compose restart` does not apply a pin: it keeps the old environment.
- The registry is needed at start only when a pin differs from the image's. A pin that
  cannot be installed refuses that harness alone (`cli not at pinned version`); the API
  still starts. The logs name the harness and both versions. Nothing retries until the next
  start.
- `./install.sh upgrade` shows the pin changes before it asks, marks a downgrade, then
  writes the new release's values. A rollback does the same with the older release's.
- `harness-bin` is not backed up, and `./install.sh uninstall` removes it. To re-seed it
  from the image, stop the stack and `docker volume rm <project>_harness-bin`; both take
  the instance down, so ask the Operator first.
- `POSTGRES_DB` is fixed after first boot, and the stack supports exactly one
  `backend-api` replica.
- **Two settings an upgrade from a release before 2026-10-12 keeps as they were.** A
  Repository's `test_globs` is now exactly what you list, and an empty list freezes no test
  file; rows saved earlier still hold the former three globs (`tests/**`, `**/*.test.*`,
  `**/*.spec.*`) until you clear them in the Repository form, and every story that edits an
  existing test parks `protected_path` until then. And `CLAUDE_ALLOWED_TOOLS` in your `.env`
  still lists command families where the new default is `Bash` whole — replace the families
  with `Bash` unless you want the narrower list.

## Known limits of this package

- No push channel to agents or the UI: they poll the API (the UI every 5 s while a Run is
  active, 30 s idle). The webhook above is the one outbound notification.
- The backend image is large (~1.1 GB compressed): it carries Python, Node, three
  harness CLIs, and Chromium system libraries for in-worktree browser tests.
- The manual path still works: `cp .env.example .env`, fill in the REQUIRED section,
  `docker compose pull && docker compose up -d --wait`. The contract file is the reference;
  `install.sh` is that procedure with the secrets generated for you.
