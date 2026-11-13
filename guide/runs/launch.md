---
title: Launching a Run
kind: procedure
audience: any
---
# Launching a Run

Never guess a template's inputs and never skip preflight.

1. **Discover templates** — `GET /api/v1/templates`, then
   `GET /api/v1/templates/{name}/{version}`: the response's `inputs` is the authoritative
   list of what this template takes. Shipped templates are `staged-*`
   (three agent sessions per story: plan, implement, review, each on its own model),
   `staged-initiative-hub` and `staged-initiative-repo`, plus `repo-init` and `agent-smoke`
   (`harness-readiness` is off the menu). Each is one file that calls no other. They evolve; read them, don't memorize them.
   - **Multi-repo initiative, hub style (the default)**: template `staged-initiative-hub`
     with repository = the hub repo whose
     `repos/*` submodules are the members; inputs include `branch` (the one initiative
     branch shared by hub and submodules) and `initiative_folder`. The `epics.yaml` it
     reads needs per-epic `workdir` + full `install`/`test`/`quality_gate` commands — see
     `spec-folder`.
   - **Single-repository initiative**: template `staged-initiative-repo` with the plain
     repository; same `epics.yaml` shape without `workdir` or commands (the repository
     record's own commands run).
   - **Staged models**: a `staged-*` root takes `model` (implements), `plan_model` (plans,
     and runs the epic's spec-gate / gen-e2e / retro) and `review_model` (reviews); the
     last two are required. Ask the human for all three.
2. **Preflight** — `POST /api/v1/runs/preflight` with everything you plan to send
   (`template_name`, `template_version`, `project_id`, `repository_id`, `base_branch`,
   `inputs`, `harness`, `model`, `budget_usd`). Every field is optional there — missing
   ones make dependent checks `skip`, not fail. Read the answer:
   - `lines[]` — each check with `status` and a `fix` when it fails; resolve every `fail`.
   - `start_allowed` and `queue_note` — whether and when it would start.
   - `rows[]` — the planned steps; `plan_error` names the exact template line otherwise.
   - `conflict_consent_required` — if true, creating the Run needs
     `conflict_consent: true` (a branch conflict the operator accepts knowingly).
3. **Create** — `POST /api/v1/runs`. Required: `template_name`, `template_version`,
   `project_id`, `repository_id`, `base_branch`, and a positive `budget_usd` — a Run
   cannot start without a budget. Optional: `inputs` (what step 1 discovered), `harness`
   (`claude` | `codex` | `local`; null takes the instance default), `model`,
   `save: true` (persist without starting; launch later with the `start` signal),
   `after_run_ids` (fan in behind one or more predecessors; requires `save: true`).
   A failed preflight line answers 409; an unbuildable plan answers 422 with structured
   `errors[]` naming template, version and line.
