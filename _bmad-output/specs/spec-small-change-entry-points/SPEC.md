---
id: SPEC-small-change-entry-points
status: draft
created: 2026-09-08
companions: []
sources:
  - ../../planning-artifacts/improvements/IMP-001-single-story-run.md
  - ../../planning-artifacts/improvements/IMP-002-issue-sized-change.md
  - ../../planning-artifacts/mvp/prd.md
  - ../../planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/mvp/template-dsl-draft.md
---

> **Post-MVP.** This spec is written against the MVP as it stands after Epic 8 and assumes every
> gate of Epics 1–8 has landed; in particular it assumes Epic 6's spec checkpoint — halt, park,
> inline edit, *Continue* — works for Stories. It is planning input, not a scheduled epic. The
> repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when
> this spec and the code disagree.

# Small-change entry points

## Why

A pain to solve: the orchestrator can only be started at initiative or epic scale, so the two
smallest units of real work have no way in. An operator who wants one Story built must start an
epic Run and rely on the already-done rule to skip the rest, which works only when the target is
the epic's single unfinished Story. An operator holding a GitHub issue — the ordinary unit of
maintenance — has nothing to start at all: no epic, no spec folder, no `stories.yaml` entry, and
writing one costs more than the change.

The ladder is missing its bottom two rungs. `initiative` and `epic` ship; one Story of an epic,
and one issue-sized change, do not. Both are cheap, because the machinery each needs already
exists and is aimed at a Story it cannot reach: the plan gate, the FR-16 routing table, the retry
and redispatch paths, the Answer box and the protected-path check are all glob-driven and
Story-agnostic (`application/rules/routing.py` imports no port; `steps/agent.py:255` and
`steps/agent_tail.py:168` read the same glob). What blocks both is narrower than it looks — a
loop with no selector, and a dispatch sentence with one hardcoded form.

## Capabilities

- **CAP-1** Run one Story of an epic — a shipped `story-run@1` Template (checkout, baseline, the
  one Story, push, compare link) that calls `story@1` unchanged, and an `only:` key on `for_each`
  that narrows a list file to the entry whose `id` matches, resolved at planning. **success:** an
  operator names a Project, Repository, working branch, spec folder and Story id on *New
  Workflow* and the Run plans exactly that Story's rows; a `story-run` onto a branch an earlier
  `epic` Run pushed continues that branch rather than starting a new one; an `only:` that matches
  nothing refuses at planning with `story id not in list` rather than planning an empty Run;
  `epic@1` and `templates/story.yaml` are byte-identical to what shipped.
- **CAP-2** Run an issue-sized change through the plan gate — a shipped `task@1` Template, flat
  (no `for_each`, no `template` call), whose one `agent` row dispatches `bmad-build-auto` on an
  operator-supplied intent and always halts after planning. **success:** the Run parks
  `CHK · spec checkpoint` with the planned spec shown inline; the operator edits it in place and
  clicks *Continue*; the resumed dispatch implements the edited plan without re-planning; verify,
  commit-guard, push and the compare link then run as they do for a Story.
- **CAP-3** A dispatch sentence that matches what the row bound — folder+id when `spec_folder`
  and `story_id` are bound, freeform intent when the row carries `intent` instead. **success:**
  `compose_prompt` is still a pure function of the resolved row; a `uses: agent` step that binds
  both forms, or neither, is refused by *Validate* at save time with its line and reason, not at
  dispatch time inside a Run.
- **CAP-4** Both Templates startable from the New Workflow form — `story-run` and `task` in the
  form's enumeration with their own inputs, and a multi-line control for `intent`. **success:**
  pre-flight, the harness list, *what will run* and the budget field work for both without
  special-casing; a disabled harness is still not selectable; the *re-review done stories* switch
  still reads a Story's file, not the operator's ticket.

## Constraints

- `templates/story.yaml` and `templates/epic.yaml` are not edited. `story-run@1` and `epic@1`
  pin the same `story@1`, so the two paths cannot drift; a Template file edited in place would
  re-seed as a new stored version while its callers stay pinned to the old one
  (`use_cases/templates.py:289`).
- `only:` filters at planning, not at execution. The list is read once, the plan is fully
  enumerated before the first row runs (FR-10, AD-7), and no row's behaviour depends on it — so
  FR-5's "no conditionals" rule stands unchanged, and the delta to FR-5 says exactly that.
- Every `agent` row declares an `expect` contract. A row without one returns `done`
  unconditionally and returns before the spend and budget check
  (`steps/agent_tail.py:168`), so an unmetered Run is one omitted key away; the validator
  refuses a `uses: agent` step with no `expect`.
- Dependency direction, the two status writers, the one credential and TDD are unchanged
  (AD-2, AD-8, AD-4/AD-5, AD-18). `task@1` reads no external service: the intent is text the
  operator supplies, so no new port, no new secret path, and no `GITHUB_TOKEN` reaches a harness.
- **Precondition, not a build decision:** PRD §5 ("the orchestrator … does not ingest issues; the
  human authors the Spec folder") must first be amended to separate *ingesting* an issue —
  fetching it unattended — from *accepting* an operator-supplied intent. That is a `bmad-prd`
  update-mode decision at the top of the cycle. Without it CAP-2 contradicts a stated non-goal.
- A Run of `task@1` writes no trajectory row. `record_trajectory` reads `build_row.story_id`
  (`use_cases/record_trajectory.py:118`), which the planner fills from a loop item; a flat
  Template has none. It declines explicitly rather than composing a path from an empty id.
  Whether task Runs should feed the training data is an AD-19 amendment and its own decision.

## Non-goals

- No `gh.issue` step kind and no GitHub API read. The operator pastes the issue body they wrote;
  fetching it is a convenience on a later cycle, and it would make a Run's intent a mutable
  external source the plan-staleness rules must then have an opinion about.
- No pull request creation — the compare link stands (PRD line 207), for these Templates as for
  `epic`.
- No `from:` selector ("run the epic from Story N onward"), no `only:` over `epics.yaml`, and no
  multi-Story selection. `only:` is specified here for one id against `stories.yaml`; widening it
  is a later decision the key's shape deliberately leaves room for.
- The orchestrator still writes no specs, epics or stories of its own. `task@1` asks
  `bmad-build-auto` to plan one change and stops for a human to read it — the planning is the
  harness's, and the approval is the operator's.

## Success signal

An issue lands on the repository on a Monday morning. The operator opens *New Workflow*, picks
`task`, names the Repository and a branch, types `gh-118` and the issue's own text, and starts
it. Eleven minutes later the card reads `CHK · spec checkpoint`; she opens it, reads the plan the
agent wrote, corrects one assumption about which module owns the retry, saves, and clicks
*Continue*. She does not touch it again. By lunch the card reads `DON · 1 link`, the compare link
opens a branch with one commit `gh-118: retry the readiness probe once (orchestrator)`, and the
quality gate is green on it. Later that week a Story of Epic 7 comes back needing a second pass —
she starts `story-run` on the same branch Epic 7 already pushed, names the Story id, and the Run
picks up the branch where the epic left it.
