---
story: "3-2"
epic: 3
title: Shipped Templates repo-init, story, epic, initiative
requirements: [FR-5, FR-9, FR-10, FR-11, FR-30, AR-20]
binds: [AD-7, AD-9, AD-15, AD-16]
---

# Story 3.2 — Shipped Templates `repo-init`, `story`, `epic`, `initiative`

As the Operator,
I want the dev loop and repository initialisation to ship as four readable YAML Templates that compose by call,
So that what runs is visible, versioned, and editable, and the planner of the next epic has something real to expand.

## Scope

**In:** `templates/repo-init.yaml`, `templates/story.yaml`, `templates/epic.yaml`, `templates/initiative.yaml` at the repository root; a test module that validates all four through `validate()` (with a fake repository holding the other three) and asserts composition, gates, and the specific structure below.
**Out:** seeding into the database (3.3); execution semantics (Epic 4, 5).

## Binding rules (inlined)

- **DSL v1 spelling.** Steps use `uses: <kind>` with `with`, or `run: <command>`; the draft's `run: git.worktree` spelling is superseded. Every step declares `gate`. Nothing else in the draft changes.
- **`story@1`** — inputs `project (project)`, `repository (repository)`, `branch (string)`, `spec_folder (path)`, `story (item)`, `harness (enum: claude, codex, local; default claude)`, `model (string, optional)`. Steps in order: `sync` (`uses: git.sync`, deterministic); `build` (`uses: agent`, `with {harness: "{{harness}}", model: "{{model}}", skill: bmad-build-auto, args: {spec_folder: "{{spec_folder}}", story_id: "{{story.id}}"}, prompt_extra: "{{story.invoke_dev_with}}"}`, `expect {files: ["{{spec_folder}}/stories/{{story.id}}-*.md"], status_in: [done, blocked, ready-for-dev]}`, `retry {max: 2, prompt: "<the draft's retry prompt>", resume_session: true}`, `escalate_when: "output.status == blocked"`, `pause_when: "story.spec_checkpoint"`, `timeout_min: 90`, liveness); `verify` (`run: "{{repository.quality_gate_command}}"`, `on_fail: {redispatch: build, max: 1}`, `timeout_min: 30`, deterministic); `commit_guard` (`uses: git.commit`, `with {message: "story {{story.id}}: {{story.title}} (orchestrator)"}`, deterministic). No checkout: `story` is a callee only.
- **`epic@1`** — inputs `project`, `repository`, `base_branch (string)`, `branch (string)`, `spec_folder (path)`, `epic (item, optional)`, `harness`, `model`. Steps: `checkout` (`uses: git.worktree`, `with {base: "{{base_branch}}", branch: "{{branch}}"}`, deterministic; `install_command` runs inside this kind, there is no separate install step); `baseline` (`run: "{{repository.quality_gate_command}}"`, `on_fail: fail`, deterministic); `stories` (`for_each: "{{spec_folder}}/stories.yaml"`, `as: story`, `pause_after_item_when: "story.done_checkpoint"`, one inner step `story` = `uses: template`, `with {name: story, version: 1, inputs: {project, repository, branch, spec_folder, story: "{{story}}", harness, model}}`); `push` (`uses: git.push`, `with {branch: "{{branch}}"}`, deterministic); `link` (`uses: pr.link`, `with {branch: "{{branch}}"}`, liveness).
- **`initiative@1`** — inputs `project`, `repository`, `base_branch`, `initiative_folder (path)`, `harness`, `model`. One step `epics` (`for_each: "{{initiative_folder}}/epics.yaml"`, `as: epic`, `pause_after_item_when: "epic.done_checkpoint"`, inner step `epic` = `uses: template`, `with {name: epic, version: 1, inputs: {project, repository, base_branch, branch: "{{epic.branch}}", spec_folder: "{{initiative_folder}}/{{epic.spec_folder}}", epic: "{{epic}}", harness, model}}`). A comment line records that `parallel` is reserved.
- **`repo-init@1`** — inputs `project`, `repository`, `base_branch (string)`. Steps: `checkout` (`uses: git.worktree`, `with {base: "{{base_branch}}", branch: chore/bmad-init}`, deterministic); `install` (`uses: bmad.install`, deterministic, `timeout_min: 30`); `commit` (`uses: git.commit`, `with {message: "chore: initialise BMAD method (orchestrator)"}`, deterministic); `push` (`uses: git.push`, `with {branch: chore/bmad-init}`, deterministic); `link` (`uses: pr.link`, `with {branch: chore/bmad-init}`, liveness).
- **Descriptions** are one line each, stating what the Template does (NFR-8 voice).
- **Location (Structural Seed):** `templates/` at the repository root; the backend reads them by path `settings.TEMPLATES_DIR` (default `../templates` in development, `/app/templates` in the image) — add the setting and its `.env.example` line.

## Acceptance criteria

**Given** the four files
**When** each is validated with a fake repository containing the other three
**Then** every result has no errors and an empty `unvalidated` list.

**Given** `initiative@1`
**When** its calls are resolved
**Then** the call chain is `initiative → epic → story` at depth 3, and every callee input is bound with a matching type (`story: {{story}}` to an `item`, `epic: {{epic}}` to an `item`).

**Given** `story@1`
**When** parsed
**Then** it has no `git.worktree` step, `verify.on_fail` is `{redispatch: build, max: 1}`, `build.expect.files` has one glob, and `build.timeout_min` is 90.

**Given** `epic@1`
**When** parsed
**Then** it has exactly one `for_each` with `pause_after_item_when: story.done_checkpoint`, no `install` step, and `baseline.on_fail` is `fail`.

**Given** `repo-init@1`
**When** parsed
**Then** its branch literal is `chore/bmad-init` on `checkout`, `push`, and `link`, and it contains one `bmad.install` step.

**Given** the four files
**When** loaded through the YAML loader
**Then** each `version` is the integer `1` and each `name` equals the file stem.

## Implementation notes

- Copy the draft skeletons from `_bmad-output/planning-artifacts/mvp/template-dsl-draft.md` §3 and convert spellings; keep comments short.
- Test module `backend-api/tests/unit/application/templates/test_shipped_templates.py` reads the files relative to the repository root (`Path(__file__).parents[4] / "templates"`).
- `Settings.TEMPLATES_DIR` + `.env.example` line `TEMPLATES_DIR=/app/templates`.

## Verification

```bash
make lint && make test
```

## Sources for detail only

`template-dsl-draft.md` §3 (skeletons), §4. Spine AD-7 (`story@1` callee-only, `epic@1` without install), AD-16 (`repo-init@1`), Structural Seed "Shipped kinds". PRD FR-9..FR-11, FR-30.
