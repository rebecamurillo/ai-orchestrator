---
story: "4-10"
epic: 4
title: Initialise a Repository from the Project screen
requirements: [FR-30, FR-4 (method cell), UX-DR12, AR-24]
binds: [AD-12, AD-16]
---

# Story 4.10 — Initialise a Repository from the Project screen

As the Operator,
I want to click *Initialise repository* on a Repository whose method is `missing` or `outdated` and get a branch with `_bmad/` pushed and a compare link,
So that a repository is ready for the dev loop without my touching a terminal (UJ-1 edge case).

## Scope

**In:** `POST /api/v1/repositories/{id}/init`, the *Initialise repository* control on the Repository row with its states, the **RUNS ON THIS PROJECT** list on the Project detail, tests.
**Out:** nothing else; this is the first vertical slice through the whole engine.

## Binding rules (inlined)

- **Endpoint.** `POST /repositories/{id}/init` → `create_run` with `repo-init@1`, `base_branch = repository.default_branch`, no harness; 201 `{run, starts_now, waiting}`; 409 when the clone check is `failed` or a non-terminal `repo-init` Run already exists for the Repository (`detail: initialisation already running: {run id}`); subject to the repository lock like any Run.
- **Row control (UX-DR12).** On a row with method `missing` or `outdated`: *Initialise repository* (test-id `projects-init-<slug>`); while its Run is non-terminal the cell reads `initialising · {run token}` linking to the Run detail; when `done` it reads the method version found by the next clone check (the endpoint triggers `run_clone_check` when the Run reaches `done` `[ASSUMPTION: a completion hook re-runs the clone check so the method cell updates without a manual re-run]`) and a `link` to the compare URL; when `failed | cancelled` the control returns with the line `last attempt {token} · {reason}`.
- **Runs on this project.** Record rows `token · template@v · branch · current step label · age`, newest first, linking to `/workflows/{id}`; the Project read model gains `runs: [RunSummary]` (last 20) — extend `GET /projects/{id}` `[one read per screen]`.
- **Copy (NFR-8):** `run Initialise repository after save` (New project readout, already present), `initialising`, `initialised · v6.11.0 · link`.

## Acceptance criteria

**Given** a Repository with `bmad_version: missing` and a passing clone check
**When** *Initialise repository* is clicked
**Then** a `repo-init@1` Run is created and the row reads `initialising · QUE` or `RUN` linking to `/workflows/{id}` (the Board card itself is 4.14's concern).

**Given** the Run reaches `done` on the e2e local remote
**When** the Project detail reloads
**Then** the method cell reads the installed version, the row shows the compare link, and the runs list shows the Run as `DON`.

**Given** a Repository whose clone check is `failed`
**When** the endpoint is called
**Then** 409 problem+json and the control is not rendered on the row.

**Given** a non-terminal `repo-init` Run for the Repository
**When** the endpoint is called again
**Then** 409 `initialisation already running`.

## Implementation notes

- Router in `api/routers/repositories.py`; use case `use_cases/repositories.init_repository`.
- Completion hook: the walker's `finish` step calls `use_cases/run_finished.on_finished(run)` which, for `repo-init`, calls `run_clone_check`; Epic 5 adds readiness evaluation to the same hook.
- Astro Action `repositories.init`; the row re-renders on the next page load (no polling on this page).

## Verification

```bash
make lint && make test && make openapi && make e2e-api && make e2e-ui
```

## Sources for detail only

PRD FR-30, UJ-1. Spine AD-16, AD-12, conventions (Routes). `EXPERIENCE-v1.md` §3 Projects.
