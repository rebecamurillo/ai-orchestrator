---
id: IMP-001
title: Start a Run for one Story
status: candidate
raised: 2026-09-08
raised-by: operator, from the New Workflow screen during Epic 5
area: template-dsl
prd-deltas: FR-5 (a plan-time list selector), FR-10 (a Story loop that plans one entry), FR-33 (a fourth shipped Template)
spine-deltas: none
effort: M
---

# IMP-001 — Start a Run for one Story

## Problem

The New Workflow screen offers `initiative`, `epic` and `repo-init`. There is no way to start
a Run for a single Story — the smallest unit of development the system knows about. An
operator who wants one Story built has to start an `epic` Run and rely on the already-done
rule to skip everything else, which means the target Story must be the only entry of its
`stories.yaml` not yet marked `done`. Re-running one Story that is already `done` is possible
only by ticking *re-review done stories*, which re-runs every done Story in the epic.

`templates/story.yaml` exists and is seeded, so the operator can see it on `/templates` and
reasonably expects to be able to start it. It is not startable, and the screen says nothing
about why.

## Evidence

- The dropdown is a fixed list, not `GET /templates`:
  `web-client/src/lib/newwf/state.ts:21` — `TEMPLATE_ORDER = ['initiative', 'epic', 'repo-init']`.
  The comment above it states the rule: `story` "is never started directly".
- `story@1` cannot be bound from a form: `templates/story.yaml:9` declares
  `story: { type: item, required: true }  # bound by the caller's for_each`. Its steps read
  `{{story.id}}`, `{{story.title}}` and `{{story.invoke_dev_with}}` — four fields that exist
  only on a `stories.yaml` entry, not on anything the form collects.
- An unbound name is not an error. `application/templates/substitute.py` resolves an unbound
  `{{ }}` to `""`, so a `story@1` Run started with no `story` value would dispatch an agent
  with an empty story id rather than refuse.
- `required` is enforced on template *calls* only — `application/templates/calls.py:166`
  `_check_required` — never on the inputs an operator supplies at Run creation. Nothing would
  catch the missing binding.
- `story@1` is a callee, not a root: it has `git.sync` but no `git.worktree`, no baseline
  quality-gate step, and no `push` or `pr.link`. `application/templates/plan_model.py:134`
  `working_branch` derives the Run's branch from the `git.worktree` step; a root Template
  without one works from the base branch.
- The loop has no selector. `ForEach` carries `source`, `as_name`, `steps` and the two
  `pause_*_item_when` conditions (`application/templates/model.py:158`), and
  `application/templates/rows.py:188` `expand_loop` plans one frame per entry of the file,
  unconditionally. The only filter that exists is the already-done rule
  (`rows.py:328` `_already_done`, FR-10).
- Composition has room: `MAX_DEPTH = 3`, root inclusive (`application/templates/calls.py:49`),
  and `initiative → epic → story` already uses all three. A new root calling `story@1`
  directly is depth 2.

## Options

### A — merge it into `story@1`, making one Template both root and callee

Add `base_branch`, a `git.worktree` step, a baseline, a `push` and a `pr.link`, and let `epic`
keep calling it.

Costs: those five steps must not run when `epic` calls it once per Story — the Run would
re-checkout and push on every Story. Suppressing them needs a per-step condition, and FR-5
states plainly that no conditionals are accepted. It also does not solve the binding problem:
`story: {type: item}` still has no form representation. And editing the shipped file re-seeds
it as stored version 2 (`application/use_cases/templates.py:289` `_seed_file` allocates
`max(existing) + 1` by content hash) while `epic.yaml`'s call stays pinned to `version: 1`,
so the file's own `version:` field and the stored number would disagree.

Rejected.

### B — a new root Template that calls `story@1` unchanged, plus a plan-time list selector

```yaml
name: story-run
version: 1
description: one story of an epic, on its branch, pushed
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
  spec_folder: { type: path,       required: true }
  story_id:    { type: string,     required: true }
  harness:     { type: enum, values: [claude, codex, local], default: claude }
  model:       { type: string,     required: false }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}" }
    gate: deterministic

  - id: baseline
    run: "{{repository.quality_gate_command}}"
    on_fail: fail
    gate: deterministic

  - id: stories
    for_each: "{{spec_folder}}/stories.yaml"
    as: story
    only: "{{story_id}}"                 # NEW — the one added key
    steps:
      - id: story
        uses: template
        with:
          name: story
          version: 1
          inputs: { project, repository, branch, spec_folder, story, harness, model }

  - id: push
    uses: git.push
    with: { branch: "{{branch}}" }
    gate: deterministic

  - id: link
    uses: pr.link
    with: { branch: "{{branch}}" }
    gate: liveness
```

Costs: one new DSL key (`only:` on `for_each`, matching an entry's `id`), one new shipped
Template file, three new fields in the web-client's fixed enumeration.

### C — a `story_id` input the planner resolves against the list file itself

A new input type (`item_ref`, or a `lookup:` step) that reads `stories.yaml` and binds the
matching entry. Same end result as B, but it invents a second way to reach a list file
alongside `for_each`, and the resolution would have to duplicate `read_list`'s frame and ref
handling (`application/templates/lists.py:95`).

### D — do nothing; document the workaround

`epic` plus the already-done rule already runs whatever is not yet `done`. Zero cost, but it
answers only "build the next unfinished Story", never "build this one".

## Recommendation

**Option B — a new `story-run` Template, and one new `for_each` selector. Do not merge into
`story@1`.**

Why B over A: `story@1` stays exactly what it is — the callee `epic` pins — so the two paths
cannot drift. Every gate, retry, redispatch and commit-guard rule a Story gets inside an epic
is the same code on the same pinned version, because it is literally the same version. A
merged Template would need conditionals FR-5 forbids, and would make the one file two things
at once.

Why B over C: the selector is the smaller primitive and it pays for itself elsewhere. `only:`
also gives "re-run just Story 5-11 of this epic" without re-running the epic, and leaves room
for a `from:` sibling ("run the epic from Story N onward") that operators have wanted at every
halt so far. C buys the same single case and nothing else.

Why B over D: D leaves the failure silent. The Template is visible on `/templates` and cannot
be started, which reads as a defect.

Two properties worth stating explicitly, because they are what make B cheap:

- **The selector filters at planning, not at execution.** `expand_loop` already reads the list
  once, at plan time, and the plan is fully enumerated before the first Step runs (FR-10,
  AD-7). Filtering the entry list there changes how many rows are planned and nothing about
  how a row executes — it is not a runtime conditional, and FR-5's "no conditionals" rule
  stands. This distinction should be written into the FR-5 delta, not left implied.
- **`git.worktree` is idempotent.** It creates the branch from `origin/{base}` when it does not
  exist and fast-forwards it when it does. So a `story-run` aimed at a branch an earlier `epic`
  Run already pushed continues that branch rather than starting a new one — which is the actual
  operator need behind this request.

## Scope of change

- `templates/story-run.yaml` — new, ~40 lines, shape above.
- `application/templates/model.py` — `ForEach.only: str | None`.
- `application/templates/table.py:29` — add `only` to `FOR_EACH_KEYS`. That frozenset is the
  key table `keys.py:213` checks a loop against, and it is what rejects every other key today.
- `application/templates/expressions.py` — `only` reads the *outer* scope (it names an input),
  unlike `pause_*_item_when`, which read the item. Same split `_check_for_each` already makes
  for `source` versus the pause conditions.
- `application/templates/rows.py::expand_loop` — filter `items` by `ID_KEY` after
  `check_entries`, before the frame loop. Entry ids are already validated unique
  (`lists.py:209` `_check_ids`), so the match is exact and at most one.
- A selector that matches nothing must be a `PlanError` — `story id not in list` — not an empty
  plan. Every other list refusal in `lists.py` works that way.
- `web-client/src/lib/newwf/state.ts` — add `story-run` to `TEMPLATE_ORDER` and its three
  fields (`WORKING BRANCH`, `SPEC FOLDER`, `STORY ID`) to `TEMPLATE_INPUT_FIELDS`.
  `usesHarness` stays true; pre-flight, the harness list and *what will run* need no change.
- `contracts/openapi.json` is unaffected: `RunIn.inputs` is already an open object.

## Open questions

1. **Name.** `story-run` sits next to `initiative`, `epic`, `repo-init` in the dropdown, which
   shows raw names. `dev` and `single-story` are the alternatives.
2. **An already-done Story.** `_already_done` skips a Story whose file reads `done` unless
   *re-review done stories* is on. Under `story-run` that plans a Run with no Story rows at
   all. Either the selector implies re-review (the operator named one Story; naming it is the
   request), or pre-flight's *what will run* must state the empty plan before start. The second
   is more honest and keeps the two flags orthogonal — decide in planning.
3. **Baseline.** Keeping it means one full quality-gate run before a single Story's agent
   starts. That is the right default on a fresh branch and pure cost when continuing a branch
   the same gate passed ten minutes ago. Possibly an input, possibly always on.
4. **`for_each` over `epics.yaml`.** `only:` is written above against `stories.yaml`, but
   nothing about it is Story-specific — `initiative` could take it too ("run just this epic").
   Worth deciding whether the key is general from the start or narrowed and widened later.
