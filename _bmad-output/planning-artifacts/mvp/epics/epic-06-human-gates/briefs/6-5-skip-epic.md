---
story: "6-5"
epic: 6
title: Skip epic
requirements: [FR-20 (skip epic), FR-11, NFR-8, UX-DR10]
binds: [AD-13]
---

# Story 6.5 — Skip epic

As the Operator,
I want to abandon the rest of an epic while still pushing what was done and getting its compare link, then move on to the next epic,
So that a bad epic does not hold the initiative hostage and nothing done is lost.

## Scope

**In:** the `skip_epic` effects (writer from 4.5 verified and completed), the push-rejected variant, the button with its inline confirm, the summary and compare-link lines, tests.
**Out:** nothing else.

## Binding rules (inlined)

- **Writer (AD-13).** Valid when `needs_you`, `park_kind ∉ {budget, plan_stale}`, `park_path` inside an `epics[i]` frame (or any story frame of an `epic` Run): as `skip_story` for the current story frame (its remaining `agent`/`checkpoint` rows skipped, its verify queued as re-baseline — or, after `re-baseline failed after skip`, its `error` verify row `→ skipped` and the `git.commit` row queued), plus every non-terminal row of the remaining story frames of that epic `→ skipped · skipped by operator`; the epic's `push`, `link`, and `after` rows stay `planned` so that every done commit reaches the remote — **except** when `park_kind == push_rejected`: then `push` and `link` `→ skipped · skipped by operator` and the next epic's first row (`epics[i+1].checkout`) `→ queued`; on an `epic` Run with a rejected push the Run ends `done` with no link.
- **Compare link.** `pr.link` runs normally; the summary lists the skipped stories beside the link: `{url} · skipped: {ids}`; `summary.skipped_epics` lists an epic whose push was skipped.
- **Button.** *Skip epic* (`wf-signal-skip_epic`) on every body that admits it, with the inline confirm `skip epic {n}: remaining stories are marked skipped, the quality gate re-runs, done work is pushed and the compare link recorded` (or `… the push is skipped` on `push_rejected`).

## Acceptance criteria

**Given** an initiative Run parked `blocked` on `epics[0].stories[1].build` with stories 2–4 remaining
**When** `skip_epic` is signalled
**Then** the current frame is handled as skip story, every row of `epics[0].stories[2..3]` is `skipped · skipped by operator`, `epics[0].push`, `epics[0].link` stay `planned`, and after the re-baseline and commit-guard the walker runs push and link, then `epics[1].checkout`.

**Given** a Run parked `push_rejected` on `epics[0].push`
**When** `skip_epic` is signalled
**Then** `epics[0].push` and `epics[0].link` are `skipped`, `epics[1].checkout` is `queued`, and `summary.skipped_epics == [1]` at the end.

**Given** a Run parked `re-baseline failed after skip` on `epics[0].stories[1].verify`
**When** `skip_epic` is signalled
**Then** that verify row is `skipped`, the frame's `git.commit` is `queued`, and the epic proceeds to push.

**Given** a Run parked `budget`
**When** `skip_epic` is signalled
**Then** 409.

**Given** the detail
**When** *Skip epic* is clicked and confirmed
**Then** the signal is posted with the right confirm text per park kind.

## Implementation notes

- Complete the 4.5 writer branches with parametrised tests over the three cases above.
- `summary.skipped_epics` in the read model (4.12) and on the done banner.

## Verification

```bash
make lint && make test && make e2e-api && make e2e-ui
```

## Sources for detail only

PRD FR-20 (skip epic paragraph), FR-11, §4.6 (skip rules line). Spine AD-13 (`skip_epic` row). `addendum.md` §I (skip epic keeps push/link).
