---
story: "1-6"
epic: 1
title: Container images and the Compose stack
requirements: [NFR-3, NFR-4, NFR-7, AR-1, AR-6, AR-14 (scripts placement), AR-21, AR-26]
binds: [AD-5, AD-10, AD-16, AD-20]
---

# Story 1.6 — Container images and the Compose stack

As the Operator,
I want `make up` on the Mac mini to bring up the whole MVP from a clone with one `.env`, with the three harness CLIs and the BMAD skill stubs already inside the backend image,
So that the stack exists once, is configured only by the environment, and a harness readiness run can be attempted the moment its adapter lands.

## Scope

**In:** `backend-api/Dockerfile`, `web-client/Dockerfile`, full `docker-compose.yml`, entrypoint, `scripts/harness/{_common,claude,codex,opencode}.sh` placed and executed at build and start, `host/README.md`, `host/litellm.config.yaml`, `make up` / `make down`, `.env.example` complete for compose.
**Out:** harness adapters (Epics 5, 7); the readiness fixture (Epic 5); egress enforcement (NFR-4 stays a documented host rule).

## Binding rules (inlined)

- **backend-api image (Structural Seed, Stack).** Base `python:3.14-slim-trixie`; install uv 0.12.9, Node 24 (for the CLIs and `npx bmad-method`), git, gh, curl, ca-certificates; `uv sync --locked --no-dev`; create user `agent` with `HOME=$AGENT_HOME` (`/home/agent`); run `scripts/harness/<name>.sh install` for `claude`, `codex`, `opencode` as `agent` at build time (installs Claude Code 2.1.258, Codex 0.152.1, OpenCode 1.18.26 globally and copies the BMAD 6.11.0 skill stubs to `~/.claude/skills` and `~/.agents/skills`); final `USER agent`.
- **Entrypoint order:** `scripts/harness/<name>.sh configure` for each harness → `alembic upgrade head` → `python -m orchestrator.main`. Configure writes only under `AGENT_HOME` from environment variable names (AD-10); it fails fast if a required variable is missing.
- **web-client image.** `node:24-bookworm-slim`, `pnpm install --frozen-lockfile`, `pnpm build`, runtime `node ./dist/server/entry.mjs` on `WEB_CLIENT_PORT`.
- **Compose (NFR-7).** Services `web-client` (port 4321), `backend-api` (port 8000, `extra_hosts: host.docker.internal:host-gateway`), `postgres` (`postgres:18`, volume `pgdata`); named volumes `work` (mounted at `WORK_DIR`) and `agent-home` (mounted at `AGENT_HOME`); `env_file: .env`; for both app services `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, `read_only: false` (worktrees live on the volume), healthchecks on `/healthz` and `/login`; `depends_on` with `condition: service_healthy`.
- **Credentials stop at the process that needs them (AD-5).** The compose file passes the whole `.env` to backend-api; the web-client service receives only `ORCHESTRATOR_TOKEN`, `ORCHESTRATOR_SESSION_SECRET`, `BACKEND_API_URL`, `WEB_CLIENT_PORT`. Nothing in the compose file contains a secret value.
- **Host side (AD-20).** `host/README.md` documents: LiteLLM 1.99.0 with `model_list`, `LITELLM_OTEL_V2=true` and the `langfuse_otel` callback, local models as `openai/<alias>` with `use_chat_completions_api: true`, the two keys (`LITELLM_API_KEY` generated with `key_type: llm_api`; `LITELLM_SPEND_KEY` = master or `proxy_admin_viewer`), Langfuse v4.27.0, oMLX, the egress allowlist as a firewall rule, the nightly `pg_dump` cron into `host/backups/` keeping 14 days. `host/litellm.config.yaml` is the starting config.
- **`.env.example`** stays the single contract: every variable compose or either image reads has a line and a comment.

## Acceptance criteria

**Given** a clean clone and a filled `.env`
**When** `make up` runs
**Then** within 30 minutes on the Mac mini all three services are healthy, `curl localhost:8000/healthz` returns 200, and `http://localhost:4321/login` accepts the token.

**Given** the running backend container
**When** `docker compose exec backend-api sh -c 'id -un; claude --version; codex --version; opencode --version'` runs
**Then** it prints `agent` and the three pinned versions.

**Given** the running backend container
**When** `docker compose exec backend-api sh -c 'ls ~/.claude/skills/bmad-build-auto/SKILL.md ~/.agents/skills/bmad-build-auto/SKILL.md'` runs
**Then** both files exist and `~/.claude/settings.json` references `LITELLM_BASE_URL`'s value and the Langfuse OTLP endpoint but contains no key value other than the Basic auth header derived from the Langfuse keys.

**Given** `docker compose config`
**When** inspected
**Then** `web-client` has exactly the four variables above, both app services carry `cap_drop: [ALL]` and `no-new-privileges`, and volumes `work`, `agent-home`, `pgdata` are declared.

**Given** `docker compose exec backend-api scripts/harness/claude.sh doctor`
**When** the host gateway is reachable
**Then** it exits 0 printing the version, skill discovery, and gateway lines; when unreachable it exits non-zero naming the gateway.

**Given** `make down`
**When** run and then `make up` again
**Then** the database and the `work` and `agent-home` volumes persist.

## Implementation notes

- Copy the four scripts from `_bmad-output/planning-artifacts/mvp/architecture/deliverables/scripts/harness/` to `scripts/harness/`, make them executable, and re-verify each CLI's install command against its documentation at the pinned version; record any flag change in `_bmad-output/planning-artifacts/mvp/addendum.md` §B.
- `backend-api/docker-entrypoint.sh` implementing the order above with `set -euo pipefail`.
- `Makefile`: `up` = `docker compose up -d --build`, `down` = `docker compose down`, `logs`.
- CI builds the images in 1.7; here `make e2e-api` gains the option to run against the compose stack (`BACKEND_API_URL=http://localhost:8000`).

## Verification

```bash
make up && curl -fs localhost:8000/healthz && docker compose exec backend-api scripts/harness/claude.sh doctor
```

## Sources for detail only

Spine: Structural Seed (deployment diagram, tree), Stack, AD-5, AD-10, AD-16, AD-20, Operations. PRD NFR-3, NFR-4, NFR-7, §12. `deliverables/scripts/harness/*.sh`, `deliverables/.env.example`, `addendum.md` §A, §B.
