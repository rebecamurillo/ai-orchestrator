---
title: Verification review — mvp-feedback §5 deltas applied to prd.md
date: 2026-09-15
reviewer: verification pass (delta completeness + consistency)
inputs:
  - prd.md (2026-09-15)
  - ../mvp-feedback/sprint-change-proposal-2026-09-14.md (§4, §5)
  - ../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md (2026-09-15, deltas 20–27)
out-of-scope (per review brief, not findings): PRD §6 (describes the shipped MVP — §0 states this); PRD §8 open questions 1–8 (historical); ARCHITECTURE-SPINE.md (deliberately not yet updated)
---

# Review: mvp-feedback contract deltas in prd.md

## Section 1 — Delta checklist (proposal §5, item by item)

| # | Delta (proposal §5) | Where in the PRD | Verdict |
| --- | --- | --- | --- |
| 1 | **FR-8** save-without-start | FR-8 intro ("Beside *Start run* sits *Save*: a saved Run is planned and stored, not enqueued") + last consequence (Save persists the same planned rows; started later by the Operator or by `after: {run_id}`); glossary **Run** carries "saved Run" | **LANDED** |
| 2 | **FR-8** server-side model validation; select over probed models; 422 naming the list | FR-8: "The model field is a select over the probed Harness's models, never free text; `create_run` rejects a model outside the list with 422 naming the list … server-side validation applies to every create, not only the form" | **LANDED** |
| 3 | **FR-8** live probe in pre-flight | FR-8 pre-flight bullet: "the Harness Probe passes (FR-33) … a failure states the specific reason (`not logged in`, `gateway unreachable`), never a bare disabled flag" | **LANDED** |
| 4 | **FR-8** shared-repository consent warning | FR-8 pre-flight bullet: warning with the facts (which Run, which branch, which Spec folder), explicit confirmation `this can lead to merge conflicts`, "never a silent queue"; echoed in UJ-2 edge case and FR-13 | **LANDED** |
| 5 | **FR-10** `timeout_min` optional, no default hard kill | FR-10: "`timeout_min` is **optional** on `agent` Steps, with no default hard kill: a healthy hour-long Story runs to its end" | **LANDED** |
| 6 | **FR-10** stall detector default, reason `stalled {path}: no activity for {n} min` | FR-10 (default 30, template-tunable, parks `timeout`-kind); §4.6 table timeout row carries both reason texts; EXPERIENCE stop table matches verbatim | **LANDED** |
| 7 | **FR-10** wall clock stays for `shell`/`git.*` | FR-10: "The wall clock remains where it is honest: `shell` (default 30) and `git.*` (default 5) … Both timers belong to the process runner, never to the workflow engine (AD-14)" | **LANDED** |
| 8 | **FR-13** (Repository, branch) partition | FR-13 intro + consequences (same branch refused/queued; different branches concurrent with consent; "The lock is the queue's per-(Repository, branch) partition (AD-12 delta …)"); FR-30 subjected to the same partition | **LANDED** |
| 9 | **FR-13** saved runs with `after: {run_id}` | FR-13: scheduler enqueues on predecessor `done`; predecessor `failed`/`cancelled` parks the dependent as a decision, never auto-started | **LANDED** (but see finding M-3 on the missing Stop kind) |
| 10 | **FR-13** `waiting for run {x}` a reason text, never a status token | FR-13: "its queue row reads `waiting for run {x}` — a reason text, never a new Status token"; FR-25 lists it among the fixed reasons | **LANDED** |
| 11 | **FR-17** budget optional; tracking untouched; `tracked, no cap` | FR-17 intro + consequences; FR-23 cost block; §11 Cost guardrail rewritten | **LANDED** |
| 12 | **FR-23** stop zone top → central diagram → summary column → one bottom tabbed region, gate record default | FR-23 intro and stop-zone consequence ("resolving a Stop never requires a scroll or a tab") | **LANDED** |
| 13 | **FR-23** artifact modal: markdown reader + edit-while-parked | FR-23: modal, reader first, source/raw toggles, download; edits while parked via FR-19's mechanism; list files read-only `planned at {commit}` | **LANDED** |
| 14 | **FR-34** (new) Step-run detail: route `/workflows/:runId/steps/{dot-index path}` | FR-34: dot-index route (`epics.0.stories.3.build`), no URL-encoding, bookmarkable, exists for any Step status | **LANDED** |
| 15 | **FR-34** per-attempt dispatch/retry prompt; verbatim agent result | FR-34: "the dispatch prompt and, for a retry, the exact `retry.prompt` the Template declared"; "the agent's result, verbatim … `## Auto Run Result` … `— running` while in flight" | **LANDED** |
| 16 | **FR-34** full log: latest-default, live-follow, download | FR-34: Attempts newest first with latest selected; log via `GET /runs/{id}/attempts/{attempt_id}/log`, cursor paging, follow on by default while running, download control, `log no longer on disk` in words | **LANDED** |
| 17 | **FR-34** full session id with copy | FR-34: "the **full Session id printed on the row with a copy control**" | **LANDED** |
| 18 | **FR-34** right-side helper drawer — side panel, never a modal | FR-34: "a side panel, never a modal; the page behind it stays live and the log keeps following under it"; two contents (*prompt · result*, *reach agent*) | **LANDED** |
| 19 | **FR-29** diagram embedded; `?view=diagram` retired | FR-29 intro: "the standalone `?view=diagram` surface is retired and redirects to the Run detail"; EXPERIENCE IA table agrees | **LANDED** |
| 20 | **FR-29** border colours: done green / running blue / error red / waiting amber / scheduled grey | FR-29 (with `signal-criterion` revival noted); NFR-6 exemption; EXPERIENCE diagram dialect matches | **LANDED** |
| 21 | **FR-29** SKP/CAN grey, never green | FR-29: "faint grey border and the word token only — skipped is never green, on the diagram as everywhere" | **LANDED** |
| 22 | **FR-29** one box per loop iteration with `k/n steps` | FR-29: iteration boxes with label, chip + token, `k/n steps`; aggregate per AD-15 group-status rule | **LANDED** |
| 23 | **FR-29** level-by-level click expansion, no hover; group boxes carry aggregate colour | FR-29: "one level per click — nested loops open level by level; hover never expands"; group token and border carry the aggregate | **LANDED** |
| 24 | **FR-29** leaf click navigates to Step-run detail; old "click scrolls the detail view" sentence removed | FR-29: "A leaf Step node navigates to its Step-run detail (FR-34)". No "scrolls/scrolled" residue anywhere in the PRD (grep-verified); EXPERIENCE delta 23 records the retirement | **LANDED** |
| 25 | **FR-33** probe gates the form with the specific reason | FR-33 intro + first consequence (`probe` verb, `GET /api/v1/harnesses/{name}/probe`, `not logged in` / `gateway unreachable`, never a bare disabled flag) | **LANDED** |
| 26 | **FR-33** readiness Run demoted to operator-triggered diagnostic | FR-33: "demoted to an operator-triggered deep diagnostic whose last result is an informational badge … never the thing between the Operator and *Start run*"; "it informs, it does not gate" | **LANDED** |
| 27 | **FR-33** `enabled` no longer read by `create_run` | FR-33: "`create_run` and pre-flight read the Probe result; the stored `enabled` flag is read by neither (AD-10 delta …)" | **LANDED** |
| 28 | **FR-5/FR-14** exactly one of `skill:` or `prompt:`/`prompt_file:`, with `expect {files, status_in}` | FR-5: "declares **exactly one** of two dispatch forms … with `expect {files, status_in}`"; validator error for "neither or both"; FR-14 mirrors it | **LANDED** |
| 29 | **FR-14** `compose_prompt` gains the second dispatch form | FR-14: "Dispatch has two forms, built by the same prompt builder (AD-9's `compose_prompt`)"; `ia-agents-skills/` at image build (AD-16 delta) | **LANDED** |
| 30 | **FR-18/FR-20** reply-or-restart `mode` on Answer and Retry payloads | FR-18: `mode: restart | session` on the Answer payload (AD-13 shape unchanged, AD-8 untouched); FR-20: "The Retry payload carries the same `mode` field as FR-18" | **LANDED** |
| 31 | **FR-18/FR-20** 422 against a non-resumable row; UI offers choice only when `reply_available` | Both FRs state it verbatim | **LANDED** |
| 32 | **§5 non-goals** e2e generation softened (F8) | §5: "It may dispatch end-to-end test **generation** to an agent (the epic tail) and verifies the result only with the Repository's own commands. *(Softened 2026-09-15, F8 …)*" | **LANDED** |
| 33 | **§5 non-goals** pasted intent via `task` template (F11) | §5: "An issue-sized change enters as Operator-pasted `intent` through the `task` Template, plan gate always on — pasted text, never API ingestion. *(Softened 2026-09-15, F11.)*" | **LANDED** |
| 34 | **NFR-6** diagram exempt from one-signal-per-surface; colour-never-alone stays | NFR-6: "The run diagram (FR-29) is the one surface exempt … colour-never-alone still holds there, and skipped or cancelled is never green" | **LANDED** |
| 35 | **§8** records AD-10, AD-12, AD-15, AD-16 as spine deltas pending the architect pass | §8 "Recorded 2026-09-15" block, items 9–12, each naming its FR; "until then, where code and spine disagree: stop and say so" (also §0) | **LANDED** |

**All 35 checklist items landed.** Status vocabularies verified frozen: no new Run or Step token appears in either document; `waiting for run {x}`, `waiting: branch held by {run}`, and stall reasons are reason texts only.

## Section 2 — Findings

The PRD itself is internally consistent apart from three medium/low residues. Every high-severity residue is in **EXPERIENCE-v1.md**, whose same-pass touch covered only the stop-table stall reason and the `tracked, no cap` cost row — its New-workflow and Runs-screen sections still state pre-delta behaviour, while its own frontmatter claims "this document and the PRD state the same contract".

### High

- **H-1 — EXPERIENCE-v1 New workflow still gates the harness list by readiness run, not probe** (contradicts PRD FR-33/FR-8).
  §2.1, line 82: "The harness row is a list, one line per harness: name, `enabled` or `disabled: {check}` in words, last readiness time, and a *re-run readiness* link; a disabled harness cannot be selected."
  Operator workflow step 3, line 63: "harness (from the readiness list: `enabled` or `disabled: {check}`)" and pre-flight includes "harness enabled".
  PRD FR-33 says the live Probe gates with a specific reason, "never a bare disabled flag", and the readiness badge "informs, it does not gate"; FR-8's pre-flight names the Probe, not `enabled`.

- **H-2 — EXPERIENCE-v1 Runs screen keeps the repository lock and misses the new queue reason** (contradicts PRD FR-13/FR-25).
  §4, line 142: "reasons from a fixed set (`repository lock held by {run}`, `global concurrency, held by {runs}`, `running`, `waiting for your answer`)" and section head "`… · one active run per repository · parked runs hold a slot`".
  PRD FR-25's fixed set is `branch held by {run}`, `global concurrency`, `running`, `waiting for your answer`, `waiting for run {x}`; PRD FR-13 partitions per (Repository, branch). The reason text differs between the two documents and `waiting for run {x}` is absent from the UX.

- **H-3 — EXPERIENCE-v1 New workflow has no *Save*, and start still keys on "the repository is free"** (contradicts PRD FR-8/FR-13).
  Line 63: "*Start run* persists the plan and enqueues: it starts immediately if the repository is free, else queues behind the run holding it"; §2.1 decision bar: "*Start run* (primary), *Cancel*, one note about queueing" — no *Save*, no saved-run/`after:` surface, and no shared-repository consent warning (`this can lead to merge conflicts`) anywhere in the pre-flight readout. Voice line 164 repeats "Starts immediately if the repository is free".

### Medium

- **M-1 — EXPERIENCE-v1 Voice list carries retired exemplar copy.**
  Line 165: "`waiting: repository lock held by feat/saved-views`" and "`enabled` / `disabled: trace not found`" sit in the canonical copy list beside the newly added `stalled …` / `tracked, no cap` lines. PRD copy is `waiting: branch held by {run}` (FR-13, UJ-2) and probe reasons (`not logged in`, `gateway unreachable`).

- **M-2 — EXPERIENCE-v1 State vocabulary explains `QUE` with the old lock.**
  Line 151: "`QUE` | enqueued, or waiting for a repository lock or a concurrency slot". Should be the branch partition, and the row omits the saved-run wait (`waiting for run {x}`).

- **M-3 — PRD FR-13's parked dependent has no Stop kind in §4.6, which claims completeness.**
  FR-13: "A predecessor ending `failed` or `cancelled` parks the dependent as a decision for the Operator — it is never auto-started." §4.6 opens with "This table is the only list of Stops", and no row covers this park (kind, reason text, admitted Signals are all undefined). EXPERIENCE-v1's stop table inherits the gap. Either a Stop row or an explicit statement that the dependent is held un-enqueued (not parked in `needs-you`) is needed.

- **M-4 — PRD FR-14 still leans on the readiness run as the thing that fails instead of a Run.**
  FR-14: "a Harness that cannot run the skill from a Worktree fails its readiness run (FR-33), not a Run." With FR-33 demoting the readiness run to a non-gating diagnostic, nothing prevents such a Harness from being offered (the Probe checks CLI/credentials/Gateway only), so the "not a Run" assurance no longer holds. The sentence needs softening or the Probe needs the capability check.

### Low

- **L-1 — PRD FR-10 retains "each under its own `timeout_min`" in the bounds sentence.**
  FR-10: "a Story step runs at most `(1 + retry.max) × (1 + redispatch.max)` Attempts (six for the shipped `story` Template), each under its own `timeout_min`". With `timeout_min` now optional and default-less on agent Steps, the default Story attempt runs under the stall detector, not a `timeout_min`.

- **L-2 — A saved Run's Run Status and Board placement are unstated.**
  FR-8/FR-13 define a saved Run as "planned and stored, not enqueued", and the vocabulary is (correctly) not extended — but no sentence says which of the six frozen Statuses it carries or in which Board column it renders. FR-13 shows it a queue row (`waiting for run {x}`) only for the `after:` case.

- **L-3 — EXPERIENCE-v1 workflow step 3 lists "budget" unmarked while "manual estimate (optional)" is marked.**
  Line 63. Implies the old mandatory budget; PRD FR-8/FR-17 make it optional.

- **L-4 — EXPERIENCE-v1 frontmatter overstates alignment.**
  Line 9: "this document and the PRD state the same contract" — untrue while H-1..H-3 stand. (The historical delta 15, "Harnesses are a readiness list", is a dated changelog entry and acceptable as record, but nothing in deltas 20–27 supersedes it, so the readiness-list rule still reads as standing.)

### Verified clean (checked, no finding)

- No "90-min" / default hard-kill residue anywhere in either document (grep-verified).
- No "click scrolls the detail view" residue; delta 23 records its retirement.
- No standalone diagram-view residue outside §6 (out of scope) — `?view=diagram` appears only as "retired and redirects".
- §4.6 stop table reason texts match FR-10/FR-16/FR-17/FR-31 and EXPERIENCE-v1's stop-body table row for row, including both timeout reasons and `gateway unreachable` under `misconfigured`.
- Glossary entries (Run, Harness, Probe, Status, Stop, Worktree) agree with the updated FRs; no new status token in either document.
- FR-24's follow-tail exception, FR-23's `tracked, no cap` cost row, and §11's optional-budget guardrail are mutually consistent and match EXPERIENCE §2.2.
