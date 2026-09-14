# Deploying ai-orchestrator

The procedure for running this system on the machine that does real work, as opposed to the
stack you develop against. `README.md` covers the development stack; this file covers the
production one, and the two differ in four places only — where the images come from, which
environment file is read, what the health probes prove, and what has to happen before a
release that changes the walker.

Production here is what PRD §12 and NFR-7 say it is: **one operator, one machine** — an
Apple Silicon Mac mini running the compose stack, with LiteLLM, Langfuse and the model
server beside it on the host (`host/README.md`). There is no cluster, no second replica and
no load balancer, and several decisions below are only correct because of that. Where one of
them stops being correct at two replicas, it says so.

---

## 1. What is published, and where

`.github/workflows/release.yml` builds both images and pushes them to GHCR when a `v*` tag
is pushed:

```
ghcr.io/optimai-labs/ai-orchestrator/backend-api:<tag>
ghcr.io/optimai-labs/ai-orchestrator/web-client:<tag>
```

Each image is pushed under two names — the release tag, and `sha-<commit>`. There is
deliberately **no `latest`**. A host running `latest` cannot answer which version it is
running, and that is the first question every rollback and every incident starts with.

Both images carry `org.opencontainers.image.revision` and `.version` labels, so the host can
answer that question without the registry:

```bash
docker inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}} {{index .Config.Labels "org.opencontainers.image.revision"}}' \
  ghcr.io/optimai-labs/ai-orchestrator/backend-api:v1.2.0
```

The images are built for `linux/arm64` only, on a native arm64 runner. `backend-api/Dockerfile`
picks its Node and `gh` archives from `dpkg --print-architecture`, and the deployment target
is Apple Silicon; an amd64 image would run under emulation or not at all.

The repository is private, so the packages are private. The host authenticates to the
registry with a token held in its own docker config — the **docker daemon's** credential, not
a container's environment. No container process receives it, so AD-5 is untouched: the one
credential a *process* holds is still `ORCHESTRATOR_TOKEN`.

---

## 2. The compose invocation

Production is `docker-compose.yml` plus the `docker-compose.prod.yml` overlay, under a
project name of its own. Note what the base file gives every stack that runs real agents,
production included: a harness may `sudo apt-get` what a target repository's install
script needs (the `backend-api` block in `docker-compose.yml` states the trade). Rather
than repeat the flags on every line, export the three variables compose reads — the same
three `make e2e` exports for the gate's stack — once per shell session on the host:

```bash
cd /path/to/ai-orchestrator
export COMPOSE_PROJECT_NAME=aio-prod
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
export COMPOSE_ENV_FILE=.env.prod
```

Every `docker compose` command in this file assumes those are set. **A command run without
them targets the development stack**, reads `.env`, and writes to a different set of volumes.

The project name is what separates production's `pgdata`, `work` and `agent-home` from any
other stack on the machine. It is not cosmetic: docker namespaces volumes by project, and
two projects sharing a name share their data.

---

## 3. First install

### 3.1 Prerequisites on the host

- Docker Desktop, started at login.
- The host stack — LiteLLM, Langfuse, the model server — up and reachable, per
  `host/README.md`. `make host-up` and `make host-doctor` are the same on this machine as
  on any other.
- A GitHub token with `read:packages`, for pulling the images:

  ```bash
  echo "$GHCR_TOKEN" | docker login ghcr.io -u <github-username> --password-stdin
  ```

### 3.2 The checkout

The host needs a checkout, because the compose files, `host/` and the backup script live in
it. Check out **the same tag the images were built from**:

```bash
git clone https://github.com/OptimAI-labs/ai-orchestrator.git
cd ai-orchestrator
git checkout v1.2.0
```

A checkout at one tag running images from another is the failure this line exists to prevent:
the compose files and the image would disagree about ports, volumes and settings, and nothing
would report it.

### 3.3 The environment

`.env.example` is the one contract (AD-20). Production copies it like every other environment
and fills it in:

```bash
cp .env.example .env.prod
chmod 600 .env.prod
```

Then set every value that must not stay a placeholder:

| Variable | How to produce it | What a placeholder costs |
| --- | --- | --- |
| `ORCHESTRATOR_SECRET_KEY` | `python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` | The stack starts and `/healthz` is green, but **every** read and write of `/api/v1/projects` answers 500, with the reason only in the logs |
| `ORCHESTRATOR_TOKEN` | `openssl rand -hex 24` | The one login credential is the committed one |
| `ORCHESTRATOR_SESSION_SECRET` | `openssl rand -hex 32` | Session cookies are forgeable |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` | — set `DATABASE_URL` to the same password in the same edit; they are two spellings of one fact |
| `GITHUB_TOKEN` | a PAT with repo access | Clones and pushes fail |
| `LITELLM_API_KEY` | a virtual key, `key_type: llm_api` (`host/README.md`) | No harness can reach a model |
| `LITELLM_SPEND_KEY` | master or `proxy_admin_viewer` key | No budget or cost readings |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | from the Langfuse project | No traces |

Set `LANGFUSE_ENVIRONMENT=production`, so production traces are not read as a developer's on
the shared tracing server.

Then append the two values that configure the docker CLI rather than the application, and so
are deliberately not in the contract:

```bash
cat >> .env.prod <<'EOF'

# ── Compose project and image tag (docker CLI, not application settings) ────
COMPOSE_PROJECT_NAME=aio-prod
IMAGE_TAG=v1.2.0
EOF
```

`IMAGE_TAG` is what the overlay substitutes into both `image:` lines. **It is the single
place this host records which version it runs**, and changing it is what an upgrade and a
rollback both are.

#### `POSTGRES_DB` is fixed the moment the volume is created

The postgres image honours `POSTGRES_DB` only when it initialises an empty data directory.
Once `aio-prod_pgdata` exists, editing `POSTGRES_DB` creates nothing: the old database stays,
the new name does not exist, and backend-api crash-loops on `alembic upgrade head` with
`FATAL: database "…" does not exist` while postgres itself reports healthy under the base
file's probe. Choose the name now — `orchestrator` is fine — and treat it as immutable for
the life of the volume. Changing it later means a dump, a fresh volume, and a restore.

#### Preflight: the environment file has every variable the release needs

A release that adds a setting adds it to `.env.example` (AD-20, enforced by `make lint`). It
cannot add it to your `.env.prod`. Check before deploying, not at container start:

```bash
comm -13 <(grep -oE '^[A-Z_]+=' .env.prod   | tr -d '=' | sort) \
         <(grep -oE '^[A-Z_]+=' .env.example | tr -d '=' | sort)
```

Anything printed is a contract variable missing from production. Empty output is the pass.

`scripts/check_env_contract.py` is deliberately **not** used here: it compares the contract
against the typed `Settings` fields, and would report `COMPOSE_PROJECT_NAME` and `IMAGE_TAG`
as unknown extras. The comparison above is the one that answers the production question.

### 3.4 Bring it up

```bash
docker compose pull
docker compose up -d --no-build --wait
```

`--no-build` is not optional. `docker-compose.yml` carries a `build:` stanza, and compose
cannot unset it from an overlay; without the flag, a tag that failed to pull is silently
built from the working tree instead, and the running container stops being the artefact CI
produced. `--wait` blocks until every service is healthy, so a failed start is the command's
exit code rather than something you find later in `docker compose ps`.

The first start runs `alembic upgrade head` in `docker-entrypoint.sh` before uvicorn binds,
seeds the shipped templates, and launches the durable engine. It takes longer than later
starts.

### 3.5 Verify

```bash
docker compose ps                                    # three services, all healthy
curl -fsS http://127.0.0.1:8000/healthz              # {"status":"ok", …}
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c 'select * from alembic_version'                 # the revision this release expects
docker compose exec -T backend-api scripts/harness/claude.sh doctor
```

Then open `http://127.0.0.1:4321/login` and sign in with `ORCHESTRATOR_TOKEN`.

Both ports are published on `127.0.0.1` only, in production as in development. Reaching the
stack from another machine is a host decision — a tunnel — not a compose one.

---

## 4. Cutting a release

1. Merge to `main`. Let `ci.yml` finish; every gate must be green.
2. Tag that commit and push the tag:

   ```bash
   git checkout main && git pull
   git tag -a v1.2.0 -m 'v1.2.0'
   git push origin v1.2.0
   ```

3. `release.yml` runs. Its first job refuses to publish anything unless a `ci.yml` run
   concluded successfully **for that exact commit** — a tag is a claim that a commit is
   releasable, and this is the only thing that can settle the claim. Its second job builds
   and pushes both images.

Nothing deploys itself. Publishing an image and running it are separate acts, performed by
different people at different times, and the host decides when.

---

## 5. Upgrading a running host

### 5.1 Decide whether this release needs a drain — before anything else

This is the step with real consequences, and it cannot be automated away.

`DBOS_APPLICATION_VERSION` pins the walker's step sequence (AD-6). The durable engine will
not resume a workflow that was started under a different version, so **bumping it makes every
in-flight Run unrecoverable.** The rule is: bump it only when the walker's step sequence
changed, and only after draining.

So, for each release, answer one question: *does this release change the walker's step
sequence?* If it does, the release notes must say so and `DBOS_APPLICATION_VERSION` must be
bumped in `.env.prod` as part of the upgrade — after draining. If it does not, leave the
value alone and skip to §5.2.

Draining means: no Run in `queued`, `running` or `needs_you`.

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -tAc "select status, count(*) from run group by status order by 1"
```

**A parked Run cannot be waited out.** A Run in `needs_you` is waiting for the operator, and
`HUMAN_WAIT_SECONDS` gives it 30 days to wait; it holds its queue slot the whole time
(AD-12). There is no version of "wait for it to finish" that terminates. Before a
walker-changing release you have exactly two options, and both are yours to choose
deliberately:

- **Answer or cancel every parked Run**, then bump. Nothing is lost.
- **Bump anyway**, accepting that those Runs will not resume. They are not corrupted, but the
  engine will not pick them up; treat them as cancelled.

Schedule walker-changing releases for a moment when the board is clear. This is a design
consequence of durable workflows meeting human checkpoints, not something the deployment
procedure can solve.

### 5.2 Back up first

The nightly dump is not a pre-deploy dump. A migration runs seconds after `up`, and the only
thing standing between a bad one and data loss is a dump taken immediately before it:

```bash
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  > "host/backups/pre-v1.2.0-$(date -u +%Y%m%dT%H%M%SZ).sql"
```

`host/README.md` describes the nightly cron. On a production host that script must export the
three `COMPOSE_*` variables of §2 before it runs — without them it targets whatever compose
defaults to, which is not this stack.

### 5.3 Deploy

```bash
git fetch --tags && git checkout v1.2.0        # compose files at the release
sed -i '' 's/^IMAGE_TAG=.*/IMAGE_TAG=v1.2.0/' .env.prod
comm -13 <(grep -oE '^[A-Z_]+=' .env.prod | tr -d '=' | sort) \
         <(grep -oE '^[A-Z_]+=' .env.example | tr -d '=' | sort)   # must print nothing
docker compose pull
docker compose up -d --no-build --wait
```

Migrations need no step of their own. `alembic upgrade head` reads `public.alembic_version`
and applies only the revisions that are not yet applied — at head it executes no DDL at all.
It runs twice per start, in the entrypoint and again as the application's start-up step; the
second call finds the schema current and does nothing. The ordering is what matters and it
already fails closed: schema, then seeds, then the engine, then uvicorn binds. A migration
that fails aborts start-up instead of serving a half-migrated schema.

That guarantee holds because there is one backend container. `alembic/env.py` takes no
advisory lock, so two containers starting at once would race the upgrade. Do not scale
`backend-api` past one replica without adding one.

Then re-run the checks in §3.5.

---

## 6. Rollback, and what it actually costs

**Read this before you need it.** Rollback is not symmetric with deployment, and the
procedure will not pretend otherwise.

Migrations run forward automatically and are never run backward. So re-pointing `IMAGE_TAG`
at the previous release leaves the schema at the newer head while the older code expects the
older one. Alembic is expected to refuse this outright — the version table holds a revision
its script directory does not contain — and fail start-up with `Can't locate revision
identified by …` rather than run against a schema it does not understand. That is the safe
failure, and it is also a blocked rollback. *(Expected from how Alembic resolves revisions;
worth confirming once on a scratch stack rather than discovering during an incident.)*

Which leaves two real cases:

**The release added no migration, or only backward-compatible ones.** Rollback is a tag
change:

```bash
sed -i '' 's/^IMAGE_TAG=.*/IMAGE_TAG=v1.1.0/' .env.prod
git checkout v1.1.0
docker compose pull && docker compose up -d --no-build --wait
```

**The release migrated the schema in a way the old code cannot read.** There is no rollback,
only a restore, and you lose everything written since the dump:

```bash
docker compose down
docker volume rm aio-prod_pgdata          # deliberate and irreversible
docker compose up -d --no-build --wait postgres
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < host/backups/pre-v1.2.0-….sql
sed -i '' 's/^IMAGE_TAG=.*/IMAGE_TAG=v1.1.0/' .env.prod
git checkout v1.1.0
docker compose up -d --no-build --wait
```

The way to keep the second case rare is a rule about how migrations are written, not
anything in this file: **expand and contract**. Add a nullable column, backfill it, ship the
code that uses it, and drop the old one in a *later* release. Every release then rolls back
by changing one line. A release that renames or drops in the same revision as the code that
needs the change has traded its rollback for a day's convenience, and the trade should be
made knowingly and named in the release notes.

A restore that has never been performed is not a backup. Rehearse it once on a scratch
project before you depend on it:

```bash
docker compose -p aio-restore-test -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file .env.prod up -d postgres
```

---

## 7. Routine operations

```bash
docker compose logs -f                       # follow; rotation is 10 MB × 5 per service
docker compose ps                            # health
docker compose restart backend-api           # re-read MAX_ACTIVE_RUNS and the other
                                             # restart-scoped settings (AD-12)
docker compose down                          # stop; pgdata, work and agent-home survive
```

`docker compose down -v` deletes all three volumes. On this host that is the database.

Changing `MAX_ACTIVE_RUNS` is a restart, not a `DBOS_APPLICATION_VERSION` bump — the spine is
explicit about the difference, and treating one as the other is how in-flight Runs get lost
for no reason.

---

## 8. What this procedure does not yet cover

Named here rather than left to be discovered:

- **`/healthz` cannot tell you what is deployed.** `backend-api/pyproject.toml` pins
  `version = "0.1.0"` statically and `/healthz` echoes it, so every release reports the same
  string. Until that is wired to the release tag, version identity on the host comes from
  `IMAGE_TAG` and the image's OCI labels (§1) — not from the API.
- **No migration lock.** Correct at one replica; a prerequisite for ever having two.
- **Nothing catches a forgotten `DBOS_APPLICATION_VERSION` bump.** The coupling in §5.1 is
  enforced by whoever writes the release notes. A CI check that hashes the walker's step
  sequence and fails when it changed without the pin changing would turn the worst failure
  mode in this system into a red build.
- **The arm64 runner label is unverified for this plan.** `release.yml` uses
  `ubuntu-24.04-arm`; if the first release run cannot find it, the fallback is documented in
  a comment in that file.
- **No post-deploy smoke test.** §3.5 is a manual checklist. `make e2e-api` is not it — its
  guard refuses any database but the gate's own, by design, and it writes fixtures it never
  removes.

---

## Running without the host services

Both host services — the LiteLLM Gateway and Langfuse — are optional. Each is controlled by
a single environment variable in `.env`. Setting either variable to blank (empty string, not
deleted) disables the corresponding service without refusing start-up.

| Variable | Blank → | Unset → |
| --- | --- | --- |
| `LITELLM_BASE_URL` | Gateway disabled, spend is provisional | start-up refuses with a configuration error |
| `LANGFUSE_BASE_URL` | Tracing disabled, no trace links | start-up refuses with a configuration error |

Both can be blanked together to run the full stack with no host services at all.

### What changes with Gateway disabled (`LITELLM_BASE_URL=`)

- **Cost is provisional.** The backend cannot read spend from LiteLLM; every attempt's cost
  figure comes from the harness's own accounting and is marked `provisional` in the Run detail
  (`cost.trace_url` null, `cost.provisional` true). The "provisional" marker is visible beside
  the spent/budget ratio in the UI.
- **`local` model is unavailable.** The Gateway is what routes `local-coder` and
  `local-general`; with it absent, those names are refused at harness readiness time with
  the reason stated.
- **Harness authentication.** Without the Gateway the harness authenticates directly against
  the upstream provider. For `claude`: log in once inside the container —
  `docker exec -it <backend-api-container> claude login` (interactive terminal required), or
  create a Project and set `ANTHROPIC_API_KEY` there. The credential is stored under
  `AGENT_HOME`, which is a named volume and survives `make down`. No credential is printed
  or stored in any log or file in this repository.
- **Stack logs** `"gateway disabled"` at start-up (with `spend="provisional"`).

### What changes with tracing disabled (`LANGFUSE_BASE_URL=`)

- **No traces, no trace links.** The backend's tracer is a no-op; no spans are sent. Every
  Run's `cost.trace_url` is null, and the trace row in the COST & TRACE block is absent
  entirely (no row, no placeholder). The `trace` cell in the history table reads "—".
- **Stack logs** `"tracing disabled"` at start-up (with `traces="absent"`).

### Running both disabled together

Set both to blank in `.env`:

```
LITELLM_BASE_URL=
LANGFUSE_BASE_URL=
```

Restart the backend: `docker compose restart backend-api`. Both log events — `"gateway disabled"`
and `"tracing disabled"` — appear in the start-up output. The stack serves normally; cost
figures are provisional and trace links are absent throughout.

### Operator run result

_Recorded here after the Operator completes the verification run described in story 9-6._
