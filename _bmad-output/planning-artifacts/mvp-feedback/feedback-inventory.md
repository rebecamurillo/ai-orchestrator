---
title: Feedback inventory — MVP testing, 2026-09-14
status: complete
source: operator feedback items 0–18, plus the three notes in specs-ideas/
purpose: normalize every item, name its pain point, and map it to exactly one covering feature
---

# Feedback inventory

Each item as the operator raised it, restated as the problem underneath it, with the feature
(F1–F11, defined in the Sprint Change Proposal) that covers it and the contract artifacts it
touches. Grounding against the codebase is noted where it changes the reading of an item.

## Items

### 0 — Readiness flow is detached and unclear
**Raised:** readiness should be live at workflow creation, gate the form, and feed the model
list for the selected harness. The two-tier recommendation (live probe gating submission;
six-check readiness Run demoted to an operator-triggered diagnostic) is adopted as the shape.
**Pain point:** fail-late — the harness's fitness is discovered away from the moment of use.
**Grounding:** `scripts/harness/_common.sh` already has a `doctor` verb (version, skill
discovery, gateway reachability) — the probe is an exposure of it, not a new capability.
`GET /harnesses` already returns per-harness models.
**Covered by:** F1. **Touches:** FR-33, FR-8 (pre-flight), AD-10 (`enabled` semantics), `scripts/harness/*.sh`.

### 1 — Baseline e2e failed and the operator could not see why
**Raised:** only some logs visible; want full logs and/or download; want a step-run detail
reachable by clicking a run or a workflow step — full log of what executed, for all step
kinds, deterministic and harness alike.
**Pain point:** the system knows (`attempt.log_path`, `/work/logs/{run_id}/`) but the screen
does not show it; diagnosis requires a shell into the container.
**Grounding:** no API route today serves an attempt's log; `run_detail` exposes step rows only.
**Covered by:** F2. **Touches:** FR-23 (new sub-screen), API routes, AD-1 (log delivery through the proxy).

### 2 — Parallel runs on one repository, warn instead of refuse
**Raised:** when a run is active on the same repository, warn ("workflow X is running — branch,
spec folder — merge conflicts possible, are you sure?") instead of queueing behind a hard lock.
**Pain point:** the repository lock serializes work that different branches keep mechanically safe.
**Covered by:** F4. **Touches:** FR-13, AD-12 (lock = queue partition), pre-flight copy.

### 3 — Invalid model accepted, run failed later
**Raised:** the model must be verified; the operator should choose from the models allowed for
the selected harness, not type free text.
**Pain point:** fail-late; the form knows the model list (`GET /harnesses`) and does not enforce it.
**Grounding:** `web-client/src/lib/newwf/state.ts` — free text stands when a harness reports no
models; nothing validates server-side at `create_run`.
**Covered by:** F1 (validation + selection), F10 (form control). **Touches:** FR-8, FR-14.

### 4 — Spec-folder quality gate before stories start
**Raised:** an agent analyses the spec/initiative folder before the story loop: complete and no
open questions → proceed; open questions → human gate; formatting issues → fix and commit.
Custom skills/agents live in `ia-agents-skills/` in this repository, installed for all
harnesses. Asked: skill or agent?
**Answer:** a **skill**. The dispatch machinery (`compose_prompt`) names a skill and reads an
output file's frontmatter — that contract is harness-portable. "Agents" (subagent definitions)
are harness-specific formats; a skill is the one unit all three harnesses already load from the
image. The skill may spawn subagents internally where the harness allows.
**Covered by:** F6 (the gate), F7 (the `ia-agents-skills/` install path). **Touches:** epic template, FR-16 routing (a new terminal status or reuse of `blocked`), AD-16.

### 5 — Artifacts and logs open raw, unreadable
**Raised:** improve and challenge the artifacts/logs UX; raw file dumps are hard on the eye.
**Covered by:** F3 (artifact modal + markdown rendering; log rendering in F2). **Touches:** FR-23.

### 6 — New-workflow form: tooltips and mandatory marks
**Raised:** explain why each input matters, as tooltips; mark mandatory inputs with `*`.
**Covered by:** F10. **Touches:** web-client form components only.

### 7 — Hard timeout and hard budget are wrong for real stories
**Raised:** timeout should be optional; the meaningful signal is *no progress* (story file not
created or not edited for a while), since healthy stories go quiet for an hour inside tests and
review. Budget cap should be optional too (subscription pricing makes a USD cap meaningless);
keep the tracking, drop the mandatory limit.
**Covered by:** F5. **Touches:** FR-10 (timeouts), FR-17 (budget halt), AD-14 (ProcessRunner owns the timer), templates.

### 8 — Parallel workflows and saved workflows with dependencies
**Raised:** run different workflow epics in parallel; define and save a workflow without
starting it; declare "B runs after A is done"; independent workflows start immediately.
**Covered by:** F4. **Touches:** FR-8 (save without start), FR-13, AD-12, Run status vocabulary (a waiting reason, not a new status).

### 9 — Done checkpoint on the last story is pointless
**Raised:** the branch is not pushed at that moment, so the operator cannot review the code
from their machine; remove it unless something was missed.
**Reading:** nothing was missed — `done_checkpoint` is declared per story in `stories.yaml` and
the epic pushes only after the last story. The checkpoint asks for review of code the operator
cannot see. The fix is ordering, not deletion of the mechanism.
**Covered by:** F8. **Touches:** shipped `epic`/`story` templates, spec-authoring guidance.

### 10 — Post-epic e2e generation and validation
**Raised:** after all stories of an epic are done, run `bmad-qa-generate-e2e-tests` for the
whole epic, run the e2e suite, send failures back to an agent to fix.
**Note:** PRD §5 states "does not generate or run end-to-end tests" — this is a PRD amendment,
not a template tweak.
**Covered by:** F8. **Touches:** PRD §5, `epic` template, FR-31 (generated tests vs frozen test set).

### 11 — Run view: model invisible, sections not navigable
**Raised:** model used is not shown. Wanted layout: setup at top; big progress diagram below;
cost and trace right (already good); steps table hidden by default behind a toggle; gate record
full-width below; artifacts below cost/trace, opening in a modal; details in tabs at the bottom;
progress and context at the top. Do `bmad-ux` before implementation.
**Covered by:** F3. **Touches:** FR-23, EXPERIENCE-v1 surfaces.

### 12 — Diagram unreadable: long horizontal line, no color state
**Raised:** border colors by state (done green, running blue, error red, waiting-human orange,
scheduled gray); loops render one box per iteration with a `2/5` steps count; hover/click opens
the iteration's steps below with the same colors; loop-in-loop opens on click.
**Note:** border-per-node color conflicts with NFR-6's "exactly one element carries a signal
colour" and the spine's UI-signal convention — the proposal amends NFR-6 for the diagram surface
while keeping word tokens (colour never alone).
**Covered by:** F3. **Touches:** FR-29, AD-15 (group status already computes the `n/m` aggregate), NFR-6.

### 13 — Retrospectives after story and after epic
**Raised:** add retrospectives; asked bmad-help where to introduce them; sessions could be
resumed and questioned so the system learns from itself.
**Answer (bmad-help):** `bmad-retrospective` already exists — an evidence-based *epic* retro
with headless support; the natural insertion is a template step after the epic's e2e gate
(F8), writing its report into the working folder. A per-story retro is already half-captured by
the trajectory row (AD-19); session-resume interrogation rides on the same `Harness.resume`
exposure F9 builds, and is staged behind it.
**Covered by:** F8. **Touches:** `epic` template, AD-19 (what the story-level record carries).

### 14 — On retry after agent failure, operator chooses: same session or fresh
**Raised:** continue the session with instructions, or start over. IMP-003 already records the
plan for the Answer path.
**Covered by:** F9 (IMP-003 accepted and extended from Answer to Retry). **Touches:** FR-18, FR-20, AD-13 (signal payload), AD-10 (capability-gated).

### 15 — The auto-retry prompt must be explicit in the template
**Raised:** specify the retry prompt sent back to the agent so workflows are maintainable.
**Grounding:** the DSL already carries `retry {max, prompt}` — the gap is that shipped templates
and the UI don't surface it. Fix: every shipped template declares an explicit prompt; the Run
view shows the prompt a retry used (F2 shows it in the attempt detail).
**Covered by:** F9. **Touches:** shipped templates, F2's attempt view.

### 16 — Markdown reader for artifacts
**Raised:** artifact view renders poorly; needs a markdown reader.
**Covered by:** F3 (modal artifact viewer with markdown rendering). **Touches:** FR-23.

### 17 — Full template freedom; custom skills/agents; non-BMAD pipelines
**Raised:** each environment maintains its own templates and no test may pin shipped template
content; steps with a liveness agent must be customizable — run a skill or not, custom prompt
inline or from a file in the working folder, custom entry folder and expected outputs; skills
and agents authored in this repository install into every harness at image build.
**Grounding:** the exemplar-freeze test strategy (memory) already commits to never pinning
shipped template content in tests.
**Covered by:** F7. **Touches:** FR-5 (DSL: `prompt` on `agent` steps, skill optional), FR-14 (`compose_prompt`), AD-9, AD-16, image build.

### 18 — Checkpoints validated at the start, not per step
**Raised:** per-story checkpoint validation is unclear; run an agent at the epic's start to
review all stories for open questions; the human validates once, then the loop runs full-auto.
**Covered by:** F6 (the same upfront gate as item 4 — one review, one human validation, then
auto). **Touches:** `epic` template, spec-authoring guidance (fewer `spec_checkpoint` flags).

## Improvements-backlog notes (challenged and merged)

| Note | Disposition | Where |
| --- | --- | --- |
| IMP-001 — Start a Run for one Story | **Accept option B** (new `story-run` root template + `only:` selector on `for_each`). Challenged: none of its reasoning is invalidated by this cycle; the `only:` selector also serves "re-run one story" asked for at every halt. | F11 |
| IMP-002 — Issue-sized change through the plan gate | **Accept B1** (pasted `intent`, `task@1` template, plan gate always on). Challenged: its PRD §5 amendment now travels together with item 10's (both soften §5 non-goals in one `bmad-prd` pass). B2 (fetching issues by API) stays deferred. | F11 |
| IMP-003 — Answer in-session or restart | **Accept option A** (`mode` on the answer payload). Extended: item 14 applies the same choice to the Retry signal, so the fork lands once in `_planned` and serves both signals. | F9 |

## Coverage matrix

| Item | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | IMP-1 | IMP-2 | IMP-3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Feature | F1 | F2 | F4 | F1 | F6/F7 | F3 | F10 | F5 | F4 | F8 | F8 | F3 | F3 | F8 | F9 | F9 | F3 | F7 | F6 | F11 | F11 | F9 |

Every item maps to exactly one owning feature (F7 is infrastructure for item 4's skill; F10
carries item 3's form control while F1 owns its validation).
