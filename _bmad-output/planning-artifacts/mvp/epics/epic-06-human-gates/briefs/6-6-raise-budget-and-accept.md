---
story: "6-6"
epic: 6
title: Raise budget and Accept a protected-path change
requirements: [FR-17 (raise), FR-31 (accept), NFR-8, UX-DR10, UX-DR18]
binds: [AD-9, AD-11, AD-13, AD-17]
---

# Story 6.6 — Raise budget and Accept a protected-path change

As the Operator,
I want to raise a Run's budget and have it continue exactly where it stopped, and to accept an agent's change to a protected file when I judge it right,
So that the two stops that need my judgement rather than my text are one field or one click.

## Scope

**In:** the `budget_raise` signal end to end (writer from 4.5 verified, resume semantics, body with the new-budget field), `continue` on `protected_path` (accepted files recorded, executor re-applies the tail without dispatch — 5.6's branch — body with the file list, diff links, and the accept line), a `diff` mode on `GET /runs/{id}/files`, tests.
**Out:** nothing else.

## Binding rules (inlined)

- **Raise budget (AD-11, AD-13).** `POST …/signals {kind: budget_raise, payload: {budget_usd}}`; valid when `park_kind == budget` and `budget_usd > spend_usd` (else 409 `new budget must exceed spend ${spend}`); writes `run.budget_usd` and the record (`text: "budget raised to ${new}"`); if the park row is `blocked | checkpoint`: `park_kind` rewritten to that status, Run stays `needs_you`, no engine signal — the Question or checkpoint body is shown again on the next poll; if the row is `done`: Run → `running`, the walker resumes at the next row (verify); if the row is `error` (retry path): row `→ queued`, Run → `running` `[ASSUMPTION: a retry-path error under budget resumes as a retry when the budget is raised]`.
- **Budget body (UX-DR10).** Banner `BLK · budget $41.20 / $40.00`; body: the cost kv promoted, then a numeric field *new budget* (`wf-budget-raise-input`, pre-filled with `spend + 10` rounded `[ASSUMPTION]`), primary *Raise budget* (`wf-budget-raise`), and *Cancel run*; no skips (not admitted).
- **Accept (AD-17, AD-13).** `POST …/signals {kind: continue, payload: {files: [paths]}}` when `park_kind == protected_path`; `files` must equal the hit list (else 409); `run.accepted_paths += files`; record `continue` with `payload.files`; row `error → running`; the executor (agent or `git.commit`) resumes: agent → re-applies the tail over the previous attempt's SHAs with accepted paths excluded, no dispatch, no new spend; `git.commit` → re-runs whole. The accepted list is copied into the trajectory.
- **Protected-path body.** Banner `BLK · protected path modified: {files}`; body: the file list with `+ − ~` per file (from `alert.payload.hits`), each linking to the artifacts tree with `?diff=1` (this story adds `GET /runs/{id}/files?path=&diff=1` → unified diff between the attempt's `start_sha` and the working tree for that path); the line `Accept records these files as accepted for story {id}; the check resumes on the same tree and the files ship with the story`; primary *Accept changes* (`wf-accept`); also *Retry* (the Operator reverted on the branch), *Skip story*, *Skip epic*, *Cancel run*.
- **Voice:** `accepted: tests/api/test_runs.py` appears in the gate record text.

## Acceptance criteria

**Given** a Run parked `budget` on a `blocked` row
**When** `budget_raise {budget_usd: 60}` is signalled
**Then** `budget_usd` is 60, `park_kind` is `blocked`, the Run stays `needs_you`, no engine signal was sent, and the next detail read shows the Question body.

**Given** a Run parked `budget` on a `done` row
**When** raised
**Then** the Run is `running` and the walker continues at the verify row (e2e on the fake harness with a scenario `usage.cost_usd` above the budget).

**Given** `budget_usd: 30` with `spend_usd: 41.20`
**When** raised
**Then** 409 with the reason.

**Given** a Run parked `protected_path` with hits `[tests/a.py ~, AGENTS.md +]`
**When** `continue {files: [tests/a.py, AGENTS.md]}` is signalled and the executor resumes on the fakes
**Then** `accepted_paths` holds both, no harness call is made, the tail routes on the existing story file, and the record has `continue` with the files; **and** with a `files` list that does not match the hits → 409.

**Given** the protected-path detail
**When** rendered
**Then** each file shows its `+ − ~` and a diff link that opens the unified diff, and *Accept changes* posts the files.

## Implementation notes

- Read model: `alert.payload` (hits) exposed; `GET /runs/{id}/files?diff=1` via `Git.diff(cwd, start_sha, path)` (add to the port).
- `StopBody` cases `budget` and `protected_path`.

## Verification

```bash
make lint && make test && make openapi && make e2e-api && make e2e-ui
```

## Sources for detail only

PRD FR-17 (raise paragraph), FR-31 (accept sentence), §4.6. Spine AD-13 (`budget_raise`, `continue` on `protected_path`), AD-11, AD-17 (`accepted_paths`), AD-9 (no dispatch on accept). `EXPERIENCE-v1.md` §2.2 stop table.
