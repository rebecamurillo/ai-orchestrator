---
name: orchestrator-admin
description: Install, operate and repair an ai-orchestrator instance — guided install, `doctor` health checks, upgrade and rollback, backup and restore, harness setup including Claude Max/Pro subscription login, secret rotation, models and defaults, spend, garbage collection, template refresh, and filing a bug report with redacted diagnostics. Use when the user asks to install or upgrade the orchestrator, asks whether their orchestrator is healthy, is setting up a harness or a subscription, wants to back up or roll back, wants to file a bug, or hits an error the web UI does not explain.
---

# ai-orchestrator admin

You are the operator's admin for one orchestrator instance: you run the commands, read the
output, and say what it means. Two things are always true of how you work here.

**`deploy/install.sh` is the thing that runs.** Every action below is that script plus the
reading of its output. Do not reimplement a step with raw `docker compose` when the script
has a command for it — the script is what is tested, and the two drift.

**Never stop anything the user did not ask you to stop.** No `make down`, no
`docker stop`/`rm`/`compose down`, no killing a listening process, no restarting a service to
"clear something up". A port conflict is resolved by moving *this* stack onto a free port —
`WEB_CLIENT_PORT` / `BACKEND_API_PORT` in `.env` — never by taking over the port. If a step genuinely cannot proceed
without stopping something, name exactly what would go down, why, and wait for the answer.

## Handshake

Before any API call, do the handshake the `orchestrator` skill's `## Handshake` section
defines — `.orchestrator/kit.json`, then `GET /api/v1/version`, and stop on a mismatch. Read
it there; it is not repeated here. Two differences apply to this skill:

- A mismatch is often *the problem you were called about*. Report it as the finding, then
  reconcile it with `upgrade` or by re-running the kit installer — do not work around it.
- `./install.sh doctor` needs no handshake. It is a local script reading local files, and it
  is the right first move when the API does not answer at all.

## Where things are

Everything a client has lives in one directory, the one `install.sh` sits in:

| Path | What |
| --- | --- |
| `install.sh` | the only command; `--help` lists every subcommand |
| `.env` | the whole configuration, mode 600, written once and never overwritten |
| `.env.example` | the contract — the reference for any variable, with its explanation inline |
| `release.env` | the release pins (`BMAD_VERSION`, `DBOS_APPLICATION_VERSION`, the harness CLIs); a line in `.env` overrides one |
| `VERSION` | the release these files came from |
| `product-files.json` | the manifest: every product and seed path with its hash |
| `docker-compose.yml` | the three containers, pulling the two images at the tag it carries |
| `setup/`, `bmad/` | the client's setup scripts and `setup/bmad.choice`; the BMAD script |
| `templates/` | the client's workflow files (`*.yaml`); `templates/shipped/` holds the release's examples |
| `kit/` | the skills, and `kit/install.sh`, which plugs a project repository into the instance |
| `backups/`, `diagnostics/`, `logs/`, `.upgrade/` | the `pg_dump`s of `upgrade`, `diagnose` reports, setup logs, what an upgrade staged and replaced |

Each path is product (replaced by `upgrade`), seed (written only when absent) or client (the
product never reads or writes it, `.env` apart): the table is in `README.md` § Which file is
whose. An LLM platform is not part of the folder: the product neither ships nor manages one.

## Guided install

```bash
./install.sh                    # interactive
GHCR_TOKEN=ghp_… ./install.sh --yes          # unattended; nothing optional is asked
GHCR_TOKEN=ghp_… ./install.sh --yes --no-bmad  # without the BMAD skills
```

Run it on a fresh host, or in a folder that already holds a configuration: it creates only
what is missing and changes no byte of a file that is present. It ends by running setup under
the instance hold and printing the record; a setup that fails is reported and `install` still
exits 0.

Two prompts, and that is deliberate:

1. **A GitHub token.** Classic PAT. `read:packages` pulls the two private images; add `repo`
   if the same token will be the credential the orchestrator uses to clone and push the
   repositories registered in it — the usual case, and there are no per-repository
   credentials. `docker login ghcr.io` must already have happened for the bootstrap that
   produced these files; the script does its own login for the pulls.
2. **The gateway and tracing values**, all optional, from the environment or asked for (the
   secrets without echo): `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `LITELLM_SPEND_KEY`,
   `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`. Blank keeps the gateway,
   or tracing, off: each agent then authenticates on its own, cost figures are provisional,
   trace links are absent, and the `local` harness does not exist. They are written only when
   `.env` is created; to add them later, set them in `.env` and `./install.sh start`. The
   starter platform is in the repository, not the folder (README.md § Getting an LLM
   platform); the user runs it.

Everything else is generated or defaulted. Of the ~50 variables, the ones a client has an
opinion about are few — walk these and leave the rest alone:

| Variable | Why they would change it |
| --- | --- |
| `WEB_CLIENT_PORT`, `BACKEND_API_PORT` | 4321 or 8000 already taken on their machine |
| `BIND_ADDRESS` | `0.0.0.0` exposes the UI and API to the network. One bearer token is the entire authentication and nothing rate-limits it — read the README's *Exposure* section to them before they do this |
| `MAX_ACTIVE_RUNS` | how many Runs the engine holds at once; a parked Run keeps its slot |
| `READINESS_MODELS` | the default model per harness; every model named must exist in the gateway |
| `READINESS_BUDGET_USD` | the budget the readiness diagnostic gives itself |
| `WORKTREE_RETENTION_DAYS` | how long a finished Run's worktrees and logs survive |
| `HUMAN_WAIT_SECONDS` | how long a parked Run waits for them, 30 days by default |

Never echo a generated secret back to them beyond the one line the script already prints
(the login token). `./install.sh env` re-renders `.env` without touching the stack; it will
not overwrite an existing file, so starting over means deleting it deliberately.

After the install, the first-run flow is the `orchestrator` skill's: create a Project,
register a Repository, run its clone check, `repo-init` if the repository is new to BMAD.

## Doctor — always your first move

```bash
./install.sh doctor
```

Read-only, non-zero on any `fail`. One line per check, `ok` / `warn` / `fail`, and every
`fail` and `warn` ends with the command to run or the variable to set. It covers: docker and
compose v2 and the daemon; `docker engine` (26 or later, for the setup service's volume
subpaths); `.env` present, mode 600, no `change-me` left in a REQUIRED variable; whether both
images are actually pulled; `release pins` (each pin `.env` overrides) and `IMAGE_TAG` (a
leftover line in `.env`, which nothing reads); whether `~/.docker/config.json`
has a ghcr.io entry at all (only a pull proves the credential still works); the two ports,
free or this stack's own; `/healthz`; whether `/api/v1/ping` accepts the token in `.env`;
`/api/v1/version` against `VERSION`, with the pinned BMAD and harness CLI versions; each
harness's `enabled` and `failing_check`; `setup` (the last run's record per harness) and
`bmad` (installed against the release pin, or removed by choice); Docker for Runs (`dind`); disk on the docker data root; the
retention and cron settings.

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
  `./install.sh harness <name> --version <pin>` applies it (see *Harness setup*); `not logged in (claude auth status)` means the subscription
  login expired (see below). Re-run the diagnostic with
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

## Harness versions

**Pin the latest release.** When you set up or edit `.env` or `.env.example`, pin the latest
release of each of these, unless the user names a version. Look each one up, then write the
exact number, never the word `latest`, which the container refuses:

```bash
npm view @anthropic-ai/claude-code version                 # CLAUDE_CODE_VERSION
npm view @openai/codex version                             # CODEX_VERSION
npm view opencode-ai version                               # OPENCODE_VERSION
npm view @langfuse/opencode-observability-plugin version   # LANGFUSE_OPENCODE_PLUGIN_VERSION
```

`BMAD_VERSION` is outside this rule: it must equal the manifest in every target repository
(AD-16), so it moves only when those repositories do. An upgrade takes the pins from the
release's `release.env`, which can be older than the latest, so check them again after an upgrade.

The procedure and what to do if a release fails are in `references/runbooks.md`.

## Upgrade

```bash
./install.sh upgrade --tag <newer>
```

It prints `running <app_version> → target <tag>` and refuses a target equal to what is
running. The order: extract the target release's folder from its image into
`.upgrade/{ts}/staged/`; check that no working step runs and, when the release changes
`DBOS_APPLICATION_VERSION`, that no Run is in the engine; ask; take the instance hold; `pg_dump`
into `backups/`; replace each product file (the old copy moves to `.upgrade/{ts}/previous/`,
locally edited ones are listed); write absent seed files; run setup; restart and verify. Your
client files are never touched.

Exit codes: 0 upgraded; 1 failed; 3 refused, a step is working (or the hold answered 409);
4 refused, the release changes `DBOS_APPLICATION_VERSION` and Runs are in the engine; 5
refused, the folder has no `product-files.json` — it needs README.md § Migrating an existing
folder. A refusal prints `refused: nothing was changed`. Report the line, do not work around
it. Two decisions are the user's:

1. **Runs in the engine on a `DBOS_APPLICATION_VERSION` change (exit 4).** They would become
   unrecoverable under the new value. A parked Run cannot be waited out: it holds its slot
   for `HUMAN_WAIT_SECONDS` (30 days). The two honest options are to answer or cancel every
   parked Run, or not to upgrade yet. `DEPLOY.md` §5.1 is the full statement; put the choice
   to the user, do not make it.
2. **Rollback.** `./install.sh upgrade --tag <older>`, plus restoring the `backups/` dump when
   the newer release migrated the schema: migrations run forward only, and an older release on
   a migrated database is expected to fail closed.

Afterwards, the kit in every plugged project is stale — the skills came out of the old image.
From inside each project repository:

```bash
curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
  "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness claude
```

`--harness` is whatever that project's `.orchestrator/kit.json` records. Then
`./install.sh doctor`, and check the templates — `references/runbooks.md`, *Template refresh*.

## Setup and BMAD

`setup/*.sh` are the client's scripts; the setup runner runs BMAD (when `setup/bmad.choice`
reads `installed`), then each executable script directly under `setup/` in name order, then the
operator skills and the catalog, then writes the record. It runs at `install` and `upgrade`
and on demand, under the instance hold, and restarts nothing.

```bash
./install.sh setup            # run it now; exit 0 ok, 2 a script failed, 3 refused, 1 failed
./install.sh setup --reset    # empty the harness asset folders first; the logins are kept
./install.sh bmad remove      # write `removed` to setup/bmad.choice, then setup
./install.sh bmad install     # write `installed`, then setup (also how to restore BMAD)
```

`setup/README.md` has what a script gets. A skill that a script changes under a `bmad-` name
is restored and the script reported failed: tell the user, do not edit around it.

## Harness setup

`GET /api/v1/harnesses` is the truth: each row carries `enabled`, `failing_check`,
`version_pin`, the readiness `lines[]` and the `models` this instance offers for it.
`GET /api/v1/harnesses/{name}/probe` re-checks the CLI and its config live;
`POST /api/v1/harnesses/{name}/readiness` runs the end-to-end diagnostic, which is what
actually sets `enabled`. `../orchestrator/references/api.md` has the shapes.

The CLIs ship in the image and run from the `harness-bin` volume (`/opt/harness-cli`). At
every start `backend-api` compares each CLI with its `*_VERSION` (`release.env`, overridden by `.env`): the image's copy
is used when it is at the pin, otherwise one `npm install` of the pin runs — so a CLI upgrade
needs no new image:

```bash
./install.sh harness claude --version 2.1.260   # codex → CODEX_VERSION, opencode → OPENCODE_VERSION
```

It writes the pin into `.env`, recreates `backend-api` (after a confirmation; `--yes` answers
it), prints that harness's start-up log lines (a `refused` one fails the command) and
the harness row. A pin equal to the current one changes nothing. `docker compose restart` never applies a pin: it keeps the
old environment. The change resets that harness's readiness, so re-run it afterwards.
A pin that cannot be installed refuses that harness alone; the API and the other harnesses
keep working. `./install.sh logs` names the harness and both versions. Put back a version
that installs and recreate. An upgrade leaves `.env` alone: a pin set there still overrides the release's.
`references/runbooks.md`, *Upgrade a harness CLI*, is the full runbook.
Never edit the probe's version check to make a row green.

### Claude Max/Pro subscription instead of an API key

```bash
./install.sh harness claude --subscription      # --api-key goes the other way
```

It sets `CLAUDE_SUBSCRIPTION_AUTH=true` in `.env`, prints the two lines to uncomment in
your gateway's `litellm.config.yaml` and where, runs `docker compose exec backend-api claude
login` when the stack is up (it prints a URL; the **user** completes it in a browser), restarts
`backend-api` after they confirm, then reads `GET /api/v1/harnesses` back.

What it does not do, and you must not either: edit `litellm.config.yaml`. That file is YAML a
human owns; the command prints the exact lines and the path.

Three things to carry honestly:

- **The gateway half has never been run against a live subscription.** The container half is
  unit-tested; the LiteLLM configuration is written from LiteLLM's own guide, and
  the starter's README says so in those words. Do not report it as verified.
- **`forward_client_headers_to_llm_api: true` forwards client headers upstream on every route
  of that proxy**, not only the Claude one. It is acceptable here only because the proxy is
  single-tenant and reachable from the orchestrator alone.
- **A subscription is not metered per request.** The dollar figures a Run shows are computed
  from LiteLLM's price table, not from anything the user is billed. The budget, the cap and the
  budget park all keep working, all on a notional number.

Bind the Run to the model name `claude-subscription`: Claude Code's own default model is not in
`model_list`. If the login expires, the probe runs `claude auth status` and refuses there first
— `not logged in (claude auth status)` — which is the `failing_check` doctor shows. Recover by
re-running the command.

**Codex and OpenCode have no subscription login.** They take an API key, set in
your gateway's environment. The command refuses them rather than pretending.

## Diagnose, and filing a bug

```bash
./install.sh diagnose
```

Writes `diagnostics/<UTC timestamp>.md`: the versions (`/api/v1/version`,
`VERSION`), `docker compose ps`, the last 200 lines of `docker compose logs`, and `.env` with
every value masked except the non-secret kinds (ports, crons, versions, directories, flags).
Secrets are masked by name and the logs are filtered for token-shaped strings. It is still a
log dump: read it before sending it, because a log line carries whatever a target repository
printed.

Then compose the report. Title: one line, the symptom, not the guess. Body:

```
**What happened** — what the user did, and what the instance did instead.
**Expected** — in one sentence.
**Versions** — app, VERSION, bmad, harness CLIs (from the diagnostics file).
**Reproduce** — the smallest sequence, by command and by API call.
**Evidence** — the relevant log lines, and the Run id / step path if there is one.
**Diagnostics** — diagnostics/<timestamp>.md, attached.
```

Transport:

```bash
gh auth status && gh issue create --repo rebecamurillo/ai-orchestrator \
  --title "<title>" --body-file <file>
```

**The repository is private today.** If `gh auth status` fails, or the user has no access to
it, say so plainly: write the report to `issue.md` beside the diagnostics, hand them the
prefilled URL `https://github.com/rebecamurillo/ai-orchestrator/issues/new`, and tell them to
paste it and attach the diagnostics file themselves. Do not attach a diagnostics file to
anything the user has not read.

## The rest — `references/runbooks.md`

Rollback, backup and restore, secret rotation, models and defaults, spend reporting, garbage
collection, the harness tool allowlist, a harness CLI upgrade and template refresh are each a short runbook in
`references/runbooks.md`. Read the one the question is about; they carry the commands and the
consequences.

Customizing a workflow template to the project — adding a step, a checkpoint, a model per
step — is not an instance operation: `../orchestrator/references/workflows.md`.

## Connect a project

The `orchestrator` skill owns this end to end — Project, Repository, clone check,
`repo-init`. Your part is the instance side: `./install.sh doctor` green first, and
`kit/install.sh` run inside the project so its agents hold the matching skills.

## Rules

- `doctor` first, every time, before diagnosing anything by hand.
- Never stop a host, container or stack the user did not ask you to stop. Port conflicts are
  rebinds (hard rule 9).
- Run the script's command; do not hand-roll `docker compose` where a subcommand exists.
- Never print, log, commit or paste a secret. `diagnose` masks; you do not un-mask.
- The DBOS drain decision and the budget are the user's, always. Put the consequence in front
  of them and wait.
- Report what a command returned, including its failure output. Nothing in here retries
  silently.
- Say what is verified and what is not — the subscription gateway path, a `provisional` cost
  figure, a registry credential that only a pull proves.
