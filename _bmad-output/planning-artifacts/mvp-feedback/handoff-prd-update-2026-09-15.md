# Handoff — bmad-prd update pass (wave 0, second gate)

Written 2026-09-15 at the close of the `bmad-ux` pass. Paste the prompt below into a fresh
context after `/bmad-prd`. The follow-on prompt for the epics pass is at the bottom.

---

## Prompt for `/bmad-prd`

Update mode. Apply the consolidated contract deltas of the approved MVP-feedback cycle to the
PRD. This is the second and last wave-0 gate: the UX gate cleared 2026-09-15 (artboards
operator-approved).

**Change signal:** `_bmad-output/planning-artifacts/mvp-feedback/sprint-change-proposal-2026-09-14.md`
— §4 (features F1–F11), §5 (the consolidated deltas list, your work order), §6 (sequencing).
Item-level evidence: `feedback-inventory.md` in the same folder.

**Document to update:** `_bmad-output/planning-artifacts/mvp/prd.md`.

**UX authority for the screen-facing deltas:**
`_bmad-output/planning-artifacts/ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md`
(deltas 20–27 state exactly what changed; its frontmatter notes it "states the target, not
the current PRD text" — this pass is what closes that gap). The approved artboards are in
`mockups/` beside it; the decision trail is `.memlog.md`.

**Deltas to apply (proposal §5):**
- FR-8 — save-without-start; server-side model validation (select over the probed harness's
  models, 422 naming the list); live probe in pre-flight; informed-consent warning on a
  shared repository.
- FR-10 — `timeout_min` optional, no default hard kill; stall detector as default liveness
  signal (`stalled {path}: no activity for {n} min`); wall clock stays for `shell`/`git.*`.
- FR-13 — queue partition narrows to (repository, branch); saved runs with `after: {run_id}`
  dependencies; `waiting for run {x}` is a reason text, never a new status token.
- FR-17 — budget optional; tracking untouched and authoritative; `tracked, no cap` copy.
- FR-23 — run view rework (stop zone top → central diagram → summary column → one bottom
  tabbed region, gate record default); new Step-run detail page: route
  `/workflows/:runId/steps/{dot-index path}`, per attempt the dispatch/retry prompt, the
  agent's result (status + message, verbatim), the full log (latest attempt default, live
  follow, download), full session id with copy, and a right-side helper drawer
  (prompt·result / reach-agent resume instructions) — a side panel, never a modal; artifact
  modal with markdown reader + edit-while-parked.
- FR-29 — diagram embedded in the run view (`?view=diagram` retired); border colour per node:
  done green, running blue (`signal-criterion` revived), error red, waiting amber, scheduled
  grey; SKP/CAN grey — skipped is never green; one box per loop iteration with `k/n steps`,
  level-by-level expansion on click (no hover); group boxes carry the AD-15 aggregate colour;
  leaf click navigates to the step-run detail — the old "click scrolls the detail view"
  sentence must go.
- FR-33 — live `probe` gates the form with the specific reason; the six-check readiness Run
  demoted to an operator-triggered diagnostic; `enabled` no longer read by create_run.
- FR-5 / FR-14 — `agent` steps declare exactly one of `skill:` or `prompt:`/`prompt_file:`,
  with `expect {files, status_in}`; `compose_prompt` gains the second dispatch form.
- FR-18 / FR-20 — reply-or-restart `mode` on Answer and Retry signal payloads; refuse (422)
  against a non-resumable row; UI offers the choice only when `reply_available`.
- §5 non-goals — soften "does not generate or run e2e tests" (F8: generation dispatched to an
  agent, verified with the repository's own command) and "does not ingest issues" (F11:
  pasted `intent` via `task@1`).
- NFR-6 — diagram surface exempt from one-signal-per-surface; colour-never-alone stays.

**Spine deltas to record (not apply — the architect pass ratifies):** AD-10 (`enabled`
semantics), AD-12 (partition key), AD-15 (diagram statuses/colors), AD-16
(`ia-agents-skills/` installed at image build). Where code and spine disagree meanwhile:
stop and say so.

**Constraints:** status vocabularies are frozen — every new waiting condition is a reason
text; the two-writer rule (AD-8) is untouched; anchors (stories.yaml, epics.yaml, AGENTS.md,
existing tests) are read-only; product copy states facts and mechanisms, never congratulates.

**Also, same pass:** when FR-10/FR-17 wording lands, EXPERIENCE-v1's stop table and cost kv
need the matching touch (timeout stop reason becomes the stall text; budget row shows
`tracked, no cap`) — apply it or flag it explicitly.

**Bookkeeping if not yet done:** add the operator-approval note to the proposal frontmatter;
flip IMP-001..003 in `mvp-feedback/specs-ideas/` from `candidate` to `accepted`.

---

## After the PRD pass

Fresh context → `/bmad-create-epics-and-stories`: cut the `v2-operability` epics from the
approved features, waved per proposal §6 — wave 1: F2, F10, F9, F5 · wave 2: F3, F1 ·
wave 3: F7, F6, F8, F11 · wave 4: F4 (the one AD-level change, lands last). Success criteria
per proposal §7: every inventory item traceable to a story; PRD and spine deltas applied
before any build story references them. Consider a `bmad-architecture` touch first to ratify
the four AD deltas the PRD pass recorded.
