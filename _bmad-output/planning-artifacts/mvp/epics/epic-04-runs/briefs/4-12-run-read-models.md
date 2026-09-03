---
story: "4-12"
epic: 4
title: Run read models for the board, the detail, and the run graph
requirements: [FR-22, FR-23, FR-28 (cost sums), FR-29 (graph backend), NFR-2, AR-20, AR-24]
binds: [AD-3, AD-15]
---

# Story 4.12 — Run read models for the board, the detail, and the run graph

As the Operator,
I want each screen to read one endpoint shaped for it,
So that the browser aggregates nothing and the Board, the detail, and the diagram can never disagree.

## Scope

**In:** `GET /api/v1/runs?view=board&project_id=`, `GET /api/v1/runs/{id}` (full), `GET /api/v1/runs/{id}/graph` with `build_run_graph`, the read-model builders in `application/use_cases/run_views.py`, tests.
**Out:** the screens (4.13–4.16), history (`GET /steps`, Epic 7), activity (Epic 8).

## Binding rules (inlined)

- **Board view.** `{columns: {queued: [Card], running: [Card], needs_you: [Card], done: [Card], failed: [Card]}, counts: {running, queued, needs_you}, generated_at}`; `cancelled` Runs are in `failed` with `token: CAN`. `Card{id, token (QUE RUN BLK CHK DON ERR CAN), status, park_kind, branch, project_name, repository_slug, current_step_label, harness, template, version, progress: {epics_done, epics_total, stories_done, stories_total, links} | null, kind_label ("repo-init" | "readiness" | null), age_seconds, needs_you_since}`. `token` for `needs_you` is `CHK` when `park_kind == checkpoint` else `BLK`. `current_step_label` = the label of the running row, else the park row, else the last done row. Progress: `epics_total` = number of `epics[i]` frames (null for `epic` Runs), `epics_done` = frames whose `push` row is `done | skipped`; `stories_total`/`stories_done` likewise over story frames (`done` when the frame's `commit_guard` row is `done | skipped`); `links = len(compare_urls)`. Filter by `project_id`.
- **Detail view.** `{run: RunSummary + inputs + plan_ref + manual_estimate_h + worktree_path + worktrees + compare_urls + terminal_session + accepted_paths, header: {meta: {project, repository, base_branch, folder (initiative or spec), template, version, harness, started_at, worktree_path}}, alert: {token, reason, park_kind} | null, steps: [StepRow], stories: [StoryCell], cost: {spent_usd, budget_usd, tokens_in, tokens_out, wall_clock_seconds, active_seconds, provisional: bool, trace_url: null}, gate_record: [GateRecord], admitted_signals: [kind], summary: {progress, links, skipped: [story ids]} (when done)}`. `StepRow{seq, path, label, kind, gate, status, token, reason, attempts: int, latest: {n, started_at, ended_at, seconds, harness, model, exit_code, cost_usd, log_tail: [str] (last 40 lines)}}`. `StoryCell{epic_index, story_id, state: done | current | future | skipped}`. Cost per row = sum of its attempts' `cost_usd`; Run spend = `run.spend_usd`.
- **Run graph (AD-15).** `build_run_graph(rows, run) -> Graph` in `application/graph.py`: node id = `step_run.path`, `label` = row label, `status`, `token`; groups = path prefixes `epics[i]` and `epics[i].stories[j]` (or `stories[j]`) with the group status rule: `error | blocked | checkpoint` if any member is, else `running` if any, else `skipped` when all are `skipped`, else `done` when all are `done | skipped`, else `queued`; a `cancelled` Run derives no group statuses (`null`) and the root token is `CAN`; the root node is the Run (`initiative` → the initiative, else the epic); edges follow `seq`; `current` marks the running or park row. Returns the same `Graph` schema as 3.4 plus `statuses`.
- **Tokens (conventions).** Step: `planned` → `QUE`, `queued` → `QUE`, `running` → `RUN`, `done` → `DON`, `blocked` → `BLK`, `checkpoint` → `CHK`, `error` → `ERR`, `skipped` → `SKP`. The API sends tokens; the UI never derives them (the group status is the only derived one, and it is derived here).
- **One read per screen (conventions "Read models"):** no endpoint here requires a second call.

## Acceptance criteria

**Given** Runs in every status including one `cancelled`
**When** `GET /runs?view=board` is read
**Then** each appears once in its column, the cancelled one under `failed` with `CAN`, `counts` are right, and a `needs_you` Run parked on a `checkpoint` has `CHK`.

**Given** an `initiative` Run with two epics and eight stories, three stories done, one epic pushed
**When** the board card is read
**Then** `progress` is `{1, 2, 3, 8, 1}` and `current_step_label` names the running row.

**Given** a Run with a row that has three attempts
**When** `GET /runs/{id}` is read
**Then** its `StepRow.attempts` is 3 and `latest.n` is 3 with the last 40 log lines; `admitted_signals` matches the park.

**Given** a `done` Run with one skipped story
**When** read
**Then** `summary.skipped` lists its id and `summary.links` the compare URLs.

**Given** an `epic` Run with rows in mixed states
**When** `GET /runs/{id}/graph` is read
**Then** groups carry statuses by the one rule (tested for each branch of the rule) and `current` is the park row; **and** a cancelled Run has `null` group statuses and root token `CAN`.

**Given** the contract
**When** `make openapi` runs
**Then** the three read models are generated into `schema.d.ts`.

## Implementation notes

- `run_views.py` pure builders over entities; router calls repositories then builders.
- `log_tail` read through the `Workspace`-independent log reader in `infrastructure/process/logs.py` (`tail(path, 40)`).
- Reuse `Graph` schema; add optional `status`, `token`, `current` fields to `Node` and `status` to `Group`.

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

PRD FR-22, FR-23, FR-28, FR-29. Spine AD-15 (group rule), conventions (Read models, Status tokens). `EXPERIENCE-v1.md` §2 (card fields), §2.2 (detail sections), §2.3 (group token).
