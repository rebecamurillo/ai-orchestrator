---
id: SPEC-mvp-epic-06-human-gates
companions: []
sources:
  - ../../prd.md
  - ../../addendum.md
  - ../../architecture/ARCHITECTURE-SPINE.md
  - ../../../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
---

> **Canonical contract for Epic 6.** Each story's full requirements live in `briefs/<id>-<slug>.md`, named from `stories.yaml` `invoke_dev_with`. Read the brief for the story you are dispatched on; do not read the other briefs. The repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when a brief and the code disagree.

# Epic 6 — Human gates: answer, continue, skip, retry, accept, terminal

## Why

A pain to solve: a Run that stops is worthless unless one screen shows what it needs and one action resumes it exactly once. Epic 5 made Runs park with the right reason; this epic gives the Operator every admitted action and its screen body: Answer with archive and re-dispatch, Continue and Reject at checkpoints, inline editing of the spec while parked, Skip story and Skip epic with the re-baseline, Raise budget, Accept a protected-path change, and the terminal resume path with its poll. It realises user journey UJ-3 and success metric SM-2, and adds a scripted test harness so the whole loop is provable end to end without a model.

## Capabilities

- **CAP-1** Answer a blocked story, with a scripted test harness — archive to `stories/.answers/`, `## Human Answer`, re-dispatch with the Answer as planning context; a `fake` harness for end-to-end tests. **success:** after *Resume with answer* the Run leaves `needs_you` within one poll and the archived file holds the answer; the e2e scenario runs on the fake harness.
- **CAP-2** Continue and Reject at checkpoints — spec checkpoint re-dispatch without the halt suffix; Reject as Answer; done-checkpoint body. **success:** the planned story file is shown inline; Continue implements without re-planning.
- **CAP-3** Inline spec editing while parked — `GET`/`PUT /runs/{id}/files`, the artifacts tree and editor, list files read-only. **success:** each save is one commit `spec: operator edit (orchestrator)` named in the gate record and never attributed to the agent.
- **CAP-4** Skip story with the re-baseline. **success:** remaining agent and checkpoint rows are skipped, verify runs as re-baseline, commit-guard commits `story {id}: skipped by operator`, a failing re-baseline parks `re-baseline failed after skip`.
- **CAP-5** Skip epic. **success:** remaining story frames are skipped, the commit-guard, push, and compare link still run, the next epic starts; on a rejected push, push and link are skipped.
- **CAP-6** Raise budget and Accept a protected-path change. **success:** Raise resumes at the row's routed status without re-dispatch; Accept records the files and resumes routing on the same tree.
- **CAP-7** Terminal resume — the command, the session flag, the poll. **success:** copying marks the session, disables the other actions until Release, and two clean `done` polls resume the Run at verify with actor `terminal`.
- **CAP-8** UJ-3 proven end to end — blocked → answer → done; spec checkpoint → continue; verify failed twice → skip; cancel while parked. **success:** the scenarios pass on the fake harness in the compose stack.

## Constraints

- Every signal is validated by `signal_run` against the AD-13 table, written to the gate record, and applied by the resumed executor; no endpoint touches the engine or a worktree directly (AD-13), except `PUT /runs/{id}/files` and cancel.
- No action is applied twice or half-way (AD-8): the executor reads `resume_signal` once per attempt.
- Copy names the mechanism whenever an action changes a file or a branch (NFR-8).
- The signal rule and the stop-body table of the experience spec are the screen contract (UX-DR10).
- Tests first; `signal_run` and the executors' resume branches stay at 100 % branch coverage (AD-18).

## Non-goals

- No codex or local harness (Epic 7); no run diagram, active time, or changed-since marks (Epic 8).
- No notification outside the Board; no editing of `stories.yaml` or `epics.yaml` in place (a new Run is the way).

## Success signal

Two days after a Run parked `BLK · story 4-1 · intent gap`, the Operator opens it, reads the question, types the answer, clicks *Resume with answer*, and within five seconds the card is back in Running; at story 4-2 the Run pauses at the spec checkpoint, she reads the planned story inline and clicks *Continue*; story 4-3's verify fails twice and she skips it; by evening the card reads `DON · 2/2 epics · 8/8 stories · 2 links` with 4-3 listed as skipped.
