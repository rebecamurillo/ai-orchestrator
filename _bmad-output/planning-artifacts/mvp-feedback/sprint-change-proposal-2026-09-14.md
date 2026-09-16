---
title: Sprint Change Proposal — MVP feedback cycle
date: 2026-09-14
status: approved
approved: 2026-09-15 — operator. Wave-0 gates cleared the same day — UX (artboards operator-approved) and the bmad-prd pass (§5 deltas applied to ../mvp/prd.md; AD deltas recorded in its §8 for the architect pass).
trigger: 19 operator feedback items from testing the full app workflow, plus 3 improvements-backlog notes
mode: batch (operator not present during drafting; every decision below is a recommendation, not a commitment)
inputs:
  - feedback-inventory.md (this folder — item-by-item normalization and coverage matrix)
  - ../mvp/prd.md · ../mvp/architecture/ARCHITECTURE-SPINE.md
  - specs-ideas/IMP-001..003 (the improvements backlog, moved into this folder 2026-09-14)
scope-classification: Major — fundamental replan (a version-planning cycle, not a sprint patch)
---

# Sprint Change Proposal — MVP feedback cycle

## 1. Issue summary

The MVP dev loop ran real epics end to end. It works — runs plan, dispatch, verify, park and
resume — but testing surfaced 19 items that cluster into six pain points. None is a defect in
a single story; together they say the *product posture* needs correcting in specific places:

1. **The operator cannot see what the system knows.** Logs exist on disk
   (`attempt.log_path`, `/work/logs/{run_id}/`) but no screen or API serves them; the model
   used is not displayed; artifacts open as raw text; the diagram is one long undifferentiated
   line. Diagnosing a failed baseline required a shell into the container. (Items 1, 5, 11,
   12, 16)
2. **The system fails late where it could fail at the form.** A mistyped model killed a run
   mid-flight; harness readiness is a detached ceremony instead of a live pre-flight; spec
   folders with open questions enter the story loop and block halfway through. (Items 0, 3,
   4, 18)
3. **Guardrails calibrated for demos punish real work.** A hard per-step timeout kills healthy
   hour-long stories; a mandatory USD budget is meaningless under subscription pricing; the
   repository lock serializes runs that different branches keep safe; per-story checkpoints
   interrupt what one upfront validation could clear. (Items 2, 7, 8, 9, 18)
4. **The method is locked in where it should be a default.** Steps can only dispatch BMAD
   skills; templates are pinned by tests; there is no way to run a custom pipeline or install
   operator-authored skills. (Items 4, 17)
5. **The loop does not close.** No epic-level e2e generation, no retrospective, no
   learning-from-sessions. (Items 10, 13)
6. **Sessions are wasted on recovery.** Answer and Retry always restart from scratch even when
   the session needed one sentence. (Items 14, 15; the motivating incident is IMP-003's.)

## 2. Impact analysis

### Epic impact
The MVP's nine epics are landed; nothing here reopens them. This proposal defines the backlog
of the **next version cycle** (working name: `v2-operability`). Epic 9 (optional services)
stays outside, as recorded.

### Artifact conflicts (must change before any build)
| Artifact | Conflict |
| --- | --- |
| PRD §5 non-goals | "does not generate or run end-to-end tests" (item 10) and "does not ingest issues" (IMP-002) are both softened. One `bmad-prd` update covers both. |
| PRD FR-13 / AD-12 | Repository lock is the queue partition, held for the run's whole life. Items 2 and 8 replace the hard lock with per-branch safety + informed consent, and add saved runs with dependencies. This is the deepest architecture touch in the set. |
| PRD FR-10 / FR-17 | Mandatory per-step timeout and mandatory budget halt become optional; a progress-based stall detector replaces the wall clock as the default liveness signal. |
| PRD FR-33 / AD-10 | `enabled`-after-readiness-run stops gating the form; a live probe does. The readiness Run is demoted to a diagnostic. |
| NFR-6 / AD-15 UI-signal rule | "Exactly one element carries a signal colour" cannot survive a status-colored diagram (item 12). Amended for the diagram surface only; word tokens stay mandatory (colour never alone). |
| FR-23 / FR-29 / EXPERIENCE-v1 | The Run view layout and the diagram are redesigned; a Step-run detail screen is added. Both are gated on a `bmad-ux` pass before implementation. |
| FR-5 DSL / AD-9 / AD-16 | `agent` steps gain custom prompt/skill dispatch; `ia-agents-skills/` installs at image build beside the BMAD stubs. |
| Frozen anchors | Template-content tests are already excluded by the exemplar-freeze strategy. Any test pinning "an Answer always archives" or the hard timeout default falls under the Operator-revision exception (root AGENTS.md, exception four) — this approved proposal is the dated product decision those revisions cite. |

### Technical impact (unchanged foundations)
AD-1..AD-9, AD-11, AD-13 (shape), AD-14, AD-17..AD-20 stand. Status vocabularies stay frozen —
every new waiting condition below is a *reason text*, never a new status token. The two-writer
rule (AD-8) is untouched: every new operator choice lands as a signal payload field, and every
new automatic behaviour lands in `apply_step_result`'s path.

## 3. Recommended approach

**Direct adjustment is impossible** (the changes amend the PRD and one AD) and **rollback is
meaningless** (nothing regressed). The path is a **scoped replan**: approve this proposal,
run the two gating activities (UX for the screens, PRD update for the deltas), then cut
epics. Features are sequenced so the trust-and-visibility fixes — the items that made testing
painful — land first, and the architecture-touching concurrency work lands once, later,
instead of leaking into every earlier story.

## 4. The features (F1–F11)

Effort: S = story-sized, M = 2–4 stories, L = its own epic.

### F1 — Live harness probe and enforced model choice — M
*Covers items 0, 3. Adopts the operator's two-tier readiness recommendation verbatim.*

- **Tier 1 — probe, gating submission.** Extend `scripts/harness/<name>.sh` with a `probe`
  verb (reusing `doctor`'s checks): CLI present at the pinned version, credentials valid (one
  trivial call), gateway reachable. Exposed as `GET /api/v1/harnesses/{name}/probe`; called
  when the harness is selected in New workflow. Failure blocks submission with the specific
  reason (`not logged in`, `gateway unreachable`) — never a bare disabled flag. Success chains
  into the model list.
- **Tier 2 — readiness Run demoted.** The six-check readiness Run (worktree flow, commit
  guard, spend attribution, trace export) remains as an operator-triggered deep diagnostic —
  post-deploy, after a version bump — its last result an informational badge on the harness,
  never the thing between the operator and Start run. AD-10 delta: `enabled` no longer read by
  `create_run`/pre-flight; the probe result is.
- **Model choice.** The model field is a select over the probed harness's models, never free
  text; `create_run` rejects a model outside the list (422, names the list). The probe's model
  discovery replaces the static instance join where the harness can enumerate models.

### F2 — Step-run detail screen with full and live logs — M
*Covers items 1, 15 (display side). New screen; UX-gated.*

- Clicking any step row, diagram node, or history row opens a **Step-run detail**: the step's
  kind, gate, `with_resolved`, every attempt with its dispatch prompt (including the retry
  prompt used), exit code, duration, cost — and the **full log**, for every step kind,
  deterministic and agent alike.
- API: `GET /runs/{id}/attempts/{attempt_id}/log` serving `attempt.log_path` with cursor
  paging; a `?follow` tail on the FR-24 poll interval gives *live* logs while the attempt
  runs; a download link serves the raw file. Delivery stays inside AD-1 (through the
  web-client proxy; the browser never reaches the volume).
- This screen is where "baseline e2e failed, why?" gets its answer without a shell.

### F3 — Run view rework: layout, diagram, artifacts — L
*Covers items 5, 11, 12, 16. UX-gated: `bmad-ux` sketches and refines before implementation,
taking inventory of every value the read model already carries (model, worktrees, plan ref,
spend, gate record, artifacts…).*

- **Layout (item 11):** setup and context at the top (including harness **and model** — the
  model is currently invisible); the progress diagram as the central element; cost and trace
  on the right; artifacts below cost/trace, opening in a **modal**; the steps table collapsed
  behind a toggle; the gate record full-width below; detail material in tabs at the bottom.
- **Diagram (item 12):** status is visible per node as a border colour — done green, running
  blue, error red, waiting-for-human orange, scheduled gray — with the word token kept beside
  it (NFR-6 amendment: the diagram is exempt from one-signal-per-surface; colour-never-alone
  stays). Loops collapse to **one box per iteration** with an `n/m` steps count — AD-15's
  group-status rule already computes exactly this aggregate — expanding on click/hover to the
  iteration's steps; nested loops (stories in epics in an initiative) expand level by level on
  click. This replaces the long horizontal line with an overview that shows *where the run is*
  at a glance.
- **Artifacts (items 5, 16):** the artifact viewer renders markdown properly (reader view),
  falls back to syntax-highlighted text, and offers the raw file; opened in a modal from the
  artifacts panel.

### F4 — Concurrency: per-branch safety, informed consent, saved runs with dependencies — L
*Covers items 2, 8. The one AD-level change (AD-12 / FR-13).*

- **Same-repository parallel runs.** The queue partition narrows from repository to
  (repository, branch): different branches hold different worktrees and are mechanically
  independent; the same branch stays refused (a worktree can only be held once). Pre-flight on
  a repository with an active run warns with the facts — which run, which branch, which spec
  folder — and requires explicit confirmation ("this can lead to merge conflicts"), instead of
  silently queueing.
- **Saved runs and dependencies.** New workflow gains *Save* beside *Start*: a saved run is
  planned and stored but not enqueued. A saved run may declare `after: {run_id}`; a scheduler
  enqueues it when the named run reaches `done` (a predecessor ending `failed`/`cancelled`
  parks the dependent as a decision, never auto-starts it). The waiting reason is
  `waiting for run {x}` — a queue reason, not a new status token. `MAX_ACTIVE_RUNS` rises with
  the lock change (instance setting, unchanged mechanism).

### F5 — Optional timeout with stall detection; optional budget cap — M
*Covers item 7.*

- **Timeout.** `timeout_min` becomes optional on agent steps with **no default hard kill**.
  The default liveness signal becomes a **stall detector**: the expected story file not
  created, and no file/commit/log activity in the worktree, for N minutes (template-tunable,
  default 30) → park `timeout`-kind with reason `stalled {path}: no activity for {n} min`.
  The wall clock remains available for `shell`/`git.*` kinds where it is honest. The timer
  stays in the ProcessRunner's world (AD-14) — the engine still never times a step.
- **Budget.** The budget input becomes optional. Tracking (FR-26/FR-28, spend per attempt,
  per story, per project) is untouched and stays authoritative; the halt (FR-17) applies only
  when a budget was set. Copy states it: `tracked, no cap` on runs without one.

### F6 — Spec-folder quality gate before the story loop — M
*Covers items 4 and 18 — one mechanism resolves both.*

- A new first step inside the `epic` template (after baseline, before the story loop):
  dispatch the **`spec-gate` skill** (new, authored in `ia-agents-skills/`) over the spec
  folder. Outcomes, routed on its output file like any agent step: **clean** → the loop
  starts; **open questions** → human gate listing every question across all stories — the
  operator answers once, up front, instead of per-story checkpoints mid-loop (item 18);
  **formatting problems** → the skill fixes and commits them (`spec: gate fixes
  (orchestrator)` — an orchestrator-attributed commit, never the agent's), then proceeds.
- **Skill, not agent** (item 4's question): the dispatch machinery names a skill and reads an
  output file — a contract all three harnesses satisfy; subagent/"agent" definitions are
  harness-specific formats. The skill can spawn subagents internally where available.
- With the gate in place, `spec_checkpoint` flags become the exception (a story the author
  *wants* to pause on), not the routine validation path.

### F7 — Custom skills, custom prompts, template freedom — L
*Covers item 17; carries F6's and F8's skills; aligns with the exemplar-freeze test strategy.*

- **`ia-agents-skills/`** at the repo root: operator-authored skills and agent definitions,
  installed into every harness's skill directory at **image build** beside the BMAD stubs
  (AD-16 delta), so they exist by default for every repository. `scripts/harness/*.sh install`
  extends to copy them; the gitignore contract extends to the corresponding folders.
- **DSL:** an `agent` step declares **either** `skill:` (any installed skill — BMAD or custom)
  **or** `prompt:` (inline text, and/or `prompt_file:` — a path in the working folder), with
  `expect {files, status_in}` naming custom entry folders and expected outputs. `compose_prompt`
  (AD-9's single prompt builder) gains the second dispatch form; the validator requires exactly
  one of the two. This is what makes non-BMAD pipelines expressible.
- **Template freedom:** shipped templates are exemplars, never contracts — no unit or e2e test
  pins their content (already the standing strategy); each environment maintains its own.

### F8 — Epic tail: push before review, e2e gate, retrospective — M
*Covers items 9, 10, 13.*

- **Item 9 (done checkpoint):** the mechanism stands; the ordering was wrong. The shipped
  `epic` template pushes the branch **before** a final done checkpoint parks, so the operator
  reviews real code through the compare link from their own machine. Spec-authoring guidance:
  drop `done_checkpoint` from non-final stories; the epic-tail checkpoint is the review point.
- **Item 10 (e2e gate):** after the last story: dispatch `bmad-qa-generate-e2e-tests` for the
  epic → run the repository's e2e command (`shell`, deterministic) → on failure, bounded
  redispatch to a fixing agent (the existing `on_fail: {redispatch, max}` mechanism, nothing
  new). PRD §5's "does not generate or run e2e tests" is amended: the orchestrator still owns
  no oracle — it dispatches the generation to an agent and verifies with the repository's own
  command. FR-31 note: tests the epic's own agents created are not in the frozen set, so the
  generation step is compatible with protected paths as specified.
- **Item 13 (retrospective):** a post-e2e step dispatches `bmad-retrospective` (exists,
  headless-capable) writing the epic retro into the working folder. Story-level: the
  trajectory row (AD-19) already captures per-story evidence; a session-interrogation retro
  ("resume the session and ask what went wrong") is staged behind F9's resume exposure and
  recorded as a follow-up improvement note, not built now.

### F9 — Recovery uses the session: reply-or-restart on Answer and Retry — M
*Covers items 14, 15. Accepts IMP-003 option A and extends it.*

- The Answer and Retry surfaces gain the choice IMP-003 specifies: **reply in the same
  session** (continue with the operator's instruction, full context kept) or **restart**
  (today's archive-and-replan). One `mode` field on the existing signal payloads (AD-13
  shape untouched); the fork lands in `_planned`, where the retry/resume fork already lives.
  Refuse, never degrade: `mode: session` against a non-resumable row is a 422 naming the
  reason; the UI offers the choice only when `reply_available` is true.
- **Item 15:** every shipped template's `retry.prompt` is written out explicitly (no implicit
  defaults), and F2's attempt view shows the exact prompt each retry used — the prompt becomes
  a maintained, visible part of the workflow definition.

### F10 — New-workflow form polish — S
*Covers item 6; carries F1's and F4's form surfaces.*

- Every input gains a tooltip stating why it matters and what consumes it; mandatory inputs
  are marked `*`; the harness row shows the live probe result inline (F1); the model field is
  the enforced select (F1); the same-repository warning renders here (F4).

### F11 — Smaller entry points: `story-run` and `task` — M
*Accepts IMP-001 (option B) and IMP-002 (B1); both challenged in the inventory and unchanged
by this cycle's findings.*

- `story-run@1`: a root template running exactly one story of an epic, via the new `only:`
  selector on `for_each` (plan-time filter — FR-5's no-conditionals rule stands).
- `task@1`: an issue-sized change from a pasted `intent`, plan gate always on, resumed by
  Continue — the entry point for "GitHub issue → plan → human validates → develop". The PRD §5
  "ingests issues" sentence is amended in the same `bmad-prd` pass as item 10's.

## 5. Consolidated contract deltas

One `bmad-prd` update-mode pass applies: FR-8 (save-without-start, model validation, probe in
pre-flight, consent on shared repository), FR-10 (timeout optionality + stall detection),
FR-13 (per-branch partition, dependencies), FR-17 (budget optional), FR-23 (layout, step-run
detail, artifact modal/markdown), FR-29 (diagram colors, iteration boxes), FR-33 (probe gates,
readiness Run demoted), FR-5/FR-14 (custom prompt/skill dispatch), FR-18/FR-20 (reply mode),
§5 non-goals (e2e generation; operator-supplied intent), NFR-6 (diagram exemption). Spine:
AD-10 (`enabled` semantics), AD-12 (partition key), AD-15 (diagram statuses), AD-16
(`ia-agents-skills/` install). Where code and spine disagree meanwhile, the standing rule
holds: stop and say so.

## 6. Sequencing

| Wave | Features | Rationale |
| --- | --- | --- |
| 0 — gates | `bmad-ux` for F2+F3 screens; `bmad-prd` deltas (§5) | Nothing UX-gated or PRD-gated builds before its gate clears. |
| 1 — see clearly | F2, F10, F9, F5 | The pain that made testing hardest; no AD changes; F10/F9/F5 are independent of the UX gate. |
| 2 — the new face | F3, F1 | Run view + diagram from the refined UX; probe + model enforcement. |
| 3 — the method opens | F7, F6, F8, F11 | Skill infrastructure first (F7 carries F6's and F8's skills), then the epic-shape changes and new templates. |
| 4 — concurrency | F4 | The AD-12 change lands once, last, when the screens that must explain it (queue reasons, consent dialog) already exist. |

## 7. Implementation handoff

**Scope: Major.** Routed to PM/Architect (operator wearing both hats), with this folder as the
input. Success criteria: every inventory item traceable to a shipped story in the next cycle's
epics; the two UX artboards approved before F2/F3 stories are cut; the PRD and spine deltas
applied before any build story references them.

| Step | Owner | Deliverable |
| --- | --- | --- |
| Approve this proposal | Operator | approval, or revisions to §4 |
| `bmad-ux` | UX skill + operator | artboards for Run view rework + Step-run detail, in this folder |
| `bmad-prd` update | PM skill + operator | PRD deltas of §5 applied; spine deltas recorded for the architect pass |
| `bmad-create-epics-and-stories` | PM skill | the `v2-operability` epics, waved per §6 |
| Mark IMP-001..003 `accepted` | Operator | frontmatter updates in `specs-ideas/` |
