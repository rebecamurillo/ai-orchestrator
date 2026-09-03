---
story: "6-4"
epic: 6
title: Skip story with the re-baseline
requirements: [FR-20 (skip story), FR-11 (summary), NFR-8, UX-DR10, SM-C3]
binds: [AD-9, AD-13]
---

# Story 6.4 — Skip story with the re-baseline

As the Operator,
I want to give up on one story and have the Run leave the tree green and committed before the next one starts,
So that skipping is honest: the story is listed as skipped, nothing half-done leaks into the next story.

## Scope

**In:** the `skip_story` effects end to end (writer from 4.5, executor behaviour on the re-baseline, the commit-guard message, the `re-baseline failed after skip` park and its Retry/Skip-epic follow-up), the *Skip story* button on every body that admits it, the skipped list in the summary and the compare-link line, tests.
**Out:** skip epic (6.5).

## Binding rules (inlined)

- **Writer (AD-13, 4.5).** `skip_story` valid when `needs_you`, `park_kind ∉ {budget, plan_stale, push_rejected}`, and `park_path` inside a story frame: every non-terminal `agent`/`checkpoint` row of the frame → `skipped · skipped by operator`; the frame's `git.commit` message re-resolved to `story {id}: skipped by operator`; the frame's `verify` row → `queued` (when it is `skipped · no quality_gate_command`, the `git.commit` row → `queued` instead); Run → `running`; record `skip_story`.
- **Re-baseline.** The `verify` row runs unchanged (`shell` with `on_fail: {redispatch: build}`); on failure `apply_step_result` finds the redispatch target `skipped` and parks `Park{verify_failed, "re-baseline failed after skip"}` (4.5 rule; verify it is wired and tested). On success the `git.commit` row commits leftovers with the skip message and the next frame starts.
- **After the re-baseline park.** Admitted: *Retry* (re-runs the verify row; syncs first per AD-13 since the kind is `verify_failed`), *Skip epic*, *Cancel run*; the Operator fixes the tree by inline edit (6.3), terminal session (6.7), or a push to the remote followed by Retry.
- **At a done checkpoint.** `skip_story` marks the checkpoint row skipped and continues (the build was done; the trajectory was already written).
- **Summary (FR-11, SM-C3).** `summary.skipped` lists the story id; the compare-link line on the done Run reads `{url} · skipped: {ids}`; the Board card's progress counts the skipped story as done for `m/m` `[ASSUMPTION: skipped stories count toward stories_done so the epic reads complete, and are named beside the link]`.
- **Button.** *Skip story* (`wf-signal-skip_story`) on `blocked`, `checkpoint`, `verify_failed`, `timeout`, `protected_path`, `misconfigured`, `internal` bodies; requires a confirm line inline (not a modal): `skip story {id}: its remaining steps are marked skipped, the quality gate re-runs, leftovers are committed as "story {id}: skipped by operator"` with *Skip story* / *Keep*.

## Acceptance criteria

**Given** a Run parked `blocked` on `stories[1].build` with rows `sync done, build blocked, verify planned, commit_guard planned, after planned`
**When** `skip_story` is signalled
**Then** `build` and `after` are `skipped · skipped by operator`, `verify` is `queued`, `commit_guard.with_resolved.message` is `story 2: skipped by operator`, the Run is `running`, and the record has `skip_story`.

**Given** the re-baseline passes on the fakes
**When** the walker continues
**Then** `commit_guard` commits (or records `no changes`) and `stories[2].sync` becomes `queued`.

**Given** the re-baseline fails
**When** applied
**Then** the Run parks `verify_failed · re-baseline failed after skip`, and `admitted_signals` is `[retry, skip_epic, cancel]`.

**Given** a frame whose verify was `skipped · no quality_gate_command`
**When** skipped
**Then** the `git.commit` row is queued directly.

**Given** a Run that finishes with one skipped story
**When** read
**Then** `summary.skipped == ["2"]`, the card reads `8/8 stories`, and the detail's compare line names the skipped id.

**Given** the detail
**When** *Skip story* is clicked and confirmed
**Then** the signal is posted; *Keep* posts nothing.

## Implementation notes

- Verify the 4.5 writer against this brief and add the missing branches with tests; the executors need no change beyond the `git.commit` message re-resolution (`with_resolved` is read at execution).
- `StopBody` gains the inline confirm component reused by 6.5.

## Verification

```bash
make lint && make test && make e2e-api && make e2e-ui
```

## Sources for detail only

PRD FR-20 (skip story paragraph), FR-11, SM-C3. Spine AD-13 (`skip_story` row), AD-9 (redispatch on a skipped target). `addendum.md` §G Skip.
