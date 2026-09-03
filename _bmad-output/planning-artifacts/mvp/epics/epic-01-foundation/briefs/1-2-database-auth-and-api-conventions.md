---
story: "1-2"
epic: 1
title: Database, migrations, bearer auth, and API conventions
requirements: [FR-1 (API half), NFR-3, AR-2, AR-5, AR-8 (ids, dates, money), AR-22, AR-24]
binds: [AD-4, AD-18, AD-20]
---

# Story 1.2 — Database, migrations, bearer auth, and API conventions

As the Operator,
I want backend-api to talk to Postgres through one datasource with migrations applied at startup, to refuse every unauthenticated API call, and to answer errors in one machine-readable shape,
So that every later endpoint inherits authentication, persistence, and error conventions instead of re-deciding them.

## Scope

**In:** `DATABASE_URL` datasource and unit-of-work, Alembic baseline, startup migration, bearer dependency, RFC 9457 problem responses, list envelope schema, UUIDv7 and time helpers, a `docker-compose.yml` with only the `postgres` service for local and CI use, the `tests/e2e/` harness (httpx scenarios + Schemathesis).
**Out:** any domain table (created by the story that needs it); cookies (1.5); the full compose stack (1.6).

## Binding rules (inlined)

- **One credential (AD-4).** `ORCHESTRATOR_TOKEN` is the only secret. Every route under `/api/v1/*` depends on `api/deps.py::require_bearer`, which compares `Authorization: Bearer <token>` with `hmac.compare_digest`. No cookies, no CORS headers on backend-api. `/healthz` and `/openapi.json` stay unauthenticated.
- **Errors (conventions).** All errors are `application/problem+json` `{type, title, status, detail, instance, errors?}`. 401 bad or missing bearer; 404 unknown entity; 409 state conflict; 422 validation, with `errors[]` entries `{template?, version?, line?, path?, reason}`. FastAPI's default validation error is translated into this shape.
- **Lists** are `{items: [...], next_cursor: string | null}`; filters are query params; no other envelope.
- **Ids and time.** UUIDv7 for every entity (`uuid.uuid7()` on Python 3.14); ISO 8601 UTC with `Z`; DB `timestamptz`; money `numeric(12,6)` USD serialised as a string; tokens as integers.
- **Migrations.** Alembic manages schema `public` only; `alembic upgrade head` runs at container start before serving. Every later model change ships with a revision.
- **Unit tests never need Postgres** (AD-18): the datasource is behind `infrastructure/db/`; use cases and routers are unit-tested with fakes. `tests/e2e/` needs the running stack.
- **Stack pins:** SQLAlchemy 2.0.52, psycopg 3.3.5, Alembic 1.19.1, httpx 0.28.1, schemathesis 4.25.2, PostgreSQL 18.

## Acceptance criteria

**Given** the app running against Postgres
**When** it starts
**Then** `alembic upgrade head` has run (a `alembic_version` row exists) before the first request is served, and the log line `migrations applied` carries the head revision.

**Given** any route under `/api/v1/`
**When** called without `Authorization`, with a wrong token, or with a token differing by one byte
**Then** it returns 401 `application/problem+json` with `title: "unauthorized"` and no other detail, and the comparison is constant-time (`hmac.compare_digest`).

**Given** `GET /api/v1/ping` (a minimal authenticated route kept for tests)
**When** called with the correct bearer
**Then** it returns 200 `{"pong": true}`.

**Given** a request body failing Pydantic validation on any route
**When** handled
**Then** the response is 422 `application/problem+json` with `errors[]` of `{path, reason}` and `detail` naming the first error.

**Given** `make e2e-api` with the `postgres` service and the app running
**When** it executes
**Then** an httpx scenario covers healthz, 401, and ping, and Schemathesis runs every operation from `/openapi.json` with the bearer and reports no 5xx.

**Given** a unit test suite run
**When** `make test` executes
**Then** it completes without a database or network (a fake unit-of-work exists in `tests/unit/fakes/db.py`).

## Implementation notes

- `infrastructure/db/{engine.py, session.py, unit_of_work.py}`: SQLAlchemy 2 engine from `DATABASE_URL`, session factory, `SQLAlchemyUnitOfWork` implementing `domain/ports/unit_of_work.py` (`__enter__/__exit__`, `commit`, `rollback`). Repository ports arrive with their entities in later stories.
- `alembic/` under `backend-api/` with `env.py` reading `DATABASE_URL` from settings; baseline revision creates nothing (schema empty is correct at this point).
- `api/deps.py::require_bearer(settings)`; `api/errors.py` with `ProblemDetail` schema, exception handlers, and `Problem` exception class used by use cases through a domain error hierarchy (`domain/errors.py`: `NotFound`, `Conflict`, `Invalid`).
- `api/schemas/common.py`: `Page[T]` (`items`, `next_cursor`), `MoneyStr` annotated type, timestamp serialiser.
- `domain/ids.py::new_id() -> UUID` (uuid7).
- `docker-compose.yml`: service `postgres` (`postgres:18`, env from `.env`, volume `pgdata`, healthcheck) only; 1.6 adds the rest.
- `tests/e2e/conftest.py` reading `BACKEND_API_URL` and `ORCHESTRATOR_TOKEN`; `tests/e2e/test_smoke.py`; `tests/e2e/test_schemathesis.py`.
- `make e2e-api` = `uv run pytest tests/e2e -q` after `docker compose up -d postgres` and the app started locally or in the stack.

## Verification

```bash
docker compose up -d postgres && make test && make e2e-api
```

## Sources for detail only

Spine: AD-4, AD-18, Consistency Conventions (Routes, Ids & keys, Dates & money, Errors, Lists, Operations). PRD FR-1, NFR-3. `deliverables/backend-api/AGENTS.md`.
