---
story: "4-3"
epic: 4
title: Pre-flight checks and the harness table
requirements: [FR-8, FR-13 (held branch), FR-33 (harness enabled line), AR-15 (table only)]
binds: [AD-7, AD-10, AD-12, AD-14, AD-16]
---

# Story 4.3 — Pre-flight checks and the harness table

As the Operator,
I want every reason a Run could fail at start reported as a line before I click *Start run*, with the fix stated,
So that I never enqueue a Run that will stop on a configuration problem.

## Scope

**In:** `application/use_cases/preflight.py`, `POST /api/v1/runs/preflight`, the `harness` table (`name, enabled, last_readiness_at, failing_check, version_pin`) with its port, fake, migration, and seeding of the three names disabled, `GET /api/v1/harnesses` (list only), tests.
**Out:** readiness runs and evaluation (Epic 5); creating the Run (4.4).

## Binding rules (inlined)

- **Request.** `{template_name, template_version, project_id, repository_id, base_branch, inputs: {initiative_folder? | branch?, spec_folder?}, harness?, model?, budget_usd?, re_review_done?}`; missing fields make the corresponding lines `skip` (not errors) so the screen can call pre-flight on every change.
- **Response.** `{lines: [{check, status: ok | warn | fail | skip, text, fix?}], start_allowed: bool, queue_note: str, rows: [PlannedRow] | null, plan_error: {template, version, line, item, reason} | null}`. `start_allowed` = no `fail` line and no `plan_error`. `queue_note` = `starts immediately if the repository is free` or `queues behind {run label}` (the non-terminal Run holding the Repository, if any) or `queues: global concurrency, held by {labels}` when active Runs ≥ `MAX_ACTIVE_RUNS` `[label = "{template} · {branch}"]`.
- **Lines, in this order** (texts verbatim; `fix` only on `fail`):
  1. `origin reachable` — `Git.ls_remote(url, "HEAD")`; fail → fix `check the URL and the instance token`.
  2. `base branch {base}` — exists on origin; fail → `branch does not exist on origin`.
  3. one line per branch the plan checks out (`repo-init`: `chore/bmad-init`; `epic`: the working branch; `initiative`: each epic's branch, deduplicated): `branch {b} · will check out` (exists) or `branch {b} · will create from {base}`; fail when held by a worktree of a non-terminal Run on this Repository → `held by run {label}`, fix `wait for that run or cancel it`.
  4. `epics.yaml` (initiative only): `{n} epics · branches … · spec folders …` or fail with the parse reason.
  5. one line per `stories.yaml`: `{spec_folder}/stories.yaml · {n} stories` or fail (parse, ids not prefix-free, missing fields).
  6. `checkpoints` — `warn` listing `story {id} · spec checkpoint` / `done checkpoint` / `epic {id} · done checkpoint`, or `ok · none declared`.
  7. `SPEC.md` — one line per spec folder: `found` / fail `missing`.
  8. `harness {name}` — `enabled` / fail `disabled: {failing_check or "no readiness run"}`, fix `re-run readiness on this screen`; `skip` for `repo-init`.
  9. `method version` — `_bmad/_config/manifest.yaml` at `plan_ref` equals `BMAD_VERSION` → `ok · {v}`; else fail `missing` / `outdated: {v}` with fix `run Initialise repository and merge its branch`; `skip` when the plan contains a `bmad.install` row.
  10. `existing story files` — `warn` listing `stories/{id}-*.md · {status}` for each found, or `ok · none`.
  11. `clone check` — Repository `clone_check.status` `ok` → ok; `failed` → fail with fix `re-run the clone check on the project`; `pending` → fail `pending · save the project`.
  12. `what will run` — `{rows} rows` from `plan_run`, or the `plan_error`.
- **Held branch (AD-14).** A branch is held when any Run with status not in `{done, failed, cancelled}` on the same Repository has an entry in `worktrees[]` for it.
- **Harness table (AD-10).** Seeded at startup with `claude`, `codex`, `local`, `enabled: false`, `version_pin` = the settings pin for each; written only by the readiness use case (Epic 5); `GET /api/v1/harnesses` → `{items: [{name, enabled, last_readiness_at, failing_check, version_pin}]}`. Pre-flight reads `enabled` here; nothing else in this epic does.
- **Pure over ports.** The use case receives `git`, `templates`, `runs`, `harnesses`, `repositories`, `projects`, `bmad_version`, `max_active_runs`; it writes nothing (`ls_remote` only).

## Acceptance criteria

**Given** a `repo-init` request on a Repository with `clone_check.ok`, a reachable origin, and no `chore/bmad-init` branch
**When** pre-flight runs
**Then** lines 1–3, 9 (`skip`), 11, 12 are present, line 3 reads `branch chore/bmad-init · will create from main`, `start_allowed` is true, `rows` has six entries, and `queue_note` is `starts immediately if the repository is free`.

**Given** an `epic` request where `stories.yaml` has ids `4-1` and `4-1-a`
**When** pre-flight runs
**Then** line 5 is `fail` naming the ids, `start_allowed` is false, and `rows` is null with `plan_error` set.

**Given** an `epic` request with `harness: claude` while `harness.enabled` is false
**When** pre-flight runs
**Then** line 8 is `fail · disabled: no readiness run` with its fix.

**Given** a non-terminal Run holding `feat/x` on the Repository
**When** pre-flight for `feat/x` runs
**Then** line 3 is `fail · held by run epic · feat/x` and `queue_note` names it.

**Given** `_bmad/_config/manifest.yaml` at `plan_ref` with version `6.10.0` and `BMAD_VERSION=6.11.0`
**When** an `epic` request runs
**Then** line 9 is `fail · outdated: 6.10.0` with fix `run Initialise repository and merge its branch`.

**Given** a request missing `repository_id`
**When** posted
**Then** 200 with every line `skip` and `start_allowed: false`.

## Implementation notes

- `preflight.py::run_preflight(req, ports…) -> PreflightResult`; each line in its own small function returning `Line`.
- Migration `0006_harness.py`; seeding in `main.py` startup (idempotent upsert of names, never touching `enabled`).
- Router `api/routers/runs.py` (`POST /runs/preflight`) and `api/routers/harnesses.py` (`GET /harnesses`); run `make openapi`.

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

PRD FR-8 (check list), FR-13, FR-33. Spine AD-7, AD-10 (harness table), AD-12 (queue note), AD-14 (held branch), AD-16 (method version). `EXPERIENCE-v1.md` §2.1 (line words `ok / ! / x / —`).
