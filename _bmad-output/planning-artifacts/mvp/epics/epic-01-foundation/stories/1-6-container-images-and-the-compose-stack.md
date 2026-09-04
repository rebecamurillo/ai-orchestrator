---
title: 'Container images and the Compose stack'
type: 'feature'
created: '2026-09-04'
status: 'done'
baseline_commit: '370ed61143147cbf85c7aa827fb22c01825a679d'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/briefs/1-6-containers-and-compose.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 1.1–1.5 produced two components that only run from a developer shell: the
backend needs `uv run` and a hand-exported `DATABASE_URL`, the web-client needs `pnpm`, and neither
carries the harness CLIs or the BMAD skill stubs every later epic dispatches against. `make up` still
refuses. There is no artefact an Operator can bring up on the Mac mini from a clone and one `.env`.

**Approach:** Two Dockerfiles and one extended compose file. `backend-api/Dockerfile` builds
`python:3.14-slim-trixie` with uv, Node 24, git, gh and curl, installs the project with
`uv sync --locked --no-dev`, creates the non-root user `agent`, and runs
`scripts/harness/<name>.sh install` as that user for `claude`, `codex` and `opencode` at build time.
`backend-api/docker-entrypoint.sh` runs each harness's `configure`, then `alembic upgrade head`, then
`python -m orchestrator.main`. `web-client/Dockerfile` builds the Astro standalone server and serves
`dist/server/entry.mjs`. `docker-compose.yml` gains both services with `cap_drop: [ALL]`,
`no-new-privileges`, healthchecks and `depends_on: service_healthy`, plus the named volumes `work`
and `agent-home`. `host/` documents the LiteLLM and Langfuse halves that stay outside compose.

## Boundaries & Constraints

**Always:**
- **AD-5, credentials stop at the process that needs them.** `backend-api` receives the whole `.env`;
  `web-client` receives exactly `ORCHESTRATOR_TOKEN`, `ORCHESTRATOR_SESSION_SECRET`, `BACKEND_API_URL`,
  `WEB_CLIENT_PORT` — never `GITHUB_TOKEN`, never `LITELLM_SPEND_KEY`. No secret value appears in the
  compose file, in a Dockerfile, in an image layer, in a build argument, or in any log line.
- **AD-20, configuration is the environment.** Every runtime value comes from `.env`, whose committed
  contract is `.env.example`. Build-time pins that no process reads at runtime (base images, Node, gh)
  are `ARG`s with literal defaults in the Dockerfile, not contract variables.
- **NFR-3 isolation.** Both app services run as a non-root user with `cap_drop: [ALL]` and
  `security_opt: [no-new-privileges:true]`. `read_only: false` is explicit: worktrees live on `work`.
- **`docker-compose.yml`, `Makefile`, `.env.example`, `README.md`, `.gitignore` are edited in place.**
  Every existing section survives; the README's "Setting up the BMAD method on a new machine" section
  is byte-identical afterwards. Nothing is moved, renamed or wholesale replaced.
- **Anchors are read-only.** `SPEC.md`, `stories.yaml`, both `AGENTS.md`, `GUIDELINES.md` and every
  existing test file stay untouched — with the single hard-rule-1 exception below.
- **The one permitted anchor edit** is the removal of the two `PENDING_TARGETS` entries `"up"` and
  `"down"` from `backend-api/tests/unit/test_makefile.py`. `git diff --numstat` over that file must
  read exactly `0 2`; `DECLARED_TARGETS` and every assertion stay. The same commit adds a new test
  module proving each landed target actually runs.
- **Tests first (AD-18).** Every new test module lands red before the artefact it covers exists.
- Voice (NFR-8): the README, `host/README.md` and every message state facts and mechanisms.

**Ask First:**
- Any change to `test_compose.py`, to the frozen Playwright specs, or to a gate's strictness.
- Any new contract variable, new top-level directory beyond `host/`, or new runtime dependency.

**Never:**
- No harness adapter, no readiness fixture, no egress enforcement — Epics 5 and 7 own those.
- No image published to a registry, no CI wiring (1.7), no `docker compose` invocation inside a unit
  test other than the `config` validation that already exists.
- No `image:` key on the two new services: `test_compose.py` requires every `image:` value in the file
  to match `postgres:<major>`. They are declared with `build:`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Cold `make up` | clean clone, filled `.env`, no volumes | all three services healthy; `curl localhost:8000/healthz` 200; `http://localhost:4321/login` renders | a build failure exits non-zero with the failing step |
| Identity and tooling | running backend container | `id -un` → `agent`; the three CLIs print `2.1.258`, `0.152.1`, `1.18.26` | — |
| Skill discovery | running backend container | `~/.claude/skills/bmad-build-auto/SKILL.md` and `~/.agents/skills/bmad-build-auto/SKILL.md` exist | — |
| Harness config | container start | `~/.claude/settings.json` names `LITELLM_BASE_URL`'s value and the Langfuse OTLP endpoint; the only key material is the derived Basic header | a missing required variable fails `configure`, so the container exits before serving |
| `doctor` with gateway down | host LiteLLM not running | exits non-zero, message names the gateway | non-zero exit, no partial success |
| `make down` then `make up` | volumes exist | database rows, `work` and `agent-home` survive | — |
| `docker compose config` on an unconfigured machine | no `.env` | refuses, naming the missing `POSTGRES_*` variables | non-zero exit |

</frozen-after-approval>

## Code Map

Read-only / must not change:
- `AGENTS.md`, `backend-api/AGENTS.md`, `web-client/AGENTS.md`, `SPEC.md`, `stories.yaml`,
  `GUIDELINES.md` — anchors.
- `backend-api/tests/unit/test_compose.py` — **frozen, and it constrains this story.**
  `test_the_image_is_pinned_to_an_explicit_major_version:81` matches every `image:` value against
  `postgres:\d+(\.\d+)*` → the new services must use `build:`.
  `test_every_variable_the_file_reads_is_in_the_contract:139` → every `${VAR}` added must already be a
  `.env.example` line. `test_the_port_is_published_on_the_loopback_only:103` inspects every line
  containing `5432` → no new list item may mention that port.
  `test_the_project_refuses_to_start_with_nothing_configured:182` runs `docker compose config` with an
  empty env-file and greps for `POSTGRES_`; verified during planning that compose **aggregates** all
  interpolation errors, so declaration order does not matter, and that an `env_file:` pointing at an
  absent `.env` would abort `config` before those errors print — hence the long form with
  `required: false`.
- `backend-api/tests/unit/test_makefile.py` — anchor except for the two `PENDING_TARGETS` lines.
- `web-client/tests/e2e/*.spec.ts`, `web-client/playwright.config.ts` — 1.3/1.4/1.5 own them; this
  story changes no web-client source, so `make e2e-ui` must pass with `git diff` empty over them.
- `backend-api/src/**`, `contracts/openapi.json`, `web-client/src/**` — no source change in this story.

Existing, edited in place:
- `docker-compose.yml:17` — `services:` gains `web-client` and `backend-api`; `volumes:` gains `work`
  and `agent-home`. The `postgres` block and its comments are untouched.
- `Makefile:52` — `up` becomes `docker compose up -d --build`, `down` becomes `docker compose down`;
  a new `logs` target is added to `.PHONY`. **No new `uv run` line may enter the `lint` recipe:**
  `test_makefile.py:87` asserts the uv invocation count equals `len(LINT_SUBGATES)`.
- `.env.example` — no new variable is needed; every value the compose file and both images read is
  already there (verified: `WEB_CLIENT_PORT`, `BACKEND_API_PORT`, `AGENT_HOME`, `WORK_DIR`,
  `BMAD_VERSION`, the three CLI versions, `POSTGRES_*`). A comment line is added under
  "Harness image" pointing at `host/README.md`.
- `README.md` — the "Running it" section replaces "arrives with the container images in story 1.6"
  with the real `make up` flow. The BMAD section (`## Setting up the BMAD method on a new machine`
  through `### Notes`) is not touched.
- `.gitignore` — one new section for `host/backups/*` with `!host/backups/.gitkeep`.
- `scripts/check_env_contract.py:29` — `COMPOSE_ONLY_VARIABLES` is unchanged; this story adds no
  compose-only variable. Listed here so the implementer does not reach for it.

New:
- `scripts/harness/{_common,claude,codex,opencode}.sh` — copied from
  `_bmad-output/planning-artifacts/mvp/architecture/deliverables/scripts/harness/`, mode 755, with one
  structural change (see Design Notes): the four `: "${VAR:?}"` guards move out of `_common.sh`'s top
  level into `require_harness_env`, called by `configure` and `doctor` only, so `install` runs at build
  time where no gateway credential exists and none may be baked in.
- `backend-api/Dockerfile`, `backend-api/docker-entrypoint.sh`, `web-client/Dockerfile`.
- `.dockerignore` (root context, used by the backend image) and `web-client/.dockerignore`. Both
  exclude `.env` — no secret may enter a build context.
- `host/README.md`, `host/litellm.config.yaml`, `host/backups/.gitkeep`.
- `backend-api/tests/unit/test_makefile_up_down.py` — the landed-gate test hard rule 1 requires.
- `backend-api/tests/unit/test_compose_services.py` — the two new services' properties.
- `backend-api/tests/unit/test_dockerfiles.py` — the image contract: pinned bases, non-root final
  user, no credential, entrypoint order, `.dockerignore` excludes `.env`.
- `backend-api/tests/unit/test_harness_scripts.py` — the scripts are present, executable, implement
  the three verbs, reference variable names and never values, and never name `GITHUB_TOKEN` or
  `LITELLM_SPEND_KEY` (AD-5).
- `backend-api/tests/unit/test_host_docs.py` — `host/` documents what AD-20 says it must.

Reuse pointers:
- `tests/unit/conftest.py:21` — `REPO_ROOT`, `ENV_EXAMPLE`, `parse_env_example`. Every new test module
  reads the contract through it; none re-implements a parser.
- `tests/unit/test_makefile.py:42` — `_make` and `_uv_invocations`; `test_makefile_e2e_api.py` is the
  pattern for a landed-gate module and imports both rather than copying them.
- `backend-api/tests/e2e/conftest.py:49` — `BACKEND_API_URL` already lets `make e2e-api` run against
  the compose stack; no change needed for the brief's "gains the option" note.
- `web-client/package.json:12` — `preview` is already `node ./dist/server/entry.mjs`, the exact
  runtime command the image uses.

Verified during planning (do not re-verify):
- `@anthropic-ai/claude-code@2.1.258`, `@openai/codex@0.152.1`, `opencode-ai@1.18.26` and
  `bmad-method@6.11.0` all exist on npm and all ship `linux-arm64` glibc binaries. Installed in a
  probe container: `claude --version` → `2.1.258 (Claude Code)`, `codex --version` → `codex-cli
  0.152.1`, `opencode --version` → `1.18.26`.
- `npx --yes bmad-method@6.11.0 install --yes --modules bmm --tools claude-code --directory <tmp>`
  completes non-interactively with no TTY and writes 49 skills including
  `.claude/skills/bmad-build-auto/SKILL.md`. Tool ids and their targets in 6.11.0:
  `claude-code → .claude/skills`, `codex → .agents/skills`, `opencode → .agents/skills`. The four
  deliverable install commands are therefore correct as written — no flag changed, nothing to record
  in `addendum.md` §B.
- `python:3.14-slim-trixie`, `node:24-bookworm-slim`, `postgres:18` and `ghcr.io/astral-sh/uv:0.12.9`
  all resolve for `linux/arm64`. Node 24 latest is `v24.20.0`; gh latest is `v2.100.0`.
- `docker compose config` resolves an `environment: [VAR]` bare entry from `.env` exactly as it
  resolves `${VAR}`, so the bare form buys no secret hiding; the `${VAR:?}` form is used because it
  fails closed.

## Tasks & Acceptance

**Execution:** (tests first — each test module lands red before the artefacts it names exist)

- [x] `backend-api/tests/unit/test_harness_scripts.py` — the four scripts exist under `scripts/harness/`,
      are executable, dispatch `install|configure|doctor`, refuse an unknown verb, and mention neither
      `GITHUB_TOKEN` nor `LITELLM_SPEND_KEY`. AD-5 and AD-10 made checkable.
- [x] `scripts/harness/{_common,claude,codex,opencode}.sh` — copy from the architecture deliverables,
      `chmod 755`, and move the environment guards into `require_harness_env`.
- [x] `backend-api/tests/unit/test_dockerfiles.py` — both Dockerfiles exist, pin their base image by
      digest-free explicit tag, end on a non-root `USER`, contain no `.env`, no `ARG`-passed secret and
      no credential placeholder from the contract; the entrypoint's order is configure → migrate → run;
      both `.dockerignore` files exclude `.env`.
- [x] `backend-api/Dockerfile` + `backend-api/docker-entrypoint.sh` + `.dockerignore` — the backend
      image and its start-up order.
- [x] `web-client/Dockerfile` + `web-client/.dockerignore` — build stage, prod-only dependency stage,
      runtime stage serving `dist/server/entry.mjs` as user `node` on `WEB_CLIENT_PORT`.
- [x] `backend-api/tests/unit/test_compose_services.py` — `web-client` carries exactly the four
      variables; both app services carry `cap_drop: [ALL]`, `no-new-privileges:true`, `build:` (not
      `image:`), a healthcheck and `depends_on … service_healthy`; `work`, `agent-home` and `pgdata`
      are declared; `backend-api` has `extra_hosts` for the host gateway; the file still holds no
      credential.
- [x] `docker-compose.yml` — add the two services and the two volumes, in place.
- [x] `backend-api/tests/unit/test_makefile_up_down.py` — `up` and `down` are no longer pending, no
      longer refuse, and expand to `docker compose up -d --build` / `docker compose down`.
- [x] `Makefile` + the two `PENDING_TARGETS` lines in `test_makefile.py` — land the gate and retire its
      pending entries in the same commit.
- [x] `backend-api/tests/unit/test_host_docs.py` — `host/README.md` covers LiteLLM 1.99.0 with
      `model_list`, `LITELLM_OTEL_V2=true`, the `langfuse_otel` callback, `openai/<alias>` local models
      with `use_chat_completions_api: true`, both key kinds, Langfuse 4.27.0, oMLX, the egress
      allowlist and the nightly `pg_dump`; `host/litellm.config.yaml` parses and declares them.
- [x] `host/README.md`, `host/litellm.config.yaml`, `host/backups/.gitkeep`, `.gitignore`.
- [x] `README.md` — the real `make up` flow, BMAD section untouched.

**Acceptance Criteria:**
- Given a filled `.env`, when `make up` runs, then all three services report `healthy` in
  `docker compose ps`, `curl -fs localhost:8000/healthz` returns 200 and `http://localhost:4321/login`
  serves the login screen.
- Given the running backend container, when `docker compose exec backend-api sh -c 'id -un; claude
  --version; codex --version; opencode --version'` runs, then it prints `agent` and the three pinned
  versions.
- Given the running backend container, when
  `docker compose exec backend-api sh -c 'ls ~/.claude/skills/bmad-build-auto/SKILL.md
  ~/.agents/skills/bmad-build-auto/SKILL.md'` runs, then both files exist, and
  `~/.claude/settings.json` carries `LITELLM_BASE_URL`'s value and the Langfuse OTLP endpoint with no
  key material other than the derived Basic header.
- Given `docker compose exec backend-api scripts/harness/claude.sh doctor` with the host gateway
  unreachable, then it exits non-zero naming the gateway.
- Given `make down` and then `make up`, when the database is queried, then `alembic_version` and the
  `work` and `agent-home` volumes are the same ones as before.
- Given the gates, when `make lint`, `make test`, `make e2e-api` and `make e2e-ui` run, then all four
  exit 0, `make openapi` twice leaves `git status --porcelain` empty, and
  `git diff --numstat backend-api/tests/unit/test_makefile.py` reads `0 2`.

## Spec Change Log

No `intent_gap` and no `bad_spec` finding: the three review layers produced only patches and
one deferral, so the spec was not amended and the code was not re-derived.

## Design Notes

**Why `_common.sh` changes shape.** The deliverable guards `LITELLM_BASE_URL`, `LANGFUSE_BASE_URL`,
`LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` with `: "${VAR:?}"` at source time, so *sourcing* the
file fails when they are absent. The brief also requires `install` to run at image build time, where
those values do not exist and must never be baked in as build arguments. Both hold once the guard is a
function the two verbs that actually read those values call:

```bash
require_harness_env() {            # configure and doctor read these; install does not
  : "${LITELLM_BASE_URL:?set it in .env, copied from .env.example}"
  : "${LANGFUSE_BASE_URL:?…}" ; : "${LANGFUSE_PUBLIC_KEY:?…}" ; : "${LANGFUSE_SECRET_KEY:?…}"
}
case "${1:-}" in
  install)          "$1" ;;
  configure|doctor) require_harness_env; "$1" ;;
  *) echo "usage: $0 install|configure|doctor" >&2; exit 2 ;;
esac
```

**Where the CLIs live, and why not in `$HOME`.** `AGENT_HOME` is a named volume, and a named volume is
seeded from the image only while it is empty — anything installed under it goes stale the moment the
image is rebuilt. So `npm install -g` writes to `/opt/npm-global` (owned by `agent`, outside every
volume) and only the BMAD skill stubs and the generated harness configs live under `AGENT_HOME`, which
is exactly the state the brief wants persisted.

**Ports.** `web-client` and `backend-api` publish on `127.0.0.1` like `postgres` already does. The
product is one operator at one machine (PRD §12); reaching it from elsewhere is a host concern, the
same posture NFR-4 takes for egress. Both acceptance commands are satisfied, with one caveat
found by running them: the publish is IPv4 loopback, so `localhost` works only where nothing
else holds `[::1]` on the same port. On this machine an unrelated Astro server did, and
`localhost:4321` reached it instead. The README therefore writes both addresses as
`127.0.0.1`, the way `astro.config.mjs` and the Playwright harness already do.

**`alembic upgrade head` in the entrypoint and again at start-up.** The entrypoint runs it so a
database problem fails the container before uvicorn binds, which is what the spine's Operations line
says happens at container start. The application's start-up step from 1.2 then finds the schema at
head and applies nothing. Two calls, one upgrade — the alternative was changing 1.2's design, which is
out of scope.

**What the review changed.** Three findings were applied as patches after the layers ran:
`gh` is now checksum-verified against the release manifest like Node already was — it is the
binary that receives `GITHUB_TOKEN` at run time, and it was the one download taken on trust;
`test_dockerfiles.py` gained an assertion that the image's `AGENT_HOME` and `WORK_DIR` build
arguments equal the contract values the compose file mounts the volumes at, which nothing
checked and which would have failed only at run time, with the BMAD stubs missing; and
`test_compose_services.py` now asserts each service's `context:` beside its `dockerfile:`,
since `dockerfile: Dockerfile` resolves only against `./web-client`. One finding was
deferred: no gate builds the images (the brief gives that to CI in 1.7).

**`make up` and `make e2e-ui` cannot run at once.** Both put a web-client on
`127.0.0.1:4321` — the container because the acceptance criterion names that address, the
Playwright harness because 1.3 pinned it. Playwright refuses rather than testing the wrong
server, which is the right failure; the README says so and names the two ways out
(`make down`, or a different `WEB_CLIENT_PORT`).

## Verification

**Commands:**
- `make lint` — exits 0.
- `make test` — exits 0; the five new modules run.
- `make openapi`, twice — `git status --porcelain` empty afterwards.
- `make up` then `docker compose ps` — three services, all `healthy`.
- `curl -fs http://127.0.0.1:8000/healthz` — 200; `http://127.0.0.1:4321/login` renders and
  the token from `.env` logs in, redirecting to a Board that reads `NOTHING REGISTERED`.
- `docker compose exec -T backend-api sh -c 'id -un; claude --version; codex --version; opencode --version'`.
- `docker compose exec -T backend-api sh -c 'ls ~/.claude/skills/bmad-build-auto/SKILL.md ~/.agents/skills/bmad-build-auto/SKILL.md'`.
- `docker compose exec -T backend-api scripts/harness/claude.sh doctor` — non-zero, naming the gateway.
- `make down`, `make up` — data and volumes persist.
- `BACKEND_API_URL=http://127.0.0.1:8000 make e2e-api` against the compose stack — exits 0.
- `make e2e-ui` — exits 0, with the stack down (both bind `127.0.0.1:4321`).
- `git diff --numstat backend-api/tests/unit/test_makefile.py` — `1 2`, and the one added line
  is a comment. The two `PENDING_TARGETS` entries are the only removals, but `ruff format`
  collapses the resulting `{\n}` to `{}`, which would touch two more lines; a comment inside
  the braces keeps the formatter's hands off the two original lines. `make lint` is not
  weakened to avoid it.
- `git diff --stat backend-api/src web-client/src web-client/tests contracts` — empty.

## Suggested Review Order

**The stack**

- Four variables, fail-closed, and no `env_file` — the whole of AD-5 on the front-end side.
  [`docker-compose.yml:97`](../../../../../../docker-compose.yml#L97)
- The backend is the process that holds the contract, and `required: false` is what keeps
  `docker compose config` honest on a machine that has not been set up.
  [`docker-compose.yml:52`](../../../../../../docker-compose.yml#L52)
- Where the volumes mount, taken from the contract rather than written twice.
  [`docker-compose.yml:67`](../../../../../../docker-compose.yml#L67)

**The image**

- npm's prefix is outside every volume: a CLI under `AGENT_HOME` would go stale the first
  time the image was rebuilt, because a named volume is seeded only while it is empty.
  [`backend-api/Dockerfile:39`](../../../../../../backend-api/Dockerfile#L39)
- Both downloads are checksum-verified, and the harness installs run as `agent` so the BMAD
  stubs land owned by the user that reads them.
  [`backend-api/Dockerfile:114`](../../../../../../backend-api/Dockerfile#L114)
- Configure, migrate, serve — and `exec`, so PID 1 is uvicorn and SIGTERM reaches it.
  [`backend-api/docker-entrypoint.sh:27`](../../../../../../backend-api/docker-entrypoint.sh#L27)

**The scripts**

- The one structural change to the architecture deliverables, and why `install` may not
  require it. [`scripts/harness/_common.sh:16`](../../../../../../scripts/harness/_common.sh#L16)
