---
id: IMP-002
title: Run an issue-sized change through the BMAD plan gate
status: accepted
accepted: 2026-09-15 — sprint-change-proposal-2026-09-14 approved by the operator
raised: 2026-09-08
raised-by: operator — "GitHub issue → plan → human validates and adapts → develop"
area: template-dsl
prd-deltas: §5 non-goal "does not ingest issues", FR-14 (a second dispatch form), FR-33 (a fifth shipped Template)
spine-deltas: AD-19 (whether a non-Story Run writes a trajectory row)
effort: S–M for the MVP-shaped version; L for issue ingestion by API
supersedes: an earlier draft of this note that proposed a one-shot freeform dispatch with no plan gate
---

# IMP-002 — Run an issue-sized change through the BMAD plan gate

## The flow, and the short answer

The operator's flow: **a human writes a GitHub issue → the Run plans it (analyse the bug or
feature, write the plan) → a human reviews, validates or adapts the plan → the Run develops it.**

That is BMAD's own phase chain at issue scale, and it splits into two halves with opposite
answers:

| Half | Status |
| --- | --- |
| plan → human validates and adapts → develop | **already MVP.** It is Epic 6, CAP-2 and CAP-3. |
| a GitHub issue as the entry point | **an explicit PRD §5 non-goal today.** |

So the question "is this feasible at the end of the 8 epics" has a narrower answer than it
looks: the hard half is already scheduled, and what remains is an entry point.

**Feasible: yes, and small — about two stories** — provided "provide a GitHub issue" means the
human pastes the issue they wrote, not that the orchestrator fetches it from the API. That
distinction is most of the cost, and it is drawn in §4.

## 1. The plan gate already exists, end to end

Every part of "plan, stop, let a human look, then build" is built or scheduled. Traced through:

1. **The halt is asked for.** `pause_when` on an `agent` step resolves to `spec_checkpoint` on
   the planned row (`templates/agent_row.py:64`), and `compose_prompt` appends
   `HALT = " Halt after planning."` when it is set and the row is a first dispatch
   (`steps/agent.py:94,172`).
2. **The skill honours it, in any dispatch mode.** `bmad-build-auto`'s READY-FOR-DEVELOPMENT
   gate (`step-02-plan.md:22`): once the spec meets the standard, set frontmatter
   `ready-for-dev`, and "if the invocation prompt directs a halt after planning … HALT with
   status `ready-for-dev`". That check sits in the gate itself, after the plan is written, so it
   is independent of how the run was dispatched.
3. **The Run parks as a checkpoint, not a failure.** `rules/routing.py:88` —
   `READY_FOR_DEV and spec_checkpoint` → `Park(kind="checkpoint", reason="spec checkpoint")`.
   Without the declared checkpoint the same status takes the retry path, so the halt and the
   park are one decision, not two that could disagree.
4. **The human validates.** Epic 6 CAP-2: "Continue and Reject at checkpoints — spec checkpoint
   re-dispatch without the halt suffix. **success:** the planned story file is shown inline;
   Continue implements without re-planning."
5. **The human adapts.** Epic 6 CAP-3: "Inline spec editing while parked" — `GET`/`PUT
   /runs/{id}/files`, an artifacts tree and editor, "each save is one commit `spec: operator
   edit (orchestrator)` … never attributed to the agent."
6. **Development resumes from the edited plan.** On resume `resume_signal` is set, so
   `compose_prompt` omits the halt; build-auto sees `ready-for-dev` and early-exits straight to
   `step-03-implement.md`. The human's edits are what it implements, because it re-reads the
   file.

Nothing in that chain needs inventing. Epic 6 is the next epic.

## 2. Which BMAD skill is the planning phase here

For an issue-sized change the planning phase **is** `bmad-build-auto`'s own step-01 → step-02
(clarify and route → plan → the ready-for-development gate). It resolves intent against the
repository's planning artifacts, writes one spec file, and stops at the gate.

`bmad-spec` and `bmad-create-epics-and-stories` are the wrong tools at this size: they produce a
SPEC kernel and a story decomposition, which is epic-scale work and exactly what the `epic`
Template already drives. Reaching for them for one issue would mean the operator authors an epic
to fix a typo.

This is why the whole flow fits in **one `agent` step with a halt**, not a chain of skill
dispatches. The orchestrator does not need to learn BMAD's phases — build-auto already runs
them, and the orchestrator's only job is to say "stop after planning" and hold the Run open
while a person reads.

## 3. What the entry point costs — three engine gaps

`story@1` gets its intent from a `stories.yaml` row. An issue-sized Run has no such row, and
three places in the engine assume one:

- **The dispatch sentence is hardcoded to folder+id.** `steps/agent.py:90`:
  `"Run the skill {skill} in folder+id dispatch mode: spec folder {spec_folder}, story id {story_id}."`
  formats for every `agent` row. Unbound expressions resolve to `""`
  (`templates/substitute.py`), never to an omission, so a Template that bound neither sends
  *"…spec folder , story id ."* — which build-auto reads as folder+id with empty values and
  halts `no stories.yaml found`. That condition is in `CONFIGURATION_CONDITIONS`
  (`rules/routing.py:44`), so the Run parks **`misconfigured`** — the park with no Answer box.
  build-auto's freeform mode (`step-01:16`, "use the invocation prompt as the intent") is fully
  built and unreachable from here. **Size: S.** `compose_prompt` is a pure function of
  `with_resolved` — no ports, no clock — so it is one branch and a unit test.
- **`pause_when` cannot say "always".** Its grammar is a bare `name.field` over a loop item
  (`substitute.py:95` `paused`, `expressions.py:204` `_check_condition`). A Template with no
  `for_each` has no item to reference, so it cannot declare the very checkpoint this flow is
  built around. Either the grammar accepts a declared boolean input, or an issue-sized Template
  halts unconditionally. **Size: S**, and the second option is arguably the better product
  answer — see §5.1.
- **A row with no `expect` contract silently opts out of budget.** `steps/agent_tail.py:168`
  reads the glob; when the row declared none, line 170 returns `done` unconditionally and
  returns *before* `_spend_and_budget`, so no spend is recorded and FR-17's budget check never
  runs. It is safe today only because every shipped Template declares one. Any new Template must
  too — the shortcut ("no Story file to expect, so leave it off") buys an unmetered Run.
  **Size: 0 if respected**, a defect if not.

Everything else already works on any file: FR-16 routing takes the parsed file and imports no
port (`rules/routing.py`), and the verify-failure writeback reads the same glob
(`steps/agent.py:255`). `done`, `blocked`, `ready-for-dev`, the retry path, the verify
redispatch, the Answer box and the protected-path check are all glob-driven, not Story-driven.

## 4. The issue itself — the decision that sets the cost

PRD §5 line 418: *"The orchestrator does not write specs, epics, or stories, and does not ingest
issues. The human authors the Spec folder."* PRD line 43 lists "anyone expecting the
orchestrator to … open issues" among who this is not for. So this half is not an oversight to
fill in; it is a stated boundary, and moving it is a PRD decision.

There are two very different ways to move it:

**B1 — the operator pastes the issue body into an `intent` field.** No new step kind, no HTTP
call, no new secret path, AD-5 untouched. A human wrote the issue and a human starts the Run, so
the human is already present at the moment the text is needed. The PRD amendment is small: the
orchestrator still ingests nothing, it accepts an intent the operator supplies — the same thing
`stories.yaml` does today, in a text box instead of a file. **Size: S.**

**B2 — a `gh.issue` step kind that fetches issue #N.** A new kind in the AD-9 table, an HTTP
call in `infrastructure`, `GITHUB_TOKEN` read at the orchestrator and never handed to the
harness (AD-5), rate limits, a not-found path, a private-repo path, and a new row on every plan.
It also makes the Run's intent something the plan reads at planning time from a mutable external
source, which the plan-staleness rules would then have to have an opinion about. **Size: M–L,
and it genuinely changes what the product is.**

**B1 delivers the operator's flow.** "Provide a GitHub issue written by a human" is satisfied by
pasting it; fetching it is a convenience on top, not the capability. B2 belongs to a later
cycle, if the paste turns out to be the friction.

## 5. Recommendation

**One new Template, `task@1`, plus the two S-sized engine changes from §3. Ship B1. Defer B2.**

Shape — flat, no `for_each`, no `template` call, and the plan gate always on:

```yaml
name: task
version: 1
description: one issue-sized change, planned for review before it is built
inputs:
  project:       { type: project,    required: true }
  repository:    { type: repository, required: true }
  base_branch:   { type: string,     required: true }
  branch:        { type: string,     required: true }
  task_id:       { type: string,     required: true }  # gh-47, PROJ-123 — leads the spec slug
  title:         { type: string,     required: true }  # one line, for the commit subject
  intent:        { type: string,     required: true }  # the issue body, as the human wrote it
  artifacts_dir: { type: path,       required: true }
  harness:       { type: enum, values: [claude, codex, local], default: claude }
  model:         { type: string,     required: false }
steps:
  - id: checkout      # git.worktree {base: base_branch, branch: branch}
  - id: baseline      # quality gate, on_fail: fail
  - id: plan-and-build
    uses: agent
    with:
      harness: "{{harness}}"
      model: "{{model}}"
      skill: bmad-build-auto
      intent: "{{intent}}"
    expect:
      files: ["{{artifacts_dir}}/spec-{{task_id}}-*.md"]
      status_in: [done, blocked, ready-for-dev]
    retry: { max: 2, prompt: "…", resume_session: true }
    escalate_when: "output.status == blocked"
    pause_when: always            # see 5.1
    timeout_min: 90
    gate: liveness
  - id: verify        # quality gate, on_fail: {redispatch: plan-and-build, max: 1}
  - id: commit-guard  # git.commit, message: "{{task_id}}: {{title}} (orchestrator)"
  - id: push
  - id: link
```

One agent row, halted after planning, resumed by the operator's *Continue* — steps 1–6 of §1,
unchanged, on a Template with no Story in it.

### 5.1 The plan gate should be unconditional here

`story@1` makes the checkpoint per-Story (`pause_when: "story.spec_checkpoint"`) because an epic
has many Stories and the operator chooses which ones to read. A `task` Run has exactly one unit
of work and the operator started it deliberately. Halting always is both simpler — no grammar
extension, `pause_when: always` as a literal, or the kind's own default — and the right product
answer: an issue-sized change that skipped the plan review would be the freeform one-shot this
note replaced, which is the thing the methodology is there to prevent.

### 5.2 `task_id` is required, not derived

`expect.files` demands exactly one match, and `{{artifacts_dir}}/spec-*.md` matches every spec
the repository has ever produced — `ambiguous story file`, every time. build-auto leads the slug
with a tracking identifier when the intent names one (`step-01:79`, e.g. `gh-47-fix-auth`), so
`spec-{{task_id}}-*.md` narrows to one by construction. It also gives the commit a stable prefix
and gives the operator a string to search on later.

## 6. Feasibility verdict, at the end of the 8 epics

**Yes. Roughly two stories, and no new architecture.**

- Half A costs nothing by then: it lands in Epic 6 for Stories and `task@1` reuses it unchanged.
- One story: the dispatch form (`steps/agent.py`), `intent` as an `agent` `with` key
  (`templates/table.py`), the validator rule that a `uses: agent` row binds folder+id **or**
  `intent` — never both, never neither — and the unconditional plan gate.
- One story: `templates/task.yaml`, the four new form fields, and the `INTENT` textarea (the one
  place the New Workflow form grows a control rather than a row — every field today is a
  single-line `<input>`, `components/NewWorkflowFields.tsx`).

Nothing in the planner, the walker, `apply_step_result`, the status vocabulary or the signal
table changes. `task@1` is the flattest Template in the set.

Two things that are **not** free and should not be waved through:

1. **It amends a stated PRD non-goal.** §5 line 418 says the orchestrator does not ingest issues
   and the human authors the Spec folder. Even B1 needs that sentence rewritten to distinguish
   "ingests" (fetches, unattended) from "accepts an operator-supplied intent". That is a
   `bmad-prd` update-mode decision at the top of the next cycle, not something a build story
   decides on its way past.
2. **Trajectory (AD-19).** `record_trajectory` reads `build_row.story_id`
   (`use_cases/record_trajectory.py:118`), filled by the planner from the loop item
   (`templates/rows.py:295`). A `task` Run has no loop, so it is `None` and `_story_file` would
   compose a path from `""`. AD-19 says a *Story* writes a trajectory row; a task is not one, so
   `record_trajectory` should decline explicitly rather than by accident. Whether task Runs
   should feed the training data at all is an AD-19 amendment and its own decision.

## 7. Open questions

1. **Naming, with IMP-001.** `task` beside `story-run` reads well; `fix` is narrower than what
   this does (a small feature is not a fix). Name the two together.
2. **Baseline on a small change.** A full quality-gate run before a one-line fix is a large
   share of the Run's cost. Same question as IMP-001 §3, with more force.
3. **Does `artifacts_dir` belong on the Repository?** It is the target repository's BMAD config
   speaking, not the operator's choice, and every other repository fact the Run needs
   (`quality_gate_command`, `default_branch`, `test_globs`) is already a Repository field set
   once. Moving it drops an input here and lets `epic` and `story-run` stop passing folders
   around too.
4. **Should `task@1` open the pull request?** `pr.link` records a compare URL and stops there;
   creating the PR is a PRD non-goal (line 207). For an issue-sized change the compare link is
   probably enough, but the issue number is right there and `Fixes #47` in a PR body is the
   thing that closes the loop the operator described.
