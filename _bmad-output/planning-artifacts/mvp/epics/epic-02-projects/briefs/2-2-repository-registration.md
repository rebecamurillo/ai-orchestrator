---
story: "2-2"
epic: 2
title: Repository registration with commands and test globs
requirements: [FR-3, AR-8, AR-24]
binds: [AD-2, AD-3, AD-14, AD-17, AD-18]
---

# Story 2.2 — Repository registration with commands and test globs

As the Operator,
I want to add Repositories to a Project with their default branch, package manager, the commands the dev loop will run, and the globs naming the tests agents must not touch,
So that a Run knows how to install, verify, and protect a repository before any agent is dispatched.

## Scope

**In:** `repository` table + migration, entity, repository port + implementation + fake, use cases (add, update, get, list by project), `api/routers/repositories.py`, embedding repositories in the Project read model, tests.
**Out:** the clone check itself (2.3; this story stores `clone_check.status = "pending"`), UI (2.4, 2.5).

## Binding rules (inlined)

- **Fields.** `id` (UUIDv7), `project_id`, `slug` (derived from the last path segment of the URL without `.git`, unique per Project), `url` (https or ssh git URL, required), `default_branch` (required, e.g. `main`), `package_manager` (enum `uv | pnpm | npm | yarn | pip | cargo | go | other`, stored, unused by the shipped Templates), `test_globs` (list of strings, default `["tests/**", "**/*.test.*", "**/*.spec.*"]`; the default is always present, the Operator can add globs), `install_command` (optional string), `quality_gate_command` (optional string), `unit_test_command` (optional string, stored, unused), `clone_check` (JSON `{status: "pending" | "ok" | "failed", at: datetime | null, output: string, bmad_version: string | null}`), `created_at`, `updated_at`.
- **Derived flag.** The read model carries `verify_skipped: bool` = `quality_gate_command` empty; the Repository row copy `verify step will be skipped` (UI) comes from it (FR-3).
- **API.** `POST /api/v1/projects/{id}/repositories` → 201; `GET /api/v1/repositories/{id}`; `PUT /api/v1/repositories/{id}`; `GET /api/v1/projects/{id}` now embeds `repositories: [...]` in URL order of creation. 409 on duplicate URL within the Project; 422 with `errors[]{path, reason}` for a missing URL or default branch or an invalid glob (must not start with `/`, no `..`).
- **`clone_check`** is written only by `run_clone_check` (2.3); this story's `PUT` never touches it, and `POST` initialises it to `pending`.
- **Layering and tests** as in 2.1: entity in `domain/`, use cases in `application/use_cases/projects.py` (same module, repository section), `tests/unit/fakes/projects.py` gains the in-memory `RepositoryRepository`.
- Run `make openapi` and commit the regenerated files.

## Acceptance criteria

**Given** a Project
**When** `POST /projects/{id}/repositories` is called with only `url` and `default_branch`
**Then** it returns 201 with `test_globs` equal to the three defaults, `verify_skipped: true`, `clone_check.status: "pending"`, and `package_manager: "other"`.

**Given** a payload with `test_globs: ["e2e/**"]`
**When** posted
**Then** the stored globs are the three defaults plus `e2e/**`, in that order, without duplicates.

**Given** a payload with `quality_gate_command: "make lint test"`
**When** posted then read
**Then** `verify_skipped` is `false`.

**Given** a second repository with the same URL under the same Project
**When** posted
**Then** 409 problem+json; the same URL under another Project is accepted.

**Given** `PUT /repositories/{id}` with a changed `default_branch`
**When** applied
**Then** the field updates and `clone_check` is unchanged (`pending` or the last result).

**Given** `GET /projects/{id}`
**When** the Project has two repositories
**Then** both are embedded with every field and `verify_skipped`.

## Implementation notes

- Migration `0003_repository.py`; unique index `(project_id, url)`; `test_globs` and `clone_check` as `JSONB`.
- `domain/entities/repository.py` with `CloneCheck` value object; `verify_skipped` as a property.
- Read model `ProjectDetail` schema in `api/schemas/projects.py` embedding `RepositoryOut`.
- Validation of globs with a small pure function in `domain/rules/globs.py` (reused by the protected-path rule later).

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

PRD FR-3, glossary "Repository", §6.2 (unused fields). Spine AD-14 (`clone_check` ownership), AD-17 (`test_globs` default), Structural Seed fields.
