---
title: MVP feedback — correct-course working folder
status: proposal-pending-approval
created: 2026-09-14
purpose: operator feedback from testing the MVP dev loop, grouped into features/fixes and carried into a Sprint Change Proposal
inputs:
  - the operator's 19 feedback items (0–18), 2026-09-14
  - specs-ideas/IMP-001-single-story-run.md (challenged and merged here)
  - specs-ideas/IMP-002-issue-sized-change.md (challenged and merged here)
  - specs-ideas/IMP-003-answer-reply-in-session.md (challenged and merged here)
  - ../mvp/prd.md · ../mvp/architecture/ARCHITECTURE-SPINE.md
---

# MVP feedback — working folder

This folder is the output of a `bmad-correct-course` pass over the operator's post-testing
feedback. It exists so the next planning cycle starts from grouped, evidenced changes rather
than a raw list.

## Files

| File | What it is |
| --- | --- |
| [feedback-inventory.md](feedback-inventory.md) | Every feedback item (0–18) normalized, with its pain point, the feature that covers it, and the PRD/spine artifacts it touches. The coverage matrix proves no item is dropped. |
| [sprint-change-proposal-2026-09-14.md](sprint-change-proposal-2026-09-14.md) | The Sprint Change Proposal: pain-point synthesis, 11 features/fixes (F1–F11), impact analysis, recommended sequencing, and the handoff. |
| [specs-ideas/](specs-ideas/) | The improvements backlog (formerly `../improvements/`): IMP-001..003 with their README/index. Moved here 2026-09-14 so the whole feedback cycle lives in one folder; the notes' conventions and lifecycle are unchanged. |

## Status

The proposal is **drafted, not approved**. The improvements-backlog notes IMP-001, IMP-002 and
IMP-003 are merged into it (dispositions in the proposal §4.11 and the inventory); their
`status:` fields in `specs-ideas/` stay `candidate` until the operator approves this
proposal, at which point they move to `accepted`.

## Next steps after approval (in order)

1. `bmad-ux` — sketch and refine the two screens the proposal gates on UX: the reworked Run
   view (F3) and the new Step-run detail with live logs (F2). Output lands in this folder.
2. `bmad-prd` (update mode) — apply the PRD deltas listed in the proposal §5 (FR-8, FR-10,
   FR-13, FR-17, FR-23, FR-29, FR-33, NFR-6, §5 non-goals).
3. `bmad-create-epics-and-stories` — cut the approved features into the next version's epics.
