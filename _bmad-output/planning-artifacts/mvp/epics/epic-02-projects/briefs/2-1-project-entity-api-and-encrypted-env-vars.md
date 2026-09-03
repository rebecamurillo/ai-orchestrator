---
story: "2-1"
epic: 2
title: Project entity, API, and encrypted environment variables
requirements: [FR-2, NFR-3, AR-8, AR-24]
binds: [AD-2, AD-3, AD-5, AD-18]
---

# Story 2.1 — Project entity, API, and encrypted environment variables

As the Operator,
I want to create and edit a Project holding the context every agent reads, its agent environment variables, and the content-logging switch,
So that a Run can scope what its agents receive, and no secret of mine ever sits in the database in clear.

## Scope

**In:** `project` table + migration, domain entity, repository port + SQLAlchemy implementation + fake, `use_cases/projects.py` (create, update, get, list), Fernet crypto adapter, `api/routers/projects.py`, schemas, unit and e2e tests.
**Out:** repositories (2.2), clone check (2.3), any UI (2.4, 2.5), deletion.

## Binding rules (inlined)

- **Fields.** `id` (UUIDv7), `slug` (unique, kebab-case derived from the name at creation, immutable; used in `/work/{slug}/…` paths `[ASSUMPTION: slug paths rather than ids]`), `name` (unique, 1–80 chars), `context_text` (text, may be empty), `context_paths` (list of repo-relative paths, may be empty), `env_vars_enc` (JSON list of `{name, value_enc}`), `log_prompt_content` (bool), `created_at`, `updated_at`.
- **Encryption (AD-5).** Values are encrypted with `cryptography.fernet.Fernet(ORCHESTRATOR_SECRET_KEY)` in `infrastructure/crypto/fernet.py` behind `domain/ports/crypto.py` (`encrypt(str) -> str`, `decrypt(str) -> str`); names stay in clear; variable names match `^[A-Z][A-Z0-9_]*$` and are unique per Project; `GITHUB_TOKEN`, `LITELLM_API_KEY`, `LITELLM_SPEND_KEY`, `LANGFUSE_*`, `ORCHESTRATOR_*` are refused as names with 422 `reason: "instance setting, not a project variable"`.
- **Masking.** API responses carry `env_vars: [{name, masked}]` where `masked` = `••••` + last four characters of the plaintext (or `••••` alone when shorter than four). Plaintext is returned by no endpoint; `decrypt_env_vars(project_id)` exists only as an application function for later Run use.
- **Update semantics.** `PUT /api/v1/projects/{id}` takes `env_vars: [{name, value?}]`; an entry with `value` sets or replaces, an entry without `value` keeps the stored ciphertext, a stored name absent from the list is deleted.
- **`log_prompt_content`** defaults to `settings.LOG_PROMPT_CONTENT_DEFAULT` when omitted on create.
- **API (conventions).** `GET /api/v1/projects` → `{items, next_cursor}` sorted by name; `POST /api/v1/projects` → 201 with the project; `GET /api/v1/projects/{id}`; `PUT /api/v1/projects/{id}`; 404 problem for unknown ids; 409 problem on duplicate name; 422 problem with `errors[]{path, reason}`.
- **Layering (AD-2).** Entity and port in `domain/`, use cases in `application/use_cases/projects.py`, SQLAlchemy model and repository in `infrastructure/db/`, router in `api/routers/projects.py`, schemas in `api/schemas/projects.py`. Unit tests drive the use cases with `tests/unit/fakes/projects.py` (in-memory repository) and `tests/unit/fakes/crypto.py`; router tests use httpx ASGI with fakes injected.
- **Contract (AD-3).** Run `make openapi` and commit the regenerated `contracts/openapi.json` and `schema.d.ts`.

## Acceptance criteria

**Given** a valid create payload with two env vars
**When** `POST /api/v1/projects` is called with the bearer
**Then** it returns 201, the row's `env_vars_enc` values are Fernet tokens (not the plaintext), and the response shows `masked` ending with each value's last four characters.

**Given** a payload whose env var name is `GITHUB_TOKEN` or fails the name pattern
**When** posted
**Then** 422 problem+json names the path `env_vars[i].name` and the reason.

**Given** a stored Project with vars `A` and `B`
**When** `PUT` sends `[{name: "A"}, {name: "C", value: "x"}]`
**Then** `A` keeps its ciphertext unchanged, `B` is deleted, `C` is added, and `updated_at` changes.

**Given** two create calls with the same name
**When** the second is made
**Then** it returns 409 problem+json.

**Given** `LOG_PROMPT_CONTENT_DEFAULT=false`
**When** a Project is created without `log_prompt_content`
**Then** it is stored `false`, and `true` when the setting is `true`.

**Given** the e2e-api suite against the stack
**When** it runs
**Then** create → get → list → update round-trips succeed and Schemathesis reports no 5xx on the new operations.

## Implementation notes

- Migration `alembic/versions/0002_project.py`; `env_vars_enc` as `JSONB`; unique indexes on `name` and `slug`.
- `domain/entities/project.py` (pydantic model, frozen), `domain/ports/repositories.py` gains `ProjectRepository` (`add`, `get`, `get_by_slug`, `list`, `update`); `application/use_cases/projects.py` functions take ports explicitly.
- Slug: lowercase, `[a-z0-9-]`, collapse dashes, max 40 chars, suffix `-2`… on collision.
- Do not add a `repositories` relation yet; 2.2 adds the child table and embeds them in the project read model.

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

PRD FR-2, NFR-3, §11 Privacy. Spine AD-5, Consistency Conventions (Routes, Errors, Lists, Ids & keys), Structural Seed fields. `backend-api/AGENTS.md`.
