---
story: "3-3"
epic: 3
title: Template versions API and seeding
requirements: [FR-6, AR-8 (template_version), AR-20, AR-24]
binds: [AD-2, AD-3, AD-15, AD-18]
---

# Story 3.3 — Template versions API and seeding

As the Operator,
I want Templates stored as immutable numbered versions I can list, read, validate, and extend with a new version, with the four shipped Templates present from the first start,
So that a Run can pin exactly what it executes and a later edit can never change it.

## Scope

**In:** tables `template` and `template_version` + migration, entities, repository port (extends 3.1's read-only protocol with `add_version`, `list`, `list_versions`, `callers_of`) + SQLAlchemy implementation + fake extension, `use_cases/templates.py` (`list_templates`, `get_version`, `validate_text`, `save_version`, `seed_shipped`), `api/routers/templates.py`, startup seeding, tests.
**Out:** graph (3.4), UI (3.5, 3.6), freeze-on-pin enforcement and `pinned_by` counting from Runs (Epic 4; here `pinned_by` is always 0).

## Binding rules (inlined)

- **Tables.** `template{name (pk, slug), description, created_at}`; `template_version{id (UUIDv7), name (fk), version (int), yaml (text), hash (sha256 of yaml), calls (JSONB list of {name, version}), created_at}` with unique `(name, version)`. `calls` is filled from the validator's parsed tree at save time.
- **Immutability (AD-15).** No endpoint updates or deletes a `template_version`; `save_version` always writes `max(version) + 1`. The SQLAlchemy repository exposes no update method for versions.
- **Endpoints.** `GET /api/v1/templates` → `{items: [{name, description, latest_version, versions: [int]}], next_cursor}`; `GET /api/v1/templates/{name}/{version}` → `{name, version, yaml, hash, calls, called_by: [{name, version}], pinned_by: 0, created_at, inputs: [{name, type, required, default, values}]}` (`inputs` from the parsed tree, for the screen's inputs table); `POST /api/v1/templates/{name}/validate` with `{yaml}` → 200 `{errors: [{template, version, line, reason}], unvalidated: [path]}` (validation problems are data here, not a 422); `POST /api/v1/templates/{name}/versions` with `{yaml}` → 201 with the new version, or 422 problem+json carrying the validator's errors in `errors[]` when invalid; the YAML's `name` must equal the path `name` and its `version` must equal the new number (`422 reason: version must be {n}`); 404 for unknown names or versions.
- **Callers.** `called_by` = every version whose `calls` contains this `(name, version)`; computed by a repository query.
- **Seeding.** At startup (`main.py`, before serving), `seed_shipped(templates_dir)` reads each `templates/*.yaml`, validates it, and inserts it as version 1 when no version with the same name and `hash` exists; a shipped file whose hash differs from any stored version is inserted as the next version with a log line `shipped template {name} seeded as v{n}`; seeding never modifies an existing row. Invalid shipped YAML fails startup with the errors printed.
- **Layering and tests** as before; the fake from 3.1 gains the write methods.

## Acceptance criteria

**Given** an empty database and the four shipped files
**When** the app starts
**Then** `GET /templates` lists `repo-init`, `story`, `epic`, `initiative` each with `versions: [1]`, and a second start inserts nothing.

**Given** `GET /templates/epic/1`
**When** read
**Then** `calls` is `[{name: story, version: 1}]`, `called_by` is `[{name: initiative, version: 1}]`, `pinned_by` is `0`, and `inputs` lists eight inputs with their types.

**Given** valid YAML for `epic` with `version: 2`
**When** posted to `/templates/epic/versions`
**Then** 201 returns version 2, `GET /templates/epic/1` still returns the original YAML byte for byte, and the list shows `versions: [1, 2]`.

**Given** YAML with `version: 5` when the next number is 2, or with `name: story` posted under `/templates/epic/versions`
**When** posted
**Then** 422 problem+json with the reason.

**Given** invalid YAML
**When** posted to `/validate`
**Then** 200 with the errors listed by line; when posted to `/versions` → 422 with the same errors in `errors[]` and no row written.

**Given** a shipped file edited on disk to a new hash
**When** the app restarts
**Then** it is inserted as the next version and the previous version is unchanged.

## Implementation notes

- Migration `0004_template.py`.
- `application/use_cases/templates.py::save_version(name, yaml, *, templates, uow)` runs `validate()` with the repository as callee source, then writes.
- `main.py` startup hook order: migrations → `seed_shipped` → serve.
- Router tests through httpx ASGI with the fake repository; e2e test posts a new version and reads it back; run `make openapi`.

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

PRD FR-6. Spine AD-15, Structural Seed fields (`template_version`), conventions (Routes, Errors, Lists).
