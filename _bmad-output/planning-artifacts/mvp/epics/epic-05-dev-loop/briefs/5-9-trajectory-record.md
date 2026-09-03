---
story: "5-9"
epic: 5
title: Trajectory record
requirements: [FR-32 (record), SM-1, SM-3, AR-23]
binds: [AD-19]
---

# Story 5.9 — Trajectory record

As the Operator,
I want one append-only record per done story capturing what ran, how many attempts, what the gates said, what it cost, and the story file as committed,
So that unattended completion and cost per harness (SM-1, SM-3) are computed from facts, and a future fine-tuning set has its trajectories.

## Scope

**In:** table `trajectory` + migration, `application/use_cases/record_trajectory.py`, the trigger from `apply_step_result` when a story frame's `build` row is `done` and its `verify` row is `done | skipped`, tests.
**Out:** the export endpoint and the Project button (Epic 7).

## Binding rules (inlined)

- **Row (AD-19).** `id`, `run_id`, `project_id`, `repository_id`, `story_id`, `epic_index`, `frame`, `harness`, `model`, `attempts: [{n, started_at, ended_at, exit_code, session_id, cost_usd, tokens_in, tokens_out, route: str}]`, `gate_results: {build: liveness, verify: done | skipped, commit_guard: done | no changes, protected_paths: {hits, accepted}}`, `cost_usd`, `tokens_in`, `tokens_out`, `wall_clock_seconds`, `story_file: text` (the committed content at the frame's end SHA), `start_sha` (the frame's first attempt `start_sha`), `end_sha` (HEAD after the commit-guard), `human_actions: [{event, at}]` (gate records of the frame: answers, continues, skips, accepts), `recorded_at`. Unique `(run_id, frame)`.
- **Trigger.** In `apply_step_result`, after the frame's `verify` row ends `done | skipped` and the `build` row is `done` (also after a `skip_story` whose build was `done`) → `record_trajectory(run, frame)` in the same unit of work; if the row already exists, do nothing (idempotent on replay). No update or delete path exists; the repository port has `add` and `list_for_project` only.
- **Story file snapshot** read through `Git.read_file(end_sha, path)`; `wall_clock_seconds` = Σ attempt durations.
- **SM inputs.** `human_actions` empty and every attempt `route == done` means "unattended" for SM-1; `cost_usd` and `wall_clock_seconds` per harness feed SM-3.

## Acceptance criteria

**Given** a frame whose build ended `done` after two attempts and whose verify ended `done`
**When** the verify result is applied
**Then** one trajectory row exists with two attempts, `gate_results.verify == done`, the story file text, `start_sha` of attempt 1 and `end_sha` of the commit-guard, cost and tokens summed, and `human_actions` empty.

**Given** a frame with a `blocked` stop answered by the operator
**When** recorded
**Then** `human_actions` lists the `blocked` park and the `answer` signal with times.

**Given** the same result applied twice (replay)
**When** the trigger runs again
**Then** the row is unchanged and no second row exists.

**Given** a frame whose verify is `skipped · no quality_gate_command`
**When** recorded
**Then** `gate_results.verify == skipped`.

**Given** the repository port
**When** inspected
**Then** it exposes no update or delete method.

## Implementation notes

- Migration `0009_trajectory.py`; JSONB for the structured fields.
- `record_trajectory(run_id, frame, *, runs, steps, attempts, gate_records, git, trajectories, clock)`.

## Verification

```bash
make lint && make test
```

## Sources for detail only

PRD FR-32, SM-1, SM-3. Spine AD-19. `GUIDELINES.md` §10.1 (what a trajectory should capture).
