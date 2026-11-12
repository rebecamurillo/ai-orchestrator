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
  plus the compose plugin (Linux). Docker Engine 26 or later: the setup service mounts volume
  subpaths (`./install.sh doctor` has a `docker engine` line). 8 GB of RAM.
- **A GitHub personal access token** (classic) with:
  - `read:packages` — pulls the two images. Your GitHub user must have been granted read
    access to the packages, or be a member of the organisation that owns them; ask the
    person who sent you this package if a pull answers `denied`.
  - `repo` — if the same token will be the credential the orchestrator uses to clone and
    push the repositories you register (the usual setup; see `GITHUB_TOKEN` below). Every
    repository you register must be reachable by this one token.
- `curl` and `openssl` (both ship with macOS and every mainstream Linux).

## Which file is whose

Every path of this folder has one role. `product-files.json` lists the product and seed paths
with their hashes; every path it does not name is yours.

| Path | Role | What it is |
| --- | --- | --- |
| `README.md`, `VERSION`, `install.sh`, `docker-compose.yml`, `release.env`, `.env.example`, `.gitignore` | product | replaced by `upgrade` |
| `product-files.json` | product | the manifest: every product and seed path with its `sha256` |
| `kit/` | product | the kit skills the instance serves |
| `bmad/install.sh`, `bmad/README.md` | product | the BMAD script and its notes |
| `setup/README.md`, `setup/examples/copy-folder.sh` | product | the setup notes and an example script |
| `templates/README.md`, `templates/shipped/*.yaml` | product | the template format and the shipped examples (nothing there loads) |
| `compose.override.yml` | seed | written only when absent, then yours |
| `setup/bmad.choice` | seed | `installed` or `removed`; written only when absent, changed by `bmad remove` and `bmad install` |
| `setup/*.sh` | client | your scripts, run by `setup` |
| `templates/*.yaml` | client | your workflow files |
| `.env` | client | the configuration; `install` writes it when it is absent, nothing else touches it |
| `backups/`, `logs/`, `diagnostics/`, `.upgrade/` | written | created by `install.sh` and git-ignored |
| anything else you add (an LLM platform folder included) | client | never read, written or removed by the product |

Product files are replaced by `upgrade`, seed files are written only when absent, and a
client file is never read or written by the product — `.env` is the one exception, written
once by `install`.

## Install

These files come out of the image you are about to run, so they can never describe a
different version than it. Log Docker in first (`docker login ghcr.io -u <your-github-user>`,
the token as the password), then:

```bash
docker run --rm ghcr.io/rebecamurillo/ai-orchestrator/backend-api:1.0.0-beta kit bootstrap | tar x
cd ai-orchestrator
./install.sh
```

`kit bootstrap` writes this whole directory — `install.sh`, the compose file, `release.env`,
the `.env` contract, this README, `product-files.json`, `kit/`, `setup/`, `bmad/`,
`templates/shipped/`, and a `VERSION` naming the tag — to stdout as a tar stream. The
starter LLM platform is not part of it (§ Getting an LLM platform). Upgrading is one
command from this folder, `./install.sh upgrade --tag <newer>` (§ Upgrading).

Offline, or where procurement needs a file to sign for: ask the person who sent you here for
`make bundle`'s tarball (`ai-orchestrator-deploy-<tag>.tar.gz`), extract it, and run
`./install.sh` from inside. `docker save` / `docker load` moves the two images the same way.

The script asks for the token and, optionally, the gateway and tracing values, and does the
rest: it logs Docker in to the registry, writes `.env` with generated secrets, pulls the
images the compose file pins, starts the stack, proves the API answers and the token works,
runs setup under the instance hold (§ Setup scripts and BMAD), and prints:

```
  Web UI     http://127.0.0.1:4321
  API        http://127.0.0.1:8000   (Authorization: Bearer <token>)
  Login      <ORCHESTRATOR_TOKEN>
```

Log in with that token. It is the one credential — the web login and the API bearer — and
it lives in `.env` beside the script. Then follow the operator flow: create a Project,
register a Repository, run its clone check, run `repo-init` if the target repository is new
to BMAD, then start a Run from `/workflows/new` with a budget.

A setup that fails is reported with its record and `install` still exits 0: the instance is
up, and `./install.sh setup` runs it again.

Unattended, from a shell or a provisioning script:

```bash
GHCR_TOKEN=ghp_… ./install.sh --yes                    # no gateway, no tracing
LITELLM_BASE_URL=… LITELLM_API_KEY=… LITELLM_SPEND_KEY=… \
LANGFUSE_BASE_URL=… LANGFUSE_PUBLIC_KEY=… LANGFUSE_SECRET_KEY=… \
GHCR_TOKEN=ghp_… ./install.sh --yes                    # gateway and tracing given
GHCR_TOKEN=ghp_… ./install.sh --yes --no-bmad          # without the BMAD skills
```

### The gateway and tracing values

Six values, all optional, each from the environment or asked for (the secrets are read
without echo): `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LITELLM_SPEND_KEY`,
`LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`. Blank keeps the gateway,
or tracing, off. They are written only when `.env` is created, and `--yes` asks for
nothing. To add them later, set them in `.env` and run `./install.sh start`.

### Installing into a folder that already holds a configuration

`./install.sh` creates only what is missing and changes no byte of a file that is present:
an existing `.env`, `compose.override.yml` or `setup/bmad.choice` stays as it is, so
re-running it after a failure picks up where it stopped without rotating the token you
already use. Delete a file deliberately to start over. `--no-bmad` writes `removed` to
`setup/bmad.choice` when that file is absent.

### What the script wrote

`.env` (mode 600) is the release contract `.env.example` with the **REQUIRED** section
filled in: a generated `ORCHESTRATOR_TOKEN`, session secret, Fernet key and database
password, and `GITHUB_TOKEN` set to the token you gave (override by exporting a different
`GITHUB_TOKEN` before running). Everything under **OPTIONAL** keeps its default; the file
explains each line. There is no `IMAGE_TAG` line: the compose file carries the image tag, the
release pins live in `release.env`, and a line in `.env` overrides one of them.

The registry credential goes to `docker login` only. It is held by the Docker daemon's own
config, never by a container: the one credential a *process* in this stack holds is
`ORCHESTRATOR_TOKEN`.

## Day 2

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

## Setup scripts and BMAD

`setup/` is yours. `install`, `upgrade` and `setup` run a one-shot setup container, under the
instance hold, in this order: BMAD (when `setup/bmad.choice` reads `installed`), each
executable `setup/*.sh` directly under `setup/` in name order, the operator skills of the
image, the catalog of each harness, and the record. A script sees the harness asset folders
under `HOME` and nothing else — no secret, no login, no database; `setup/README.md` has what it
gets, the clash rule and `examples/copy-folder.sh`. The record is
`.orchestrator/setup-run.json` in the agent home; the logs are `logs/setup/{timestamp}/`.
No command restarts backend-api.

- `./install.sh setup` runs it now. Exit 0: every phase passed; 2: a script failed or the
  record is not ok; 3: refused, a step is working; 1: failed.
- `./install.sh setup --reset` first empties the harness asset folders and BMAD's record,
  then runs every phase. The harness logins are not in them and are kept.
- `./install.sh bmad remove` writes `removed` to `setup/bmad.choice` and runs setup: BMAD's
  skills are deleted and stay out through every later install and upgrade.
- `./install.sh bmad install` writes `installed` and runs setup; it is also how to restore
  BMAD after a remove.
- `./install.sh install --no-bmad` writes `removed` before the first setup.

## Editing the workflow templates

The shipped templates are a starting point, not a fixed part of the product. Five single
files ship — `staged-initiative-hub` and `staged-initiative-repo` (three agent sessions per
story: plan, implement, review, each on its own model), `repo-init`, `agent-smoke` and the
off-menu `harness-readiness` — and none calls another template. The format, with three
working examples, is in `templates/README.md`.

Your own templates live in the folder `./templates` next to `docker-compose.yml`, mounted
read-only into the backend at `/app/operator-templates` (`OPERATOR_TEMPLATES_DIR`). The
folder is read at start-up and on `POST /api/v1/templates/reload`; the answer lists what was
`stored`, `unchanged`, `refused` and `not_in_folder`. Editing at `/templates` in the web UI
still works: open a template and a version, edit the YAML, **Validate**, and **Save as
v{n+1}**. A saved version never changes.

When the folder holds a file named after a template, edit the file: a version saved on the instance is superseded by the file's content as the next version at the next reload or start-up, and stays listed.

A save or a reload applies to Runs planned after it: a Run that is already planned, queued or
running keeps the tree it was planned from.

An upgrade that ships a changed template adds a new version of it on first boot and never
overwrites or removes the versions you saved. A changed shipped file lands as a new version,
and a folder file of that name then wins again at the next reload or start-up.


Upgrading from 1.0.0-beta.3: the staged pieces `staged-hub-epic`, `staged-hub-story`,
`staged-epic` and `staged-story` are no longer shipped or called — `staged-initiative-hub` and
`staged-initiative-repo` are single files. A version you saved of one of those pieces stays
listed but no Run reaches it any more; re-apply its change inside the single file, as a folder
file or a web save. A folder from before this release has no `product-files.json` and is
migrated (§ Migrating an existing folder), which brings the `./templates` mount and its `.env`
values with the new `docker-compose.yml` and `.env.example`.

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

## Getting an LLM platform

The product neither ships nor manages an LLM platform: this folder holds none, and no
command of `install.sh` starts one. A model gateway (LiteLLM: routes every model call, mints
per-harness keys, records spend so a Run's budget is real) and tracing (Langfuse) are
optional. Without them each coding agent authenticates on its own, cost figures are
provisional, trace links are absent, and the `local` harness is unavailable.

A starter is published: `deploy/llm-platform/` of
`https://github.com/rebecamurillo/ai-orchestrator`, at the tag `v<VERSION>` of this release
(`VERSION` in this folder). Its README there says how to start it; you run it, as its own
compose project, wherever you keep it — it is yours, not part of this folder's product. Any
other LiteLLM or Langfuse works the same way.

Point the instance at it with the six values (§ The gateway and tracing values), at install
or later in `.env` followed by `./install.sh start`. `LITELLM_API_KEY` is a model-routes-only
virtual key; `LITELLM_SPEND_KEY` is admin-scoped, reads spend, is read by backend-api only and
never reaches a harness.

Every model named in `READINESS_MODELS` must exist in the gateway's `model_list`, or
backend-api refuses to start.

## Docker for Runs (optional, off by default)

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

`VERIFY_DOCKER=true` widens that. The `docker` sidecar is privileged, and anything that can
reach its daemon — every Run's commands and every coding agent, by design — can start a
privileged container or mount the host filesystem of the machine the daemon runs on: root
in Docker Desktop's VM, root on a Linux host running Docker Engine. What it does not give is
this stack's own daemon: the sidecar is a separate dockerd with its own containers, images
and networks, so a Run cannot see, stop or read the orchestrator's containers, its database
or its `.env` through it, and nothing it publishes leaves backend-api's network namespace.
Containers it starts can still reach the network, and the rest of the compose network
(`postgres`, `web-client`) can reach the ports they publish on backend-api. Turn it on only
for repositories you would let run `docker` on that machine, and turn it off when none
needs it.

## Upgrading

```bash
./install.sh upgrade --tag <newer>
```

Run it from this folder, with nothing extracted over it first: `upgrade` takes the release's
files from the target image itself, and a `kit bootstrap | tar x` over this folder would
replace product files outside the hold, with no copy in `previous/`.

`upgrade` prints `running <version> → target <tag>` and refuses a target equal to what is
running. The order is fixed: it extracts the target release's folder from its own image into
`.upgrade/{ts}/staged/`; checks, with nothing written, that no working step runs and, when the
release changes `DBOS_APPLICATION_VERSION`, that no Run is in the engine; asks to continue;
takes the instance hold; takes a `pg_dump` into `backups/`; replaces each product file, the
previous copy moving to `.upgrade/{ts}/previous/`; writes each seed file that is absent; runs
setup; restarts and proves the API. It prints what it will do before it asks, and a report at
the end: `replaced`, `added`, `removed` and `edited` lines, `seed written`, the release pins
it changes, the `.env` overrides of `release.env` (which keep their value) and the Runs that
continue. An example workflow of `templates/shipped/` whose content changed, and whose name
you hold in `templates/`, is listed as `improved:`; a new one as `new:`. Your own files are
never touched.

- `.upgrade/{ts}/staged/` is the release's folder as extracted; `.upgrade/{ts}/previous/`
  holds every product file the upgrade replaced or removed. A product file whose content you
  had edited is listed as `edited` and its copy is in `previous/`.
- **Refusals** print `refused: nothing was changed` and leave the folder as it was. Exit 3:
  a working step runs (or the hold answered 409). Exit 4: the release changes
  `DBOS_APPLICATION_VERSION` and Runs are in the engine — finish or cancel them. Exit 5: the
  folder has no `product-files.json` — follow § Migrating an existing folder. Exit 1: anything
  else failed (the line says what). Exit 0: upgraded.
- **Rollback** is `./install.sh upgrade --tag <older>`, plus restoring the `pg_dump` of
  `backups/` when the newer release migrated the schema: migrations run forward only, so
  running an older release on a migrated database is expected to fail closed. By hand the
  backup is
  `docker compose exec postgres pg_dump -U orchestrator -Fc orchestrator > backup.dump`.
- **`DBOS_APPLICATION_VERSION`** is a release pin in `release.env` and versions the engine's
  durable step sequence. A release that changes it makes every in-flight Run unrecoverable
  under the old value, so `upgrade` refuses with exit 4 while any Run is parked, queued or
  blocked in the engine (a parked `needs_you` Run holds its slot for up to
  `HUMAN_WAIT_SECONDS`, 30 days by default). Never set it in `.env` as routine.
- **Harness CLI versions are release pins** (`CLAUDE_CODE_VERSION`, `CODEX_VERSION`,
  `OPENCODE_VERSION`, `LANGFUSE_OPENCODE_PLUGIN_VERSION`, with `BMAD_VERSION`) in
  `release.env`, read before `.env`: a line in `.env` overrides one, and `doctor` and `upgrade`
  report each override. The upgrade no longer writes pins into `.env`. At every start
  `backend-api` copies the image's CLI onto the `harness-bin` volume (`/opt/harness-cli`) when
  the image's is at the pin, and otherwise runs one `npm install` of the pin there, kept
  across a recreate.
- `./install.sh harness <claude|codex|opencode> --version X` edits `.env` and recreates
  `backend-api`. `docker compose restart` does not apply a pin: it keeps the old environment.
- The registry is needed at start only when a pin differs from the image's. A pin that
  cannot be installed refuses that harness alone (`cli not at pinned version`); the API
  still starts. The logs name the harness and both versions. Nothing retries until the next
  start.
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
- **`VERIFY_DOCKER` is absent from an `.env` written before Docker for Runs**, which means
  off. If you added a `docker` sidecar to `docker-compose.yml` by hand, set
  `VERIFY_DOCKER=true` before the upgrade (`./install.sh start --with-docker` appends it):
  otherwise the first start after it removes that container. A volume named `docker-data`
  is reused as the image cache. A hand-added service the new file no longer declares is left
  as an orphan container — `docker compose up -d --remove-orphans` from this directory
  removes it — and `docker volume rm` removes any volume only it used.

## Migrating an existing folder

A folder installed before this release has no `product-files.json`, so `upgrade` refuses it
with exit 5. Production's migration is done by hand, in this order:

1. Extract this release into a **new, empty folder** (`kit bootstrap | tar x`, § Install).
2. Copy into it from the old folder: `.env`, `templates/*.yaml` and `backups/`.
3. In the new `.env`, delete the `IMAGE_TAG` line and the six release pins —
   `BMAD_VERSION`, `DBOS_APPLICATION_VERSION`, `CLAUDE_CODE_VERSION`, `CODEX_VERSION`,
   `OPENCODE_VERSION`, `LANGFUSE_OPENCODE_PLUGIN_VERSION` — so `release.env` supplies them.
4. Check that `COMPOSE_PROJECT_NAME` in the new `.env` equals the old folder's project. When
   the old `.env` has none, set it to the old folder's name. The data volumes are named after
   the compose project: a different name starts an empty database.
5. Stop the old stack, from the old folder (`./install.sh stop`).
6. Start from the new folder (`./install.sh`; with the `.env` present it creates only what is
   missing).

An `llm-platform/` folder in the old folder stays where it is, untouched, with its stack
running — it is your environment, and the new `.env` keeps the values that point at it.
Never run an older `install.sh upgrade` across this release.

## Known limits of this package

- No push channel to agents or the UI: they poll the API (the UI every 5 s while a Run is
  active, 30 s idle). The webhook above is the one outbound notification.
- The backend image is large (~1.2 GB compressed): it carries Python, Node, three
  harness CLIs, Chromium system libraries for in-worktree browser tests, and the docker
  CLI with its compose and buildx plugins.
- The manual path still works: `cp .env.example .env`, fill in the REQUIRED section,
  `docker compose pull && docker compose up -d --wait`; `release.env` is read with `.env`. The
  contract file is the reference; `install.sh` is that procedure with the secrets generated for
  you.
