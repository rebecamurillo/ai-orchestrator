---
story: "4-2"
epic: 4
title: Pure planner plan_run
requirements: [FR-8, FR-10 (list read once, already done), NFR-2, AR-10]
binds: [AD-2, AD-7, AD-9, AD-15, AD-16]
---

# Story 4.2 — Pure planner `plan_run`

As the Operator,
I want the whole Run planned into rows from my branch at one commit before anything starts,
So that *What will run* is exactly what runs, and no later edit of the branch or the repository can change it.

## Scope

**In:** `application/templates/plan.py::plan_run`, `application/use_cases/plan_run.py` (thin wrapper resolving the template tree through the repository port), row path and label rules, list-file reading through `Git`, the skipped rules, plan-time errors, unit tests on fake `Git` for the four shipped Templates.
**Out:** persistence (4.4), pre-flight lines (4.3), execution.

## Binding rules (inlined)

- **Signature.** `plan_run(tree: ResolvedTree, inputs: RunInputs, *, git: Git, bmad_version: str) -> Plan{plan_ref, plan_refs, rows: [PlannedRow]}` — pure apart from `Git.ls_remote / read_file / list_files`; no clock, no randomness. `ResolvedTree` = the root `ParsedTemplate` plus every callee `ParsedTemplate` by `(name, version)` (loaded by the wrapper through `TemplateVersionRepository`; a missing callee is a plan error). `RunInputs` = `{project: ProjectSnapshot, repository: RepositorySnapshot, base_branch, template inputs…, harness, model, re_review_done}`.
- **`plan_ref`.** For `epic@1` and `repo-init@1`: SHA of `origin/{branch}` when the working branch exists, else of `origin/{base_branch}`. For `initiative@1`: SHA of `origin/{base_branch}` `[ASSUMPTION: the Initiative folder is read on the base branch; a list file absent at base is read at the epic's branch head when that branch exists, and that SHA is recorded in plan_refs[path]]`. Every `Git.read_file` / `list_files` uses the recorded ref for that path.
- **Rows and order.** Traversal order of the pinned tree, `seq` dense from 1. Row 1 is always `plan` (`kind: plan.check`, `gate: deterministic`, `label: plan`). A `template` call is not a row; its callee's steps are inlined. **Paths:** top-level step → its id; `for_each` element `i` → `{loop_id}[{i}]` prefix; a `template` call inside a `for_each` contributes no segment; a `template` call at top level contributes its id. So `initiative@1` yields `epics[0].checkout`, `epics[0].baseline`, `epics[0].stories[3].sync`, `epics[0].stories[3].build`, `epics[0].stories[3].verify`, `epics[0].stories[3].commit_guard`, `epics[0].stories[3].after`, `epics[0].push`, `epics[0].link`, `epics[0].after`; `epic@1` yields `checkout`, `stories[3].build`, …; `repo-init@1` yields `checkout install commit push link`. **Frame:** the innermost `…stories[n]` or `epics[n]` prefix; `story_id` = the item's `id` for rows inside a story frame.
- **Labels.** `epic {i+1}` for an `epics[i]` frame, `story {item.id}` for a `stories[j]` frame, then the step id with `_` → ` `: `epic 1 · story 4-1 · build`; `epic 1 · checkout`; top-level `checkout`. Checkpoint rows: `… · done checkpoint` (`after`) / `… · before`.
- **Checkpoint rows (AD-7).** `pause_after_item_when: <as>.<field>` → a row `{prefix}.after` (`kind: checkpoint`, `gate: human`, `status: planned`) only when the item's field is truthy; `pause_before_item_when` → `{prefix}.before` first in the frame. `pause_when` on an `agent` step stays a flag: `with_resolved.spec_checkpoint = bool(item.field)`.
- **List files.** `for_each: "{{spec_folder}}/stories.yaml"` → `Git.read_file(ref, path)` parsed as a YAML list; `epics.yaml` likewise. Validation at plan time (errors carry `{template, version, line, item}`): missing file; unparseable; a `stories.yaml` entry without `id`, `title`, `description`; ids not unique; ids not prefix-free (`4-1` vs `4-1-a` → error, `4-1` vs `4-10` fine); an `epics.yaml` entry without `id`, `title`, `branch`, `spec_folder`. Each list file is read once.
- **Substitution.** `with_resolved` = every `with` value with `{{name}}` / `{{name.field}}` replaced from `RunInputs`, the loop item, and the entity whitelist (`project.name`, `repository.url | default_branch | install_command | quality_gate_command | unit_test_command`); an `item` value used whole (`story: "{{story}}"`) passes the item mapping through to the callee's inputs. The agent row's `with_resolved` also carries `story` (whole item), `spec_folder`, `story_id`, `prompt_extra` (= `invoke_dev_with` or empty), `expect`, `retry`, `timeout_min`.
- **Skipped at plan time.** A `shell` row whose resolved command is empty → `status: skipped`, `reason: no quality_gate_command` when the expression was `{{repository.quality_gate_command}}`, else `no command`. A story whose file `{spec_folder}/stories/{id}-*.md` exists at the ref with frontmatter `status: done` → every row of its frame (`sync`, `build`, `verify`, `commit_guard`, `before`, `after`) `skipped · already done`, unless `inputs.re_review_done`. Two or more matching files at plan time → plan error `ambiguous story file: {id}`.
- **Defaults.** `timeout_min` from the step or the kind default (90 agent / 30 shell / 5 git; `bmad.install` 30; `checkpoint` none); `gate` from the step or `unvalidated` when absent (never inferred from the kind).
- **Layering:** `plan.py` imports the parsed model, the kind registry, `domain`; no YAML file I/O except through `Git`.

## Acceptance criteria

**Given** `repo-init@1` with a repository snapshot and `base_branch: main`, and a fake `Git` where `chore/bmad-init` does not exist
**When** planned
**Then** `plan_ref` is the base SHA and the rows are `plan, checkout, install, commit, push, link` with `seq` 1–6, gates `deterministic ×5, liveness`, `checkout.with_resolved = {base: main, branch: chore/bmad-init}`, `push.with_resolved.branch = chore/bmad-init`.

**Given** `epic@1` with a `stories.yaml` of three stories where story `2` has `done_checkpoint: true` and story `3` has a `done` story file, and `re_review_done` false
**When** planned
**Then** rows are `plan, checkout, baseline, stories[0].sync, stories[0].build, stories[0].verify, stories[0].commit_guard, stories[1].sync … stories[1].commit_guard, stories[1].after, stories[2].sync … (all skipped · already done), push, link`; labels read `story 1 · build`, `story 2 · done checkpoint`; `story_id` and `frame` are set on every story row.

**Given** the same with `re_review_done: true`
**When** planned
**Then** story `3`'s rows are `planned`, not skipped.

**Given** a repository without `quality_gate_command`
**When** `epic@1` is planned
**Then** `baseline` and every `verify` row are `skipped · no quality_gate_command`.

**Given** `initiative@1` with two epics on the same branch and eight stories
**When** planned
**Then** paths follow `epics[i].stories[j].<step>`, labels `epic 1 · story 4-1 · build`, each epic frame ends with `epics[i].push`, `epics[i].link`, and `epics[i].after` only when the epic declares `done_checkpoint`; the second epic's list file is read once.

**Given** a `stories.yaml` with ids `4-1` and `4-1-a`, or a missing `SPEC.md`-independent required field
**When** planned
**Then** a `PlanError{template, version, line, item, reason}` is raised naming the entry.

**Given** a step without `gate` in a custom template
**When** planned
**Then** its row has `gate: unvalidated`.

## Implementation notes

- `application/templates/plan.py`: `_walk(steps, prefix, scope)` recursion, `_expand_loop`, `_resolve_with`, `_story_done(ref, spec_folder, id)`; keep functions ≤ 50 lines.
- Snapshots: `ProjectSnapshot{id, name, slug}`, `RepositorySnapshot{id, slug, url, default_branch, install_command, quality_gate_command, unit_test_command, test_globs}` in `application/dto.py`.
- Test fixtures: fake `Git` scripted with `{(ref, path): content}` and `{(ref, prefix): [files]}`.

## Verification

```bash
make lint && make test
```

## Sources for detail only

PRD FR-8 (What will run, plan commit), FR-10 (list read once, already done). Spine AD-7 (the rule text), AD-15, Structural Seed "Shipped kinds" defaults, `template-dsl-draft.md` §3 for the Template shapes.
