---
title: 'Attempt roles'
type: 'refactor'
created: '2026-11-02'
status: 'done'
route: 'dispatch'
baseline_commit: 'e9a4654957960ad463c42989d67f2c1e3e8ae205'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Every attempt reader takes the row's or the Run's newest attempt. Once story 1-4 records a senior's consult as an attempt on the row, `answer`, the terminal command, the park diff and the AD-17 ranges would pick the senior's session instead of the original agent's.

**Approach:** AD-21. `attempt.role` is `agent | consult | session`, default `agent`. Every read that picks a session, numbers an archive, counts a retry or builds an AD-17 range reads `agent` attempts only. The step's attempts table labels the other roles. Nothing writes a non-`agent` attempt yet, so behaviour is unchanged.

## Boundaries & Constraints

**Always:** Spend, logs, traces, `step_detail`'s attempt list, `start_attempt`'s numbering and interrupted-attempt close, `_close_attempt`, `signal_effects._cancel` and `harness_readiness_evaluate` keep reading every role. Where every attempt is `agent`, each reader returns exactly what it returns today.

**Never:** No consult logic, no gate event or actor, no new Run, Step or park status token. `record_trajectory` is unchanged. No test pins shipped template content. The only existing test file edited is `tests/unit/fakes/runs.py`, under hard rule 1(b): AD-21, ratified 2026-11-01, declares the change. The edit names story 1-7 and that date.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Newer consult attempt | Row parked; attempt n `agent` (session s1), attempt n+1 `consult` (session s2) | `previous_attempt`, `reply_available` (both readers), the terminal command, the park diff, `terminal_poll`'s end SHA and the frame's AD-17 attempts all use attempt n or s1 | N/A |
| Consult attempt in the table | Same row | Step detail lists both attempts; n+1 carries `role: consult`, `resume_command: null`; n omits `role` | N/A |
| Only agent attempts | Any existing Run | Every reader's answer is unchanged | N/A |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `domain/statuses.py` -- `AttemptRole = Literal["agent", "consult", "session"]`.
- `domain/entities/attempt.py` -- `role: AttemptRole = "agent"`, plus `agent_attempts(attempts)`, the one list filter.
- `domain/ports/repositories.py`, `infrastructure/db/repositories/attempts.py`, `infrastructure/db/models/run.py` -- the column; `get_latest_agent(step_run_id)`; `latest_for_run` returns `agent` attempts only. Its callers are the two `reply_available` readers and `announce`.
- `use_cases/walk.py::_context` -- `previous_attempt` = the last of `agent_attempts(attempts[:-1])`.
- `use_cases/walk_frame.py::read_frame` -- the frame's attempts pass through `agent_attempts`.
- `jobs/terminal_poll.py::_record_end_sha`, `use_cases/run_files.py::_park_attempt` -- `get_latest_agent`.
- `use_cases/run_views.py::run_detail` -- `_alert` and `_terminal` get the park row's newest `agent` attempt.
- `use_cases/terminal.py::resume_command` -- `None` for a non-`agent` attempt.
- `api/schemas/step_detail.py`, `api/routers/step_detail.py` -- `role`, omitted when `agent`, following `reply_available`'s omit-when-default serializer.
- `web-client/src/components/run/AttemptsTable.tsx` -- the `#` cell reads `{n} · senior` for `consult` and `{n} · session` for `session`. The column set is unchanged.

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/application/test_attempt_roles.py` -- new; covers each matrix row for each reader in the Code Map through the shared fakes, and is seen failing first -- TDD.
- [x] `backend-api/tests/unit/fakes/runs.py` -- `FakeAttemptRepository` stores `role`, gains `get_latest_agent`, and filters `latest_for_run` -- the shared fake for the changed port.
- [x] `backend-api/src/orchestrator/domain/statuses.py`, `domain/entities/attempt.py` -- the role and the filter.
- [x] `backend-api/alembic/versions/0023_attempt_role.py` -- `role Text NOT NULL server_default 'agent'` -- existing rows read `agent`.
- [x] Repository port, adapter and model -- per Code Map.
- [x] Each reader in the Code Map -- switch to the agent-only read.
- [x] Step detail schema and router -- `role`; run `make openapi`.
- [x] `web-client/src/components/run/AttemptsTable.tsx` and `web-client/tests/unit/attempt-table-role.test.ts` (new) -- the label, asserted for all three roles.

**Acceptance Criteria:**
- Given an existing database, when migrations run, then every attempt reads `role = agent`.
- Given a parked row whose newest attempt is a `consult` with its own session, when the Operator opens the Run page and sends `answer` with no `mode`, then the mode defaults to `session`, and the walker resumes the `agent` attempt's session, not the consult's.
- Given the same row, when the attempts table renders, then the consult row reads `· senior` and offers no terminal command.

## Design Notes

AD-21 names one repository method. Three reads are needed: the latest `agent` attempt of one row, the run-scoped `reply_available` read, and AD-17's frame lists. A single helper, `agent_attempts`, defines "agent attempt" once. `get_latest_agent` covers row-scoped reads, and `latest_for_run` turns agent-only, keeping `reply_available`'s run scope. That scope is what `test_run_views_reply_available.py` pins.

## Verification

**Commands:**
- `make lint` -- expected: passes, including import-linter, the 400-line cap and test pairs.
- `make test` -- expected: passes, with domain and application at 100% branch coverage.
- `make openapi` -- expected: no drift after generation.
- `make e2e` -- expected: passes; the migrations test covers 0023.

## Implementation Notes

- **Decided.** `AttemptRole` and `ATTEMPT_ROLES` live in `domain/statuses.py`. `AGENT_ROLE` and `agent_attempts` live in `domain/entities/attempt.py`. `previous_attempt` is `next(reversed(agent_attempts(attempts[:-1])), None)`. A row whose only earlier attempt is a consult therefore has no previous attempt. `read_frame` filters once, so `frame_start_sha`, the frozen test set and the AD-17 ranges all read `agent` attempts. `run_detail` filters the park row's attempts once, and `_alert` and `_terminal` both read the result. `resume_command` answers `None` for a non-`agent` attempt. That covers the Run page's terminal and each row of the step attempts table.
- **Decided.** `AttemptDetailOut.role` is `drop_default`-guarded. A wrap `model_serializer` omits it when the value is `agent`, so the generated type is `role?: "agent" | "consult" | "session"`. The web-client's hand-written `AttemptDetail` gains the same optional field.
- **Surprised.** `walk.py` was at its 400-line cap. Collapsing the `plan_model` import onto one line made room for the new import, and the module ends at 398 lines.
- **Surprised.** The column's server default only applies on insert. `test_history_repository_adapter.py` builds an `AttemptRow` in memory with no `role`, which read as `None` and failed entity validation. Under rule 1(a), the code was fixed, not the test: `to_entity` reads a missing role as `agent`. `test_attempt_role_adapter.py` covers that case.
- **Surprised.** The fake's `latest_for_run` orders by `n` while the adapter orders by `started_at`. Both now filter on role, and their ordering is unchanged.
- **Tests.** New test files: `tests/unit/application/test_attempt_roles.py` (seen failing first), `tests/unit/test_attempt_role_adapter.py`, `tests/unit/test_step_detail_role.py` and `web-client/tests/unit/attempt-table-role.test.ts`. The only existing test file edited is `tests/unit/fakes/runs.py`, under rule 1(b), and the edit names story 1-7 and 2026-11-01. `make e2e` was not run in this session.

## Review Triage

| # | Finding | Verdict | Resolution |
|---|---------|---------|------------|
| 1 | `run_views.py::_step_row` took `latest` and the attempt count over every role. The Answer hint (`answer.ts::answerTarget`, reading `latest.n`) then named the consult's archive number, and the diagram counted the consult as a retry | fix | `latest` and `attempts` read `agent_attempts(attempts)`; `cost_usd` stays summed over every role. Covered by `tests/unit/application/test_attempt_roles_step_rows.py`, seen failing first |
| 2 | `run_views_alert.py::_checkpoint_story` counted every role in "N attempts" | fix | Counts the build row's `agent` attempts; the frame cost still sums every role. Same test file |
| 3 | `test_attempt_role_adapter.py` asserted `"attempt.role" in rendered`, which the SELECT column list already satisfies, so removing the filter left it green | fix | Now asserts `attempt.role = :role_1` in the WHERE clause. Both tests failed with the filter removed and pass with it restored |
