---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/mvp/prd.md (2026-09-15)
  - _bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md (2026-09-15, four AD deltas ratified)
  - _bmad-output/planning-artifacts/mvp-feedback/sprint-change-proposal-2026-09-14.md (§4 features, §6 waves, §7 success criteria)
  - _bmad-output/planning-artifacts/mvp-feedback/feedback-inventory.md (items 0–18, IMP-001..003, coverage matrix)
  - _bmad-output/planning-artifacts/mvp-feedback/specs-ideas/IMP-001-single-story-run.md (accepted, option B)
  - _bmad-output/planning-artifacts/mvp-feedback/specs-ideas/IMP-002-issue-sized-change.md (accepted, B1)
  - _bmad-output/planning-artifacts/mvp-feedback/specs-ideas/IMP-003-answer-reply-in-session.md (accepted, option A extended to Retry)
  - _bmad-output/planning-artifacts/ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md (deltas 20–28; artboards in mockups/, operator-approved 2026-09-15)
  - _bmad-output/planning-artifacts/ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md (design tokens; `signal-criterion` revived for the diagram)
---

# ai-orchestrator v2-operability — Epic Breakdown

## Overview

This document provides the epic and story breakdown for the **v2-operability cycle**: the 11 approved features (F1–F11) of the MVP-feedback correct-course pass, decomposed into orchestrator-runnable epics. It builds **deltas on the shipped MVP** — the requirements below are the amended contract, not the whole product. Authority order: `ARCHITECTURE-SPINE.md` (AD-1..AD-20, updated 2026-09-15) binds over any story text; the PRD (2026-09-15) is the product contract; unbuilt target text in both carries `*(ratified 2026-09-15)*` markers.

Execution contract: `epics.yaml` in this folder is the initiative list file read by `templates/initiative.yaml`; each epic's spec folder holds `SPEC.md` + one `stories.yaml` (complete story requirements inline — no per-story briefs) + an empty `stories/` for the dev agents' own story files.

## Requirements Inventory

### Functional Requirements

The cycle's functional requirements are the eleven approved features, each bound to the amended FRs it realises:

FR-D1 (F1 — Live harness probe and enforced model choice, M): a `probe` verb on `scripts/harness/<name>.sh` exposed as `GET /api/v1/harnesses/{name}/probe` and as `Harness.probe() → ProbeResult` gates New workflow, pre-flight, and `create_run` with the specific reason (`not logged in`, `gateway unreachable`), never a stored flag; the model field is a select over the probed harness's models with server-side 422 naming the list; the readiness Run is demoted to an operator-triggered diagnostic badge. [FR-33, FR-8, AD-10]

FR-D2 (F2 — Step-run detail screen with full and live logs, M): route `/workflows/:runId/steps/{dot-index path}`; per attempt the dispatch/retry prompt, the agent's verbatim result, the full log via `GET /runs/{id}/attempts/{attempt_id}/log` (cursor paging, live follow, download), the full Session id with copy, and a right-side helper drawer (prompt·result / reach-agent) — a side panel, never a modal. [FR-34 (new), FR-24, AD-1, AD-15]

FR-D3 (F3 — Run view rework: layout, diagram, artifacts, L): stop zone top → central embedded diagram (`?view=diagram` retired) → summary column → one bottom tabbed region, gate record default; diagram border colours per stored token (done green, running blue `signal-criterion`, error red, waiting amber, scheduled grey; SKP/CAN faint grey — never green), one box per loop iteration with `k/n steps`, level-by-level click expansion, leaf click → Step-run detail; artifact modal with markdown reader and edit-while-parked. [FR-23, FR-29, NFR-6, AD-15]

FR-D4 (F4 — Concurrency: per-branch safety, consent, saved runs with dependencies, L): queue partition narrows to `{repository_id}:{declared branch}`; same-repository different-branch runs execute concurrently after an explicit consent warning; *Save* beside *Start run* (saved = `engine_ref` null); `after: {run_id}` dependents enqueued on predecessor `done`, parked `dependency` on `failed`/`cancelled`; queue reasons `branch held by {run}`, `waiting for run {x}`, `saved — not started` — reason texts, never status tokens. [FR-8, FR-13, FR-25, AD-12, AD-8, AD-13]

FR-D5 (F5 — Optional timeout with stall detection; optional budget, M): `timeout_min` optional on `agent` steps, no default hard kill; stall detector in the ProcessRunner (mtime under cwd incl. `.git` + log growth; `wait` returns exited|timed_out|stalled; default 30, template-tunable) with reason `stalled {path}: no activity for {n} min`; wall clock stays for `shell`/`git.*`; budget optional — `tracked, no cap`, halt only when set. [FR-10, FR-17, AD-14, AD-11]

FR-D6 (F6 — Spec-folder quality gate before the story loop, M): a `spec-gate` skill (authored in `ia-agents-skills/`) dispatched after baseline, before the story loop; clean → proceed; open questions → one human gate listing every question; formatting problems → fixed and committed as `spec: gate fixes (orchestrator)`; `spec_checkpoint` becomes the exception. [epic template, FR-16 routing, AD-16]

FR-D7 (F7 — Custom skills, custom prompts, template freedom, L): `ia-agents-skills/` at the repo root installed into every harness's skill directory at image build (build fails on name collision; `skills-manifest.json` behind the `SkillCatalog` port; pre-flight verifies installed skills); `agent` steps declare exactly one dispatch form in `with` — `skill` or `prompt`/`prompt_file` — with `expect {files, status_in}`; `compose_prompt` gains the second form; shipped templates stay exemplars (no test pins their content). [FR-5, FR-14, AD-9, AD-16]

FR-D8 (F8 — Epic tail: push before review, e2e gate, retrospective, M): the shipped `epic` template pushes before the final done checkpoint; post-stories e2e tail — dispatch `bmad-qa-generate-e2e-tests`, run the repository's e2e command, bounded `on_fail: {redispatch, max}` to a fixing agent; a post-e2e step dispatches `bmad-retrospective` (headless) into the working folder. [§5 non-goal softened (F8), FR-31 compatibility, epic template]

FR-D9 (F9 — Recovery uses the session: reply-or-restart, M): `mode: restart | session` on Answer and Retry payloads; `mode: session` is a **new Attempt** inheriting the session id (spend/SHA/protected-path owned by it); 422 against a non-resumable row; UI offers the choice only when `reply_available`; every shipped template's `retry.prompt` written out explicitly and shown in F2's attempt view. [FR-18, FR-20, AD-13, AD-10]

FR-D10 (F10 — New-workflow form polish, S): tooltips stating why each input matters, mandatory `*` marks; carries F1's probe row + enforced model select and F4's consent warning + *Save* on its surface. [FR-8, web-client only]

FR-D11 (F11 — Smaller entry points, M): `story-run@1` root template running exactly one story via the new `only:` plan-time selector on `for_each`; `task@1` for an issue-sized change from operator-pasted `intent`, plan gate always on, resumed by Continue — pasted text, never API ingestion. [§5 non-goal softened (F11), FR-5, IMP-001 B, IMP-002 B1]

### NonFunctional Requirements

NFR-6 (amended): the run diagram is the one surface exempt from one-signal-per-surface; colour-never-alone still holds there; skipped or cancelled is never green.
NFR-8 (standing, binds all new copy): product copy states facts and mechanisms, never congratulates or apologises; `skipped`, `unvalidated`, `blocked`, `exit 1` are words on screen.
NFR-2 (standing): `skipped` and `unvalidated` are words, never green — the diagram dialect and `k/n` counts must respect it.
NFR-9 (standing): a step kind, a harness, or the engine is replaced by adding one adapter — F7's `SkillCatalog` and F1's `probe()` follow the same port discipline.
Status vocabularies are frozen: every new waiting condition in this cycle is a reason text, never a Run or Step status token.

### Additional Requirements

- **Anchors are read-only** (AGENTS.md rule 1): SPEC.md, stories.yaml, epics.yaml, AGENTS.md, existing tests. Two known anchor consequences this cycle: (a) F4's queue-reason renames (`repository lock held by {label}` → `branch held by {run}`, `held by {labels}` → `held by {runs}`) revise test-pinned strings — the wave-4 story lands them only under the operator-revision exception, named and dated 2026-09-15 in the revised test; (b) F5 retires the agent 90-min default pinned in `KIND_META` — same discipline if a test pins it.
- **Two-writer rule untouched** (AD-8): F4's dependent resolution rides the terminal-transition writers (idempotent `engine.enqueue` on `run_id`, container-start sweep); F9's session mode changes no writer.
- **Port discipline** (AD-2/AD-6): probe reaches the application through `Harness.probe()`; installed skills through `SkillCatalog`; the stall detector lives in `ProcessRunner`; `engine_ref` content stays adapter-only (its nullness is the saved predicate); the engine port's `partition_key` widens to `str` deliberately.
- **Dot-index bijection** in one web-client util; the API speaks canonical bracket Paths only; `validate.py` rejects all-digit step ids.
- **Config is the environment** (AD-20): any new setting lands in typed settings + `.env.example` in the same change.
- **Contract generated, never hand-written** (AD-3): new routes (`probe`, attempt log) flow through `make openapi` / `pnpm gen:api`.
- **Trajectory capture** (AD-19) unchanged; F8's retro step adds no second data-collection path.
- **TDD** (AD-18): every story's tests exist and fail first; unit tests use the shared fakes in `tests/unit/fakes/` — new ports (`SkillCatalog`, `probe()`, stall-capable `ProcessRunner`) get one fake each there.
- **Exemplar freeze** (standing test strategy): no unit or e2e test pins shipped template content — F7/F8/F11 template work ships as exemplars.

### UX Design Requirements

UX-DR1: Run detail layout per EXPERIENCE-v1 §2.2 — stop zone on top (resolving a stop never needs a scroll or tab), central diagram, summary column, one bottom tabbed region with the gate record as default tab; Stories strip kept. [F3]
UX-DR2: Step-run detail per EXPERIENCE-v1 §2.3 — attempts newest-first with latest selected, per-attempt prompt and verbatim `## Auto Run Result`, full-viewport live log (follow on by default, scroll-up pauses, download control, `log no longer on disk` in words), full session id with copy control. [F2]
UX-DR3: Helper drawer — a right-side panel, never a modal; the page stays live and the log keeps following under it; two contents: *prompt · result* and *reach agent* (FR-21 resume instructions bound to the attempt's session). [F2]
UX-DR4: Diagram dialect — border colour beside the word token per the AD-15 map; `now` marker on the current node; boxes never move or re-collapse under the cursor; group boxes expand one level per click, hover never expands. [F3]
UX-DR5: Artifact modal — reader view first (markdown rendered, YAML/code highlighted), `RENDERED · SOURCE · RAW` toggle, download; *Edit* while parked with commit hint `spec: operator edit (orchestrator)`; `stories.yaml`/`epics.yaml` read-only `planned at {sha}`. [F3]
UX-DR6: New-workflow form — probe-gated harness rows in words (`ok` / specific reason), readiness badge informs-not-gates, model select loaded on probe success, budget `(optional)` with `tracked, no cap`, *Save* beside *Start run* with the `after: {run_id}` wait note, shared-repository consent warning with the facts; tooltips + `*` marks on every input. [F1, F4, F10]
UX-DR7: Runs screen — queue reasons from the fixed set including `waiting for run {x}` and `saved — not started`; history rows link to the Step-run detail. [F2, F4]
UX-DR8: Voice — all new copy from the canonical list (`stalled {path}: no activity for {n} min`, `tracked, no cap`, `waiting: branch held by {run}`, `run {x} ended {status}`, `no attempts yet`, `12/22 steps`); never icons, never congratulation. [all]

### FR Coverage Map

| Requirement | Epic | Notes |
| --- | --- | --- |
| FR-D2 (F2 step-run detail) | Epic 1 | FR-34 (new), FR-24 follow, AD-1 log delivery, AD-15 dot-index |
| FR-D3 (F3 run view rework) | Epic 1 | FR-23, FR-29, NFR-6 exemption, AD-15 dialect + `k/n` |
| FR-D1 (F1 probe + model) | Epic 2 | FR-33, FR-8, AD-10 `Harness.probe()` |
| FR-D10 (F10 form polish) | Epic 2 | FR-8 surface; tooltips, `*` marks |
| FR-D5 (F5 stall + optional budget) | Epic 3 | FR-10, FR-17, AD-14 stall, AD-11 nullable budget |
| FR-D9 (F9 reply-or-restart) | Epic 3 | FR-18, FR-20, AD-13 mode = new Attempt, AD-10 `reply_available`; explicit `retry.prompt` |
| FR-D7 (F7 skills + DSL freedom) | Epic 4 | FR-5, FR-14, AD-16 manifest + `SkillCatalog`, AD-9 `compose_prompt` |
| FR-D6 (F6 spec-gate) | Epic 4 | epic template step; skill authored in `ia-agents-skills/` |
| FR-D8 (F8 epic tail) | Epic 4 | push-before-checkpoint, e2e gate, retrospective; §5 softening (F8) |
| FR-D11 (F11 story-run / task) | Epic 4 | `only:` selector, `task@1` pasted intent; §5 softening (F11) |
| FR-D4 (F4 concurrency) | Epic 5 | FR-13, FR-8 save/consent, FR-25 reasons, AD-12/AD-8/AD-13; anchor revisions |

Inventory traceability (proposal §7 success criterion):

| Item | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | IMP-1 | IMP-2 | IMP-3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Epic | 2 | 1 | 5 | 2 | 4 | 1 | 2 | 3 | 5 | 4 | 4 | 1 | 1 | 4 | 3 | 3+1 | 1 | 4 | 4 | 4 | 4 | 3 |

UX-DR mapping: UX-DR1–5 → Epic 1 · UX-DR6 probe/model/tooltip half → Epic 2, Save/consent half → Epic 5 · UX-DR7 → Epics 1 (history links) and 5 (queue reasons) · UX-DR8 → all epics (voice).

## Epic List

### Epic 1: See every Run clearly — Step-run detail and the reworked Run view
The Operator answers "it failed, why?" and "where is the run?" entirely from the screen: a bookmarkable Step-run detail with every attempt's prompt, verbatim result, and full live log; the Run detail reworked around the embedded status-coloured diagram; artifacts readable in a modal.
**FRs covered:** FR-D2, FR-D3 (FR-34 new, FR-23, FR-29, FR-24, NFR-6) · items 1, 5, 11, 12, 15(display), 16 · branch `feat/v2-observability`

### Epic 2: Fail at the form, not in the run — live probe and enforced model choice
Selecting a harness probes it live and loads its real model list; an unusable harness or invalid model is refused at submission with the specific reason; the readiness Run becomes an informational diagnostic; every input explains itself. (The form's *Save* button and consent warning belong to Epic 5, which owns their mechanism.)
**FRs covered:** FR-D1, FR-D10 (FR-33, FR-8, FR-14) · items 0, 3, 6 · branch `feat/v2-probe-form`

### Epic 3: Runs that stall park, healthy runs finish — liveness and session recovery
A healthy hour-long story runs to its end (stall detector replaces the default hard kill; budget optional, `tracked, no cap`); when a story blocks or errors the Operator chooses reply-in-session or restart; every retry prompt is explicit in the template.
**FRs covered:** FR-D5, FR-D9 (FR-10, FR-17, FR-18, FR-20) · items 7, 14, 15 · IMP-003 · branch `feat/v2-liveness-recovery`

### Epic 4: The method opens — custom skills, spec gate, epic tail, small entry points
Operator-authored skills install into every harness at image build; `agent` steps dispatch any skill or a custom prompt; the spec-gate reviews the spec folder once before the loop; the epic tail pushes before review, generates and runs e2e, and writes a retrospective; `story-run@1` and `task@1` open small entries. F7's infrastructure stories come first.
**FRs covered:** FR-D7, FR-D6, FR-D8, FR-D11 (FR-5, FR-14, §5 softenings) · items 4, 9, 10, 13, 17, 18 · IMP-001, IMP-002 · branch `feat/v2-method`

### Epic 5: Safe concurrency — branch partition, consent, saved runs with dependencies
Different branches of one repository run in parallel behind an informed-consent warning; a Run can be saved without starting and chained with `after: {run_id}`; every waiting condition is a reason text. Carries the two anchor-revision moments (queue-reason strings, `KIND_META` timeout residue) under the dated operator exception. Deliberately last.
**FRs covered:** FR-D4 (FR-13, FR-8 save/consent, FR-25) · items 2, 8 · branch `feat/v2-concurrency`

**Execution notes:** `epics.yaml` lists epics 1→5 in this order (list order is the dependency under `initiative.yaml`). Epics 1+3 and 1+4 are disjoint enough to run concurrently on their branches; 2 and 5 should not overlap each other or 4 in flight. Cross-epic file overlaps (Epics 3/4 both brush `steps/agent.py`; Epics 2/5 both brush `create_run`) are handled by order, not merged — each pair serves a different domain end-to-end.

## Epic 1: See every Run clearly — Step-run detail and the reworked Run view

The Operator answers "it failed, why?" and "where is the run?" entirely from the screen: a bookmarkable Step-run detail with every attempt's prompt, verbatim result, and full live log; the Run detail reworked around the embedded status-coloured diagram; artifacts readable in a modal.

### Story 1-1: Serve any Attempt's full log

As an Operator,
I want any attempt's complete log served over the API,
So that diagnosis never requires a shell into the container.

**Acceptance Criteria:**

**Given** a Run with a finished attempt
**When** `GET /api/v1/runs/{id}/attempts/{attempt_id}/log` is called through the web-client proxy
**Then** the raw log streams with cursor paging, for every step kind — deterministic and agent alike (FR-34; AD-1: the browser never reaches the log volume)
**And** polling with the last cursor while the attempt runs returns only appended content (live follow on the FR-24 interval)
**And** a garbage-collected log answers `log no longer on disk` — words, never an error surface
**And** a download variant serves the raw file; `make openapi` + `pnpm gen:api` show no drift (AD-3).

### Story 1-2: Step-run detail page

As an Operator,
I want every planned Step on its own bookmarkable page with all its attempts,
So that "it failed, why?" is answered from the screen.

**Acceptance Criteria:**

**Given** any Step of any status
**When** I open `/workflows/:runId/steps/{path}` in dot-index form (`epics.0.stories.3.build`)
**Then** the page shows kind, Gate strength, `with_resolved`, and the canonical bracket Path; `planned` shows `no attempts yet`; skipped shows the reason in words (FR-34)
**And** one web-client util owns the bracket↔dot-index bijection; the API is called with bracket Paths only (AD-15)
**And** attempts render newest first, latest selected: status, exit code, duration, cost, full Session id with copy control
**And** per agent attempt the dispatch prompt (and a retry's exact `retry.prompt`) and the agent's verbatim result (`## Auto Run Result`; `— running` in flight) are shown; non-agent attempts show command and exit lines
**And** the selected attempt's log renders via story 1-1: follow on by default while running, scroll-up pauses, resume control, download; the page survives reload mid-follow
**And** Steps-table and Runs-history rows link here (FR-25); a blocked/checkpointed Step states the stop and links back to the Run detail's stop zone — no signal actions on this page.

### Story 1-3: Helper drawer — prompt·result and reach-agent

As an Operator,
I want a side drawer with the attempt's prompt/result blocks and the exact resume instructions,
So that I can inspect or take over without leaving the live page.

**Acceptance Criteria:**

**Given** an attempt row on the Step-run detail
**When** I open *prompt · result*
**Then** a right-side side panel — never a modal — shows the blocks with copy controls; the page stays live and the log keeps following under it (FR-34)
**And** *reach agent* shows FR-21's numbered resume instructions bound to that attempt's session
**And** opening or closing the drawer changes nothing else on the page.

### Story 1-4: Run detail layout rework

As an Operator,
I want the Run detail organized as stop-zone-top → central diagram → summary column → one bottom tabbed region,
So that resolving a Stop never requires a scroll or a tab.

**Acceptance Criteria:**

**Given** a Run in `needs_you`
**When** I open its detail
**Then** the stop zone (reason + admitted Signals) renders at the top and resolving it needs no scroll or tab change (FR-23, UX-DR1)
**And** the diagram island renders as the central element; `?view=diagram` redirects to the Run detail (FR-29)
**And** the summary column carries cost/trace and setup context including the model used (item 11); artifacts below it; the Stories strip kept
**And** one bottom tabbed region holds the gate record (default tab), the collapsed Steps table, and detail material; copy stays factual (NFR-8).

### Story 1-5: Diagram dialect — colours, iteration boxes, click navigation

As an Operator,
I want the diagram to show each node's status as a border colour with loops as per-iteration boxes,
So that where the run is reads at a glance.

**Acceptance Criteria:**

**Given** a running Run's diagram
**Then** every node's border colour follows the AD-15 map exactly — `done`→green, `running`→blue (`signal-criterion`), `error`→red, `blocked|checkpoint`→amber, `planned|queued`→grey, `skipped|cancelled`→faint grey — word token always beside it, no node with two colours, skipped never green (FR-29, NFR-6 exemption, NFR-2)
**And** `graph.py` computes each group's `k/n steps` into the `groups` payload (k = rows `done`, n = rows not `skipped`; all-skipped groups show no count); iteration boxes carry label, chip + token, `k/n`
**And** group boxes expand one level per click, never hover; the path to the current node starts expanded; the `now` marker sits on the current node; poll updates change statuses in place — boxes never move or re-collapse under the cursor
**And** a leaf node navigates to its Step-run detail (story 1-2); no click-scrolls behaviour remains.

### Story 1-6: Artifact modal with markdown reader and edit-while-parked

As an Operator,
I want artifacts opening in a readable modal I can edit while the Run is parked,
So that raw file dumps stop being the review surface.

**Acceptance Criteria:**

**Given** an artifact in the artifacts panel
**When** I open it
**Then** a modal shows reader view: markdown rendered, YAML/code highlighted, `RENDERED · SOURCE · RAW` toggle, download (FR-23, UX-DR5)
**And** while the Run is `needs_you` with no terminal session, *Edit* + save commits via `PUT /runs/{id}/files` as `spec: operator edit (orchestrator)` with the hint saying so; a rejected save prints the git output verbatim and keeps the buffer
**And** `stories.yaml` and `epics.yaml` open read-only with `planned at {sha} — start a new run to change the list`.

## Epic 2: Fail at the form, not in the run — live probe and enforced model choice

Selecting a harness probes it live and loads its real model list; an unusable harness or invalid model is refused at submission with the specific reason; the readiness Run becomes an informational diagnostic; every input explains itself.

### Story 2-1: The probe — script verb, port, and route

As an Operator,
I want each harness to expose a live probe,
So that its fitness is known at the moment of use.

**Acceptance Criteria:**

**Given** any installed harness
**When** `scripts/harness/<name>.sh probe` runs
**Then** it reuses `doctor`'s checks — CLI at the pinned version, credentials valid (one trivial call), Gateway reachable — and enumerates models (FR-33)
**And** the `Harness` port gains `probe() → ProbeResult{ok, failing_reason?, version, models[]}`; the adapter shells the verb, application code reads only the port (AD-10, AD-2); one shared fake lands in `tests/unit/fakes/`
**And** `GET /api/v1/harnesses/{name}/probe` serves it, failures carrying the specific reason (`not logged in`, `gateway unreachable`) — never a bare flag; contract regenerated without drift (AD-3).

### Story 2-2: Probe gates create_run and pre-flight; model enforced server-side

As an Operator,
I want an unusable harness or invalid model refused at submission with the reason,
So that runs stop failing late on configuration.

**Acceptance Criteria:**

**Given** a create attempt
**Then** pre-flight's harness line reads the Probe result; the stored `enabled` flag is read by neither pre-flight nor `create_run` (FR-33, AD-10)
**And** `create_run` re-runs the Probe inline once at create and rejects a model outside the probed list with 422 naming the list — every create, not only the form (FR-8)
**And** a harness whose version pin changed fails the Probe's version check until the CLI matches; queued and parked Runs keep their harness and resume on it
**And** the readiness Run is subject to the same Probe as any create; the old `enabled`-exemption logic is removed.

### Story 2-3: Probe-gated New-workflow form with enforced model select

As an Operator,
I want the form to show each harness's live state and only its real models,
So that I cannot submit what cannot run.

**Acceptance Criteria:**

**Given** the New-workflow form
**Then** the harness row lists one line per harness with the live probe result in words (`ok`, or the specific reason); a failing harness cannot be selected and its line states why (UX-DR6)
**And** probe success loads the model select over the probed models — never free text; the probe runs on harness selection and on submit only; other field changes re-run pure `plan_run` (AD-10)
**And** a probe failure blocks submission with the reason in the pre-flight readout; warnings never block.

### Story 2-4: Readiness demoted to an informational diagnostic

As an Operator,
I want the six-check readiness Run available on demand as a badge,
So that deep diagnosis exists without standing between me and Start run.

**Acceptance Criteria:**

**Given** the harness row
**Then** it shows the readiness badge — last run time and, on failure, the first failing check line — beside a *run readiness* link; it informs, it does not gate (FR-33)
**And** `GET /harnesses` carries probe result + badge; `use_cases/harness_readiness` keeps writing the state; `sync_pins()` resets the badge of a harness whose pin changed (AD-10)
**And** readiness Runs stay ordinary Runs on the Board (Project `readiness`, branch `readiness/{harness}/{date}`, never pushed).

### Story 2-5: Form tooltips and mandatory marks

As an Operator,
I want every input to explain why it matters,
So that the form teaches instead of guessing.

**Acceptance Criteria:**

**Given** the New-workflow form
**Then** every input carries a tooltip stating why it matters and what consumes it; mandatory inputs are marked `*` (item 6)
**And** optional inputs say so in words — e.g. manual estimate `(optional)`; the budget field gains its `(optional)` mark when FR-17's optionality lands (Epic 3, story 3-2 — until then it renders as today); copy states facts and mechanisms, never congratulates (NFR-8).

## Epic 3: Runs that stall park, healthy runs finish — liveness and session recovery

A healthy hour-long story runs to its end (stall detector replaces the default hard kill; budget optional, `tracked, no cap`); when a story blocks or errors the Operator chooses reply-in-session or restart; every retry prompt is explicit in the template.

### Story 3-1: Stall detector replaces the default hard kill

As an Operator,
I want agent steps watched for inactivity instead of killed by a wall clock,
So that a healthy hour-long Story runs to its end.

**Acceptance Criteria:**

**Given** a dispatched agent Attempt
**Then** `ProcessRunner.start` takes optional `timeout_min` and `stall_min` and `wait` returns `{exited(code) | timed_out | stalled}` (AD-14); the shared fake is extended, not duplicated
**And** the runner's stall signal is exactly no mtime change under `cwd` (`.git` included) and no growth of the attempt log for `n` minutes → kill group; the `agent` executor composes the park — row `error`, `timeout` kind, reason `stalled {path}: no activity for {n} min` (FR-10)
**And** `timeout_min` on `agent` steps is optional with no default hard kill; `stall_min` defaults 30, template-tunable (`validate.py` accepts the key); the wall clocks stay for `shell` (30) and `git.*` (5), which never receive `stall_min`
**And** any existing test pinning the old agent 90-min default is revised only under the operator revision of 2026-09-15, named and dated in the revised test (anchor exception 4).

### Story 3-2: Optional budget — tracked, no cap

As an Operator,
I want the budget cap optional while tracking stays authoritative,
So that subscription-priced runs aren't parked by a meaningless USD limit.

**Acceptance Criteria:**

**Given** a Run created without a budget
**Then** `run.budget_usd` is nullable; with null the budget rule is a no-op and nothing parks `budget`-kind; spend tracking per attempt/story/project is untouched and authoritative (FR-17, AD-11)
**And** cost surfaces show `tracked, no cap` where the budget row would render — cost block and card summary (UX-DR8)
**And** the Claude adapter omits `--max-budget-usd` when `budget_usd` is null (AD-10)
**And** `create_run` accepts the missing budget and the halt applies only when one is set.

### Story 3-3: Reply-or-restart — the mode field on Answer and Retry

As an Operator,
I want to answer or retry into the recorded session when one sentence suffices,
So that a re-plan isn't the only recovery.

**Acceptance Criteria:**

**Given** a parked Run
**Then** the Answer and Retry payloads carry `mode: restart | session`; `restart` is today's mechanism unchanged; the Signal shape is otherwise untouched and the two-writer rule holds (FR-18, FR-20, AD-8/AD-13)
**And** `mode: session` against an Attempt not `reply_available` (harness `capabilities.resume` ∧ recorded `session_id`, AD-10) is refused with 422 naming the reason
**And** a session-mode delivery is a new Attempt on the same row: `n+1`, `session_id` inherited, `start_sha = HEAD` at delivery, `env_for` of the new Attempt — spend, trace, and the AD-17 range bill to it; `mark_started`/`mark_finished`, protected-path check, FR-16 routing, `Gateway.spend`, budget rule run exactly as after a dispatch; the prepare commit is skipped; nothing archived, no re-plan (AD-13)
**And** `Harness.resume` returns a `HarnessResult` like `run`; the Claude adapter implements it; a harness without `resume` never offers the mode.

### Story 3-4: The choice on the Answer and Retry surfaces

As an Operator,
I want the UI to offer reply-in-session only when it can work and say what each mode does,
So that recovery is never a guess.

**Acceptance Criteria:**

**Given** a blocked or errored row
**Then** the Answer box and Retry control offer the mode choice only when `reply_available` is true; otherwise restart is the only path shown (FR-18/FR-20)
**And** the box states in words, above the button, exactly what each mode will do — restart: which file is archived where and that the Story is re-planned; session: the session continues with the Answer and the Story file stays in place
**And** the gate record names the mode; the Run leaves `needs_you` within one poll interval.

### Story 3-5: Explicit retry prompts in the shipped templates

As a Template author,
I want every automatic retry's prompt written in the template,
So that workflows are maintainable and the prompt is a visible part of the definition.

**Acceptance Criteria:**

**Given** the shipped templates
**Then** every `retry` block declares its `prompt` explicitly — no implicit defaults (item 15)
**And** no unit or e2e test pins the shipped templates' content (exemplar freeze); the Step-run detail (story 1-2) displays the exact prompt a retry used, verified in the e2e flow.

## Epic 4: The method opens — custom skills, spec gate, epic tail, small entry points

Operator-authored skills install into every harness at image build; agent steps dispatch any skill or a custom prompt; the spec-gate reviews the spec folder once before the loop; the epic tail pushes before review, generates and runs e2e, and writes a retrospective; story-run@1 and task@1 open small entries.

### Story 4-1: ia-agents-skills/ installed into every harness at image build

As an Operator,
I want my own skills authored in this repository installed for every harness,
So that custom capability exists by default everywhere.

**Acceptance Criteria:**

**Given** the repository-root `ia-agents-skills/` (created with a README stating the authoring contract)
**When** the backend-api image builds
**Then** it copies the folder beside the BMAD stubs into `~/.claude/skills` and `~/.agents/skills`; `scripts/harness/*.sh install` extends to cover it (AD-16)
**And** the build fails on a name collision between the stub set and `ia-agents-skills/`, and writes `skills-manifest.json` — the union, per harness home
**And** the gitignore contract extends to the corresponding folders; a change to `ia-agents-skills/` ships by image rebuild, never per Run.

### Story 4-2: SkillCatalog port and the installed-skill pre-flight check

As an Operator,
I want pre-flight to refuse a plan naming an uninstalled skill,
So that skill typos fail at the form, not mid-run.

**Acceptance Criteria:**

**Given** a plan with a `skill:` Step
**Then** a `SkillCatalog` port exposes `skills-manifest.json` read-only, with one shared fake in `tests/unit/fakes/`; `validate.py` stays pure (AD-16, AD-2)
**And** pre-flight's installed-skill line fails naming an absent skill — never a runtime park.

### Story 4-3: DSL dispatch forms — skill or prompt/prompt_file

As a Template author,
I want an agent step to run any installed skill or my own prompt,
So that non-BMAD pipelines are expressible.

**Acceptance Criteria:**

**Given** an `agent` step
**Then** its `with` declares exactly one dispatch form — `skill` (string, as shipped `story.yaml` already does) or `prompt` / `prompt_file`; zero or more than one (including `prompt` beside `prompt_file`) is a validation error naming line and reason (FR-5, FR-14)
**And** both forms carry `expect {files, status_in}`; `prompt_file` is read from the working folder; `compose_prompt` remains the only prompt builder and gains the second form (AD-9)
**And** `validate.py` additionally rejects an all-digit step `id` (guards AD-15's dot-index bijection)
**And** contract and template-editor errors stay consistent; no test pins shipped template content.

### Story 4-4: The spec-gate — one review before the story loop

As an Operator,
I want the spec folder reviewed once before stories run,
So that I answer every open question up front and the loop then runs full-auto.

**Acceptance Criteria:**

**Given** an epic Run past baseline
**Then** the shipped `epic` template dispatches the `spec-gate` skill (authored in `ia-agents-skills/`) over the spec folder via the `skill:` form with `expect`, routed on its output file like any agent step (FR-16; items 4, 18)
**And** outcomes route: clean → the loop starts; open questions → one human gate listing every question across all stories; formatting problems → fixed and committed as `spec: gate fixes (orchestrator)`, then proceeds
**And** spec-authoring guidance records that `spec_checkpoint` is now the exception, not the routine validation path.

### Story 4-5: Epic tail reorder — push before review

As an Operator,
I want the branch pushed before the final done checkpoint,
So that I review real code through the compare link from my own machine.

**Acceptance Criteria:**

**Given** the shipped `epic` template
**Then** it pushes the branch and records the compare link before a final done checkpoint parks (item 9)
**And** spec-authoring guidance drops `done_checkpoint` from non-final stories — the epic tail is the review point; exemplar freeze holds.

### Story 4-6: E2e generation gate in the epic tail

As an Operator,
I want e2e tests generated and run after the last story,
So that the epic is verified end to end without the orchestrator owning an oracle.

**Acceptance Criteria:**

**Given** an epic whose last story is done
**Then** the template dispatches `bmad-qa-generate-e2e-tests` for the epic (skill form), then runs the repository's e2e command as a deterministic `shell` step (item 10, §5 softening)
**And** on failure the existing `on_fail: {redispatch, max}` sends it to a fixing agent, bounded; exhaustion parks
**And** tests the epic's own agents created are not in the frozen set — no protected-path hit from generation (FR-31).

### Story 4-7: Retrospective step in the epic tail

As an Operator,
I want an evidence-based retro written after the e2e gate,
So that each epic leaves a record of what went wrong and right.

**Acceptance Criteria:**

**Given** the e2e gate has run
**Then** a post-e2e step dispatches `bmad-retrospective` (headless) via the `skill:` form; the report lands in the working folder and is committed by the step's flow (item 13)
**And** no second data-collection path exists: the trajectory row (AD-19) stays the per-story record; session-interrogation retro stays a recorded follow-up note.

### Story 4-8: story-run@1 and the only: selector

As an Operator,
I want to run exactly one story of an epic,
So that a single fix doesn't require the whole loop.

**Acceptance Criteria:**

**Given** a `for_each` with an `only:` selector
**Then** it is a plan-time filter (FR-5's no-conditionals rule stands); `validate.py` accepts it; `plan_run` plans only the matching frame (IMP-001 B)
**And** a `story-run@1` root template runs one story via `only:`; `create_run` accepts it; pre-flight behaves as for `epic`.

### Story 4-9: task@1 — an issue-sized change through the plan gate

As an Operator,
I want to paste an issue-sized intent and get a planned, gated, developed change,
So that small work has a small entry.

**Acceptance Criteria:**

**Given** a pasted `intent`
**Then** `task@1` plans it with the plan gate (spec checkpoint) always on; the parked plan is resumed by Continue (IMP-002 B1)
**And** entry is pasted text only — never API ingestion (§5 boundary); the template is an exemplar, unpinned by tests.

## Epic 5: Safe concurrency — branch partition, consent, saved runs with dependencies

Different branches of one repository run in parallel behind an informed-consent warning; a Run can be saved without starting and chained with `after: {run_id}`; every waiting condition is a reason text. Carries the two anchor-revision moments under the dated operator exception. Deliberately last.

### Story 5-1: The queue partitions by (Repository, branch)

As an Operator,
I want runs on different branches of one repository to execute concurrently,
So that the repository lock stops serializing mechanically independent work.

**Acceptance Criteria:**

**Given** two Runs on one repository, different declared branches
**Then** `engine.enqueue` uses `partition_key = "{repository_id}:{declared branch}"` — the branch the plan's `git.worktree` row was declared from, never an allocated fresh name; an `initiative` plan uses its base branch; the engine port's `partition_key` widens to `str` deliberately (AD-12, FR-13)
**And** `engine.enqueue` is idempotent on `run_id` — a second enqueue is a recorded no-op
**And** the same branch stays refused: pre-flight's held-branch check covers branches declared by `git.worktree` rows of non-terminal Runs, and `git.worktree` parks `misconfigured: branch held by {run}` as the backstop (AD-14, PRD §4.6)
**And** queue reasons become `branch held by {run}` and `global concurrency, held by {runs}` — revising test-pinned strings only as the operator revision of 2026-09-15 (anchor exception 4), the revised test naming the decision and date
**And** `MAX_ACTIVE_RUNS` stays the instance setting; a `needs_you` Run still holds partition and slot.

### Story 5-2: Shared-repository informed consent

As an Operator,
I want an explicit warning with the facts before two runs share a repository,
So that parallelism is a choice, never a surprise.

**Acceptance Criteria:**

**Given** a create on a repository with an active Run elsewhere
**Then** pre-flight warns with the facts — which Run, which branch, which Spec folder — and *Start run* requires explicit confirmation (`this can lead to merge conflicts`); never refused, never silently queued (FR-8, FR-13, UX-DR6)
**And** two Runs on different branches then execute concurrently; the facts land in words, one signal colour max per row (NFR-6).

### Story 5-3: Save a Run without starting it

As an Operator,
I want Save beside Start run,
So that I can plan now and start later.

**Acceptance Criteria:**

**Given** a valid New-workflow form
**When** I press *Save*
**Then** the same planned rows persist without enqueueing: the saved Run is status `queued` with `engine_ref` null — the null is the saved state, no new token; it renders in the Queued column with reason `saved — not started` (FR-8, FR-13, AD-12)
**And** the `start` Signal (valid only when `engine_ref` null and status `queued`) enqueues it: gate-record event `started_by_operator`, `after_run_id` cleared in the same unit of work, the Probe re-read exactly as `create_run` does (AD-13, AD-10)
**And** `list_queue` appends saved Runs to the engine's queue view; reason texts, never status tokens (FR-25).

### Story 5-4: after: {run_id} — dependencies between Runs

As an Operator,
I want a saved Run to start when its predecessor finishes,
So that chained work runs unattended in order.

**Acceptance Criteria:**

**Given** a saved Run declaring `after: {run_id}` (stored `run.after_run_id`)
**Then** its queue row reads `waiting for run {x}` (FR-13, FR-25)
**And** the writer applying the predecessor's terminal transition resolves dependents (`engine_ref` null only) in the same unit of work: `done` → idempotent `engine.enqueue`; `failed | cancelled` → dependent `needs_you`, `park_kind = dependency`, `park_path` null, reason `run {x} ended {status}` — still the two writers, no poller (AD-8, AD-12, §4.6)
**And** container start sweeps crash residue: every Run whose `after_run_id` names a `done` Run and whose `engine_ref` is null is enqueued (AD-12)
**And** on a `dependency` park Continue enqueues (start anyway) and Cancel cancels — `signal_run` calls `engine.enqueue`, not `engine.signal`, for these; a dependency park never expires; `cancel`'s effects are recorded no-ops where referents don't exist (AD-13).
