---
title: 'Operator senior session turns'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: '6edfcfaa46390b3c6fce9196ffeee259b0e71659'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2-3 opens and closes a session, but nothing runs inside it. The Operator cannot message the senior, and nothing runs the senior, commits its work or bills it.

**Approach:** AD-23, second half, on 2-3's lock. `POST /runs/{id}/session/messages {text}` writes one queued `session` attempt on the parked row and calls `Engine.enqueue_session_turn`. A durable workflow on its own queue, outside the walker, runs the turn. It commits each tree, bills the Run, and stores the reply the senior wrote to a file. `GET /runs/{id}/session` gains the turns.

## Boundaries & Constraints

**Always:**
- `post_message` runs under `runs.get_for_update`. It refuses with 409 `no senior session open`, 422 on empty text, 409 `turn running` while a session attempt is open, and 409 `no remaining budget`. It adds the attempt (`role = session`, `status = queued`, `n` one above the row's highest, `started_at = now`, `message`, and the harness and model of the `session_start` payload), commits, and then enqueues. If the enqueue raises, the attempt closes `error` with the text, and the answer is 500. Otherwise 202 with the turn.
- `enqueue_session_turn(run_id, attempt_id)`: workflow id = attempt id = its one argument (the facade's `enqueue`, unchanged), partition key = run id, queue `sessions`. The queue is declared at launch after `runs`, with concurrency `MAX_ACTIVE_RUNS`; there is no new setting. At container start, after the dependency sweep, every `queued` session attempt is enqueued again, or closed `error` `session closed` when its Run no longer has `senior_session`.
- Workflow `run_session_turn(attempt_id)` has two engine steps, `session_turn` then `session_commit`, with retries off. The walker's five steps are unchanged, and `DBOS_APPLICATION_VERSION` stays `1`.
- `session_turn`:
  - Session no longer open: the attempt closes `error` `session closed`, with no dispatch.
  - Attempt `running` (recovered): kill the recorded `pgid` and wait out `index.lock` as `agent._kill_previous` does. Record `status = error` and `output_ref = attempt interrupted`. It is never dispatched again (hard rule 7).
  - Attempt `queued`: the session's first turn sweeps both trees as `wip: before session (orchestrator)`. A git error makes the attempt `error` with git's output, and nothing is dispatched. Write `.orchestrator/.gitignore` (1-4's) and an empty `.orchestrator/session/reply.md` in the dispatch tree. `mark_started` records `status = running` and the start SHAs as an agent attempt records them. Inside the attempt span, call `start_resume` with the text alone when the session's newest attempt with a `session_id` exists, or `start` with the opening line otherwise. Commit `pgid` and `session_id`, then `wait`. Record `exit_code`, `session_id`, `log_path`, usage, and status `done` on exit 0 or `error` otherwise. `ended_at` stays empty, so the turn is busy until it is committed.
  - The context comes from `walk_context.context` on the park row, with the turn as its attempt. cwd is `agent_workdir.tree`, `add_dirs` comes from `agent_env.add_dirs`, and the env from `agent_env.environment` (contract, aliases and Project env, never `GITHUB_TOKEN`). The remaining budget is passed. `stall_min` is the row's or 30, with no wall clock.
- `session_commit` runs on every path, interrupted and cancelled ones included:
  - Unless the Run is terminal, `agent_workdir.sweep_trees(…, "session: turn {k} (orchestrator)")`. `k` is the attempt's position among the session's attempts, from 1. A git error goes to `output_ref` and makes the status `error`.
  - The reply file is read through `Workspace`, capped at 64 KiB, into `attempt.reply`.
  - The end SHAs and `ended_at` are recorded through `mark_finished`.
  - `record_attempt_spend` runs with the Run read by `get_for_update` in that spend unit of work, so a concurrent `cancel` is never overwritten.
  - Re-running after a crash is safe, because a clean tree commits nothing.
- The read model adds `turn_running` and `turns[{attempt_id, turn, status, message, reply, started_at, ended_at, exit_code, cost_usd}]`. An empty `reply` renders `no reply file` with the attempt's log link.

**Never:** No Run or Step status write; the turn writes attempt rows only (AD-8). No automatic re-dispatch. Nothing is routed on the reply. `steps/agent.py`'s resume path is unchanged (deferred). No UI. No container is stopped.

**Decided:**
1. **Opening context**: the operator-authored skill `ia-agents-skills/senior-session/SKILL.md`. The first turn's prompt is `senior-session {scope} {spec_folder} {story_id} {frame} {park_kind} {park_reason}`, values only, `-` for an empty value, then a newline and the Operator's text. Reason: every word stays operator-authored. A DSL key would contradict "any stop", and no context fails CAP-7.
2. **Reply text**: a fixed reply file, the same mechanism as 1-4's decision file, with the log as the fallback. Reason: there is no per-harness parsing (AD-10), and a fixed path works because a resumed turn receives only the Operator's text.
3. **Resumed pgid**: `Harness.start_resume(…) -> HarnessHandle` is added. Each adapter's `resume` becomes `wait(start_resume(…))` with argv unchanged, and the fakes record `start_resume`. Sessions use it now, and the agent path is deferred. Reason: the agent fix rewrites `steps/agent.py::_run` and the tests that pin its `resume` calls. Landing the port here makes that follow-up mechanical.
- `session_start` also refuses 422 `skill senior-session is not installed` when `skill_catalog.installed_skills()` is `None` or lacks it.
- Under rule 1(b), AD-23 declares the queue. `test_dbos_adapter.py::test_launching_configures_starts_and_then_declares_the_queue`: the call list becomes `["configure", "start", "register_queue", "register_queue"]`. The revision cites 2-5, 2026-11-02 and AD-23, and a new test asserts `(SESSION_QUEUE, CONCURRENCY)`. `tests/unit/fakes/engine.py`, `harness.py` and `runs.py` gain the new members; the Operator reviews them at the AD-17 park. `test_dbos_walker.py`'s five-step test stays unchanged, because the turn workflow is built by its own function.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected | Error |
|---|---|---|---|
| First message | Session open, no turn | 202; attempt `queued` with `message`; turn enqueued | N/A |
| First turn | No earlier `session_id` | WIP sweep; `start`, new session, opening line + text | N/A |
| Next turn | An earlier turn has a `session_id` | `start_resume`, text alone, the session's harness and model | N/A |
| Refused | No session; empty text; open turn; no budget | Nothing written | 409 / 422 |
| Enqueue fails | Engine raises | Attempt `error` | 500 |
| Turn ends | Any exit | `session: turn {k}` in each dirty tree; reply stored; closed; billed | Git error in `output_ref` |
| Crash mid-turn | Recovered, attempt `running` | Group killed; `attempt interrupted`; commit and billing run; no dispatch | N/A |
| Crash before enqueue | `queued`, no workflow | Startup enqueues it | N/A |
| Cancel mid-turn | `cancel` during turn 2 | `_cancel` kills its recorded group; commit skipped; closed and billed; Run stays `cancelled` | N/A |
| Cancel before start | Attempt `queued` | `session closed`; no dispatch | N/A |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `domain/entities/attempt.py` -- `message: str = ""`, `reply: str = ""`. `alembic/versions/{next}_attempt_session_text.py`, plus the DB model and repository -- both `TEXT NOT NULL server_default ''`, kept out of `NULLABLE`.
- `domain/ports/harness.py`, `infrastructure/harness/{claude,codex,opencode,fake}/adapter.py`, `tests/unit/fakes/harness.py` -- `start_resume`.
- `domain/ports/engine.py`, `tests/unit/fakes/engine.py`, `infrastructure/engine/local.py` (a no-op, so its anchor test's `isinstance` holds) -- `enqueue_session_turn`.
- `infrastructure/dbos/config.py` (`SESSION_QUEUE = "sessions"`), `adapter.py` (builds the turn workflow before `start`, declares the queue after `runs`), `session_walker.py` (new), `startup.py` -- the sweep.
- `application/rules/session.py` (2-3's) -- `resumable`, `turn_number`, `opening_line`.
- `application/use_cases/session_turn.py` (new) -- `post_message`, `run_turn` and `commit_turn`. At the 400-line cap, dispatch moves to `session_dispatch.py`. `session_sweep.py` (new) -- the startup sweep. `session_checks.py` -- the skill refusal.
- `session_view.py`, `api/schemas/session.py`, `api/routers/session.py` -- the turns and `POST …/session/messages`.
- `ia-agents-skills/senior-session/SKILL.md`, a `README.md` line, `tests/unit/test_senior_session_skill.py` -- the skill states the senior role, the fact positions, what each scope reads, the rule to edit only the cwd tree and the hub root, that anchors change only at the Operator's explicit request and are confirmed at close, and that `.orchestrator/session/reply.md` is written every turn. The test asserts each of these.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- `make openapi` only.

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/application/test_session_turn_*.py`, `tests/unit/test_dbos_session_walker.py`, `tests/unit/test_session_messages_router.py`, `tests/unit/test_harness_start_resume.py` -- new. Cover every matrix row through the shared fakes and fixture templates, and see each fail first (TDD).
- [x] The test edits named under Decided.
- [x] Code Map in order: domain and migration, then the harness port, the engine port and DBOS, the turn use case and sweep, the read model and router, the skill, then `make openapi`.

**Acceptance Criteria:**
- Given two turns on a fixture template, when the second runs, then it resumes the first turn's `session_id`. Given the same Run, when `answer {mode: session}` follows `session_end`, then it resumes the original agent attempt's session.
- Given a hub Run whose parked row declares `workdir`, when a turn edits both trees, then each tree gets its own `session: turn 1 (orchestrator)` commit.
- Given a turn whose spend write meets a `cancel`, when both commit, then the Run is `cancelled` and `spend_usd` includes the turn.

## Implementation Notes

I wrote the tests first, at baseline `6edfcfa`. The new test files failed on import before any source existed.

**Where the code went.**
- `use_cases/session_turn.py` holds `post_message`, `read_turn`, `run_turn` and `commit_turn`.
- `use_cases/session_dispatch.py` holds the dispatch, the interrupt and the attempt writes.
- `use_cases/session_sweep.py` is the startup sweep.
- `infrastructure/dbos/session_walker.py` builds `run_session_turn`.
- Migration `0027_attempt_session_text` adds `message` and `reply`. `reply` is part of the finish half.
- The startup sweep runs inside `startup.dependency_startup_sweep`, after the dependency sweep, so `main.py` stays at 400 lines.
- `record_attempt_spend` gains `locked=True`, which re-reads the Run through `get_for_update` inside its own unit of work.
- HEAD has no `agent_workdir.sweep_trees`. The turn uses `agent_workdir.sweep`, which commits both trees.

**Choices the spec left open.**
- The first-turn sweep (`wip: before session`) runs on the first turn of the session that has no earlier `start_sha`. This is not always the first attempt: if turn 1 never dispatched (unknown harness, git error), turn 2 still sweeps. Otherwise the agent's leftover dirt would count as session anchor edits.
- Crash recovery (from the 2-3 review): the workflow calls `session_commit` in a `finally`. `commit_turn` writes `ended_at` on every path:
  - a turn still `queued` or `running` closes `error` `attempt interrupted`;
  - an unexpected exception closes the turn `error` with the exception's text.

  A turn left `running` is recovered by DBOS at launch. It is killed, closed, billed and committed, and `session_end` then passes. `test_session_turn_flow.py` and `test_dbos_session_walker.py` test this.
- An exception during dispatch makes the turn `error` with `{Class}: {message}`. It is never re-dispatched.
- Empty opening-line values become `-`, and whitespace is collapsed so the line stays one line.
- The skill refusal is skipped when no catalog port is wired, as in pre-flight and `agent_skill`.
- The route declares its 500 in the contract.

**Revised tests (rule 1(b), story 2-5, 2026-11-02, AD-23).**
- `test_dbos_adapter.py::test_launching_configures_starts_and_then_declares_the_queue`: two `register_queue` calls. `test_dbos_session_walker.py` asserts `(SESSION_QUEUE, CONCURRENCY)`.
- `test_session_router.py::test_a_stop_reads_an_available_session`: the expected body gains `"turn_running": False, "turns": []`. The coordinator approved this one, which was not in the spec's list. `test_session_messages_router.py` asserts a running turn and a non-empty `turns`.
- The fakes `engine.py` (`enqueue_session_turn`, `session_turn_error`), `harness.py` (`start_resume`) and `runs.py` (`list_queued_sessions`) gain new members.

**DBOS_APPLICATION_VERSION** stays `1`. The walker's five steps are unchanged, and the turn workflow is new, so no recorded step sequence changed.

**Gates.**
- `make lint` is green.
- `make test` (after review): 9170 backend passed (1 skipped) and 1729 web-client passed, with 100% branch coverage on `domain` and `application`.
- `make openapi` shows no drift.
- Not run: `make e2e`, `make e2e-ui`, `make durability` and the manual checks.
- `session_start` returns 422 on the dev stack until the image is rebuilt with `ia-agents-skills/senior-session`.

## Review Triage Log

| Finding | Layer | Verdict | Route | Evidence and action |
| --- | --- | --- | --- | --- |
| A `commit_turn` that raises before `mark_finished` leaves the turn open, its workflow ERROR, and the session refusing messages and the close for good | edge | verified | patch | `list_queued_sessions` became `list_open_sessions`. The startup sweep reads `held_session_turns()` (the `sessions` queue's ENQUEUED and PENDING workflows) before it lists the open turns. Each open turn past `queued` that the queue does not hold goes through `run_turn` (interrupting it if it was `running`) and then `commit_turn`. One failed recovery is logged and the sweep moves on. Tests: `test_session_turn_sweep.py`. Not covered: a `queued` turn whose workflow ended ERROR is re-enqueued, which DBOS treats as a no-op. That needs both reads of the turn to fail. |
| The reply-file and `.gitignore` writes follow a link | security | verified | patch | A link at `.orchestrator/session` (or above it) refuses the turn with `reply file is under a link`. A link at either file is removed before the write. Tests use `FsWorkspace` on a real `tmp_path` tree. |
| Nothing tested that the turn workflow is registered before `start` | verification | verified | patch | `FakeDurableEngine` now records declarations in `calls` too (rule 1(b), the order this story declares). The launch-order test checks that every declaration comes before `start`, and a new test checks that `run_session_turn` precedes `start`. |
| A `cancel` landing between the session check and the group commit kills nothing | edge | suspected | patch | The group is committed under `runs.get_for_update`. If that read finds the session closed, the turn kills its group, waits, and closes `error` `session closed`. |
| A turn that never dispatched still gets the commit sweep | edge | suspected | patch | A new rule, `session.dispatched` (a `pgid` or a `start_sha`), gates the `session: turn {k}` commit. |
| A failure late in the close drops the end SHAs and the reply, and turns a `done` turn into `error` | edge | suspected | patch | The close now runs in parts: the commit, then the end SHAs, then the reply. A failing part writes `output_ref` and changes no status; a git refusal still makes the turn `error`, as the spec says. The reply alone is read through a new port method, `Workspace.read_lenient`, which replaces undecodable bytes. `read` stays strict for every other caller, so a file that is read and written back is never altered (`test_workspace_lenient_read.py`). The earlier test `test_an_unexpected_failure_still_closes_the_turn_naming_it`, which this story wrote, now asserts `done` along with the end SHA and the reply. |

## Verification

**Commands:**
- `make lint` and `make test` -- green; coverage unchanged; new modules paired.
- `make openapi` -- no drift.
- `make e2e` -- green (disposable stack only).

**Manual checks:**
- On the dev stack, run one two-turn session each on `claude`, `codex` and `local`. Each first turn invokes the skill and writes the reply file.
