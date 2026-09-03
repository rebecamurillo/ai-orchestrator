---
story: "4-15"
epic: 4
title: Run detail core
requirements: [FR-20 (cancel confirm, retry), FR-23, FR-24, NFR-2, NFR-6, NFR-8, UX-DR5, UX-DR9, UX-DR10 (retry/continue/plan-stale bodies), UX-DR16, UX-DR17, UX-DR18]
binds: [AD-1, AD-3, AD-8, AD-13]
---

# Story 4.15 — Run detail core

As the Operator,
I want one screen for a Run that shows every planned step from the start, what stopped it and why, the record of every decision, and the actions the Run admits,
So that the Run detail is the only place decisions are made and nothing on it can look checked when it was not.

## Scope

**In:** `src/pages/workflows/[id].astro`, the `RunDetail` island polling `GET /runs/{id}`, header, alert banner, Steps table, gate record, cost kv, links, the `DIAGRAM · DETAIL` toggle (DIAGRAM disabled until Epic 8), stop bodies for `plan_stale`, `push_rejected`, `timeout`, `misconfigured`, `internal`, `verify_failed`, the done-checkpoint body, the *Cancel run* confirm modal, `RUN` / `ERR` / `DON` / `CAN` states, Playwright and Vitest.
**Out:** Question/Answer, Stories strip content beyond the cells, resume command, artifacts tree, budget and protected-path bodies (Epics 5, 6); active time (Epic 8).

## Binding rules (inlined)

- **Header (UX-DR9).** Crumb `workflows / {branch}`; chip + token + branch + age of the current state; meta line unabridged: `project · repository · base · initiative or spec folder · template v · harness · started · worktree path` (never truncated, wraps if needed).
- **Alert banner.** Only when `needs_you` or `failed`: token, the reason text verbatim (`alert.reason`), right-aligned progress and `spent / budget`; 2px left rule amber (`BLK`/`CHK`) or red (`ERR`).
- **Left column, in order.** Stop body (below) → *Or continue in the session* placeholder (absent until Epic 6) → **STEPS** dense table `path · kind · gate · status · time · harness · cost`: every planned row from `steps[]`, `planned` rows as `QUE`, the current row promoted to primary text, `· {n} attempts` when > 1; gate column prints the word (`liveness / deterministic / human / unvalidated`); status column prints the token and, for skipped rows, `skipped · {reason}`; nothing in these two columns is ever green — the only coloured cell is the token, and `SKP`/`unvalidated` are grey words.
- **Right column.** **STORIES** strip (`n/m` per epic, one cell per story by id: done filled, current amber, future hollow, skipped struck) → artifacts placeholder (absent until Epic 6) → **COST & TRACE** kv (`spent / budget` as a ratio, tokens in/out, wall-clock, `your active time —`, trace link absent, the compare links, the branch link) → **GATE RECORD** (timeline rows `time · path · event · actor · text`, current row `■` in the signal colour).
- **Stop bodies present in this epic (UX-DR10).** `plan_stale` → the list-file diff (`GET /runs/{id}/plan-diff` `[ASSUMPTION: a small endpoint returning the unified diff of the stale file, added in this story]`) + *Continue on the recorded plan* + *Cancel run* + link `start a new run` (to `/workflows/new` pre-filled); `push_rejected` → git output (log tail) + line `resolve on the remote, then Retry — Retry fetches first` + *Retry* + *Skip epic* (disabled until Epic 6, shown only if admitted) + *Cancel run*; `timeout`, `misconfigured`, `internal`, `verify_failed` → log tail (last 40 lines) in a command block + *Retry* + skips (if admitted) + *Cancel run*; `checkpoint` on a `checkpoint` row → the story's summary line + *Continue* + *Cancel run*. Buttons render only the kinds in `admitted_signals`; each posts to `/runs/{id}/signals` and re-fetches; a 409 prints the problem detail beside the buttons.
- **Cancel run.** Destructive outline button; the only modal in the product: `cancel run {branch}? running processes are killed, worktrees removed, branches created by this run and never pushed are deleted` with *Cancel run* (destructive) and *Keep running*; posts `{kind: cancel, payload: {confirm: true}}`.
- **Other states.** `RUN`: no banner, current row marked. `ERR` (Run `failed`): red banner, the failing command's log tail, no action but the `start a new run` link. `DON`: banner replaced by the summary line `{progress} · {links} · skipped: {ids}` with the compare links. `CAN`: grey banner `cancelled by operator at {time}`.
- **Polling:** the same `$poll` store; state swap; failed fetch → the full-surface readout.
- **Naming (UX-DR16):** the Steps table and gate record print `path`; the banner, strip, and header print labels.
- **Test-ids:** `wf-header`, `wf-token`, `wf-meta`, `wf-alert`, `wf-stop-<kind>`, `wf-steps`, `wf-step-<seq>`, `wf-stories`, `wf-cost`, `wf-gate-record`, `wf-signal-<kind>`, `wf-cancel`, `wf-cancel-confirm`, `wf-toggle-diagram`, `wf-summary`.

## Acceptance criteria

**Given** a stubbed detail with 12 planned rows, row 5 running
**When** rendered
**Then** all 12 rows are listed by path with tokens, row 5 is promoted, gate words are plain, and no cell other than tokens carries colour.

**Given** a Run parked `plan_stale`
**When** rendered
**Then** the banner reads `plan stale: stories.yaml`, the body shows the diff, and the buttons are exactly *Continue on the recorded plan* and *Cancel run*; clicking Continue posts the signal and the banner disappears after the next poll.

**Given** a Run parked `push_rejected` with `admitted_signals [retry, cancel]`
**When** rendered
**Then** the body shows the log tail and the resolve line; *Retry* posts `{kind: retry}`.

**Given** *Cancel run* clicked
**When** the modal is confirmed
**Then** the signal is posted with `confirm: true`; when dismissed nothing is posted.

**Given** a `failed` Run
**When** rendered
**Then** the banner is red, the log tail is shown, and the only control is `start a new run`.

**Given** a `done` Run with one skipped story and two links
**When** rendered
**Then** the summary line replaces the banner and lists the links and the skipped id; no amber or red pixel is present.

**Given** a skipped row with reason `no quality_gate_command`
**When** rendered
**Then** its status cell reads `SKP · skipped — no quality_gate_command` in grey.

## Implementation notes

- `src/islands/RunDetail.tsx` composed of `Header`, `AlertBanner`, `StopBody`, `StepsTable`, `StoriesStrip`, `CostBlock`, `GateRecord` in `src/components/run/` (React, each ≤ 300 lines); `StopBody` switches on `park_kind` and is extended by Epics 5–6.
- Backend: `GET /runs/{id}/plan-diff` in `api/routers/runs.py` (diff of the stale list file between `plan_ref` content and head content, computed with `difflib`).
- Playwright `tests/e2e/run-detail.spec.ts` with stubbed responses per state.

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

`EXPERIENCE-v1.md` §2.2 Run detail (sections, stop bodies table, other states), §Naming rule, §Voice. PRD FR-23, FR-20, §4.6. `DESIGN.md` (detail header, alert banner, kv table, activity timeline, command block, buttons).
