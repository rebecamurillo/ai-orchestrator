---
title: Install
kind: procedure
audience: host
readme: install
---

Local agent on the host or the user only.

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

### For the host agent

Two prompts, and that is deliberate. The first is a GitHub token: a classic PAT. `read:packages`
pulls the two private images; add `repo` if the same token will be the credential the
orchestrator uses to clone and push the repositories registered in it — the usual case, and
there are no per-repository credentials. `docker login ghcr.io` must already have happened for
the bootstrap that produced these files; the script does its own login for the pulls. The second
is the gateway and tracing values, all optional. Blank keeps the gateway, or tracing, off: each
agent then authenticates on its own, cost figures are provisional, trace links are absent, and
the `local` harness does not exist. The starter platform is in the repository, not the folder
(README.md § Getting an LLM platform); the user runs it.

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

Never echo a generated secret back to them beyond the one line the script already prints (the
login token). `./install.sh env` re-renders `.env` without touching the stack; it will not
overwrite an existing file, so starting over means deleting it deliberately.

After the install, the first-run flow is `projects` and `runs/first-run`: create a Project,
register a Repository, run its clone check, `repo-init` if the repository is new to BMAD.
