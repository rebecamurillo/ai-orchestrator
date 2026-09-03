---
id: SPEC-mvp-epic-01-foundation
companions: []
sources:
  - ../../prd.md
  - ../../architecture/ARCHITECTURE-SPINE.md
  - ../../architecture/deliverables/
  - ../../../ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md
  - ../../../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
---

> **Canonical contract for Epic 1.** Each story's full requirements live in `briefs/<id>-<slug>.md`, named from `stories.yaml` `invoke_dev_with`. Read the brief for the story you are dispatched on; do not read the other briefs. The architecture spine (`AD-n`) is the binding contract when a brief and the code disagree.

# Epic 1 — Repository foundation, quality gates, and Operator login

## Why

A mandate and an opportunity: every later epic is built unattended by coding agents, and an agent can only be trusted with a story when the gates that decide "done" already exist and are green. This epic turns an empty repository into the two-component monorepo the spine describes, with its constitutions, layering linter, contract pipeline, test harnesses, containers, the instrument-dark shell, and the Operator's token login. After it, the Operator brings the stack up from a clone in under 30 minutes, logs in, and sees an empty Board.

## Capabilities

- **CAP-1** Repository constitution and backend-api skeleton with layering gates
  - **intent:** The repository carries its root and backend constitutions, the configuration contract, and a backend-api package whose layering, lint, type, and unit-test gates run green from `make lint` and `make test`.
  - **success:** `make lint test` passes on a fresh clone; a deliberate import from `application/` into `sqlalchemy` fails `make lint`; a settings field missing from `.env.example` fails `make lint`; `GET /healthz` returns 200.
- **CAP-2** Database, migrations, bearer auth, and API conventions
  - **intent:** backend-api connects to Postgres through one datasource, runs Alembic migrations at startup, authenticates every `/api/v1/*` request by constant-time bearer comparison, and answers errors as RFC 9457 problem documents.
  - **success:** an unauthenticated `/api/v1/*` call returns 401 `application/problem+json`; the correct bearer returns 200; `make e2e-api` runs an httpx scenario and Schemathesis against the running stack.
- **CAP-3** Generated contract and web-client skeleton
  - **intent:** The OpenAPI contract is exported from Pydantic, TypeScript types are generated from it, and the web-client skeleton exists with its proxy, eslint restrictions, lint, unit, and e2e harnesses.
  - **success:** `make openapi` writes `contracts/openapi.json` and `src/api/schema.d.ts`; `make lint` fails on drift; eslint fails on a `fetch` inside `src/islands/`; the proxy forwards with the bearer and the token never reaches the browser.
- **CAP-4** Design tokens and the instrument-dark shell
  - **intent:** One stylesheet holds every visual token and the shell (rail, surface bar, footer readout) and base components render every screen route as an empty readout.
  - **success:** token values match `DESIGN.md`; a unit test proves no radius, no shadow, and AA contrast for primary and secondary text; every route renders inside the shell with zero amber or red pixels.
- **CAP-5** Operator token login
  - **intent:** The Operator logs in once with the access token and receives a 30-day signed HttpOnly cookie; every page and every proxied API call requires it.
  - **success:** wrong token → login page with `token rejected`; right token → cookie + redirect to `/` reading `NOTHING REGISTERED`; unauthenticated page → 302 `/login`; unauthenticated `/api/*` → 401.
- **CAP-6** Container images and the Compose stack
  - **intent:** Two Dockerfiles and one compose file bring up web-client, backend-api (non-root, with the three harness CLIs and BMAD skill stubs installed at pinned versions), and Postgres with named volumes and hardening flags; host-side LiteLLM and Langfuse are documented.
  - **success:** `make up` from a clean clone with `.env` reaches a green `/healthz` and a working login; `docker compose exec backend-api` runs as `agent`, prints the pinned CLI versions, and finds `bmad-build-auto` under `~/.claude/skills` and `~/.agents/skills`.
- **CAP-7** CI pipeline and coverage gates
  - **intent:** A CI workflow runs lint → unit → e2e-api → e2e-ui in that order, regenerates the contract and fails on drift, and enforces the coverage thresholds.
  - **success:** the workflow passes on the epic's final commit; a commit that breaks a gate fails at that gate; coverage configuration enforces 100 % branch on `domain/` and `application/` rules and ≥ 90 % on changed lines.

## Constraints

- Layering (AD-2): `domain/` ← `application/` ← {`api/`, `infrastructure/`} ← `main.py`; `domain/` and `application/` never import `fastapi`, `sqlalchemy`, `dbos`, `subprocess`, `os`, `shutil`, `httpx`, `langfuse`, `git`. Enforced by import-linter.
- One browser origin (AD-1): only `src/api/server.ts` and `src/api/client.ts` call `fetch`; islands, stores, and components never hold `BACKEND_API_URL` or the token.
- Contract generated, never hand-written (AD-3).
- One credential (AD-4, AD-5): `ORCHESTRATOR_TOKEN` for login and API; secrets only in `infrastructure/settings.py` / `astro:env`; never in code, tests, logs, or fixtures.
- Configuration is the environment (AD-20): every setting in the typed settings module and in `.env.example`, same change.
- Stack versions are the spine's Stack table; pin them.
- Visual system: instrument-dark tokens only, monospace, radius 0, no shadows, status as word tokens, at most one signal colour per card or row (NFR-6).
- Copy states facts and mechanisms, never congratulates or apologises (NFR-8).
- Tests first: a story's tests exist and fail before its implementation; unit tests use shared fakes in `tests/unit/fakes/` (AD-18).

## Non-goals

- No domain entities beyond what login needs: no Project, Repository, Template, or Run tables (later epics create tables when they need them).
- No login lockout counter (Epic 8).
- No harness adapter code, no DBOS walker, no tracing (Epics 4, 5); the image only installs the CLIs.
- No egress allowlist enforcement (documented host rule, NFR-4).

## Success signal

A newly cloned repository with a filled `.env` reaches a logged-in empty Board through `make up` in under 30 minutes, and `make lint test e2e-api e2e-ui` is green in CI, so that from Epic 2 on a coding agent can be dispatched on a story and judged by those gates alone.
