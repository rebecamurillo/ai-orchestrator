---
title: Template DSL — skeleton draft (initiative → epic → story)
status: draft
created: 2026-09-02
purpose: input to bmad-architecture; records the 2026-09-02 decisions on template composition, auto-retry, and one repository per run
supersedes-partially: ../v1-dev-loop-2026-08-26/architecture-v1.md §2.2 (template schema)
prd-deltas: FR-5, FR-7, FR-10, FR-13, FR-16, FR-29 (listed in §5)
---

# Template DSL — skeleton

## 1. Decisions (2026-09-02)

1. **Three templates, composed by call.** `initiative` loops over epics and calls `epic`; `epic` loops over stories and calls `story`. A Run instantiates one top-level Template Version; the callee Versions are pinned with it.
2. **One Run = one Repository = one Initiative.** Multi-repository initiatives are split by the human into one Run per Repository (PRD §6.2 stands).
3. **Auto-retry is a Step parameter.** An `agent` Step may declare `expect` (files the agent must produce) and `retry { max, prompt }`; a missing artifact resumes the agent's session with the retry prompt up to `max` times before the Run goes `needs-you`. Without `retry`, behaviour is PRD FR-16 (straight to `needs-you`).
4. **No pre-check step.** The agent is instructed to stop `blocked` when information is missing; that is the existing `needs-you` path (FR-16/FR-18).
5. **Epics run sequentially in the MVP.** List order is the dependency. `parallel: n` on a `for_each` is reserved in the schema and rejected by the validator until a later version (see §4).

## 2. Step vocabulary

Every Step: `id`, `run`, `with`, `gate` (`liveness | deterministic | human`; missing → `unvalidated`), `timeout_min` (defaults 90 agent / 30 shell / 5 git), `on_fail` (`escalate` default | `fail` | `continue`). All Steps of a Run execute in the Run's single Worktree.

| `run` | What it does | `with` parameters | Gate |
|---|---|---|---|
| `git.worktree` | Idempotent checkout: create the Worktree on `branch` from `origin/{base}` when the branch does not exist; when it exists, `fetch` + `pull --ff-only` from origin before anything else. Refuses on a dirty tree. | `base`, `branch` | deterministic |
| `git.sync` | `fetch` + `pull --ff-only` on the current branch (used at the start of each story so a long epic picks up pushes made meanwhile). | — | deterministic |
| `shell` | Run a Repository command in the Worktree; `skipped` when the bound command is empty. | `command` | deterministic |
| `agent` | Dispatch a Harness (FR-14); record harness, model, session id, usage, cost, exit code on the Attempt. | `harness`, `model?`, `skill`, `args{}`, `prompt_extra?`, `expect{}`, `retry{}`, `escalate_when`, `pause_when` | liveness |
| `git.commit` | Commit-guard: stage the Spec folder first, then everything else; `no changes` is the normal case. | `message` | deterministic |
| `git.push` | Push the branch with the Project token injected per command; refuses on the default branch; rejected push → `needs-you`. | `branch` | deterministic |
| `pr.link` | Record the GitHub compare URL `{default}...{branch}` on the Run (no PR creation). | `branch` | liveness |
| `template` | Call another Template Version with explicit inputs; its Steps execute inline under this Step's path. | `name`, `version`, `inputs{}` | (inherits) |

Constructs: `for_each: <list file>` + `as: <name>` + `steps: [...]`, with `pause_before_item_when` / `pause_after_item_when` (item expressions only). One `for_each` per Template, no nesting inside a Template — nesting is achieved only by `template` calls, which keeps FR-5's "no nested for_each" rule per file while allowing depth by composition.

### `agent` extras

```yaml
expect:
  files: ["{{spec_folder}}/stories/{{story.id}}-*.md"]   # each glob must match exactly one file
  status_in: [done, blocked, ready-for-dev]               # frontmatter routing set (FR-16)
retry:
  max: 2                       # extra attempts after the first
  prompt: "..."                # sent as a resume message into the same session
  resume_session: true         # false → new session, prompt prepended (harness without resume)
escalate_when: "output.status == blocked"
pause_when: "story.spec_checkpoint"      # only item fields; evaluated by the caller
```

Retry semantics: an `expect` miss (zero/several files, unparseable frontmatter, status outside `status_in`) → new Attempt on the same Step, same session id when the Harness `capabilities.resume` is true, otherwise a new session with the retry prompt prepended. Attempts are numbered on `step_run`; the Steps table shows the latest and counts the rest (Glossary: Attempt). Exhausted → Step `error`, Run `needs-you` with reason `expect failed after {max+1} attempts` and the last output. Configuration failures (FR-16 list) are never retried.

## 3. The three skeletons

### 3.1 `story` v1

```yaml
name: story
version: 1
description: one story to a verified commit
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  branch:      { type: string,     required: true }
  spec_folder: { type: path,       required: true }
  story:       { type: item,       required: true }     # bound by the caller's for_each
  harness:     { type: enum, values: [claude, codex, local], default: claude }
  model:       { type: string,     required: false }
steps:
  - id: sync
    run: git.sync
    gate: deterministic

  - id: build
    run: agent
    with:
      harness: "{{harness}}"
      model: "{{model}}"
      skill: bmad-build-auto
      args: { spec_folder: "{{spec_folder}}", story_id: "{{story.id}}" }
      prompt_extra: "{{story.invoke_dev_with}}"
    expect:
      files: ["{{spec_folder}}/stories/{{story.id}}-*.md"]
      status_in: [done, blocked, ready-for-dev]
    retry:
      max: 2
      prompt: "No story file with a terminal status was found at {{spec_folder}}/stories/{{story.id}}-*.md. Finish the story and write that file, or set status: blocked with the reason."
      resume_session: true
    escalate_when: "output.status == blocked"
    pause_when: "story.spec_checkpoint"
    timeout_min: 90
    gate: liveness

  - id: verify
    run: shell
    with: { command: "{{repository.quality_gate_command}}" }
    on_fail: { redispatch: build, max: 1 }     # append '## Verify Failure', status in-progress (FR-10)
    timeout_min: 30
    gate: deterministic

  - id: commit_guard
    run: git.commit
    with: { message: "story {{story.id}}: {{story.title}} (orchestrator)" }
    gate: deterministic
```

### 3.2 `epic` v1

```yaml
name: epic
version: 1
description: all stories of one epic on one branch, pushed
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
  spec_folder: { type: path,       required: true }     # holds SPEC.md, stories.yaml, stories/
  epic:        { type: item,       required: false }    # bound when called from initiative
  harness:     { type: enum, values: [claude, codex, local], default: claude }
  model:       { type: string,     required: false }
steps:
  - id: checkout
    run: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}" }
    gate: deterministic

  - id: baseline
    run: shell
    with: { command: "{{repository.quality_gate_command}}" }
    on_fail: fail                                   # FR-9: non-zero baseline → Run failed
    gate: deterministic

  - id: stories
    for_each: "{{spec_folder}}/stories.yaml"
    as: story
    pause_after_item_when: "story.done_checkpoint"
    steps:
      - id: story
        run: template
        with:
          name: story
          version: 1
          inputs:
            project: "{{project}}"
            repository: "{{repository}}"
            branch: "{{branch}}"
            spec_folder: "{{spec_folder}}"
            story: "{{story}}"
            harness: "{{harness}}"
            model: "{{model}}"

  - id: push
    run: git.push
    with: { branch: "{{branch}}" }
    gate: deterministic

  - id: pr
    run: pr.link
    with: { branch: "{{branch}}" }
    gate: liveness
```

### 3.3 `initiative` v1

```yaml
name: initiative
version: 1
description: every epic of one initiative, in order, on one repository
inputs:
  project:           { type: project,    required: true }
  repository:        { type: repository, required: true }
  base_branch:       { type: string,     required: true }
  initiative_folder: { type: path,       required: true }   # holds epics.yaml + one spec folder per epic
  harness:           { type: enum, values: [claude, codex, local], default: claude }
  model:             { type: string,     required: false }
steps:
  - id: epics
    for_each: "{{initiative_folder}}/epics.yaml"
    as: epic
    # parallel: 1   — reserved; sequential in the MVP, list order is the dependency
    steps:
      - id: epic
        run: template
        with:
          name: epic
          version: 1
          inputs:
            project: "{{project}}"
            repository: "{{repository}}"
            base_branch: "{{base_branch}}"
            branch: "{{epic.branch}}"
            spec_folder: "{{initiative_folder}}/{{epic.spec_folder}}"
            epic: "{{epic}}"
            harness: "{{harness}}"
            model: "{{model}}"
```

`epics.yaml` (new, human-authored; `bmad-spec` produces `stories.yaml` per epic, not this list):

```yaml
- id: notifications
  title: Notifications
  branch: feat/notifications
  spec_folder: notifications          # relative to initiative_folder
  done_checkpoint: false
- id: saved-views
  title: Saved views
  branch: feat/notifications          # same branch → stacked; different branch → separate PR
  spec_folder: saved-views
```

## 4. Implications of composition

- **Versions pin a tree.** Starting a Run under `initiative@1` pins `epic@1` and `story@1` as well; FR-6 immutability becomes transitive (a callee Version pinned by any Run is frozen). The versions list shows callers.
- **Validation is cross-template.** The validator resolves every `template` call, checks input names and types against the callee's declared inputs, rejects cycles and depth > 3, and rejects `parallel` until supported. Unbound variables are reported with the calling Template's line.
- **Execution planning happens at Run start.** The interpreter reads each `for_each` list file exactly once (a DBOS step, so recovery replays the same plan) and expands the tree lazily as it descends; the Steps table stores each Attempt under a **path** (`epics[0].epic.stories[3].story.build`) rather than a flat step id. Attempt counts, retries, and Skip/Retry act on the path.
- **Variables do not inherit.** A callee sees only what its caller passes in `inputs`; item bindings (`{{story.*}}`) are explicit inputs of type `item`. This keeps FR-5's "substitution only" rule and makes each Template testable alone.
- **Worktree is per Run, branch per epic.** One Worktree per Run (FR-9 path unchanged) — `git.worktree` at the head of `epic` switches or creates the epic's branch; when two epics share a branch it degrades to `git.sync`. Two epics on different branches therefore run on one worktree sequentially. Parallel epics would need one Worktree per branch and a per-branch lock — that is why `parallel` is deferred, not because of the queue.
- **Skip gains a level.** "Skip story" stays; "Skip epic" (skip remaining stories, no push) is a new Operator action on the Run detail (FR-20). Cancel is Run-level as before.
- **Checkpoints stay item-level.** `spec_checkpoint` / `done_checkpoint` are story fields; `epics.yaml` may carry `done_checkpoint` per epic, evaluated by the initiative's `for_each` after the epic's `pr` step.
- **Push and PR move from Run-end to epic-end.** A Run ends with one compare URL per epic; the card reads `n/n epics · m/m stories · k PRs`.
- **Diagrams.** FR-7 renders a Template file with `template` calls as collapsed nodes (expand on click, read-only). FR-29's run tree gains the initiative as its root: initiative → epics → stories → story sub-steps — the level removed on 2026-08-28 returns as the root of one Run, still within one repository.
- **Tracing and cost roll up.** Spans nest by path; cost per epic and per initiative are sums, no new instrumentation.
- **Standalone use.** `epic` remains startable directly from *New workflow* — the dev-loop of PRD UJ-2 is exactly `epic@1`; `story` is a callee only (it has no checkout), and the harness readiness run uses `epic@1` (spine AD-10, 2026-09-02). `initiative` is the new top level. `install_command` runs inside `git.worktree`, so `epic@1` has no separate install step (spine kinds table).

## 5. PRD deltas to apply

| FR | Change |
|---|---|
| FR-5 | Add step types `git.sync`, `pr.link`, `template`; input type `item`; `expect`/`retry` on `agent`; `for_each` options `pause_before_item_when`, `pause_after_item_when`, reserved `parallel`; cross-template validation rules (§4). |
| FR-6 | Transitive pinning of callee Versions. |
| FR-7 | Collapsed callee nodes in the rendered diagram. |
| FR-9 / FR-10 / FR-11 | Loop and push/PR described per epic; `git.sync` per story; ships three Templates instead of one `dev-loop`. |
| FR-16 | Add the `expect` + `retry` path before `needs-you`; retries resume the same session where the Harness allows. |
| FR-20 | Add *Skip epic*. |
| FR-22 / FR-23 | Card and header counts per epic; Steps table keyed by path. |
| FR-29 | Initiative as the root level of the Run diagram. |
| Glossary | Initiative, `epics.yaml`, Path, Callee Version. |
| §6.1 | Tier: `story`/`epic` templates + `template` call MUST; `initiative` template SHOULD; `parallel` out of scope. |

## 6. Open points for bmad-architecture

1. Is `template` a Step (`run: template`) or a construct like `for_each` (`call:`)? Draft uses a Step so it can carry `timeout_min`/`on_fail` — the callee's own Steps still own their gates.
2. Retry prompt delivery for Harnesses without `resume` (OpenCode?): new session with the retry text prepended, or refuse `retry` for that Harness at validation time.
3. Does `verify` re-dispatch (FR-10, `## Verify Failure`) count against the same `retry.max` or its own counter? Draft: separate (`on_fail.max`).
4. Worktree switching between epic branches on one Worktree vs. one Worktree per branch (`/work/{project}/{repo}/wt/{branch}` already keys by branch — the second is closer to FR-9's path).
